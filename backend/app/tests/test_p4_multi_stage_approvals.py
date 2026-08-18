from pathlib import Path
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.services.approvals.workflow import DEFAULT_STAGES, ApprovalWorkflow
from app.tests.conftest import ORG_ID, USER_ID
from app.tests.test_p2_dynamic_review import PRESCRIPTION_ID, SCHEMA_ID

ROOT = Path(__file__).parents[3]
OTHER_USER = str(uuid4())

TWO_STAGE = {
    "stages": [
        {"key": "reviewer", "name": "Transcription review", "role": "reviewer", "order": 1},
        {"key": "clinician", "name": "Clinical sign-off", "role": "admin", "order": 2},
    ]
}


def step(stage_key, order, user=str(USER_ID)):
    return {"stage_key": stage_key, "stage_order": order, "approved_by": user}


def test_no_configuration_yields_the_previous_single_reviewer_behaviour():
    workflow = ApprovalWorkflow.from_config(None)
    assert workflow.is_multi_stage is False
    assert [stage.key for stage in workflow.stages] == ["reviewer"]
    assert workflow.stages[0].to_dict() == DEFAULT_STAGES[0]
    assert workflow.require_distinct_reviewers is False


def test_an_empty_stage_list_also_falls_back_to_the_default():
    assert ApprovalWorkflow.from_config({"stages": []}).is_multi_stage is False


def test_stages_are_ordered_by_their_declared_order():
    workflow = ApprovalWorkflow.from_config(
        {"stages": [{"key": "second", "order": 2}, {"key": "first", "order": 1}]}
    )
    assert [stage.key for stage in workflow.stages] == ["first", "second"]


def test_duplicate_and_malformed_stages_are_rejected():
    for stages in (
        [{"key": "a"}, {"key": "a"}],
        [{"key": "bad key"}],
        ["not-an-object"],
        [{"name": "no key"}],
    ):
        with pytest.raises(AppError) as error:
            ApprovalWorkflow.from_config({"stages": stages})
        assert error.value.code == "APPROVAL_WORKFLOW_INVALID"


def test_finalisation_is_blocked_until_every_stage_is_signed():
    workflow = ApprovalWorkflow.from_config(TWO_STAGE)
    empty = workflow.progress([])
    assert empty.can_finalize is False
    assert empty.next_stage.key == "reviewer"
    assert empty.blocked_reason == "AWAITING_REVIEWER"

    partial = workflow.progress([step("reviewer", 1)])
    assert partial.can_finalize is False
    assert partial.completed_keys == ["reviewer"]
    assert partial.next_stage.key == "clinician"

    complete = workflow.progress([step("reviewer", 1), step("clinician", 2, OTHER_USER)])
    assert complete.can_finalize is True
    assert complete.next_stage is None
    assert complete.blocked_reason == ""


def test_a_later_stage_signed_first_does_not_advance_the_workflow():
    progress = ApprovalWorkflow.from_config(TWO_STAGE).progress([step("clinician", 2)])
    assert progress.completed_keys == []
    assert progress.can_finalize is False
    assert progress.next_stage.key == "reviewer"


def test_out_of_order_sign_off_is_refused():
    workflow = ApprovalWorkflow.from_config(TWO_STAGE)
    with pytest.raises(AppError) as error:
        workflow.assert_can_sign("clinician", str(USER_ID), "admin", [])
    assert error.value.code == "APPROVAL_STAGE_OUT_OF_ORDER"
    assert error.value.details["expected_stage"] == "reviewer"


def test_signing_the_same_stage_twice_is_refused():
    workflow = ApprovalWorkflow.from_config(TWO_STAGE)
    with pytest.raises(AppError) as error:
        workflow.assert_can_sign("reviewer", OTHER_USER, "reviewer", [step("reviewer", 1)])
    assert error.value.code == "APPROVAL_STAGE_ALREADY_SIGNED"


def test_an_unknown_stage_is_refused():
    with pytest.raises(AppError) as error:
        ApprovalWorkflow.from_config(TWO_STAGE).assert_can_sign("nope", str(USER_ID), "admin", [])
    assert error.value.code == "APPROVAL_STAGE_UNKNOWN"
    assert error.value.details["known_stages"] == ["reviewer", "clinician"]


def test_a_stage_role_is_enforced():
    workflow = ApprovalWorkflow.from_config(TWO_STAGE)
    with pytest.raises(AppError) as error:
        workflow.assert_can_sign("reviewer", str(USER_ID), "viewer", [])
    assert error.value.code == "APPROVAL_ROLE_REQUIRED"
    assert workflow.assert_can_sign("reviewer", str(USER_ID), "reviewer", []).key == "reviewer"


def test_an_admin_may_sign_any_stage():
    workflow = ApprovalWorkflow.from_config(TWO_STAGE)
    assert workflow.assert_can_sign("reviewer", str(USER_ID), "admin", []).key == "reviewer"


def test_multi_stage_requires_a_second_pair_of_eyes_by_default():
    workflow = ApprovalWorkflow.from_config(TWO_STAGE)
    assert workflow.require_distinct_reviewers is True
    with pytest.raises(AppError) as error:
        workflow.assert_can_sign("clinician", str(USER_ID), "admin", [step("reviewer", 1)])
    assert error.value.code == "APPROVAL_DISTINCT_REVIEWER_REQUIRED"
    assert workflow.assert_can_sign(
        "clinician", OTHER_USER, "admin", [step("reviewer", 1)]
    ).key == "clinician"


def test_distinct_reviewers_can_be_disabled_explicitly():
    workflow = ApprovalWorkflow.from_config(
        {**TWO_STAGE, "require_distinct_reviewers": False}
    )
    assert workflow.assert_can_sign(
        "clinician", str(USER_ID), "admin", [step("reviewer", 1)]
    ).key == "clinician"


