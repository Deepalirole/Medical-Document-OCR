import asyncio
import json
import re
import time
from typing import Any

import httpx

from app.core.errors import AppError
from app.services.llm.base import LLMExtraction
from app.services.llm.prompt import SYSTEM_PROMPT, build_user_prompt


class OpenRouterProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        max_tokens: int = 4000,
        retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.retries = retries

    @property
    def name(self) -> str:
        return "openrouter"

    def health(self) -> dict[str, str | bool]:
        return {"provider": self.name, "configured": bool(self.api_key), "model": self.model}

    async def extract(
        self,
        raw_text: str,
        evidence: list[dict[str, Any]],
        schema_definition: dict[str, Any],
        json_schema: dict[str, Any],
    ) -> LLMExtraction:
        if not self.api_key:
            raise AppError("LLM_NOT_CONFIGURED", "OpenRouter is not configured.", 503)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(raw_text, evidence, schema_definition),
                },
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "prescription_transcription",
                    "strict": True,
                    "schema": json_schema,
                },
            },
        }
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, trust_env=False
                ) as client:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code != 200:
                    raise AppError(
                        "LLM_FAILED",
                        "OpenRouter rejected the extraction request.",
                        502,
                        {"status": response.status_code},
                    )
                payload = response.json()
                choice = payload.get("choices", [{}])[0]
                if choice.get("finish_reason") == "error" or choice.get("error"):
                    raise AppError("LLM_FAILED", "OpenRouter provider failed safely.", 502)
                content = choice.get("message", {}).get("content")
                structured = self.parse_json(content)
                return LLMExtraction(
                    provider=self.name,
                    model=payload.get("model", self.model),
                    structured_output=structured,
                    raw_response=payload,
                    processing_ms=int((time.perf_counter() - started) * 1000),
                )
            except AppError:
                raise
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                last_error = error
                if attempt < self.retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
        raise AppError("LLM_FAILED", "OpenRouter extraction failed safely.", 502) from last_error

    @staticmethod
    def parse_json(content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise AppError("LLM_INVALID_JSON", "OpenRouter returned invalid JSON.", 502)
        candidate = content.strip()

        # 1. Try direct parsing
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # 2. Extract from markdown code fence ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", candidate, re.IGNORECASE)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        # 3. Extract from first '{' to last '}'
        first_brace = candidate.find("{")
        last_brace = candidate.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                parsed = json.loads(candidate[first_brace : last_brace + 1])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        raise AppError("LLM_INVALID_JSON", "OpenRouter returned invalid JSON.", 502)
