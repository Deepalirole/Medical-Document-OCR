import httpx
import pytest

from app.api.dependencies import get_ocr_engine
from app.core.config import Settings
from app.core.errors import AppError
from app.services.ocr.cloud import (
    AzureDocumentIntelligenceOCREngine,
    GoogleVisionOCREngine,
)

PNG = b"\x89PNG\r\n\x1a\nfake"

VISION_PAYLOAD = {
    "responses": [
        {
            "fullTextAnnotation": {
                "text": "Tab Augmentin 625",
                "pages": [
                    {
                        "blocks": [
                            {
                                "paragraphs": [
                                    {
                                        "words": [
                                            {
                                                "confidence": 0.98,
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 10, "y": 12},
                                                        {"x": 60, "y": 12},
                                                        {"x": 60, "y": 40},
                                                        {"x": 10, "y": 40},
                                                    ]
                                                },
                                                "symbols": [
                                                    {"text": "T"},
                                                    {"text": "a"},
                                                    {"text": "b"},
                                                ],
                                            },
                                            {
                                                "confidence": 0.90,
                                                "symbols": [{"text": "Augmentin"}],
                                            },
                                            {"confidence": 0.5, "symbols": [{"text": "  "}]},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        }
    ]
}

AZURE_RESULT = {
    "status": "succeeded",
    "analyzeResult": {
        "content": "Cap Omeprazole 20 mg",
        "pages": [
            {
                "words": [
                    {
                        "content": "Cap",
                        "confidence": 0.995,
                        "polygon": [10, 12, 60, 12, 60, 40, 10, 40],
                    },
                    {"content": "Omeprazole", "confidence": 0.97, "polygon": [70, 12, 180, 40]},
                    {"content": "  ", "confidence": 0.1},
                ]
            }
        ],
    },
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, invalid_json=False):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("not json")
        return self._payload


class FakeClient:
    def __init__(self, script, log, timeout=None, **kwargs):
        self.script = script
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(self, method, url, headers=None, params=None, json=None, content=None):
        self.log.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "params": params or {},
                "json": json,
                "content": content,
            }
        )
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def patch_client(monkeypatch, script, log):
    monkeypatch.setattr(
        "app.services.ocr.cloud.httpx.Client",
        lambda timeout=None, **kwargs: FakeClient(script, log),
    )
    monkeypatch.setattr("app.services.ocr.cloud.time.sleep", lambda _seconds: None)


# --- Google Vision -------------------------------------------------------------------


def test_vision_is_unconfigured_without_a_key():
    engine = GoogleVisionOCREngine("")
    assert engine.health()["configured"] is False
    with pytest.raises(AppError) as error:
        engine.extract(PNG)
    assert error.value.code == "OCR_NOT_CONFIGURED"
    assert error.value.status_code == 503


def test_vision_emits_canonical_evidence(monkeypatch):
    log: list = []
    patch_client(monkeypatch, [FakeResponse(200, VISION_PAYLOAD)], log)
    result = GoogleVisionOCREngine("vision-key", "en,hi").extract(PNG)

    assert result.provider == "google_vision"
    assert result.raw_text == "Tab Augmentin 625"
    assert [token.text for token in result.tokens] == ["Tab", "Augmentin"]
    assert result.tokens[0].confidence == 0.98
    box = result.tokens[0].bbox
    assert (box.x1, box.y1, box.x2, box.y2) == (10, 12, 60, 40)
    assert result.tokens[1].bbox is None
    assert result.confidence == pytest.approx((0.98 + 0.90) / 2)
    assert result.metadata["language_hints"] == ["en", "hi"]


def test_vision_sends_the_key_as_a_query_parameter_not_in_the_body(monkeypatch):
    log: list = []
    patch_client(monkeypatch, [FakeResponse(200, VISION_PAYLOAD)], log)
    GoogleVisionOCREngine("vision-key").extract(PNG)
    call = log[0]
    assert call["params"] == {"key": "vision-key"}
    assert "vision-key" not in str(call["json"])
    assert call["json"]["requests"][0]["features"] == [{"type": "DOCUMENT_TEXT_DETECTION"}]


def test_vision_surfaces_a_per_image_error(monkeypatch):
    payload = {"responses": [{"error": {"message": "Bad image data"}}]}
    patch_client(monkeypatch, [FakeResponse(200, payload)], [])
    with pytest.raises(AppError) as error:
        GoogleVisionOCREngine("vision-key").extract(PNG)
    assert error.value.code == "OCR_FAILED"
    assert error.value.details["reason"] == "Bad image data"


def test_vision_retries_transient_failure_then_succeeds(monkeypatch):
    log: list = []
    patch_client(
        monkeypatch, [FakeResponse(503, {}), FakeResponse(200, VISION_PAYLOAD)], log
    )
    result = GoogleVisionOCREngine("vision-key").extract(PNG)
    assert result.raw_text == "Tab Augmentin 625"
    assert len(log) == 2


def test_vision_gives_up_on_permanent_rejection(monkeypatch):
    patch_client(monkeypatch, [FakeResponse(403, {})], [])
    with pytest.raises(AppError) as error:
        GoogleVisionOCREngine("vision-key").extract(PNG)
    assert error.value.code == "OCR_FAILED"
    assert error.value.details["status"] == 403


def test_vision_reports_a_network_failure_after_exhausting_retries(monkeypatch):
    patch_client(
        monkeypatch,
        [httpx.ConnectError("dns"), httpx.ConnectError("dns"), httpx.ConnectError("dns")],
        [],
    )
    with pytest.raises(AppError) as error:
        GoogleVisionOCREngine("vision-key").extract(PNG)
    assert error.value.code == "OCR_FAILED"


def test_vision_handles_a_page_with_no_text(monkeypatch):
    patch_client(monkeypatch, [FakeResponse(200, {"responses": [{}]})], [])
    result = GoogleVisionOCREngine("vision-key").extract(PNG)
    assert result.tokens == []
    assert result.raw_text == ""
    assert result.confidence is None


def test_non_json_response_is_reported_safely(monkeypatch):
    patch_client(monkeypatch, [FakeResponse(200, None, invalid_json=True)], [])
    with pytest.raises(AppError) as error:
        GoogleVisionOCREngine("vision-key").extract(PNG)
    assert error.value.code == "OCR_FAILED"


# --- Azure Document Intelligence -----------------------------------------------------


def test_azure_is_unconfigured_without_endpoint_or_key():
    assert AzureDocumentIntelligenceOCREngine("", "").health()["configured"] is False
    with pytest.raises(AppError) as error:
        AzureDocumentIntelligenceOCREngine("https://x", "").extract(PNG)
    assert error.value.code == "OCR_NOT_CONFIGURED"


def test_azure_submits_then_polls_until_succeeded(monkeypatch):
    log: list = []
    patch_client(
        monkeypatch,
        [
            FakeResponse(202, {}, headers={"operation-location": "https://poll.test/op/1"}),
            FakeResponse(200, {"status": "running"}),
            FakeResponse(200, AZURE_RESULT),
        ],
        log,
    )
    engine = AzureDocumentIntelligenceOCREngine(
        "https://ocr.example.test/", "azure-key", poll_interval_seconds=0
    )
    result = engine.extract(PNG)

    assert result.provider == "azure_document_intelligence"
    assert result.raw_text == "Cap Omeprazole 20 mg"
    assert [token.text for token in result.tokens] == ["Cap", "Omeprazole"]
    box = result.tokens[0].bbox
    assert (box.x1, box.y1, box.x2, box.y2) == (10, 12, 60, 40)
    assert log[0]["method"] == "POST"
    assert log[0]["url"].endswith("/documentModels/prebuilt-read:analyze")
    assert log[0]["content"] == PNG
    assert log[0]["headers"]["Ocp-Apim-Subscription-Key"] == "azure-key"
    assert [entry["url"] for entry in log[1:]] == ["https://poll.test/op/1"] * 2


def test_azure_reports_a_missing_operation_location(monkeypatch):
    patch_client(monkeypatch, [FakeResponse(202, {}, headers={})], [])
    with pytest.raises(AppError) as error:
        AzureDocumentIntelligenceOCREngine("https://x", "k").extract(PNG)
    assert error.value.code == "OCR_FAILED"
    assert "operation location" in error.value.message


def test_azure_surfaces_a_failed_analysis(monkeypatch):
    patch_client(
        monkeypatch,
        [
            FakeResponse(202, {}, headers={"operation-location": "https://poll.test/op/2"}),
            FakeResponse(200, {"status": "failed"}),
        ],
        [],
    )
    engine = AzureDocumentIntelligenceOCREngine("https://x", "k", poll_interval_seconds=0)
    with pytest.raises(AppError) as error:
        engine.extract(PNG)
    assert error.value.details["status"] == "failed"


def test_azure_polling_is_bounded(monkeypatch):
    log: list = []
    script = [FakeResponse(202, {}, headers={"operation-location": "https://poll.test/op/3"})]
    script.extend(FakeResponse(200, {"status": "running"}) for _ in range(5))
    patch_client(monkeypatch, script, log)
    engine = AzureDocumentIntelligenceOCREngine(
        "https://x", "k", poll_interval_seconds=0, max_poll_attempts=3
    )
    with pytest.raises(AppError) as error:
        engine.extract(PNG)
    assert "polling budget" in error.value.message
    assert len(log) == 4  # one submit plus three bounded polls


def test_azure_ignores_a_malformed_polygon(monkeypatch):
    payload = {
        "status": "succeeded",
        "analyzeResult": {
            "content": "Cap",
            "pages": [{"words": [{"content": "Cap", "confidence": 0.9, "polygon": [1, 2, 3]}]}],
        },
    }
    patch_client(
        monkeypatch,
        [
            FakeResponse(202, {}, headers={"operation-location": "https://poll.test/op/4"}),
            FakeResponse(200, payload),
        ],
        [],
    )
    engine = AzureDocumentIntelligenceOCREngine("https://x", "k", poll_interval_seconds=0)
    result = engine.extract(PNG)
    assert result.tokens[0].bbox is None
    assert result.tokens[0].confidence == 0.9


# --- Wiring --------------------------------------------------------------------------


def test_provider_setting_selects_each_cloud_engine_without_leaking_keys():
    vision = get_ocr_engine(
        Settings(ocr_provider="google_vision", google_vision_api_key="vision-secret")
    )
    azure = get_ocr_engine(
        Settings(
            ocr_provider="azure_document_intelligence",
            azure_ocr_endpoint="https://ocr.example.test",
            azure_ocr_api_key="azure-secret",
        )
    )
    assert isinstance(vision, GoogleVisionOCREngine)
    assert isinstance(azure, AzureDocumentIntelligenceOCREngine)
    assert vision.health()["configured"] is True
    assert azure.health()["configured"] is True
    assert "vision-secret" not in str(vision.health())
    assert "azure-secret" not in str(azure.health())


def test_unconfigured_cloud_provider_selected_by_name_still_fails_safely():
    engine = get_ocr_engine(Settings(ocr_provider="google_vision"))
    assert engine.health()["status"] == "OCR_NOT_CONFIGURED"
    with pytest.raises(AppError) as error:
        engine.extract(PNG)
    assert error.value.code == "OCR_NOT_CONFIGURED"
