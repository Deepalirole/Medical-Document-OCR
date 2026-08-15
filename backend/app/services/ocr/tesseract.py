import shutil
import time
from io import BytesIO

import pytesseract
from PIL import Image
from pytesseract import Output

from app.core.errors import AppError
from app.services.ocr.base import BoundingBox, OCRDocumentResult, OCRToken


class TesseractEngine:
    def __init__(self, command: str = "", language: str = "eng") -> None:
        self.command = command or shutil.which("tesseract") or ""
        self.language = language
        if self.command:
            pytesseract.pytesseract.tesseract_cmd = self.command

    @property
    def name(self) -> str:
        return "tesseract"

    def health(self) -> dict[str, str | bool]:
        configured = bool(self.command)
        return {"provider": self.name, "configured": configured, "command": configured}

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        if not self.command:
            raise AppError("OCR_NOT_CONFIGURED", "Tesseract is not configured on the server.", 503)
        started = time.perf_counter()
        try:
            with Image.open(BytesIO(png_bytes)) as image:
                data, rotation, page_segmentation_mode = self._best_result(image)
            version = str(pytesseract.get_tesseract_version())
        except (pytesseract.TesseractError, OSError) as error:
            raise AppError("OCR_FAILED", "Tesseract could not process the page.", 502) from error

        tokens: list[OCRToken] = []
        confidence_values: list[float] = []
        text_parts: list[str] = []
        for index, text in enumerate(data["text"]):
            normalized = text.strip()
            if not normalized:
                continue
            raw_confidence = float(data["conf"][index])
            confidence = raw_confidence / 100 if raw_confidence >= 0 else None
            if confidence is not None:
                confidence_values.append(confidence)
            left, top = int(data["left"][index]), int(data["top"][index])
            width, height = int(data["width"][index]), int(data["height"][index])
            tokens.append(
                OCRToken(
                    text=normalized,
                    confidence=confidence,
                    bbox=BoundingBox(left, top, left + width, top + height),
                    sequence_index=len(tokens),
                )
            )
            text_parts.append(normalized)
        elapsed = int((time.perf_counter() - started) * 1000)
        average = sum(confidence_values) / len(confidence_values) if confidence_values else None
        return OCRDocumentResult(
            provider=self.name,
            provider_version=version,
            raw_text=" ".join(text_parts),
            confidence=average,
            processing_ms=elapsed,
            tokens=tokens,
            metadata={
                "language": self.language,
                "rotation_degrees": rotation,
                "page_segmentation_mode": page_segmentation_mode,
            },
        )

    def _best_result(self, image: Image.Image) -> tuple[dict, int, int]:
        """Recover text from scans whose camera orientation/layout is unknown.

        Tesseract's automatic layout mode can legitimately return no words for a
        sideways sparse prescription. Try the inexpensive default first, then
        score sparse-text results in every right-angle orientation.
        """
        candidates: list[tuple[float, dict, int, int]] = []
        for rotation, page_segmentation_mode in (
            (0, 3),
            (0, 11),
            (90, 11),
            (270, 11),
            (180, 11),
        ):
            candidate = image if rotation == 0 else image.rotate(rotation, expand=True)
            data = pytesseract.image_to_data(
                candidate,
                lang=self.language,
                config=f"--psm {page_segmentation_mode}",
                output_type=Output.DICT,
                timeout=30,
            )
            score = self._score(data)
            candidates.append((score, data, rotation, page_segmentation_mode))
            if rotation == 0 and page_segmentation_mode == 3 and score >= 12:
                break
        _, data, rotation, page_segmentation_mode = max(candidates, key=lambda item: item[0])
        return data, rotation, page_segmentation_mode

    @staticmethod
    def _score(data: dict) -> float:
        score = 0.0
        for text, confidence in zip(data.get("text", []), data.get("conf", []), strict=False):
            normalized = text.strip()
            if not normalized:
                continue
            try:
                confidence_value = max(float(confidence), 0.0) / 100
            except (TypeError, ValueError):
                confidence_value = 0.0
            alphanumeric = sum(character.isalnum() for character in normalized)
            score += alphanumeric * (0.25 + confidence_value)
        return score
