from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import EMRConnectorDep, HMISConnectorDep
from app.core.auth import AuthDep, RepoDep
from app.core.errors import AppError
from app.models.integrations import HMISDispatchResponse, HMISHealth, HMISPreview
from app.services.integrations.pipeline import HMISDispatchService

router = APIRouter(tags=["integrations"])


@router.get("/integrations/hmis/health", response_model=HMISHealth)
async def hmis_health(auth: AuthDep, connector: HMISConnectorDep) -> HMISHealth:
    del auth
    return HMISHealth.model_validate(connector.health())


async def _service(
    prescription_id: UUID, auth: AuthDep, repository: RepoDep, connector: HMISConnectorDep
) -> HMISDispatchService:
    prescription = await repository.prescription_for_user(prescription_id)
    if not prescription:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription not found.", 404)
    await repository.assert_membership(auth.user_id, UUID(str(prescription["organization_id"])))
    return HMISDispatchService(repository, connector)


@router.get("/integrations/emr/health", response_model=HMISHealth)
async def emr_health(auth: AuthDep, connector: EMRConnectorDep) -> HMISHealth:
    del auth
    return HMISHealth.model_validate(connector.health())


@router.post(
    "/prescriptions/{prescription_id}/emr-dispatch", response_model=HMISDispatchResponse
)
async def emr_dispatch(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    connector: EMRConnectorDep,
) -> HMISDispatchResponse:
    service = await _service(prescription_id, auth, repository, connector)
    result = await service.dispatch(prescription_id)
    return HMISDispatchResponse(
        connector=result.connector,
        dispatched=result.dispatched,
        idempotent=result.idempotent,
        source_id=result.source_id,
        item_count=result.item_count,
        target_ids=result.target_ids,
    )


@router.get("/prescriptions/{prescription_id}/hmis-preview", response_model=HMISPreview)
async def hmis_preview(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    connector: HMISConnectorDep,
) -> HMISPreview:
    service = await _service(prescription_id, auth, repository, connector)
    document = await service.build_document(prescription_id)
    return HMISPreview(
        contract_version=document.contract_version,
        source_id=document.source_id,
        prescription_id=document.prescription_id,
        organization_id=document.organization_id,
        approved_version=document.approved_version,
        patient=document.patient,
        prescription=document.prescription,
        prescription_items=document.prescription_items,
        unmapped=document.unmapped,
    )


@router.post(
    "/prescriptions/{prescription_id}/hmis-dispatch", response_model=HMISDispatchResponse
)
async def hmis_dispatch(
    prescription_id: UUID,
    auth: AuthDep,
    repository: RepoDep,
    connector: HMISConnectorDep,
) -> HMISDispatchResponse:
    service = await _service(prescription_id, auth, repository, connector)
    result = await service.dispatch(prescription_id)
    return HMISDispatchResponse(
        connector=result.connector,
        dispatched=result.dispatched,
        idempotent=result.idempotent,
        source_id=result.source_id,
        item_count=result.item_count,
        target_ids=result.target_ids,
    )
