from pydantic import BaseModel, Field


class ApprovalStageModel(BaseModel):
    key: str
    name: str
    role: str
    order: int


class ApprovalStepResponse(BaseModel):
    stage_key: str
    stage_order: int
    created_at: str | None = None


class ApprovalStepRequest(BaseModel):
    stage_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    notes: str | None = Field(default=None, max_length=500)


class ApprovalStatusResponse(BaseModel):
    prescription_id: str
    stages: list[ApprovalStageModel]
    completed_keys: list[str]
    next_stage: ApprovalStageModel | None = None
    can_finalize: bool
    require_distinct_reviewers: bool
    blocked_reason: str
    is_multi_stage: bool
    signed_steps: list[ApprovalStepResponse]
