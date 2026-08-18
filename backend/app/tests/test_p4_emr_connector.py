import asyncio

import httpx
import pytest

from app.api.dependencies import get_emr_connector
from app.core.config import Settings
from app.core.errors import AppError
from app.services.integrations.fhir import SOURCE_SYSTEM, FHIREMRConnector
from app.services.integrations.medikunj import MedikunjMapper
from app.tests.test_p2_dynamic_review import GENERAL_SCHEMA
from app.tests.test_p4_hmis_connector import APPROVED_PAYLOAD, approved_repository

DOCUMENT = MedikunjMapper().map(
    {
        **APPROVED_PAYLOAD,
        "data": {
            "patient": {"name": "Rahul Sharma", "age": 41},
            "medicines": [
                {
                    "medicine_name": "Augmentin",
                    "strength": "625 mg",
                    "frequency": "1-0-1",
                    "duration": "5 days",
                },
                {"medicine_name": "Pantoprazole", "strength": "40 mg"},
            ],
        },
    },
    GENERAL_SCHEMA,
)


def created_response(count=2):
    entries = [{"response": {"status": "201 Created", "location": "Patient/p1"}}]
    entries += [
        {"response": {"status": "201 Created", "location": f"MedicationRequest/m{index}"}}
        for index in range(count)
    ]
    return {"resourceType": "Bundle", "type": "transaction-response", "entry": entries}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, invalid=False):
        self.status_code = status_code
        self._payload = payload
        self._invalid = invalid

    def json(self):
        if self._invalid:
            raise ValueError("not json")
        return self._payload


def patch_transport(monkeypatch, script, log):
    class FakeClient:
        def __init__(self, timeout=None, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            log.append({"url": url, "headers": headers or {}, "json": json})
            item = script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr("app.services.integrations.fhir.httpx.AsyncClient", FakeClient)


# --- Bundle construction --------------------------------------------------------------


def test_bundle_is_a_fhir_transaction_with_patient_and_medication_requests():
    bundle = FHIREMRConnector("https://emr.test/fhir").build_bundle(DOCUMENT)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    kinds = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert kinds == ["Patient", "MedicationRequest", "MedicationRequest"]


def test_patient_resource_carries_only_approved_values():
    patient = FHIREMRConnector("https://emr.test/fhir").build_bundle(DOCUMENT)["entry"][0]
    resource = patient["resource"]
    assert resource["name"] == [{"text": "Rahul Sharma"}]
    assert resource["identifier"][0]["value"] == DOCUMENT.source_id
    # No gender, phone or address was approved, so none is invented.
    assert "gender" not in resource
    assert "telecom" not in resource
    assert "address" not in resource


def test_medication_request_maps_dosage_and_links_the_patient():
    bundle = FHIREMRConnector("https://emr.test/fhir").build_bundle(DOCUMENT)
    first = bundle["entry"][1]["resource"]
    assert first["medicationCodeableConcept"]["text"] == "Augmentin"
    assert first["dosageInstruction"][0]["text"] == "625 mg 1-0-1 5 days"
    assert first["subject"]["reference"] == bundle["entry"][0]["fullUrl"]
    assert first["status"] == "active" and first["intent"] == "order"


def test_a_medicine_without_dosage_detail_omits_the_instruction():
    second = FHIREMRConnector("https://emr.test/fhir").build_bundle(DOCUMENT)["entry"][2]
    assert second["resource"]["dosageInstruction"][0]["text"] == "40 mg"


def test_conditional_create_makes_replay_idempotent():
    bundle = FHIREMRConnector("https://emr.test/fhir").build_bundle(DOCUMENT)
    patient_request = bundle["entry"][0]["request"]
    assert patient_request["method"] == "POST"
    assert patient_request["ifNoneExist"] == (
        f"identifier={SOURCE_SYSTEM}|{DOCUMENT.source_id}"
    )
    medication_request = bundle["entry"][1]["request"]
    assert medication_request["ifNoneExist"].endswith(f"{DOCUMENT.source_id}:0")


def test_invalid_gender_values_are_dropped_rather_than_coerced():
    document = MedikunjMapper().map(
        {
            **APPROVED_PAYLOAD,
            "data": {
                "patient": {"name": "A", "gender": "not-a-fhir-code"},
                "medicines": [{"medicine_name": "Augmentin"}],
            },
        },
        GENERAL_SCHEMA,
    )
    resource = FHIREMRConnector("https://emr.test/fhir").build_bundle(document)["entry"][0]
    assert "gender" not in resource["resource"]


# --- Transport -------------------------------------------------------------------------


def test_unconfigured_destination_fails_gracefully():
    connector = FHIREMRConnector("")
    assert connector.health()["status"] == "EMR_NOT_CONFIGURED"
    with pytest.raises(AppError) as error:
        asyncio.run(connector.dispatch(DOCUMENT))
    assert error.value.code == "EMR_NOT_CONFIGURED"
    assert error.value.status_code == 503


def test_successful_dispatch_reports_created_locations(monkeypatch):
    log: list = []
    patch_transport(monkeypatch, [FakeResponse(200, created_response())], log)
    result = asyncio.run(
        FHIREMRConnector("https://emr.test/fhir", "emr-token").dispatch(DOCUMENT)
    )
    assert result.connector == "fhir_emr"
    assert result.dispatched is True
    assert result.idempotent is False
    assert result.item_count == 2
    assert result.target_ids["patient"] == "Patient/p1"
    assert result.target_ids["medication_request_0"] == "MedicationRequest/m0"
    assert log[0]["headers"]["Authorization"] == "Bearer emr-token"
    assert log[0]["headers"]["Content-Type"] == "application/fhir+json"


def test_a_fully_matched_bundle_is_reported_as_idempotent(monkeypatch):
    matched = {
        "resourceType": "Bundle",
        "entry": [
            {"response": {"status": "200 OK", "location": "Patient/p1"}},
            {"response": {"status": "200 OK", "location": "MedicationRequest/m0"}},
            {"response": {"status": "200 OK", "location": "MedicationRequest/m1"}},
        ],
    }
    patch_transport(monkeypatch, [FakeResponse(200, matched)], [])
    result = asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert result.idempotent is True


def test_an_error_operation_outcome_is_a_failure_even_with_http_200(monkeypatch):
    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "diagnostics": "invalid reference"}],
    }
    patch_transport(monkeypatch, [FakeResponse(200, outcome)], [])
    with pytest.raises(AppError) as error:
        asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert error.value.code == "EMR_DISPATCH_FAILED"


