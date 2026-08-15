import asyncio
from uuid import UUID, uuid4

import pytest

from app.core.errors import AppError
from app.services.extraction.mapper import DynamicFieldMapper, build_structured_json
from app.services.extraction.pipeline import ExtractionService
from app.services.llm.base import LLMExtraction
from app.services.llm.openrouter import OpenRouterProvider
from app.services.llm.prompt import SYSTEM_PROMPT
from app.services.schema.registry import SchemaRegistry
from app.services.validation.dynamic import DynamicValidator

ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
PRESCRIPTION_ID = UUID("44444444-4444-4444-8444-444444444444")
SCHEMA_ID = UUID("55555555-5555-4555-8555-555555555555")

GENERAL_SCHEMA = {
    "schema_key": "general_opd",
    "version": 1,
    "sections": [
        {
            "key": "patient",
            "type": "object",
            "fields": [
                {"key": "name", "type": "string", "required": True},
                {"key": "age", "type": "number", "required": False},
            ],
        },
        {
            "key": "medicines",
            "type": "medicine_list",
            "required": True,
            "item_schema": {
                "medicine_name": {"type": "string", "required": True},
                "strength": {"type": "string"},
                "frequency": {"type": "string"},
            },
        },
    ],
}

ALTERNATE_SCHEMA = {
    "schema_key": "investigation_only",
    "version": 1,
    "sections": [
        {
            "key": "investigations",
            "type": "array",
            "item_schema": {"type": "string"},
        },
        {"key": "follow_up", "type": "date", "required": False},
    ],
}


def test_registry_supports_nested_medicines_and_scalar_arrays():
    registry = SchemaRegistry()
    first = registry.to_json_schema(GENERAL_SCHEMA)
    second = registry.to_json_schema(ALTERNATE_SCHEMA)
    assert first["properties"]["medicines"]["items"]["properties"]["strength"]
    assert first["required"] == ["patient", "medicines"]
    assert first["properties"]["patient"]["required"] == ["name", "age"]
    assert second["properties"]["investigations"]["items"]["type"] == ["string", "null"]


def test_invalid_schema_is_rejected_before_persistence():
    with pytest.raises(AppError) as error:
        SchemaRegistry().validate({"sections": [{"key": "bad", "type": "unknown"}]})
    assert error.value.code == "SCHEMA_INVALID"


def test_openrouter_parser_only_repairs_json_fencing():
    parsed = OpenRouterProvider.parse_json('```json\n{"patient": null}\n```')
    assert parsed == {"patient": None}
    with pytest.raises(AppError) as error:
        OpenRouterProvider.parse_json('{"patient": invented}')
    assert error.value.code == "LLM_INVALID_JSON"
    assert "Never invent a medicine" in SYSTEM_PROMPT


def test_mapper_flags_unsupported_medical_content_for_review():
    output = {
        "patient": {"name": "Rahul", "age": None},
        "medicines": [
            {"medicine_name": "InventedDrug", "strength": "625 mg", "frequency": "1-0-1"}
        ],
    }
    evidence = [
        {"text": "Rahul", "confidence": 0.9, "source": "ocr"},
        {"text": "625 mg 1-0-1", "confidence": 0.8, "source": "ocr"},
    ]
    fields = DynamicFieldMapper().map(GENERAL_SCHEMA, output, evidence)
    medicine = next(field for field in fields if field.field_path.endswith("medicine_name"))
    assert medicine.review_status == "REVIEW_REQUIRED"
    assert medicine.confidence is None
    patient = next(field for field in fields if field.field_path == "patient.name")
    assert patient.review_status == "HIGH"


def test_mapper_rebuilds_nested_json_and_repeatable_rows():
    output = {
        "patient": {"name": "Rahul", "age": 42},
        "medicines": [
            {"medicine_name": "Augmentin", "strength": "625 mg", "frequency": "1-0-1"},
            {"medicine_name": "Paracetamol", "strength": "500 mg", "frequency": None},
        ],
    }
    supported_values = [
        "Rahul",
        42,
        "Augmentin",
        "625 mg",
        "1-0-1",
        "Paracetamol",
        "500 mg",
    ]
    evidence = [
        {"text": str(value), "confidence": 0.9} for value in supported_values
    ]
    mapped = DynamicFieldMapper().map(GENERAL_SCHEMA, output, evidence)
    rows = [field.as_dict() for field in mapped]
    rebuilt = build_structured_json(rows)
    assert rebuilt == output
    assert len({row["array_item_id"] for row in rows if row["array_item_id"]}) == 2


