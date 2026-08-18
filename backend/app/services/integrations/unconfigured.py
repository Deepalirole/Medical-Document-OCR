from app.core.errors import AppError
from app.services.integrations.base import HMISDispatchResult, HMISDocument


class UnconfiguredHMISConnector:
    """Default destination: mapping and preview stay available, transport stays inert."""

    @property
    def name(self) -> str:
        return "unconfigured"

    def health(self) -> dict[str, str | bool]:
        return {"provider": self.name, "configured": False, "status": "HMIS_NOT_CONFIGURED"}

    async def dispatch(self, document: HMISDocument) -> HMISDispatchResult:
        del document
        raise AppError(
            "HMIS_NOT_CONFIGURED",
            "No HMIS/EMR destination is configured; approved payloads can still be exported.",
            503,
        )
