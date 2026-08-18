"""Cloud OCR adapters.

Both adapters speak plain HTTP through ``httpx`` rather than vendor SDKs, so no extra
dependency is needed and the transport stays inspectable. Credentials are supplied by
configuration, never logged, and an unconfigured adapter reports ``OCR_NOT_CONFIGURED``
instead of attempting an anonymous call.

Word-level confidence and geometry are taken from the provider response where the provider
supplies them, and left as ``None`` where it does not.
"""

import base64
import time
from typing import Any

import httpx

from app.core.errors import AppError
from app.services.ocr.base import BoundingBox, OCRDocumentResult, OCRToken

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
GOOGLE_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


class _CloudOCRBase:
    def __init__(self, timeout_seconds: int = 30, retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        json: Any = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                    response = client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=json,
                        content=content,
                    )
                if response.status_code in TRANSIENT_STATUSES and attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code >= 400:
                    raise AppError(
                        "OCR_FAILED",
                        f"{self.name} rejected the page.",
                        502,
                        {"status": response.status_code},
                    )
                return response
            except AppError:
                raise
            except httpx.HTTPError as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
        raise AppError("OCR_FAILED", f"{self.name} could not be reached.", 502) from last_error

    @staticmethod
    def _finish(
        provider: str,
        tokens: list[OCRToken],
        started: float,
        metadata: dict[str, Any],
        raw_text: str | None = None,
    ) -> OCRDocumentResult:
        confidences = [token.confidence for token in tokens if token.confidence is not None]
        return OCRDocumentResult(
            provider=provider,
            provider_version=None,
            raw_text=raw_text if raw_text is not None else " ".join(t.text for t in tokens),
            confidence=sum(confidences) / len(confidences) if confidences else None,
            processing_ms=int((time.perf_counter() - started) * 1000),
            tokens=tokens,
            metadata=metadata,
        )


class GoogleVisionOCREngine(_CloudOCRBase):
    def __init__(
        self,
        api_key: str = "",
        language_hints: str = "",
        timeout_seconds: int = 30,
        retries: int = 2,
    ) -> None:
        super().__init__(timeout_seconds, retries)
        self.api_key = api_key
        self.language_hints = [h.strip() for h in language_hints.split(",") if h.strip()]

    @property
    def name(self) -> str:
        return "google_vision"

    def health(self) -> dict[str, str | bool]:
        configured = bool(self.api_key)
        return {
            "provider": self.name,
            "configured": configured,
            "status": "OCR_READY" if configured else "OCR_NOT_CONFIGURED",
        }

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        if not self.api_key:
            raise AppError("OCR_NOT_CONFIGURED", "Google Vision has no API key.", 503)
        started = time.perf_counter()
        body: dict[str, Any] = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(png_bytes).decode("ascii")},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                }
            ]
        }
        if self.language_hints:
            body["requests"][0]["imageContext"] = {"languageHints": self.language_hints}
        response = self._request(
            "POST",
            GOOGLE_VISION_URL,
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
            json=body,
        )
        payload = _json(response, self.name)
        first = (payload.get("responses") or [{}])[0]
        if first.get("error"):
            raise AppError(
                "OCR_FAILED",
                "Google Vision returned an error for the page.",
                502,
                {"reason": str(first["error"].get("message", ""))[:200]},
            )
        annotation = first.get("fullTextAnnotation") or {}
        tokens = list(self._iter_words(annotation))
        return self._finish(
            self.name,
            tokens,
            started,
            {"language_hints": self.language_hints, "feature": "DOCUMENT_TEXT_DETECTION"},
            raw_text=str(annotation.get("text", "")).strip() or None,
        )

    @staticmethod
    def _iter_words(annotation: dict[str, Any]):
        index = 0
        for page in annotation.get("pages") or []:
            for block in page.get("blocks") or []:
                for paragraph in block.get("paragraphs") or []:
                    for word in paragraph.get("words") or []:
                        text = "".join(
                            str(symbol.get("text", "")) for symbol in word.get("symbols") or []
                        ).strip()
                        if not text:
                            continue
                        yield OCRToken(
                            text=text,
                            confidence=_confidence(word.get("confidence")),
                            bbox=_vertices_to_bbox(
                                (word.get("boundingBox") or {}).get("vertices")
                            ),
                            sequence_index=index,
                        )
                        index += 1


