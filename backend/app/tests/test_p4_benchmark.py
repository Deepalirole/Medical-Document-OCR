import json

import pytest

from app.core.errors import AppError
from app.services.benchmark.dataset import load_cases
from app.services.benchmark.harness import BenchmarkCase, BenchmarkHarness
from app.services.benchmark.metrics import (
    character_error_rate,
    expected_calibration_error,
    normalize_text,
    word_error_rate,
)
from app.services.ocr.base import BoundingBox, OCRDocumentResult, OCRToken

CASES = [
    BenchmarkCase("printed-01", b"page-one", "Tab Augmentin 625 mg twice daily", "printed"),
    BenchmarkCase("hand-01", b"page-two", "Cap Omeprazole 20 mg", "handwritten"),
]


def make_result(text, confidences=None, provider="stub"):
    words = text.split()
    confidences = confidences or [None] * len(words)
    tokens = [
        OCRToken(word, confidence, BoundingBox(0, 0, 1, 1), index)
        for index, (word, confidence) in enumerate(zip(words, confidences, strict=False))
    ]
    scored = [c for c in confidences if c is not None]
    return OCRDocumentResult(
        provider=provider,
        provider_version="1.0",
        raw_text=text,
        confidence=sum(scored) / len(scored) if scored else None,
        processing_ms=12,
        tokens=tokens,
        metadata={},
    )


class StubEngine:
    def __init__(self, name, outputs, configured=True):
        self._name = name
        self.outputs = outputs
        self.configured = configured

    @property
    def name(self):
        return self._name

    def health(self):
        return {"provider": self._name, "configured": self.configured}

    def extract(self, png_bytes):
        output = self.outputs[png_bytes]
        if isinstance(output, Exception):
            raise output
        return output


def test_normalization_ignores_case_and_whitespace_formatting():
    assert normalize_text("  Tab   AUGMENTIN\n625 mg ") == "tab augmentin 625 mg"
    assert character_error_rate("Tab Augmentin", "tab   augmentin") == 0.0


def test_error_rates_are_relative_to_the_reference_length():
    assert character_error_rate("abcd", "abcd") == 0.0
    assert character_error_rate("abcd", "abXd") == 0.25
    assert word_error_rate("one two three four", "one two three") == 0.25
    assert character_error_rate("abcd", "") == 1.0
    assert character_error_rate("", "") == 0.0


def test_calibration_error_punishes_overconfidence():
    honest = expected_calibration_error([(0.9, True)] * 9 + [(0.9, False)])
    overconfident = expected_calibration_error([(0.95, True)] * 5 + [(0.95, False)] * 5)
    assert honest is not None and overconfident is not None
    assert overconfident > honest
    assert expected_calibration_error([]) is None


def test_harness_scores_and_ranks_competing_engines():
    perfect = StubEngine(
        "perfect",
        {
            b"page-one": make_result("Tab Augmentin 625 mg twice daily"),
            b"page-two": make_result("Cap Omeprazole 20 mg"),
        },
    )
    sloppy = StubEngine(
        "sloppy",
        {
            b"page-one": make_result("Tab Augmentn 625 mg twice"),
            b"page-two": make_result("Cap Omeprazole 20"),
        },
    )
    report = BenchmarkHarness(CASES).run([sloppy, perfect])
    assert report.ranking == ["perfect", "sloppy"]
    by_engine = {score.engine: score for score in report.scores}
    assert by_engine["perfect"].mean_character_error_rate == 0.0
    assert by_engine["sloppy"].mean_character_error_rate > 0.0
    assert by_engine["perfect"].cases_succeeded == 2
    assert by_engine["perfect"].median_processing_ms == 12


def test_a_failing_provider_is_recorded_rather_than_aborting_the_run():
    broken = StubEngine(
        "broken",
        {
            b"page-one": AppError("HTR_NOT_CONFIGURED", "no provider", 503),
            b"page-two": RuntimeError("model exploded"),
        },
        configured=False,
    )
    working = StubEngine(
        "working",
        {
            b"page-one": make_result("Tab Augmentin 625 mg twice daily"),
            b"page-two": make_result("Cap Omeprazole 20 mg"),
        },
    )
    report = BenchmarkHarness(CASES).run([broken, working])
    scores = {score.engine: score for score in report.scores}
    assert scores["broken"].cases_succeeded == 0
    assert scores["broken"].success_rate == 0.0
    assert scores["broken"].mean_character_error_rate is None
    assert scores["broken"].failures == {"HTR_NOT_CONFIGURED": 1, "RuntimeError": 1}
    assert scores["broken"].configured is False
    assert report.ranking == ["working", "broken"]


