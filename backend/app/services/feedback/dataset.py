"""Advanced feedback dataset.

Turns reviewer corrections into supervised examples: what the model proposed, what the
reviewer approved, and the OCR evidence both were looking at. That triple is what makes the
dataset useful for prompt evaluation and provider comparison.

Two rules are enforced here rather than left to the caller:

* **Approved-only.** A prescription with no immutable approved version contributes nothing. An
  in-flight review is not ground truth, and exporting it would teach against unverified values.
* **Reviewer identity is never exported.** Corrections carry ``corrected_by``; the dataset
  carries only whether a change happened and when, so an evaluation artefact cannot become a
  record of who touched which patient.
"""

import json
from dataclasses import dataclass, field
from typing import Any

REDACTED_CORRECTION_KEYS = {"corrected_by", "reason"}


@dataclass(frozen=True)
class FeedbackExample:
    prescription_id: str
    schema_id: str
    schema_version: int
    approved_version: int
    field_path: str
    field_type: str
    proposed_value: Any
    approved_value: Any
    corrected: bool
    correction_count: int
    review_status: str
    confidence: float | None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prescription_id": self.prescription_id,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "approved_version": self.approved_version,
            "field_path": self.field_path,
            "field_type": self.field_type,
            "proposed_value": self.proposed_value,
            "approved_value": self.approved_value,
            "corrected": self.corrected,
            "correction_count": self.correction_count,
            "review_status": self.review_status,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class FeedbackDataset:
    examples: list[FeedbackExample]
    prescriptions_considered: int
    prescriptions_exported: int
    prescriptions_skipped_unapproved: int

    @property
    def corrected_count(self) -> int:
        return sum(1 for example in self.examples if example.corrected)

    @property
    def correction_rate(self) -> float:
        return self.corrected_count / len(self.examples) if self.examples else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prescriptions_considered": self.prescriptions_considered,
            "prescriptions_exported": self.prescriptions_exported,
            "prescriptions_skipped_unapproved": self.prescriptions_skipped_unapproved,
            "example_count": len(self.examples),
            "corrected_count": self.corrected_count,
            "correction_rate": round(self.correction_rate, 4),
            "examples": [example.to_dict() for example in self.examples],
        }

    def to_jsonl(self) -> str:
        return "\n".join(
            json.dumps(example.to_dict(), ensure_ascii=False, sort_keys=True)
            for example in self.examples
        )


class FeedbackDatasetBuilder:
    """Assembles examples from already-fetched rows so it stays storage-agnostic."""

    def __init__(self, include_evidence: bool = True) -> None:
        self.include_evidence = include_evidence

    def build(
        self,
        prescriptions: list[dict[str, Any]],
        approved_versions: dict[str, dict[str, Any]],
        fields_by_prescription: dict[str, list[dict[str, Any]]],
        corrections_by_field: dict[str, list[dict[str, Any]]] | None = None,
    ) -> FeedbackDataset:
        corrections_by_field = corrections_by_field or {}
        examples: list[FeedbackExample] = []
        exported = 0
        skipped = 0

        for prescription in prescriptions:
            prescription_id = str(prescription.get("id", ""))
            version = approved_versions.get(prescription_id)
            if not version:
                skipped += 1
                continue
            approved_json = version.get("structured_json")
            if not isinstance(approved_json, dict):
                skipped += 1
                continue

            exported += 1
            for row in fields_by_prescription.get(prescription_id, []):
                examples.append(
                    self._example(prescription_id, version, row, corrections_by_field)
                )

        return FeedbackDataset(
            examples=examples,
            prescriptions_considered=len(prescriptions),
            prescriptions_exported=exported,
            prescriptions_skipped_unapproved=skipped,
        )

    def _example(
        self,
        prescription_id: str,
        version: dict[str, Any],
        row: dict[str, Any],
        corrections_by_field: dict[str, list[dict[str, Any]]],
    ) -> FeedbackExample:
        field_id = str(row.get("id", ""))
        corrections = corrections_by_field.get(field_id, [])
        proposed = row.get("original_value")
        approved = row.get("current_value")
        return FeedbackExample(
            prescription_id=prescription_id,
            schema_id=str(version.get("schema_id", "")),
            schema_version=int(version.get("schema_version", 0) or 0),
            approved_version=int(version.get("version", 0) or 0),
            field_path=str(row.get("field_path", "")),
            field_type=str(row.get("field_type", "")),
            proposed_value=proposed,
            approved_value=approved,
            corrected=bool(corrections) or proposed != approved,
            correction_count=len(corrections),
            review_status=str(row.get("review_status", "")),
            confidence=_optional_float(row.get("confidence")),
            evidence=self._safe_evidence(row.get("evidence")),
        )

    def _safe_evidence(self, evidence: Any) -> list[dict[str, Any]]:
        if not self.include_evidence or not isinstance(evidence, list):
            return []
        return [
            {
                "text": item.get("text"),
                "page": item.get("page"),
                "bbox": item.get("bbox"),
                "source": item.get("source"),
                "engine": item.get("engine"),
                "confidence": item.get("confidence"),
            }
            for item in evidence
            if isinstance(item, dict)
        ]


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
