"""PaddleOCR adapter.

PaddleOCR and its model weights are large, so the dependency is optional: it is imported
lazily on first use and the engine reports itself unconfigured when the package is absent.
An unavailable adapter therefore behaves like the unconfigured HTR provider — it fails
explicitly instead of silently degrading the evidence other stages depend on.
"""

import time
from io import BytesIO
from typing import Any

from app.core.errors import AppError
from app.services.ocr.base import BoundingBox, OCRDocumentResult, OCRToken


class PaddleOCREngine:
    def __init__(
        self,
        language: str = "en",
        use_angle_classification: bool = True,
        enabled: bool = True,
    ) -> None:
        self.language = language
        self.use_angle_classification = use_angle_classification
        self.enabled = enabled
        self._reader: Any = None
        self._version: str | None = None

    @property
    def name(self) -> str:
        return "paddleocr"

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import paddleocr  # noqa: F401
        except ImportError:
            return False
        return True

    def health(self) -> dict[str, str | bool]:
        available = self.available
        return {
            "provider": self.name,
            "configured": available,
            "language": self.language,
            "status": "OCR_READY" if available else "OCR_NOT_CONFIGURED",
        }

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        reader = self._load_reader()
        started = time.perf_counter()
        try:
            image = self._to_array(png_bytes)
            raw = reader.ocr(image, cls=self.use_angle_classification)
        except AppError:
            raise
        except Exception as error:  # noqa: BLE001 - provider surface is not typed
            raise AppError("OCR_FAILED", "PaddleOCR could not process the page.", 502) from error

        tokens: list[OCRToken] = []
        confidences: list[float] = []
        for box, text, confidence in self._iter_predictions(raw):
            normalized = text.strip()
            if not normalized:
                continue
            if confidence is not None:
                confidences.append(confidence)
            tokens.append(
                OCRToken(
                    text=normalized,
                    confidence=confidence,
                    bbox=box,
                    sequence_index=len(tokens),
                )
            )
        return OCRDocumentResult(
            provider=self.name,
            provider_version=self._version,
            raw_text=" ".join(token.text for token in tokens),
            confidence=sum(confidences) / len(confidences) if confidences else None,
            processing_ms=int((time.perf_counter() - started) * 1000),
            tokens=tokens,
            metadata={
                "language": self.language,
                "angle_classification": self.use_angle_classification,
            },
        )

    def _load_reader(self) -> Any:
        if self._reader is not None:
            return self._reader
        if not self.enabled:
            raise AppError(
                "OCR_NOT_CONFIGURED",
                "The PaddleOCR adapter is disabled by configuration.",
                503,
            )
        try:
            import paddleocr
        except ImportError as error:
            raise AppError(
                "OCR_NOT_CONFIGURED",
                "PaddleOCR is not installed; install the 'paddle' extra to enable it.",
                503,
            ) from error
        try:
            self._reader = paddleocr.PaddleOCR(
                lang=self.language,
                use_angle_cls=self.use_angle_classification,
                show_log=False,
            )
        except TypeError:
            # Newer releases dropped show_log from the constructor signature.
            self._reader = paddleocr.PaddleOCR(
                lang=self.language, use_angle_cls=self.use_angle_classification
            )
        except Exception as error:  # noqa: BLE001 - model download/initialisation failures
            raise AppError(
                "OCR_NOT_CONFIGURED",
                "PaddleOCR is installed but its models could not be initialised.",
                503,
            ) from error
        self._version = getattr(paddleocr, "__version__", None)
        return self._reader

    @staticmethod
    def _to_array(png_bytes: bytes) -> Any:
        import numpy
        from PIL import Image

        with Image.open(BytesIO(png_bytes)) as image:
            return numpy.array(image.convert("RGB"))

    @staticmethod
    def _iter_predictions(raw: Any):
        """Normalise PaddleOCR's nested result shape into (bbox, text, confidence).

        Releases differ: some return ``[page][line]``, others a flat ``[line]`` list, and a
        page with no text can come back as ``None``.
        """
        if not raw:
            return
        pages = raw if isinstance(raw, list) else [raw]
        if pages and pages[0] is not None and not _is_line(pages[0]):
            lines = [line for page in pages if page for line in page]
        else:
            lines = [line for line in pages if line]
        for line in lines:
            if not _is_line(line):
                continue
            box, payload = line[0], line[1]
            text, confidence = (payload[0], payload[1]) if len(payload) > 1 else (payload[0], None)
            yield _to_bbox(box), str(text), _to_confidence(confidence)


def _is_line(candidate: Any) -> bool:
    return (
        isinstance(candidate, (list, tuple))
        and len(candidate) >= 2
        and isinstance(candidate[1], (list, tuple))
        and bool(candidate[1])
        and isinstance(candidate[1][0], str)
    )


def _to_bbox(box: Any) -> BoundingBox | None:
    try:
        xs = [int(point[0]) for point in box]
        ys = [int(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    return BoundingBox(min(xs), min(ys), max(xs), max(ys))


def _to_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))
