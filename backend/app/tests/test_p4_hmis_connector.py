import asyncio
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.integrations.medikunj import MedikunjMapper
from app.services.integrations.medikunj_supabase import MedikunjSupabaseConnector
from app.services.integrations.pipeline import HMISDispatchService
from app.services.integrations.unconfigured import UnconfiguredHMISConnector
from app.tests.test_p2_dynamic_review import (
    ALTERNATE_SCHEMA,
    GENERAL_SCHEMA,
    ORG_ID,
    PRESCRIPTION_ID,
    SCHEMA_ID,
)

APPROVED_PAYLOAD = {
    "contract_version": "1.0",
    "prescription_id": str(PRESCRIPTION_ID),
    "organization_id": str(ORG_ID),
    "schema": {"id": str(SCHEMA_ID), "version": 1},
    "approved_version": 2,
    "approved_at": "2026-08-12T10:00:00Z",
    "data": {
        "patient": {"name": "Rahul Sharma", "age": 41},
        "medicines": [
            {
                "medicine_name": "Augmentin",
                "strength": "625 mg",
                "frequency": "1-0-1",
                "duration": "5 days",
            }
        ],
        "advice": "Review after five days.",
    },
}


class StubRepository:
    def __init__(self, version=None, prescription=None, definition=None):
        self.version = version
        self.prescription = prescription
        self.definition = definition
        self.membership_calls = []

    async def prescription_for_user(self, prescription_id):
        return self.prescription

    async def approved_version(self, prescription_id):
        return self.version

    async def schema_for_user(self, schema_id):
        return {"id": str(schema_id), "definition": self.definition} if self.definition else None

    async def assert_membership(self, user_id, organization_id, roles=None):
        self.membership_calls.append((user_id, organization_id, roles))
        return {"role": "reviewer"}


def approved_repository(definition=GENERAL_SCHEMA):
    return StubRepository(
        version={
            "schema_id": str(SCHEMA_ID),
            "schema_version": 1,
            "version": 2,
            "structured_json": APPROVED_PAYLOAD["data"],
        },
        prescription={
            "id": str(PRESCRIPTION_ID),
            "organization_id": str(ORG_ID),
            "approved_at": "2026-08-12T10:00:00Z",
        },
        definition=definition,
    )


def test_mapper_projects_approved_fields_onto_medikunj_columns():
    document = MedikunjMapper().map(APPROVED_PAYLOAD, GENERAL_SCHEMA)
    assert document.source_id == f"pse:{PRESCRIPTION_ID}:v2"
    assert document.patient["full_name"] == "Rahul Sharma"
    assert document.patient["age_at_reg"] == 41
    assert document.patient["source_id"] == document.source_id
    assert document.prescription["notes"] == "Review after five days."
    assert document.prescription_items == [
        {
            "drug_name": "Augmentin",
            "dosage": "625 mg",
            "frequency": "1-0-1",
            "duration": "5 days",
        }
    ]
    assert document.unmapped == []


def test_mapper_reports_uncovered_paths_instead_of_dropping_them():
    payload = {
        **APPROVED_PAYLOAD,
        "data": {**APPROVED_PAYLOAD["data"], "diagnosis": "Acute pharyngitis"},
    }
    document = MedikunjMapper().map(payload, GENERAL_SCHEMA)
    assert "diagnosis" in document.unmapped
    assert document.source_data["data"]["diagnosis"] == "Acute pharyngitis"


def test_mapper_locates_medicine_section_by_schema_type_not_by_name():
    schema = {
        "schema_key": "ward_round",
        "sections": [{"key": "drug_chart", "type": "medicine_list"}],
    }
    payload = {
        **APPROVED_PAYLOAD,
        "data": {"drug_chart": [{"medicine_name": "Pantop", "strength": "40 mg"}]},
    }
    document = MedikunjMapper().map(payload, schema)
    assert document.prescription_items[0]["drug_name"] == "Pantop"


def test_alternate_schema_maps_without_connector_changes():
    payload = {
        **APPROVED_PAYLOAD,
        "data": {"investigations": ["CBC", "CRP"], "follow_up": "2026-09-01"},
    }
    document = MedikunjMapper().map(payload, ALTERNATE_SCHEMA)
    assert document.prescription_items == []
    assert document.unmapped == ["follow_up", "investigations[]"]


