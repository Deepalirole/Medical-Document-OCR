from uuid import uuid4

from app.services.schema.detection import SchemaDetector
from app.tests.conftest import ORG_ID
from app.tests.test_p2_dynamic_review import PRESCRIPTION_ID

OPD_ID = str(uuid4())
DENTAL_ID = str(uuid4())
LAB_ID = str(uuid4())

OPD = {
    "id": OPD_ID,
    "organization_id": str(ORG_ID),
    "schema_key": "general_opd",
    "name": "General OPD",
    "version": 2,
    "is_active": True,
    "definition": {
        "sections": [
            {
                "key": "patient",
                "type": "object",
                "fields": [
                    {"key": "name", "type": "string"},
                    {"key": "age", "type": "string"},
                ],
            },
            {
                "key": "medicines",
                "type": "medicine_list",
                "item_schema": {
                    "medicine_name": {"type": "string"},
                    "strength": {"type": "string"},
                    "frequency": {"type": "string"},
                },
            },
        ]
    },
}

DENTAL = {
    "id": DENTAL_ID,
    "organization_id": str(ORG_ID),
    "schema_key": "dental",
    "name": "Dental Chart",
    "version": 1,
    "is_active": False,
    "definition": {
        "sections": [
            {
                "key": "dentition",
                "type": "object",
                "label": "Dentition Chart",
                "fields": [
                    {"key": "quadrant", "type": "string", "aliases": ["occlusion"]},
                    {
                        "key": "procedure",
                        "type": "enum",
                        "options": ["scaling", "extraction", "root canal"],
                    },
                ],
            }
        ]
    },
}

LAB = {
    "id": LAB_ID,
    "organization_id": str(ORG_ID),
    "schema_key": "lab_panel",
    "name": "Lab Panel",
    "version": 1,
    "is_active": False,
    "definition": {
        "sections": [
            {"key": "investigations", "type": "array", "item_schema": {"type": "string"}},
            {
                "key": "specimen",
                "type": "enum",
                "options": ["serum", "plasma", "urine"],
            },
        ]
    },
}

ALL_SCHEMAS = [OPD, DENTAL, LAB]

OPD_TEXT = "Patient name Rahul age 41 medicines medicine_name Augmentin strength 625 frequency"
DENTAL_TEXT = "Dentition chart quadrant occlusion procedure root canal and extraction performed"


def test_the_matching_schema_is_ranked_first_and_suggested():
    report = SchemaDetector().detect(OPD_TEXT, ALL_SCHEMAS)
    assert report.candidates[0].schema_key == "general_opd"
    assert report.suggested_schema_id == OPD_ID
    assert report.confident is True
    assert report.reason == "CONFIDENT"


def test_a_different_document_selects_a_different_schema():
    report = SchemaDetector().detect(DENTAL_TEXT, ALL_SCHEMAS)
    assert report.candidates[0].schema_key == "dental"
    assert report.suggested_schema_id == DENTAL_ID


def test_enum_options_and_aliases_count_as_document_vocabulary():
    report = SchemaDetector().detect(DENTAL_TEXT, [DENTAL])
    matched = report.candidates[0].matched_terms
    assert "occlusion" in matched
    assert "root canal" in matched
    assert "extraction" in matched


def test_low_signal_text_suggests_nothing():
    report = SchemaDetector().detect("illegible smudge xxxx", ALL_SCHEMAS)
    assert report.suggested_schema_id is None
    assert report.confident is False
    assert report.reason == "LOW_SIGNAL"


def test_ambiguous_documents_refuse_to_pick_a_winner():
    twin = {**DENTAL, "id": str(uuid4()), "schema_key": "dental_copy"}
    report = SchemaDetector().detect(DENTAL_TEXT, [DENTAL, twin])
    assert report.reason == "AMBIGUOUS"
    assert report.suggested_schema_id is None
    assert report.confident is False
    assert report.margin == 0.0


def test_empty_ocr_text_is_reported_distinctly_from_low_signal():
    report = SchemaDetector().detect("   ", ALL_SCHEMAS)
    assert report.reason == "NO_OCR_TEXT"
    assert report.suggested_schema_id is None
    assert len(report.candidates) == 3


def test_no_schemas_is_reported_distinctly():
    report = SchemaDetector().detect(OPD_TEXT, [])
    assert report.reason == "NO_SCHEMAS"
    assert report.candidates == []


def test_schemas_without_a_definition_are_skipped():
    report = SchemaDetector().detect(OPD_TEXT, [{"id": "x", "schema_key": "broken"}, OPD])
    assert [candidate.schema_key for candidate in report.candidates] == ["general_opd"]


