from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class HMISDocument:
    """An approved prescription translated into destination HMIS/EMR records.

    The mapper never fabricates target values: every populated key is traceable to an
    approved reviewer field, and every approved path the mapping does not cover is
    reported in ``unmapped`` instead of being silently dropped.
    """

    contract_version: str
    source_id: str
    prescription_id: str
    organization_id: str
    approved_version: int
    patient: dict[str, Any]
    prescription: dict[str, Any]
    prescription_items: list[dict[str, Any]]
    source_data: dict[str, Any]
    unmapped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HMISDispatchResult:
    connector: str
    dispatched: bool
    idempotent: bool
    source_id: str
    item_count: int
    target_ids: dict[str, str] = field(default_factory=dict)


class HMISConnector(Protocol):
    @property
    def name(self) -> str: ...
    def health(self) -> dict[str, str | bool]: ...
    async def dispatch(self, document: HMISDocument) -> HMISDispatchResult: ...
