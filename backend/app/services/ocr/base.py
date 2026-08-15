from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class OCRToken:
    text: str
    confidence: float | None
    bbox: BoundingBox | None
    sequence_index: int


@dataclass(frozen=True)
class OCRDocumentResult:
    provider: str
    provider_version: str | None
    raw_text: str
    confidence: float | None
    processing_ms: int
    tokens: list[OCRToken]
    metadata: dict


class OCREngine(Protocol):
    @property
    def name(self) -> str: ...
    def health(self) -> dict[str, str | bool]: ...
    def extract(self, png_bytes: bytes) -> OCRDocumentResult: ...