def test_detection_never_mutates_the_supplied_schemas():
    before = [dict(schema) for schema in ALL_SCHEMAS]
    SchemaDetector().detect(OPD_TEXT, ALL_SCHEMAS)
    assert ALL_SCHEMAS == before


def test_report_always_states_that_a_reviewer_must_confirm():
    payload = SchemaDetector().detect(OPD_TEXT, ALL_SCHEMAS).to_dict()
    assert payload["requires_reviewer_confirmation"] is True
    assert payload["candidates"][0]["score"] > payload["candidates"][1]["score"]


def test_thresholds_are_tunable():
    partial = "patient name Rahul"
    assert SchemaDetector().detect(partial, [OPD]).reason == "CONFIDENT"
    assert SchemaDetector(min_score=0.99).detect(partial, [OPD]).reason == "LOW_SIGNAL"
    # A margin requirement above the 1.0 maximum can never be met, so nothing is suggested.
    assert SchemaDetector(min_margin=1.01).detect(OPD_TEXT, ALL_SCHEMAS).reason == "AMBIGUOUS"


def test_very_short_tokens_are_not_treated_as_signals():
    schema = {
        "id": "s",
        "schema_key": "tiny",
        "name": "Tiny",
        "version": 1,
        "definition": {
            "sections": [{"key": "ab", "type": "string"}, {"key": "note", "type": "string"}]
        },
    }
    report = SchemaDetector().detect("ab ab ab", [schema])
    assert report.candidates[0].total_terms == 1
    assert report.candidates[0].matched_terms == []


# --- API -----------------------------------------------------------------------------


class FakeProcessingRepository:
    def __init__(self, rows):
        self.rows = rows
        self.include_tokens: bool | None = None

    async def ocr_results(self, prescription_id, include_tokens=True):
        self.include_tokens = include_tokens
        return self.rows


def wire(repository, schemas=ALL_SCHEMAS, schema_id=None):
    async def prescription_for_user(_id):
        return {
            "id": str(PRESCRIPTION_ID),
            "organization_id": str(ORG_ID),
            "schema_id": schema_id,
        }

    async def schemas_for_user(_user_id):
        return schemas

    repository.prescription_for_user = prescription_for_user
    repository.schemas_for_user = schemas_for_user


def call_endpoint(client, rows):
    from app.api.dependencies import get_processing_repository
    from app.main import app

    processing = FakeProcessingRepository(rows)
    app.dependency_overrides[get_processing_repository] = lambda: processing
    try:
        return client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/schema-suggestions"), processing
    finally:
        app.dependency_overrides.pop(get_processing_repository, None)


def test_endpoint_ranks_schemas_from_persisted_ocr_text(client, repository):
    wire(repository, schema_id=DENTAL_ID)
    response, processing = call_endpoint(client, [{"raw_text": OPD_TEXT}])

    assert response.status_code == 200
    body = response.json()
    assert body["suggested_schema_id"] == OPD_ID
    assert body["active_schema_id"] == DENTAL_ID
    assert body["requires_reviewer_confirmation"] is True
    assert body["candidates"][0]["schema_key"] == "general_opd"
    assert processing.include_tokens is False


def test_endpoint_concatenates_multi_page_ocr_text(client, repository):
    wire(repository)
    response, _ = call_endpoint(
        client, [{"raw_text": "Dentition chart quadrant"}, {"raw_text": "occlusion root canal"}]
    )
    assert response.json()["candidates"][0]["schema_key"] == "dental"


def test_endpoint_reports_no_ocr_text_without_failing(client, repository):
    wire(repository)
    response, _ = call_endpoint(client, [])
    assert response.status_code == 200
    assert response.json()["reason"] == "NO_OCR_TEXT"
    assert response.json()["suggested_schema_id"] is None


def test_endpoint_only_considers_schemas_from_the_same_organization(client, repository):
    foreign = {**OPD, "id": str(uuid4()), "organization_id": str(uuid4())}
    wire(repository, schemas=[foreign, DENTAL])
    response, _ = call_endpoint(client, [{"raw_text": OPD_TEXT}])
    keys = [candidate["schema_key"] for candidate in response.json()["candidates"]]
    assert keys == ["dental"]


def test_endpoint_is_404_for_an_unknown_prescription(client, repository):
    async def missing(_id):
        return None

    repository.prescription_for_user = missing
    response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/schema-suggestions")
    assert response.status_code == 404


def test_endpoint_enforces_membership(client, repository):
    async def foreign(_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(uuid4())}

    repository.prescription_for_user = foreign
    response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/schema-suggestions")
    assert response.status_code == 403
