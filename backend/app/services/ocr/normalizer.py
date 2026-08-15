from dataclasses import asdict
from typing import Any
from uuid import UUID

from app.services.ocr.base import OCRDocumentResult


def normalize_evidence(
    result: OCRDocumentResult,
    prescription_id: UUID,
    page_id: UUID,
    page_number: int,
    source: str,
) -> list[dict[str, Any]]:
    return [
        {
            "text": token.text,
            "confidence": token.confidence,
            "page": page_number,
            "bbox": asdict(token.bbox) if token.bbox else None,
            "source": source,
            "engine": result.provider,
            "prescription_id": str(prescription_id),
            "page_id": str(page_id),
            "sequence_index": token.sequence_index,
        }
        for token in result.tokens
    ]

