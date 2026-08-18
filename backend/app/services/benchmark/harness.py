"""Provider-agnostic OCR/HTR benchmark harness.

Any object satisfying the ``OCREngine``/``HTREngine`` shape (``name``, ``health``, ``extract``)
can be scored, so printed and handwriting providers are compared on identical inputs with
identical metrics. Engine failures are recorded as failures rather than aborting the run — a
provider that crashes on a page is a benchmark result, not a benchmark error.
"""

import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.errors import AppError
from app.services.benchmark.metrics import (
    character_error_rate,
    expected_calibration_error,
    normalize_text,
    word_error_rate,
)


class BenchmarkEngine(Protocol):
    @property
    def name(self) -> str: ...
    def health(self) -> dict[str, str | bool]: ...
    def extract(self, png_bytes: bytes) -> Any: ...


@dataclass(frozen=True)
class BenchmarkCase:
    """One labelled page. ``kind`` separates printed from handwritten scoring."""

    name: str
    png_bytes: bytes
    expected_text: str
    kind: str = "printed"


@dataclass(frozen=True)
class CaseResult:
    case: str
    kind: str
    engine: str
    succeeded: bool
    character_error_rate: float | None
    word_error_rate: float | None
    reported_confidence: float | None
    processing_ms: int
    error_code: str | None = None


@dataclass(frozen=True)
class EngineScore:
    engine: str
    configured: bool
    cases_attempted: int
    cases_succeeded: int
    mean_character_error_rate: float | None
    mean_word_error_rate: float | None
    median_processing_ms: float | None
    calibration_error: float | None
    failures: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.cases_succeeded / self.cases_attempted if self.cases_attempted else 0.0


@dataclass(frozen=True)
class BenchmarkReport:
    scores: list[EngineScore]
    results: list[CaseResult]

    @property
    def ranking(self) -> list[str]:
        """Best first: lowest mean CER, with a completely failed engine ranked last."""
        return [
            score.engine
            for score in sorted(
                self.scores,
                key=lambda item: (
                    item.mean_character_error_rate is None,
                    item.mean_character_error_rate or 0.0,
                    -item.success_rate,
                ),
            )
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranking": self.ranking,
            "scores": [
                {
                    "engine": score.engine,
                    "configured": score.configured,
                    "cases_attempted": score.cases_attempted,
                    "cases_succeeded": score.cases_succeeded,
                    "success_rate": round(score.success_rate, 4),
                    "mean_character_error_rate": _round(score.mean_character_error_rate),
                    "mean_word_error_rate": _round(score.mean_word_error_rate),
                    "median_processing_ms": _round(score.median_processing_ms, 1),
                    "calibration_error": _round(score.calibration_error),
                    "failures": score.failures,
                }
                for score in self.scores
            ],
        }


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


class BenchmarkHarness:
    def __init__(self, cases: list[BenchmarkCase]) -> None:
        if not cases:
            raise AppError(
                "BENCHMARK_NO_CASES",
                "A benchmark needs at least one labelled case.",
                400,
            )
        self.cases = cases

    def run(self, engines: list[BenchmarkEngine], kind: str | None = None) -> BenchmarkReport:
        cases = [case for case in self.cases if kind is None or case.kind == kind]
        if not cases:
            raise AppError(
                "BENCHMARK_NO_CASES",
                f"No labelled cases of kind {kind!r} are available.",
                400,
            )
        results: list[CaseResult] = []
        scores: list[EngineScore] = []
        for engine in engines:
            engine_results, calibration = self._run_engine(engine, cases)
            results.extend(engine_results)
            scores.append(self._score(engine, engine_results, calibration))
        return BenchmarkReport(scores=scores, results=results)

    def _run_engine(
        self, engine: BenchmarkEngine, cases: list[BenchmarkCase]
    ) -> tuple[list[CaseResult], list[tuple[float, bool]]]:
        results: list[CaseResult] = []
        calibration: list[tuple[float, bool]] = []
        for case in cases:
            started = time.perf_counter()
            try:
                output = engine.extract(case.png_bytes)
            except AppError as error:
                results.append(
                    CaseResult(
                        case=case.name,
                        kind=case.kind,
                        engine=engine.name,
                        succeeded=False,
                        character_error_rate=None,
                        word_error_rate=None,
                        reported_confidence=None,
                        processing_ms=int((time.perf_counter() - started) * 1000),
                        error_code=error.code,
                    )
                )
                continue
            except Exception as error:  # noqa: BLE001 - a crashing provider is a result
                results.append(
                    CaseResult(
                        case=case.name,
                        kind=case.kind,
                        engine=engine.name,
                        succeeded=False,
                        character_error_rate=None,
                        word_error_rate=None,
                        reported_confidence=None,
                        processing_ms=int((time.perf_counter() - started) * 1000),
                        error_code=type(error).__name__,
                    )
                )
                continue
            calibration.extend(self._token_calibration(case.expected_text, output))
            results.append(
                CaseResult(
                    case=case.name,
                    kind=case.kind,
                    engine=engine.name,
                    succeeded=True,
                    character_error_rate=character_error_rate(case.expected_text, output.raw_text),
                    word_error_rate=word_error_rate(case.expected_text, output.raw_text),
                    reported_confidence=output.confidence,
                    processing_ms=int(output.processing_ms),
                )
            )
        return results, calibration

    @staticmethod
    def _token_calibration(expected_text: str, output: Any) -> list[tuple[float, bool]]:
        """Pair each token's stated confidence with whether that token really appears.

        Matching consumes the reference multiset, so a provider repeating a correct word ten
        times is credited once per genuine occurrence rather than ten times.
        """
        remaining = Counter(normalize_text(expected_text).split())
        pairs: list[tuple[float, bool]] = []
        for token in getattr(output, "tokens", []) or []:
            if token.confidence is None:
                continue
            normalized = normalize_text(token.text)
            correct = bool(normalized) and remaining.get(normalized, 0) > 0
            if correct:
                remaining[normalized] -= 1
            pairs.append((float(token.confidence), correct))
        return pairs

    @staticmethod
    def _score(
        engine: BenchmarkEngine,
        results: list[CaseResult],
        calibration: list[tuple[float, bool]],
    ) -> EngineScore:
        succeeded = [result for result in results if result.succeeded]
        failures = Counter(
            result.error_code or "UNKNOWN" for result in results if not result.succeeded
        )
        try:
            configured = bool(engine.health().get("configured", False))
        except Exception:  # noqa: BLE001 - health must never break a benchmark
            configured = False
        return EngineScore(
            engine=engine.name,
            configured=configured,
            cases_attempted=len(results),
            cases_succeeded=len(succeeded),
            mean_character_error_rate=(
                statistics.fmean(r.character_error_rate or 0.0 for r in succeeded)
                if succeeded
                else None
            ),
            mean_word_error_rate=(
                statistics.fmean(r.word_error_rate or 0.0 for r in succeeded)
                if succeeded
                else None
            ),
            median_processing_ms=(
                statistics.median(r.processing_ms for r in succeeded) if succeeded else None
            ),
            calibration_error=expected_calibration_error(calibration),
            failures=dict(failures),
        )
