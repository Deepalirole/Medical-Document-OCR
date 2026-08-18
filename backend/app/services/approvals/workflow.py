"""Multi-stage approval workflow.

A prescription may need more than one sign-off before its immutable version is cut — typically
a transcription reviewer followed by a clinician. This module decides *whether* finalisation is
allowed; it never writes the snapshot itself.

Defaults matter here: an organization with no configured workflow gets a single reviewer stage,
which is byte-for-byte the behaviour that existed before multi-stage approvals, so no existing
deployment silently gains a blocking gate.

When more than one stage is configured, distinct reviewers are required by default. A second
sign-off by the same person is not a second pair of eyes, and the whole point of the extra stage
is the independent check.
"""

from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError

DEFAULT_STAGES: list[dict[str, Any]] = [
    {"key": "reviewer", "name": "Reviewer sign-off", "role": "reviewer", "order": 1}
]


@dataclass(frozen=True)
class ApprovalStage:
    key: str
    name: str
    role: str
    order: int

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name, "role": self.role, "order": self.order}


@dataclass(frozen=True)
class ApprovalProgress:
    stages: list[ApprovalStage]
    completed_keys: list[str]
    next_stage: ApprovalStage | None
    can_finalize: bool
    require_distinct_reviewers: bool
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [stage.to_dict() for stage in self.stages],
            "completed_keys": self.completed_keys,
            "next_stage": self.next_stage.to_dict() if self.next_stage else None,
            "can_finalize": self.can_finalize,
            "require_distinct_reviewers": self.require_distinct_reviewers,
            "blocked_reason": self.blocked_reason,
            "is_multi_stage": len(self.stages) > 1,
        }


class ApprovalWorkflow:
    def __init__(
        self,
        stages: list[dict[str, Any]] | None = None,
        require_distinct_reviewers: bool | None = None,
    ) -> None:
        self.stages = self._parse(stages if stages else DEFAULT_STAGES)
        if require_distinct_reviewers is None:
            require_distinct_reviewers = len(self.stages) > 1
        self.require_distinct_reviewers = require_distinct_reviewers

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "ApprovalWorkflow":
        config = config or {}
        stages = config.get("stages")
        return cls(
            stages if isinstance(stages, list) and stages else None,
            config.get("require_distinct_reviewers"),
        )

    @property
    def is_multi_stage(self) -> bool:
        return len(self.stages) > 1

    def progress(self, steps: list[dict[str, Any]]) -> ApprovalProgress:
        completed = self._completed_in_order(steps)
        remaining = [stage for stage in self.stages if stage.key not in completed]
        next_stage = remaining[0] if remaining else None
        return ApprovalProgress(
            stages=self.stages,
            completed_keys=[stage.key for stage in self.stages if stage.key in completed],
            next_stage=next_stage,
            can_finalize=not remaining,
            require_distinct_reviewers=self.require_distinct_reviewers,
            blocked_reason="" if not remaining else f"AWAITING_{next_stage.key.upper()}",
        )

    def assert_can_sign(
        self, stage_key: str, user_id: str, role: str, steps: list[dict[str, Any]]
    ) -> ApprovalStage:
        """Validate a sign-off attempt, or explain precisely why it is refused."""
        stage = next((item for item in self.stages if item.key == stage_key), None)
        if stage is None:
            raise AppError(
                "APPROVAL_STAGE_UNKNOWN",
                f"Unknown approval stage: {stage_key}.",
                422,
                {"known_stages": [item.key for item in self.stages]},
            )
        completed = self._completed_in_order(steps)
        if stage.key in completed:
            raise AppError(
                "APPROVAL_STAGE_ALREADY_SIGNED",
                f"Approval stage {stage.key} is already signed off.",
                409,
            )
        expected = next((item for item in self.stages if item.key not in completed), None)
        if expected is not None and expected.key != stage.key:
            raise AppError(
                "APPROVAL_STAGE_OUT_OF_ORDER",
                f"Approval stage {expected.key} must be completed before {stage.key}.",
                409,
                {"expected_stage": expected.key},
            )
        if stage.role and role != stage.role and role != "admin":
            raise AppError(
                "APPROVAL_ROLE_REQUIRED",
                f"Approval stage {stage.key} requires the {stage.role} role.",
                403,
            )
        if self.require_distinct_reviewers and any(
            str(step.get("approved_by")) == str(user_id) for step in steps
        ):
            raise AppError(
                "APPROVAL_DISTINCT_REVIEWER_REQUIRED",
                "A different reviewer must complete this approval stage.",
                403,
            )
        return stage

    def _completed_in_order(self, steps: list[dict[str, Any]]) -> set[str]:
        """Only a prefix of the configured stages counts as complete.

        A stage signed while an earlier one is still outstanding does not advance the workflow,
        so reordering the configuration later cannot retroactively unlock finalisation.
        """
        signed = {str(step.get("stage_key")) for step in steps}
        completed: set[str] = set()
        for stage in self.stages:
            if stage.key not in signed:
                break
            completed.add(stage.key)
        return completed

    @staticmethod
    def _parse(stages: list[dict[str, Any]]) -> list[ApprovalStage]:
        parsed: list[ApprovalStage] = []
        seen: set[str] = set()
        for index, raw in enumerate(stages, start=1):
            if not isinstance(raw, dict):
                raise AppError("APPROVAL_WORKFLOW_INVALID", "Stages must be objects.", 422)
            key = raw.get("key")
            if not isinstance(key, str) or not key.replace("_", "a").isalnum():
                raise AppError(
                    "APPROVAL_WORKFLOW_INVALID", "Each stage needs a valid key.", 422
                )
            if key in seen:
                raise AppError(
                    "APPROVAL_WORKFLOW_INVALID", f"Duplicate approval stage: {key}.", 422
                )
            seen.add(key)
            parsed.append(
                ApprovalStage(
                    key=key,
                    name=str(raw.get("name") or key.replace("_", " ").title()),
                    role=str(raw.get("role") or ""),
                    order=int(raw.get("order") or index),
                )
            )
        parsed.sort(key=lambda stage: stage.order)
        return parsed