def test_a_warning_only_outcome_is_not_treated_as_failure(monkeypatch):
    outcome = {"resourceType": "OperationOutcome", "issue": [{"severity": "warning"}]}
    patch_transport(monkeypatch, [FakeResponse(200, outcome)], [])
    result = asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert result.dispatched is True
    assert result.idempotent is False


def test_permanent_rejection_is_surfaced(monkeypatch):
    patch_transport(monkeypatch, [FakeResponse(422, {})], [])
    with pytest.raises(AppError) as error:
        asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert error.value.details["status"] == 422


def test_transient_failure_is_retried(monkeypatch):
    log: list = []
    patch_transport(
        monkeypatch, [FakeResponse(503, {}), FakeResponse(200, created_response())], log
    )
    result = asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert result.dispatched is True
    assert len(log) == 2


def test_network_failure_after_retries_is_reported(monkeypatch):
    patch_transport(
        monkeypatch,
        [httpx.ConnectError("dns"), httpx.ConnectError("dns"), httpx.ConnectError("dns")],
        [],
    )
    with pytest.raises(AppError) as error:
        asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert error.value.code == "EMR_DISPATCH_FAILED"


def test_a_non_json_body_is_reported_safely(monkeypatch):
    patch_transport(monkeypatch, [FakeResponse(200, None, invalid=True)] * 3, [])
    with pytest.raises(AppError) as error:
        asyncio.run(FHIREMRConnector("https://emr.test/fhir").dispatch(DOCUMENT))
    assert error.value.code == "EMR_DISPATCH_FAILED"


# --- Wiring ----------------------------------------------------------------------------


def test_emr_defaults_to_inert_and_never_leaks_the_key():
    assert Settings().emr_configured is False
    inert = get_emr_connector(Settings())
    assert inert.health()["status"] == "EMR_NOT_CONFIGURED"

    configured = Settings(
        emr_provider="fhir",
        emr_base_url="https://emr.example.test/fhir",
        emr_api_key="super-secret-emr-key",
    )
    assert configured.emr_configured is True
    connector = get_emr_connector(configured)
    assert connector.health()["status"] == "EMR_READY"
    assert "super-secret-emr-key" not in str(connector.health())
    assert "super-secret-emr-key" not in repr(configured)


def test_emr_health_endpoint_reports_the_inert_destination(client):
    response = client.get("/api/integrations/emr/health")
    assert response.status_code == 200
    assert response.json()["provider"] == "fhir_emr"
    assert response.json()["configured"] is False


def test_emr_dispatch_is_approved_only(client, repository):
    async def prescription_for_user(_id):
        return {
            "id": APPROVED_PAYLOAD["prescription_id"],
            "organization_id": APPROVED_PAYLOAD["organization_id"],
        }

    async def no_version(_id):
        return None

    repository.prescription_for_user = prescription_for_user
    repository.approved_version = no_version
    response = client.post(
        f"/api/prescriptions/{APPROVED_PAYLOAD['prescription_id']}/emr-dispatch"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_APPROVED"


def test_emr_dispatch_is_blocked_until_a_destination_is_configured(client, repository):
    stub = approved_repository()
    repository.prescription_for_user = stub.prescription_for_user
    repository.approved_version = stub.approved_version
    repository.schema_for_user = stub.schema_for_user
    response = client.post(
        f"/api/prescriptions/{APPROVED_PAYLOAD['prescription_id']}/emr-dispatch"
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMR_NOT_CONFIGURED"