def test_mapper_refuses_a_medicine_row_without_a_mappable_drug_name():
    payload = {
        **APPROVED_PAYLOAD,
        "data": {"medicines": [{"strength": "625 mg", "frequency": "1-0-1"}]},
    }
    with pytest.raises(AppError) as error:
        MedikunjMapper().map(payload, GENERAL_SCHEMA)
    assert error.value.code == "HMIS_MEDICINE_UNMAPPABLE"


def test_mapper_rejects_unknown_contract_version():
    with pytest.raises(AppError) as error:
        MedikunjMapper().map({**APPROVED_PAYLOAD, "contract_version": "2.0"}, GENERAL_SCHEMA)
    assert error.value.code == "HMIS_CONTRACT_UNSUPPORTED"


def test_uncoercible_integer_is_reported_rather_than_guessed():
    payload = {
        **APPROVED_PAYLOAD,
        "data": {
            "patient": {"name": "Rahul Sharma", "age": "not recorded"},
            "medicines": APPROVED_PAYLOAD["data"]["medicines"],
        },
    }
    document = MedikunjMapper().map(payload, GENERAL_SCHEMA)
    assert "age_at_reg" not in document.patient
    assert "patient.age:not-coercible" in document.unmapped


def test_dispatch_requires_a_reviewer_approved_version():
    repository = StubRepository(
        version=None, prescription={"id": str(PRESCRIPTION_ID), "organization_id": str(ORG_ID)}
    )
    service = HMISDispatchService(repository, UnconfiguredHMISConnector())  # type: ignore[arg-type]
    with pytest.raises(AppError) as error:
        asyncio.run(service.dispatch(PRESCRIPTION_ID))
    assert error.value.code == "NOT_APPROVED"


def test_unconfigured_destination_fails_gracefully_after_mapping_succeeds():
    service = HMISDispatchService(approved_repository(), UnconfiguredHMISConnector())  # type: ignore[arg-type]
    document = asyncio.run(service.build_document(PRESCRIPTION_ID))
    assert document.prescription_items[0]["drug_name"] == "Augmentin"
    with pytest.raises(AppError) as error:
        asyncio.run(service.dispatch(PRESCRIPTION_ID))
    assert error.value.code == "HMIS_NOT_CONFIGURED"
    assert UnconfiguredHMISConnector().health()["configured"] is False


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.content = b"1"

    def json(self):
        return self._payload


