"""Automatic schema detection.

Scores an organization's schemas against the raw OCR text of a document and ranks them, so a
reviewer handling a mixed intake queue is pointed at the right schema instead of discovering
mid-review that the wrong one was pinned.

This module only ever *suggests*. It never activates a schema, never re-pins a prescription,
and never mutates state — the reviewer stays the decision-maker, which is the same rule that
governs extracted medical values elsewhere in the pipeline.
"""

import re
from dataclasses import dataclass, field
from typing import Any

WORD = re.compile(r"[a-z0-9]+")

# An enum option or an explicit alias is document vocabulary the author expects to *see* on the
# page, so it is stronger evidence than a field key, which is often an internal name.
WEIGHT_ALIAS = 2.0
WEIGHT_ENUM_OPTION = 2.0
WEIGHT_LABEL = 1.5
WEIGHT_KEY = 1.0

MIN_SUGGESTION_SCORE = 0.15
MIN_SUGGESTION_MARGIN = 0.05


@dataclass(frozen=True)
class SchemaCandidate:
    schema_id: str
    schema_key: str
    name: str
    version: int
    is_active: bool
    score: float
    matched_terms: list[str]
    total_terms: int


@dataclass(frozen=True)
class DetectionReport:
    candidates: list[SchemaCandidate]
    suggested_schema_id: str | None
    confident: bool
    margin: float
    active_schema_id: str | None = None
    reason: str = ""
    signals_considered: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggested_schema_id": self.suggested_schema_id,
            "confident": self.confident,
            "margin": round(self.margin, 4),
            "active_schema_id": self.active_schema_id,
            "reason": self.reason,
            "signals_considered": self.signals_considered,
            "requires_reviewer_confirmation": True,
            "candidates": [
                {
                    "schema_id": candidate.schema_id,
                    "schema_key": candidate.schema_key,
                    "name": candidate.name,
                    "version": candidate.version,
                    "is_active": candidate.is_active,
                    "score": round(candidate.score, 4),
                    "matched_terms": candidate.matched_terms,
                    "total_terms": candidate.total_terms,
                }
                for candidate in self.candidates
            ],
        }


@dataclass
class _Signals:
    weights: dict[str, float] = field(default_factory=dict)

    def add(self, term: str, weight: float) -> None:
        normalized = " ".join(WORD.findall(term.lower()))
        if not normalized or len(normalized) < 3:
            return
        # A term discovered through several routes keeps its strongest weight.
        self.weights[normalized] = max(self.weights.get(normalized, 0.0), weight)


class SchemaDetector:
    def __init__(
        self,
        min_score: float = MIN_SUGGESTION_SCORE,
        min_margin: float = MIN_SUGGESTION_MARGIN,
    ) -> None:
        self.min_score = min_score
        self.min_margin = min_margin

    def detect(
        self,
        raw_text: str,
        schemas: list[dict[str, Any]],
        active_schema_id: str | None = None,
    ) -> DetectionReport:
        normalized = " ".join(WORD.findall(raw_text.lower()))
        words = set(normalized.split())
        candidates = [
            self._score_schema(schema, normalized, words)
            for schema in schemas
            if isinstance(schema.get("definition"), dict)
        ]
        candidates.sort(key=lambda candidate: (-candidate.score, candidate.schema_key))

        if not candidates:
            return DetectionReport(
                candidates=[],
                suggested_schema_id=None,
                confident=False,
                margin=0.0,
                active_schema_id=active_schema_id,
                reason="NO_SCHEMAS",
            )
        if not words:
            return DetectionReport(
                candidates=candidates,
                suggested_schema_id=None,
                confident=False,
                margin=0.0,
                active_schema_id=active_schema_id,
                reason="NO_OCR_TEXT",
                signals_considered=sum(c.total_terms for c in candidates),
            )

        top = candidates[0]
        runner_up = candidates[1].score if len(candidates) > 1 else 0.0
        margin = top.score - runner_up
        if top.score < self.min_score:
            reason = "LOW_SIGNAL"
        elif margin < self.min_margin:
            reason = "AMBIGUOUS"
        else:
            reason = "CONFIDENT"
        confident = reason == "CONFIDENT"
        return DetectionReport(
            candidates=candidates,
            suggested_schema_id=top.schema_id if confident else None,
            confident=confident,
            margin=margin,
            active_schema_id=active_schema_id,
            reason=reason,
            signals_considered=sum(c.total_terms for c in candidates),
        )

    def _score_schema(
        self, schema: dict[str, Any], normalized_text: str, words: set[str]
    ) -> SchemaCandidate:
        signals = _Signals()
        self._collect(schema["definition"], signals)
        matched: list[str] = []
        matched_weight = 0.0
        total_weight = sum(signals.weights.values())
        for term, weight in signals.weights.items():
            if self._matches(term, normalized_text, words):
                matched.append(term)
                matched_weight += weight
        return SchemaCandidate(
            schema_id=str(schema.get("id", "")),
            schema_key=str(schema.get("schema_key", "")),
            name=str(schema.get("name", "")),
            version=int(schema.get("version", 0) or 0),
            is_active=bool(schema.get("is_active", False)),
            score=(matched_weight / total_weight) if total_weight else 0.0,
            matched_terms=sorted(matched),
            total_terms=len(signals.weights),
        )

    @staticmethod
    def _matches(term: str, normalized_text: str, words: set[str]) -> bool:
        if " " in term:
            return term in normalized_text
        return term in words

    def _collect(self, node: Any, signals: _Signals) -> None:
        if isinstance(node, dict):
            for alias in node.get("aliases") or []:
                if isinstance(alias, str):
                    signals.add(alias, WEIGHT_ALIAS)
            for option in node.get("options") or []:
                if isinstance(option, str):
                    signals.add(option, WEIGHT_ENUM_OPTION)
            label = node.get("label")
            if isinstance(label, str):
                signals.add(label, WEIGHT_LABEL)
            key = node.get("key")
            if isinstance(key, str):
                signals.add(key, WEIGHT_KEY)

            for child_key, child in node.items():
                if child_key in {"aliases", "options", "label", "key"}:
                    continue
                if child_key == "item_schema" and isinstance(child, dict):
                    for item_key, item_value in child.items():
                        signals.add(item_key, WEIGHT_KEY)
                        self._collect(item_value, signals)
                    continue
                self._collect(child, signals)
        elif isinstance(node, list):
            for child in node:
                self._collect(child, signals)
