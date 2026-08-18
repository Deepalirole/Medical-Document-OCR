"""Production EMR connector (FHIR R4).

Consumes the same :class:`~app.services.integrations.base.HMISDocument` the HMIS connector
does, so an approved prescription reaches an EMR through the identical approved-only path and
mapping — only the transport and resource shape differ.

Idempotency uses FHIR's own conditional-create (``ifNoneExist``) keyed on the deterministic
``source_id`` identifier, so replaying an approved version resolves to the existing resources
on the server rather than creating duplicate clinical records.
"""

from typing import Any

import httpx

from app.core.errors import AppError
from app.services.integrations.base import HMISDispatchResult, HMISDocument

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
SOURCE_SYSTEM = "https://prescription-evidence-studio/source-id"
FHIR_JSON = "application/fhir+json"


class FHIREMRConnector:
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout_seconds: int = 30,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    @property
    def name(self) -> str:
        return "fhir_emr"

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def health(self) -> dict[str, str | bool]:
        return {
            "provider": self.name,
            "configured": self.configured,
            "authenticated": bool(self.api_key),
            "status": "EMR_READY" if self.configured else "EMR_NOT_CONFIGURED",
        }

    async def dispatch(self, document: HMISDocument) -> HMISDispatchResult:
        if not self.configured:
            raise AppError(
                "EMR_NOT_CONFIGURED",
                "The FHIR EMR destination has no base URL configured.",
                503,
            )
        bundle = self.build_bundle(document)
        response = await self._post(bundle)
        locations = self._locations(response)
        return HMISDispatchResult(
            connector=self.name,
            dispatched=True,
            idempotent=self._all_matched(response),
            source_id=document.source_id,
            item_count=len(document.prescription_items),
            target_ids=locations,
        )

    def build_bundle(self, document: HMISDocument) -> dict[str, Any]:
        patient_uuid = f"urn:uuid:patient-{document.prescription_id}"
        identifier = {"system": SOURCE_SYSTEM, "value": document.source_id}
        entries: list[dict[str, Any]] = [
            {
                "fullUrl": patient_uuid,
                "resource": self._patient(document, identifier),
                "request": {
                    "method": "POST",
                    "url": "Patient",
                    "ifNoneExist": f"identifier={SOURCE_SYSTEM}|{document.source_id}",
                },
            }
        ]
        for index, item in enumerate(document.prescription_items):
            entries.append(
                {
                    "fullUrl": f"urn:uuid:medreq-{document.prescription_id}-{index}",
                    "resource": self._medication_request(
                        item, patient_uuid, identifier, index
                    ),
                    "request": {
                        "method": "POST",
                        "url": "MedicationRequest",
                        "ifNoneExist": (
                            f"identifier={SOURCE_SYSTEM}|{document.source_id}:{index}"
                        ),
                    },
                }
            )
        return {"resourceType": "Bundle", "type": "transaction", "entry": entries}

    @staticmethod
    def _patient(document: HMISDocument, identifier: dict[str, str]) -> dict[str, Any]:
        patient = document.patient
        resource: dict[str, Any] = {
            "resourceType": "Patient",
            "identifier": [identifier],
        }
        name = patient.get("full_name")
        if name:
            resource["name"] = [{"text": str(name)}]
        gender = str(patient.get("gender", "")).lower()
        if gender in {"male", "female", "other", "unknown"}:
            resource["gender"] = gender
        mobile = patient.get("mobile_number")
        if mobile:
            resource["telecom"] = [{"system": "phone", "value": str(mobile)}]
        address = patient.get("address")
        if address:
            resource["address"] = [{"text": str(address)}]
        return resource

    @staticmethod
    def _medication_request(
        item: dict[str, Any],
        patient_reference: str,
        identifier: dict[str, str],
        index: int,
    ) -> dict[str, Any]:
        dosage: dict[str, Any] = {}
        text_parts = [
            str(item[key])
            for key in ("dosage", "frequency", "duration", "instructions")
            if item.get(key)
        ]
        if text_parts:
            dosage["text"] = " ".join(text_parts)
        resource: dict[str, Any] = {
            "resourceType": "MedicationRequest",
            "identifier": [
                {"system": identifier["system"], "value": f"{identifier['value']}:{index}"}
            ],
            "status": "active",
            "intent": "order",
            "subject": {"reference": patient_reference},
            "medicationCodeableConcept": {"text": str(item.get("drug_name", ""))},
        }
        if dosage:
            resource["dosageInstruction"] = [dosage]
        quantity = item.get("quantity")
        if isinstance(quantity, int):
            resource["dispenseRequest"] = {"quantity": {"value": quantity}}
        return resource

    async def _post(self, bundle: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": FHIR_JSON, "Accept": FHIR_JSON}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, trust_env=False
                ) as client:
                    response = await client.post(self.base_url, headers=headers, json=bundle)
                if response.status_code in TRANSIENT_STATUSES and attempt < self.retries:
                    continue
                if response.status_code >= 400:
                    raise AppError(
                        "EMR_DISPATCH_FAILED",
                        "The FHIR EMR rejected the approved prescription.",
                        502,
                        {"status": response.status_code},
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise AppError(
                        "EMR_DISPATCH_FAILED", "The FHIR EMR returned an unexpected body.", 502
                    )
                self._raise_on_operation_outcome(payload)
                return payload
            except AppError:
                raise
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt < self.retries:
                    continue
        raise AppError(
            "EMR_DISPATCH_FAILED", "The FHIR EMR could not be reached.", 502
        ) from last_error

    @staticmethod
    def _raise_on_operation_outcome(payload: dict[str, Any]) -> None:
        """A 200 carrying an OperationOutcome is still a rejection."""
        if payload.get("resourceType") != "OperationOutcome":
            return
        issues = payload.get("issue") or []
        severities = {str(issue.get("severity", "")).lower() for issue in issues}
        if severities & {"error", "fatal"}:
            raise AppError(
                "EMR_DISPATCH_FAILED",
                "The FHIR EMR returned an error outcome for the bundle.",
                502,
            )

    @staticmethod
    def _locations(payload: dict[str, Any]) -> dict[str, str]:
        located: dict[str, str] = {}
        medication_index = 0
        for entry in payload.get("entry") or []:
            location = str((entry.get("response") or {}).get("location", ""))
            if not location:
                continue
            if location.startswith("Patient"):
                located["patient"] = location
            elif location.startswith("MedicationRequest"):
                located[f"medication_request_{medication_index}"] = location
                medication_index += 1
        return located

    @staticmethod
    def _all_matched(payload: dict[str, Any]) -> bool:
        """True when every entry resolved to an existing resource (HTTP 200, not 201)."""
        entries = payload.get("entry") or []
        if not entries:
            return False
        statuses = [
            str((entry.get("response") or {}).get("status", "")) for entry in entries
        ]
        return all(status.startswith("200") for status in statuses)