def test_dynamic_validator_does_not_modify_invalid_medical_values():
    data = {"patient": {"name": "Rahul", "age": "forty"}, "medicines": []}
    result = DynamicValidator().validate(GENERAL_SCHEMA, data)
    assert not result.valid
    assert {warning["code"] for warning in result.warnings} == {
        "TYPE_MISMATCH",
        "REQUIRED_VALUE_MISSING",
    }
    assert data["patient"]["age"] == "forty"


class FakeLLM:
    name = "test-llm"

    def __init__(self, fail: bool = False):
        self.fail = fail

    def health(self):
        return {"configured": not self.fail, "model": "test-model"}

    async def extract(self, raw_text, evidence, schema_definition, json_schema):
        assert "Augmentin" in raw_text
        assert evidence and json_schema["type"] == "object"
        if self.fail:
            raise AppError("LLM_FAILED", "Provider unavailable.", 502)
        return LLMExtraction(
            provider=self.name,
            model="test-model",
            structured_output={
                "patient": {"name": "Rahul", "age": None},
                "medicines": [
                    {"medicine_name": "Augmentin", "strength": "625 mg", "frequency": "1-0-1"}
                ],
            },
            raw_response={"id": "test-response"},
            processing_ms=7,
        )


class FakeExtractionRepository:
    def __init__(self):
        self.field_rows = []
        self.runs = []
        self.jobs = []
        self.updates = []

    async def schema(self, schema_id):
        return {"id": str(schema_id), "definition": GENERAL_SCHEMA}

    async def fields(self, prescription_id):
        return self.field_rows

    async def ocr_results(self, prescription_id, include_tokens=True):
        return [
            {
                "page_id": str(uuid4()),
                "provider": "tesseract",
                "raw_text": "Rahul Augmentin 625 mg 1-0-1",
                "confidence": 0.88,
                "ocr_tokens": [],
            }
        ]

    async def create_job(self, data):
        row = {**data, "id": str(uuid4())}
        self.jobs.append(row)
        return row

    async def finish_job(self, job_id, data):
        self.jobs[-1].update(data)

    async def create_extraction_run(self, data):
        self.runs.append(data)
        return {**data, "id": str(uuid4())}

    async def create_fields(self, fields):
        self.field_rows.extend(fields)
        return fields

    async def delete_fields(self, prescription_id):
        self.field_rows = [f for f in self.field_rows if f.get("prescription_id") != str(prescription_id)]

    async def update_prescription(self, prescription_id, data):
        self.updates.append(data)


def test_extraction_persists_ai_output_and_review_fields_separately():
    repository = FakeExtractionRepository()
    service = ExtractionService(repository, FakeLLM())
    result = asyncio.run(
        service.extract(
            {
                "id": str(PRESCRIPTION_ID),
                "organization_id": str(ORG_ID),
                "schema_id": str(SCHEMA_ID),
            }
        )
    )
    assert result["status"] == "REVIEW_REQUIRED"
    assert repository.runs[0]["structured_output"]["medicines"][0]["medicine_name"] == "Augmentin"
    assert any(row["field_path"] == "patient.name" for row in repository.field_rows)


def test_llm_failure_keeps_manual_null_fields_available():
    repository = FakeExtractionRepository()
    result = asyncio.run(
        ExtractionService(repository, FakeLLM(fail=True)).extract(
            {
                "id": str(PRESCRIPTION_ID),
                "organization_id": str(ORG_ID),
                "schema_id": str(SCHEMA_ID),
            }
        )
    )
    assert result["status"] == "LLM_FAILED"
    assert repository.runs[0]["error_code"] == "LLM_FAILED"
    assert any(row["current_value"] is None for row in repository.field_rows)