def test_kind_filter_separates_handwriting_from_printed_scoring():
    engine = StubEngine(
        "stub",
        {
            b"page-one": make_result("Tab Augmentin 625 mg twice daily"),
            b"page-two": make_result("totally wrong"),
        },
    )
    printed = BenchmarkHarness(CASES).run([engine], kind="printed")
    handwritten = BenchmarkHarness(CASES).run([engine], kind="handwritten")
    assert printed.scores[0].cases_attempted == 1
    assert printed.scores[0].mean_character_error_rate == 0.0
    assert handwritten.scores[0].mean_character_error_rate > 0.0
    with pytest.raises(AppError) as error:
        BenchmarkHarness(CASES).run([engine], kind="nonexistent")
    assert error.value.code == "BENCHMARK_NO_CASES"


def test_calibration_uses_token_confidence_against_the_reference():
    engine = StubEngine(
        "confident",
        {
            b"page-one": make_result(
                "Tab Augmentin 625 mg twice daily", [0.99, 0.99, 0.99, 0.99, 0.99, 0.99]
            ),
            b"page-two": make_result("wrong wrong wrong", [0.99, 0.99, 0.99]),
        },
    )
    report = BenchmarkHarness(CASES).run([engine])
    calibration = report.scores[0].calibration_error
    assert calibration is not None and calibration > 0.0


def test_repeated_tokens_are_credited_only_per_genuine_occurrence():
    case = [BenchmarkCase("dup", b"p", "paracetamol", "printed")]
    engine = StubEngine(
        "repeater",
        {b"p": make_result("paracetamol paracetamol paracetamol", [0.9, 0.9, 0.9])},
    )
    report = BenchmarkHarness(case).run([engine])
    # One of three high-confidence tokens is genuine, so calibration must be far from perfect.
    assert report.scores[0].calibration_error > 0.5


def test_empty_case_list_is_rejected():
    with pytest.raises(AppError) as error:
        BenchmarkHarness([])
    assert error.value.code == "BENCHMARK_NO_CASES"


def test_report_serialises_to_json_for_ci_comparison():
    engine = StubEngine(
        "stub",
        {
            b"page-one": make_result("Tab Augmentin 625 mg twice daily"),
            b"page-two": make_result("Cap Omeprazole 20 mg"),
        },
    )
    payload = json.loads(json.dumps(BenchmarkHarness(CASES).run([engine]).to_dict()))
    assert payload["ranking"] == ["stub"]
    assert payload["scores"][0]["success_rate"] == 1.0
    assert payload["scores"][0]["mean_character_error_rate"] == 0.0


def test_dataset_loader_pairs_images_with_ground_truth_by_kind(tmp_path):
    for kind, stem, text in (
        ("printed", "page-01", "Tab Augmentin"),
        ("handwritten", "note-01", "Cap Omeprazole"),
    ):
        directory = tmp_path / kind
        directory.mkdir()
        (directory / f"{stem}.png").write_bytes(b"image-bytes")
        (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
    (tmp_path / "printed" / "orphan.png").write_bytes(b"no-label")

    cases = load_cases(tmp_path)
    assert [(case.kind, case.name) for case in cases] == [
        ("handwritten", "note-01"),
        ("printed", "page-01"),
    ]
    assert cases[0].expected_text == "Cap Omeprazole"


def test_dataset_loader_reports_a_missing_directory(tmp_path):
    with pytest.raises(AppError) as error:
        load_cases(tmp_path / "absent")
    assert error.value.code == "BENCHMARK_DATASET_MISSING"


def test_dataset_loader_reports_an_empty_directory(tmp_path):
    with pytest.raises(AppError) as error:
        load_cases(tmp_path)
    assert error.value.code == "BENCHMARK_NO_CASES"
