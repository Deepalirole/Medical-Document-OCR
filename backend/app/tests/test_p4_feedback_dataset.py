import json
from uuid import uuid4

from app.services.feedback.dataset import FeedbackDatasetBuilder
from app.tests.conftest import ORG_ID

P1 = str(uuid4())
P2 = str(uuid4())
SCHEMA = str(uuid4())

PRESCRIPTIONS = [{"id": P1}, {"id": P2}]

APPROVED = {
    P1: {
        "schema_id": SCHEMA,
        "schema_version": 2,
        "version": 1,
        "structured_json": {"patient": {"name": "Rahul Sharma"}},
    }
}

FIELDS = {
    P1: [
        {
            "id": "field-1",
            "field_path": "patient.name",
            "field_type": "string",
            "original_value": "Rahu1 Sharma",
            "current_value": "Rahul Sharma",
            "review_status": "REVIEW_REQUIRED",
            "confidence": 0.62,
            "evidence": [
                {
                    "text": "Rahu1",
                    "page": 1,
                    "bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
                    "source": "ocr_token",
                    "engine": "tesseract",
                    "confidence": 0.61,
                    "prescription_id": P1,
                    "page_id": "page-secret",
                }
            ],
        },
        {
            "id": "field-2",
            "field_path": "medicines[0].medicine_name",
            "field_type": "string",
            "original_value": "Augmentin",
            "current_value": "Augmentin",
            "review_status": "HIGH",
            "confidence": 0.98,
            "evidence": [],
        },
    ]
}

CORRECTIONS = {
    "field-1": [
        {"id": "c1", "prescription_field_id": "field-1", "created_at": "2026-08-14T09:00:00Z"}
    ]
}


def build(**kwargs):
    return FeedbackDatasetBuilder(**kwargs).build(
        PRESCRIPTIONS, APPROVED, FIELDS, CORRECTIONS
    )


def test_only_approved_prescriptions_are_exported():
    dataset = build()
    assert dataset.prescriptions_considered == 2
    assert dataset.prescriptions_exported == 1
    assert dataset.prescriptions_skipped_unapproved == 1
    assert {example.prescription_id for example in dataset.examples} == {P1}


def test_examples_pair_the_proposed_value_with_the_approved_value():
    example = build().examples[0]
    assert example.proposed_value == "Rahu1 Sharma"
    assert example.approved_value == "Rahul Sharma"
    assert example.corrected is True
    assert example.correction_count == 1
    assert example.schema_version == 2
    assert example.approved_version == 1


def test_an_untouched_field_is_exported_as_not_corrected():
    example = build().examples[1]
    assert example.corrected is False
    assert example.correction_count == 0
    assert example.proposed_value == example.approved_value


def test_a_value_changed_without_a_correction_row_still_counts_as_corrected():
    fields = {
        P1: [
            {
                "id": "f",
                "field_path": "patient.age",
                "field_type": "number",
                "original_value": None,
                "current_value": 41,
                "review_status": "REVIEW_REQUIRED",
            }
        ]
    }
    dataset = FeedbackDatasetBuilder().build(PRESCRIPTIONS, APPROVED, fields, {})
    assert dataset.examples[0].corrected is True
    assert dataset.examples[0].correction_count == 0


def test_correction_rate_is_reported():
    dataset = build()
    assert dataset.corrected_count == 1
    assert dataset.correction_rate == 0.5


def test_evidence_is_projected_without_internal_identifiers():
    evidence = build().examples[0].evidence[0]
    assert evidence["text"] == "Rahu1"
    assert evidence["engine"] == "tesseract"
    assert "page_id" not in evidence
    assert "prescription_id" not in evidence


def test_evidence_can_be_excluded_entirely():
    dataset = build(include_evidence=False)
    assert all(example.evidence == [] for example in dataset.examples)


def test_reviewer_identity_never_reaches_the_dataset():
    payload = json.dumps(build().to_dict())
    assert "corrected_by" not in payload
    assert "reason" not in payload


def test_an_approved_version_without_a_snapshot_is_skipped():
    dataset = FeedbackDatasetBuilder().build(
        PRESCRIPTIONS, {P1: {"schema_id": SCHEMA, "structured_json": None}}, FIELDS, {}
    )
    assert dataset.prescriptions_exported == 0
    assert dataset.prescriptions_skipped_unapproved == 2
    assert dataset.examples == []


def test_jsonl_export_is_one_valid_object_per_line():
    lines = build().to_jsonl().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["field_path"] == "patient.name"
    assert parsed[0]["corrected"] is True


def test_empty_input_produces_an_empty_dataset():
    dataset = FeedbackDatasetBuilder().build([], {}, {}, {})
    assert dataset.examples == []
    assert dataset.correction_rate == 0.0
    assert dataset.to_jsonl() == ""


# --- API -----------------------------------------------------------------------------


def wire(repository, roles_ok=True):
    async def list_prescriptions(_org, _limit, _before):
        return PRESCRIPTIONS

    async def approved_version(prescription_id):
        return APPROVED.get(str(prescription_id))

    async def fields_for_user(prescription_id):
        return FIELDS.get(str(prescription_id), [])

    async def corrections_for_prescriptions(prescription_ids):
        assert [str(p) for p in prescription_ids] == [P1]
        return CORRECTIONS["field-1"]

    async def assert_membership(user_id, organization_id, roles=None):
        from app.core.errors import AppError

        if not roles_ok or roles != {"admin"}:
            raise AppError("AUTHORIZATION_FAILED", "Admin access required.", 403)
        return {"role": "admin"}

    repository.list_prescriptions = list_prescriptions
    repository.approved_version = approved_version
    repository.fields_for_user = fields_for_user
    repository.corrections_for_prescriptions = corrections_for_prescriptions
    repository.assert_membership = assert_membership


def test_endpoint_returns_the_dataset_for_an_admin(client, repository):
    wire(repository)
    response = client.get(f"/api/organizations/{ORG_ID}/feedback-dataset")
    assert response.status_code == 200
    body = response.json()
    assert body["prescriptions_exported"] == 1
    assert body["prescriptions_skipped_unapproved"] == 1
    assert body["example_count"] == 2
    assert body["corrected_count"] == 1
    assert body["examples"][0]["approved_value"] == "Rahul Sharma"


def test_endpoint_requires_admin_membership(client, repository):
    wire(repository, roles_ok=False)
    response = client.get(f"/api/organizations/{ORG_ID}/feedback-dataset")
    assert response.status_code == 403


def test_jsonl_endpoint_streams_ndjson(client, repository):
    wire(repository)
    response = client.get(f"/api/organizations/{ORG_ID}/feedback-dataset.jsonl")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = response.text.splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["prescription_id"] == P1


def test_evidence_can_be_dropped_through_the_query_parameter(client, repository):
    wire(repository)
    response = client.get(
        f"/api/organizations/{ORG_ID}/feedback-dataset", params={"include_evidence": "false"}
    )
    assert all(example["evidence"] == [] for example in response.json()["examples"])