class RecordingClient:
    def __init__(self, script, log):
        self.script = script
        self.log = log

    def __call__(self, timeout, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def request(self, method, url, headers=None, params=None, json=None):
        table = url.rsplit("/", 1)[-1]
        self.log.append((method, table, params, json))
        return self.script.pop(0)


def build_connector(monkeypatch, script, log):
    monkeypatch.setattr(
        "app.services.integrations.medikunj_supabase.httpx.AsyncClient",
        RecordingClient(script, log),
    )
    return MedikunjSupabaseConnector("https://hmis.example.test", "service-key", "branch-1")


def test_configured_connector_writes_patient_prescription_items_and_lineage(monkeypatch):
    log: list = []
    patient_id, prescription_id = str(uuid4()), str(uuid4())
    script = [
        FakeResponse(200, []),  # medimind_id_map lookup
        FakeResponse(200, []),  # patients lookup
        FakeResponse(201, [{"id": patient_id}]),  # patients insert
        FakeResponse(201, [{"id": prescription_id}]),  # prescriptions insert
        FakeResponse(201, [{"id": str(uuid4())}]),  # prescription_items insert
        FakeResponse(201, [{"id": str(uuid4())}]),  # medimind_id_map insert
    ]
    connector = build_connector(monkeypatch, script, log)
    document = MedikunjMapper().map(APPROVED_PAYLOAD, GENERAL_SCHEMA)
    result = asyncio.run(connector.dispatch(document))

    assert result.dispatched is True and result.idempotent is False
    assert result.target_ids == {"prescription": prescription_id, "patient": patient_id}
    tables = [entry[1] for entry in log]
    assert tables == [
        "medimind_id_map",
        "patients",
        "patients",
        "prescriptions",
        "prescription_items",
        "medimind_id_map",
    ]
    prescription_body = log[3][3]
    assert prescription_body["patient_id"] == patient_id
    assert prescription_body["branch_id"] == "branch-1"
    assert log[4][3][0]["prescription_id"] == prescription_id
    assert log[5][3]["source_id"] == document.source_id


def test_replayed_dispatch_is_idempotent_through_the_id_map(monkeypatch):
    log: list = []
    existing = str(uuid4())
    connector = build_connector(monkeypatch, [FakeResponse(200, [{"target_id": existing}])], log)
    document = MedikunjMapper().map(APPROVED_PAYLOAD, GENERAL_SCHEMA)
    result = asyncio.run(connector.dispatch(document))
    assert result.idempotent is True and result.dispatched is False
    assert result.target_ids == {"prescription": existing}
    assert len(log) == 1


def test_connector_retries_transient_destination_failure(monkeypatch):
    log: list = []
    script = [FakeResponse(503, {}), FakeResponse(200, [{"target_id": str(uuid4())}])]
    connector = build_connector(monkeypatch, script, log)
    document = MedikunjMapper().map(APPROVED_PAYLOAD, GENERAL_SCHEMA)
    result = asyncio.run(connector.dispatch(document))
    assert result.idempotent is True
    assert len(log) == 2


def test_connector_surfaces_permanent_destination_rejection(monkeypatch):
    connector = build_connector(monkeypatch, [FakeResponse(400, {})], [])
    document = MedikunjMapper().map(APPROVED_PAYLOAD, GENERAL_SCHEMA)
    with pytest.raises(AppError) as error:
        asyncio.run(connector.dispatch(document))
    assert error.value.code == "HMIS_DISPATCH_FAILED"
    assert error.value.status_code == 502


def wire_approved(repository, definition=GENERAL_SCHEMA):
    stub = approved_repository(definition)
    repository.prescription_for_user = stub.prescription_for_user
    repository.approved_version = stub.approved_version
    repository.schema_for_user = stub.schema_for_user
    return stub


def test_health_endpoint_reports_the_inert_destination(client):
    response = client.get("/api/integrations/hmis/health")
    assert response.status_code == 200
    assert response.json() == {
        "provider": "unconfigured",
        "configured": False,
        "status": "HMIS_NOT_CONFIGURED",
        "branch_scoped": False,
    }


def test_preview_endpoint_returns_mapped_records_without_dispatching(client, repository):
    wire_approved(repository)
    response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/hmis-preview")
    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == f"pse:{PRESCRIPTION_ID}:v2"
    assert body["prescription_items"][0]["drug_name"] == "Augmentin"
    assert body["unmapped"] == []


def test_dispatch_endpoint_is_blocked_until_a_destination_is_configured(client, repository):
    wire_approved(repository)
    response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/hmis-dispatch")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "HMIS_NOT_CONFIGURED"


def test_dispatch_endpoint_rejects_unapproved_prescriptions(client, repository):
    async def prescription_for_user(_prescription_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(ORG_ID)}

    async def no_version(_prescription_id):
        return None

    repository.prescription_for_user = prescription_for_user
    repository.approved_version = no_version
    response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/hmis-dispatch")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_APPROVED"


def test_dispatch_endpoint_enforces_organization_membership(client, repository):
    async def foreign_prescription(_prescription_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(uuid4())}

    repository.prescription_for_user = foreign_prescription
    response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/hmis-dispatch")
    assert response.status_code == 403


def test_hmis_settings_default_to_inert_and_never_leak_the_key():
    settings = Settings(hmis_provider="", hmis_base_url="", hmis_service_key="")
    assert settings.hmis_configured is False
    configured = Settings(
        hmis_provider="medikunj_supabase",
        hmis_base_url="https://hmis.example.test",
        hmis_service_key="super-secret-hmis-key",
    )
    assert configured.hmis_configured is True
    assert "super-secret-hmis-key" not in repr(configured)
    assert "super-secret-hmis-key" not in str(
        MedikunjSupabaseConnector(
            configured.hmis_base_url, configured.hmis_service_key.get_secret_value()
        ).health()
    )