def test_migration_creates_append_only_stage_tables():
    sql = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    )
    assert "prescription_approval_steps" in sql
    assert "approval_workflows" in sql
    assert "unique (prescription_id, stage_key)" in sql
    assert "approval_steps_member_insert" in sql
    assert "enable row level security" in sql


# --- API -----------------------------------------------------------------------------


def wire(repository, workflow_config=None, steps=None, role="reviewer"):
    state = {"steps": list(steps or []), "recorded": []}

    async def prescription_for_user(_id):
        return {
            "id": str(PRESCRIPTION_ID),
            "organization_id": str(ORG_ID),
            "schema_id": str(SCHEMA_ID),
        }

    async def assert_membership(user_id, organization_id, roles=None):
        from app.core.errors import AppError as Err

        if organization_id != ORG_ID:
            raise Err("AUTHORIZATION_FAILED", "denied", 403)
        return {"role": role}

    async def approval_workflow(_org):
        return workflow_config

    async def approval_steps(_prescription_id):
        return state["steps"]

    async def record_approval_step(data):
        state["recorded"].append(data)
        state["steps"].append(data)
        return data

    repository.prescription_for_user = prescription_for_user
    repository.assert_membership = assert_membership
    repository.approval_workflow = approval_workflow
    repository.approval_steps = approval_steps
    repository.record_approval_step = record_approval_step
    return state


def test_status_endpoint_reports_the_default_single_stage(client, repository):
    wire(repository)
    body = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/approval-status").json()
    assert body["is_multi_stage"] is False
    assert body["can_finalize"] is False
    assert body["next_stage"]["key"] == "reviewer"


def test_signing_a_stage_advances_the_status(client, repository):
    state = wire(repository, TWO_STAGE, role="admin")
    response = client.post(
        f"/api/prescriptions/{PRESCRIPTION_ID}/approval-steps",
        json={"stage_key": "reviewer", "notes": "transcription checked"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["completed_keys"] == ["reviewer"]
    assert body["next_stage"]["key"] == "clinician"
    assert body["can_finalize"] is False
    assert state["recorded"][0]["approved_by"] == str(USER_ID)
    assert state["recorded"][0]["stage_order"] == 1


def test_out_of_order_sign_off_is_rejected_by_the_endpoint(client, repository):
    wire(repository, TWO_STAGE, role="admin")
    response = client.post(
        f"/api/prescriptions/{PRESCRIPTION_ID}/approval-steps",
        json={"stage_key": "clinician"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_STAGE_OUT_OF_ORDER"


def test_the_same_reviewer_cannot_complete_both_stages(client, repository):
    wire(repository, TWO_STAGE, steps=[step("reviewer", 1)], role="admin")
    response = client.post(
        f"/api/prescriptions/{PRESCRIPTION_ID}/approval-steps",
        json={"stage_key": "clinician"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "APPROVAL_DISTINCT_REVIEWER_REQUIRED"


def test_status_endpoint_enforces_membership(client, repository):
    async def foreign(_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(uuid4())}

    wire(repository)
    repository.prescription_for_user = foreign
    response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/approval-status")
    assert response.status_code == 403


def wire_approvable(repository, workflow_config=None, steps=None):
    state = wire(repository, workflow_config, steps, role="admin")

    async def fields_for_user(_id):
        return [
            {
                "id": str(uuid4()),
                "prescription_id": str(PRESCRIPTION_ID),
                "schema_id": str(SCHEMA_ID),
                "field_path": "patient.name",
                "field_type": "string",
                "original_value": "Rahul",
                "current_value": "Rahul",
                "review_status": "HIGH",
                "validation": {},
            }
        ]

    async def schema_for_user(_schema_id):
        return {
            "id": str(SCHEMA_ID),
            "definition": {
                "sections": [
                    {
                        "key": "patient",
                        "type": "object",
                        "fields": [{"key": "name", "type": "string"}],
                    }
                ]
            },
        }

    async def approve_snapshot(prescription_id, snapshot):
        return {
            "id": str(uuid4()),
            "prescription_id": str(prescription_id),
            "schema_id": str(SCHEMA_ID),
            "schema_version": 1,
            "version": 1,
            "structured_json": snapshot,
            "status": "APPROVED",
        }

    repository.fields_for_user = fields_for_user
    repository.schema_for_user = schema_for_user
    repository.approve_snapshot = approve_snapshot
    return state


def test_approval_is_blocked_while_stages_are_outstanding(client, repository):
    wire_approvable(repository, TWO_STAGE)
    response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/approve")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "APPROVAL_STAGES_INCOMPLETE"
    assert error["details"]["next_stage"] == "reviewer"


def test_approval_proceeds_once_every_stage_is_signed(client, repository):
    wire_approvable(
        repository, TWO_STAGE, steps=[step("reviewer", 1), step("clinician", 2, OTHER_USER)]
    )
    response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/approve")
    assert response.status_code == 200
    assert response.json()["structured_json"]["patient"]["name"] == "Rahul"


def test_single_stage_organizations_approve_without_any_sign_off(client, repository):
    wire_approvable(repository, workflow_config=None)
    response = client.post(f"/api/prescriptions/{PRESCRIPTION_ID}/approve")
    assert response.status_code == 200


def test_a_malformed_stage_key_is_rejected_before_reaching_the_workflow(client, repository):
    wire(repository, TWO_STAGE)
    response = client.post(
        f"/api/prescriptions/{PRESCRIPTION_ID}/approval-steps",
        json={"stage_key": "Bad Key"},
    )
    assert response.status_code == 422
