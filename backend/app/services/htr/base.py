from typing import Protocol

from app.services.ocr.base import OCRDocumentResult


class HTREngine(Protocol):
    @property
    def name(self) -> str: ...
    def health(self) -> dict[str, str | bool]: ...
    def extract(self, png_bytes: bytes) -> OCRDocumentResult: ...

