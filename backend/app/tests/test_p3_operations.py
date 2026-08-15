import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4

from app.core.logging import JsonFormatter
from app.repositories.supabase.processing import SupabaseProcessingRepository
from app.services.extraction.pipeline import ExtractionService
from app.services.llm.base import LLMExtraction
from app.services.llm.openrouter import OpenRouterProvider
from app.tests.test_p2_dynamic_review import (
    GENERAL_SCHEMA,
    ORG_ID,
    PRESCRIPTION_ID,
    SCHEMA_ID,
    FakeExtractionRepository,
)

ROOT = Path(__file__).parents[3]


class CountingLLM:
    name = "counting-llm"

    def __init__(self):
        self.calls = 0

    def health(self):
        return {"configured": True, "model": "test-model"}

    async def extract(self, raw_text, evidence, schema_definition, json_schema):
        self.calls += 1
        return LLMExtraction(
            provider=self.name,
            model="test-model",
            structured_output={
                "patient": {"name": "Rahul", "age": None},
                "medicines": [
                    {"medicine_name": "Augmentin", "strength": "625 mg", "frequency": "1-0-1"}
                ],
            },
            raw_response={"id": "one"},
            processing_ms=5,
        )


def test_extraction_is_idempotent_after_fields_exist():
    repository = FakeExtractionRepository()
    provider = CountingLLM()
    service = ExtractionService(repository, provider)
    prescription = {
        "id": str(PRESCRIPTION_ID),
        "organization_id": str(ORG_ID),
        "schema_id": str(SCHEMA_ID),
        "status": "REVIEW_REQUIRED",
    }
    first = asyncio.run(service.extract(prescription, "same-request"))
    field_count = len(repository.field_rows)
    second = asyncio.run(service.extract(prescription, "same-request"))
    assert first["status"] == "REVIEW_REQUIRED"
    assert second["idempotent"] is True
    assert len(repository.field_rows) == field_count
    assert provider.calls == 1


class CapturingClient:
    def __init__(self):
        self.params = None

    async def request(self, method, path, **kwargs):
        self.params = kwargs.get("params")
        return []


def test_ocr_list_omits_heavy_tokens_by_default():
    client = CapturingClient()
    repository = SupabaseProcessingRepository(client)  # type: ignore[arg-type]
    asyncio.run(repository.ocr_results(PRESCRIPTION_ID, include_tokens=False))
    assert client.params["select"] == "*"


def test_structured_logs_do_not_include_medical_content_or_secrets():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "api.access", logging.INFO, __file__, 1, "request_completed", (), None
    )
    record.request_id = "request-id"
    record.method = "POST"
    record.path = "/api/prescriptions/id/process"
    record.status = 200
    record.duration_ms = 12
    payload = formatter.format(record)
    parsed = json.loads(payload)
    assert parsed["event"] == "request_completed"
    assert "Augmentin" not in payload
    assert "token" not in payload.casefold()


def test_hardening_migrations_pin_schema_and_export_metrics():
    sql = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    )
    assert "schema_version integer not null" in sql
    assert "organization_processing_metrics" in sql
    assert "source_sha256" in sql and "prescriptions_org_source_dedupe" in sql
    assert "idempotency_key" in sql
    assert "approve_prescription_snapshot" in sql


def test_frontend_bundle_source_has_no_server_secret_names():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "frontend" / "src").rglob("*")
        if path.is_file()
    )
    assert "SUPABASE_SERVICE_ROLE_KEY" not in source
    assert "OPENROUTER_API_KEY" not in source


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_openrouter_retries_transient_failure(monkeypatch):
    responses = [
        FakeResponse(503, {"error": {"message": "unavailable"}}),
        FakeResponse(
            200,
            {
                "model": "test-model",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"patient": null}'}}
                ],
            },
        ),
    ]

    class FakeClient:
        def __init__(self, timeout, **kwargs):
            self.timeout = timeout
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return responses.pop(0)

    monkeypatch.setattr("app.services.llm.openrouter.httpx.AsyncClient", FakeClient)
    provider = OpenRouterProvider("secret-test-key", "test-model", retries=1)
    result = asyncio.run(provider.extract("text", [], GENERAL_SCHEMA, {"type": "object"}))
    assert result.structured_output == {"patient": None}
    assert responses == []


def test_integration_payload_requires_approved_version(client, repository):
    async def prescription_for_user(_prescription_id):
        return {
            "id": str(PRESCRIPTION_ID),
            "organization_id": str(ORG_ID),
            "approved_at": "2026-08-12T10:00:00Z",
        }

    async def no_version(_prescription_id):
        return None

    repository.prescription_for_user = prescription_for_user
    repository.approved_version = no_version
    denied = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/integration-payload")
    assert denied.status_code == 409

    async def approved(_prescription_id):
        return {
            "schema_id": str(uuid4()),
            "schema_version": 2,
            "version": 1,
            "structured_json": {"patient": {"name": "Reviewed"}},
        }

    repository.approved_version = approved
    allowed = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/integration-payload")
    assert allowed.status_code == 200
    assert allowed.json()["data"]["patient"]["name"] == "Reviewed"
