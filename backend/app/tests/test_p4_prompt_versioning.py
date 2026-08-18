import asyncio
import dataclasses
from pathlib import Path

import pytest

from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.core.errors import AppError
from app.services.extraction.pipeline import ExtractionService
from app.services.llm.openrouter import OpenRouterProvider
from app.services.llm.prompt import SYSTEM_PROMPT
from app.services.llm.prompt_registry import (
    LATEST_PROMPT_VERSION,
    PROMPT_VERSIONS,
    PromptVersion,
    digest,
    get_prompt,
    list_prompts,
)
from app.tests.test_p2_dynamic_review import (
    GENERAL_SCHEMA,
    ORG_ID,
    PRESCRIPTION_ID,
    SCHEMA_ID,
    FakeExtractionRepository,
)
from app.tests.test_p3_operations import CountingLLM

ROOT = Path(__file__).parents[3]


def test_every_released_prompt_still_matches_its_pinned_digest():
    """Editing a released prompt must fail here and force a new version instead."""
    for version, prompt in PROMPT_VERSIONS.items():
        assert prompt.matches_pin, (
            f"Prompt {version} text changed but its expected_sha256 was not updated. "
            "Register a new PromptVersion rather than editing a released one."
        )


def test_v1_is_the_current_system_prompt():
    prompt = get_prompt("v1")
    assert prompt.system_prompt == SYSTEM_PROMPT
    assert prompt.sha256 == digest(SYSTEM_PROMPT)
    assert "Never invent a medicine" in prompt.system_prompt


def test_prompt_versions_are_immutable():
    prompt = get_prompt()
    with pytest.raises(dataclasses.FrozenInstanceError):
        prompt.system_prompt = "tampered"  # type: ignore[misc]


def test_default_resolves_to_the_latest_version():
    assert get_prompt().version == LATEST_PROMPT_VERSION
    assert get_prompt(None).version == LATEST_PROMPT_VERSION


def test_an_unknown_version_is_a_hard_error_not_a_silent_fallback():
    with pytest.raises(AppError) as error:
        get_prompt("v99")
    assert error.value.code == "PROMPT_VERSION_UNKNOWN"
    assert "v1" in error.value.details["known_versions"]


def test_a_retired_version_cannot_be_selected(monkeypatch):
    retired = PromptVersion(
        version="v0", system_prompt="legacy", description="legacy", retired=True
    )
    monkeypatch.setitem(PROMPT_VERSIONS, "v0", retired)
    with pytest.raises(AppError) as error:
        get_prompt("v0")
    assert error.value.code == "PROMPT_VERSION_RETIRED"


def test_a_drifted_pin_is_reported_rather_than_hidden():
    drifted = PromptVersion(
        version="vx",
        system_prompt="changed text",
        description="drifted",
        expected_sha256=digest("original text"),
    )
    assert drifted.matches_pin is False
    assert drifted.to_dict()["matches_pin"] is False


def test_listing_exposes_digests_but_not_prompt_text():
    listed = list_prompts()
    assert [item["version"] for item in listed] == sorted(PROMPT_VERSIONS)
    for item in listed:
        assert "system_prompt" not in item
        assert len(item["sha256"]) == 64


# --- Provider ------------------------------------------------------------------------


def test_provider_reports_the_prompt_it_will_send():
    provider = OpenRouterProvider("key", "model")
    assert provider.prompt_version == LATEST_PROMPT_VERSION
    assert provider.prompt_sha256 == get_prompt(LATEST_PROMPT_VERSION).sha256
    health = provider.health()
    assert health["prompt_version"] == LATEST_PROMPT_VERSION
    assert health["prompt_sha256"] == provider.prompt_sha256
    assert "key" not in str(health)


def test_provider_sends_the_selected_prompt_version(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "model": "test-model",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"patient": null}'}}
                ],
            }

    class FakeClient:
        def __init__(self, timeout, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            captured["body"] = json
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.openrouter.httpx.AsyncClient", FakeClient)
    provider = OpenRouterProvider("key", "test-model", prompt_version="v1")
    asyncio.run(provider.extract("text", [], GENERAL_SCHEMA, {"type": "object"}))
    assert captured["body"]["messages"][0]["content"] == get_prompt("v1").system_prompt


def test_an_invalid_configured_version_fails_at_construction():
    with pytest.raises(AppError) as error:
        OpenRouterProvider("key", "model", prompt_version="nope")
    assert error.value.code == "PROMPT_VERSION_UNKNOWN"


def test_settings_default_to_the_latest_prompt_and_can_pin_one():
    assert Settings().openrouter_prompt_version == ""
    assert get_llm_provider(Settings()).prompt_version == LATEST_PROMPT_VERSION
    pinned = get_llm_provider(Settings(openrouter_prompt_version="v1"))
    assert pinned.prompt_version == "v1"


# --- Extraction lineage --------------------------------------------------------------


class PromptAwareLLM(CountingLLM):
    prompt_version = "v1"
    prompt_sha256 = digest(SYSTEM_PROMPT)


def run_extraction(provider):
    repository = FakeExtractionRepository()
    service = ExtractionService(repository, provider)
    asyncio.run(
        service.extract(
            {
                "id": str(PRESCRIPTION_ID),
                "organization_id": str(ORG_ID),
                "schema_id": str(SCHEMA_ID),
                "status": "UPLOADED",
            }
        )
    )
    return repository


def test_a_successful_run_records_the_prompt_lineage():
    repository = run_extraction(PromptAwareLLM())
    run = repository.runs[0]
    assert run["prompt_version"] == "v1"
    assert run["prompt_sha256"] == digest(SYSTEM_PROMPT)


def test_a_provider_without_a_versioned_prompt_records_no_lineage():
    repository = run_extraction(CountingLLM())
    run = repository.runs[0]
    assert run["prompt_version"] is None
    assert run["prompt_sha256"] is None


def test_the_migration_adds_the_lineage_columns():
    sql = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    )
    assert "prompt_version text" in sql
    assert "prompt_sha256 text" in sql
    assert "extraction_runs_prompt_version_idx" in sql


# --- API -----------------------------------------------------------------------------


def test_endpoint_lists_registered_versions(client):
    response = client.get("/api/assistance/prompt-versions")
    assert response.status_code == 200
    body = response.json()
    assert body["latest"] == LATEST_PROMPT_VERSION
    versions = {item["version"]: item for item in body["versions"]}
    assert versions["v1"]["matches_pin"] is True
    assert SYSTEM_PROMPT not in response.text
