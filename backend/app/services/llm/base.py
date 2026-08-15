from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMExtraction:
    provider: str
    model: str
    structured_output: dict[str, Any]
    raw_response: dict[str, Any]
    processing_ms: int


class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    def health(self) -> dict[str, str | bool]: ...
    async def extract(
        self,
        raw_text: str,
        evidence: list[dict[str, Any]],
        schema_definition: dict[str, Any],
        json_schema: dict[str, Any],
    ) -> LLMExtraction: ...

