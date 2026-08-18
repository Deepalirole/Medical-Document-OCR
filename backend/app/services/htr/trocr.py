"""TrOCR handwriting adapter.

TrOCR is a sequence-to-sequence model: it transcribes an image region into text and has no
concept of per-word boxes. The adapter is honest about that — tokens carry ``bbox=None``
rather than a fabricated rectangle, and per-token confidence is only populated when the model
actually returns generation scores.

``transformers`` and ``torch`` are optional; without them the engine reports itself
unconfigured and raises ``HTR_NOT_CONFIGURED``, so printed OCR keeps working.
"""

import time
from io import BytesIO
from typing import Any

from app.core.errors import AppError
from app.services.ocr.base import OCRDocumentResult, OCRToken

DEFAULT_MODEL = "microsoft/trocr-base-handwritten"
# Last-resort vocabulary when a checkpoint ships none and names no source of its own.
FALLBACK_TOKENIZER = "roberta-large"


class TrOCREngine:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        max_new_tokens: int = 128,
        enabled: bool = True,
        tokenizer_name: str = "",
    ) -> None:
        self.model_name = model_name or DEFAULT_MODEL
        self.max_new_tokens = max_new_tokens
        self.enabled = enabled
        self.tokenizer_name = tokenizer_name
        self._processor: Any = None
        self._model: Any = None

    @property
    def name(self) -> str:
        return "trocr"

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def health(self) -> dict[str, str | bool]:
        available = self.available
        return {
            "provider": self.name,
            "configured": available,
            "model": self.model_name,
            "status": "HTR_READY" if available else "HTR_NOT_CONFIGURED",
        }

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        processor, model, torch = self._load()
        started = time.perf_counter()
        try:
            from PIL import Image

            with Image.open(BytesIO(png_bytes)) as image:
                pixel_values = processor(
                    images=image.convert("RGB"), return_tensors="pt"
                ).pixel_values
            with torch.no_grad():
                generated = model.generate(
                    pixel_values,
                    max_new_tokens=self.max_new_tokens,
                    output_scores=True,
                    return_dict_in_generate=True,
                )
            sequences = getattr(generated, "sequences", generated)
            text = processor.batch_decode(sequences, skip_special_tokens=True)[0]
            confidence = self._sequence_confidence(generated, model, torch)
        except AppError:
            raise
        except Exception as error:  # noqa: BLE001 - provider surface is not typed
            raise AppError("HTR_FAILED", "TrOCR could not transcribe the page.", 502) from error

        words = str(text).split()
        return OCRDocumentResult(
            provider=self.name,
            provider_version=self.model_name,
            raw_text=" ".join(words),
            confidence=confidence,
            processing_ms=int((time.perf_counter() - started) * 1000),
            tokens=[
                OCRToken(text=word, confidence=confidence, bbox=None, sequence_index=index)
                for index, word in enumerate(words)
            ],
            metadata={
                "model": self.model_name,
                "line_level": True,
                "bounding_boxes_available": False,
            },
        )

    def _load(self) -> tuple[Any, Any, Any]:
        if self._processor is not None and self._model is not None:
            import torch

            return self._processor, self._model, torch
        if not self.enabled:
            raise AppError(
                "HTR_NOT_CONFIGURED",
                "The TrOCR adapter is disabled by configuration.",
                503,
            )
        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        except ImportError as error:
            raise AppError(
                "HTR_NOT_CONFIGURED",
                "TrOCR requires transformers and torch; install the 'trocr' extra to enable it.",
                503,
            ) from error
        try:
            self._processor = self._load_processor(TrOCRProcessor)
            self._model = VisionEncoderDecoderModel.from_pretrained(self.model_name)
            self._model.eval()
        except Exception as error:  # noqa: BLE001 - weight download/load failures
            raise AppError(
                "HTR_NOT_CONFIGURED",
                f"TrOCR weights for {self.model_name} could not be loaded: {error}",
                503,
            ) from error
        return self._processor, self._model, torch

    def _load_processor(self, processor_class: Any) -> Any:
        """Build the processor, tolerating checkpoints that ship no tokenizer vocabulary.

        The official ``microsoft/trocr-*`` repositories contain only a ``tokenizer_config.json``
        that names a *different* repository (``roberta-large``) as the real vocabulary source.
        Transformers 4.x followed that pointer; 5.x does not, and fails with a misleading
        "install sentencepiece" message. So when the direct load fails we resolve the tokenizer
        ourselves and assemble the processor from its two halves.
        """
        try:
            return processor_class.from_pretrained(self.model_name)
        except Exception:
            from transformers import AutoImageProcessor, AutoTokenizer

            tokenizer_name = self.tokenizer_name or self._tokenizer_hint() or FALLBACK_TOKENIZER
            return processor_class(
                image_processor=AutoImageProcessor.from_pretrained(self.model_name),
                tokenizer=AutoTokenizer.from_pretrained(tokenizer_name),
            )

    def _tokenizer_hint(self) -> str:
        """Read the vocabulary repository named by the checkpoint's tokenizer config."""
        try:
            import json

            from huggingface_hub import hf_hub_download

            path = hf_hub_download(self.model_name, "tokenizer_config.json")
            with open(path, encoding="utf-8") as handle:
                name = json.load(handle).get("name_or_path")
            return str(name) if name and name != self.model_name else ""
        except Exception:  # noqa: BLE001 - hint only; the caller has a default
            return ""

    @staticmethod
    def _sequence_confidence(generated: Any, model: Any, torch: Any) -> float | None:
        """Mean per-step probability of the emitted sequence, or None when unavailable.

        This is a real model signal, not a placeholder: when the model cannot supply
        transition scores the adapter reports no confidence rather than inventing one.
        """
        scores = getattr(generated, "scores", None)
        sequences = getattr(generated, "sequences", None)
        if not scores or sequences is None:
            return None
        try:
            transitions = model.compute_transition_scores(
                sequences, scores, normalize_logits=True
            )
            finite = transitions[0][torch.isfinite(transitions[0])]
            if finite.numel() == 0:
                return None
            return round(float(torch.exp(finite.mean())), 6)
        except Exception:  # noqa: BLE001 - confidence is optional, never fatal
            return None
