from app.core.errors import AppError
from app.services.ocr.base import OCRDocumentResult


class UnconfiguredHTREngine:
    @property
    def name(self) -> str:
        return "unconfigured"

    def health(self) -> dict[str, str | bool]:
        return {"provider": self.name, "configured": False, "status": "HTR_NOT_CONFIGURED"}

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        del png_bytes
        raise AppError(
            "HTR_NOT_CONFIGURED",
            "No handwriting recognition provider is configured; printed OCR can continue.",
            503,
        )