class AzureDocumentIntelligenceOCREngine(_CloudOCRBase):
    """Azure Document Intelligence ``prebuilt-read``.

    Analysis is asynchronous: the POST returns an operation URL that is polled until the job
    reports ``succeeded``. Polling is bounded, so a stuck job surfaces as a failure rather
    than hanging a processing worker.
    """

    def __init__(
        self,
        endpoint: str = "",
        api_key: str = "",
        model: str = "prebuilt-read",
        timeout_seconds: int = 30,
        retries: int = 2,
        poll_interval_seconds: float = 1.0,
        max_poll_attempts: int = 30,
    ) -> None:
        super().__init__(timeout_seconds, retries)
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max_poll_attempts

    @property
    def name(self) -> str:
        return "azure_document_intelligence"

    def health(self) -> dict[str, str | bool]:
        configured = bool(self.endpoint and self.api_key)
        return {
            "provider": self.name,
            "configured": configured,
            "model": self.model,
            "status": "OCR_READY" if configured else "OCR_NOT_CONFIGURED",
        }

    def extract(self, png_bytes: bytes) -> OCRDocumentResult:
        if not (self.endpoint and self.api_key):
            raise AppError(
                "OCR_NOT_CONFIGURED",
                "Azure Document Intelligence has no endpoint or key.",
                503,
            )
        started = time.perf_counter()
        submitted = self._request(
            "POST",
            f"{self.endpoint}/documentintelligence/documentModels/{self.model}:analyze",
            headers={
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Content-Type": "image/png",
            },
            params={"api-version": "2024-11-30"},
            content=png_bytes,
        )
        operation_url = submitted.headers.get("operation-location")
        if not operation_url:
            raise AppError(
                "OCR_FAILED",
                "Azure Document Intelligence did not return an operation location.",
                502,
            )
        result = self._poll(operation_url)
        analyze = result.get("analyzeResult") or {}
        tokens = list(self._iter_words(analyze))
        return self._finish(
            self.name,
            tokens,
            started,
            {"model": self.model, "api_version": "2024-11-30"},
            raw_text=str(analyze.get("content", "")).strip() or None,
        )

    def _poll(self, operation_url: str) -> dict[str, Any]:
        for _ in range(self.max_poll_attempts):
            response = self._request(
                "GET", operation_url, headers={"Ocp-Apim-Subscription-Key": self.api_key}
            )
            payload = _json(response, self.name)
            status = str(payload.get("status", "")).lower()
            if status == "succeeded":
                return payload
            if status in {"failed", "canceled"}:
                raise AppError(
                    "OCR_FAILED",
                    "Azure Document Intelligence failed to analyse the page.",
                    502,
                    {"status": status},
                )
            time.sleep(self.poll_interval_seconds)
        raise AppError(
            "OCR_FAILED",
            "Azure Document Intelligence did not finish within the polling budget.",
            502,
        )

    @staticmethod
    def _iter_words(analyze: dict[str, Any]):
        index = 0
        for page in analyze.get("pages") or []:
            for word in page.get("words") or []:
                text = str(word.get("content", "")).strip()
                if not text:
                    continue
                yield OCRToken(
                    text=text,
                    confidence=_confidence(word.get("confidence")),
                    bbox=_polygon_to_bbox(word.get("polygon")),
                    sequence_index=index,
                )
                index += 1


def _json(response: httpx.Response, provider: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise AppError("OCR_FAILED", f"{provider} returned a non-JSON response.", 502) from error
    if not isinstance(payload, dict):
        raise AppError("OCR_FAILED", f"{provider} returned an unexpected response.", 502)
    return payload


def _confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))


def _vertices_to_bbox(vertices: Any) -> BoundingBox | None:
    if not vertices:
        return None
    try:
        xs = [int(vertex.get("x", 0)) for vertex in vertices]
        ys = [int(vertex.get("y", 0)) for vertex in vertices]
    except (AttributeError, TypeError, ValueError):
        return None
    return BoundingBox(min(xs), min(ys), max(xs), max(ys)) if xs and ys else None


def _polygon_to_bbox(polygon: Any) -> BoundingBox | None:
    """Azure returns a flat ``[x1, y1, x2, y2, ...]`` list of corner coordinates."""
    if not polygon or len(polygon) < 4 or len(polygon) % 2:
        return None
    try:
        xs = [int(float(polygon[i])) for i in range(0, len(polygon), 2)]
        ys = [int(float(polygon[i])) for i in range(1, len(polygon), 2)]
    except (TypeError, ValueError):
        return None
    return BoundingBox(min(xs), min(ys), max(xs), max(ys))
