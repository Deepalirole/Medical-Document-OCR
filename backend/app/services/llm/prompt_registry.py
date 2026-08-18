"""Versioned, immutable extraction prompts.

Every registered version carries a ``sha256`` pinned in the source. A released prompt is
therefore frozen: editing its text changes the digest and fails
``test_p4_prompt_versioning``, which forces the change to be published as a *new* version
instead. That is what makes an extraction run traceable — a stored ``prompt_version`` means
something only if that version's text can never quietly change underneath it.

To add a prompt: append a new ``PromptVersion``, set ``LATEST_PROMPT_VERSION``, and record the
new digest. Never edit the text of an already-registered version.
"""

import hashlib
from dataclasses import dataclass

from app.core.errors import AppError
from app.services.llm.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_V2


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptVersion:
    version: str
    system_prompt: str
    description: str
    expected_sha256: str = ""
    retired: bool = False

    @property
    def sha256(self) -> str:
        return digest(self.system_prompt)

    @property
    def matches_pin(self) -> bool:
        """False when a released prompt's text drifted from its recorded digest."""
        return not self.expected_sha256 or self.sha256 == self.expected_sha256

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "version": self.version,
            "description": self.description,
            "sha256": self.sha256,
            "retired": self.retired,
            "matches_pin": self.matches_pin,
        }


V1 = PromptVersion(
    version="v1",
    system_prompt=SYSTEM_PROMPT,
    description=(
        "Initial strict non-invention transcription prompt covering patient, clinician, "
        "complaint, vitals, diagnosis, history, medicines, and advice sections."
    ),
    expected_sha256="8b6082aea7d45c2199254001d980acd1463038e5f9884c6bc140c1a09f029bf4",
)

V2 = PromptVersion(
    version="v2",
    system_prompt=SYSTEM_PROMPT_V2,
    description=(
        "Comprehensive medical document, clinical prescription, and medical bill / receipt "
        "transcription prompt with batch/unique codes, item costs, and financial totals."
    ),
    expected_sha256="da66e537a43bf3e339ecba6e60e589706be2010cf3a504de23b390b6348ac2aa",
)

PROMPT_VERSIONS: dict[str, PromptVersion] = {V1.version: V1, V2.version: V2}
LATEST_PROMPT_VERSION = V2.version


def get_prompt(version: str | None = None) -> PromptVersion:
    """Resolve a prompt version, defaulting to the latest release.

    An unknown version is a hard error rather than a silent fallback: pinning a prompt that
    does not exist must not quietly run a different one.
    """
    resolved = version or LATEST_PROMPT_VERSION
    prompt = PROMPT_VERSIONS.get(resolved)
    if prompt is None:
        raise AppError(
            "PROMPT_VERSION_UNKNOWN",
            f"Unknown extraction prompt version: {resolved}.",
            500,
            {"known_versions": sorted(PROMPT_VERSIONS)},
        )
    if prompt.retired:
        raise AppError(
            "PROMPT_VERSION_RETIRED",
            f"Extraction prompt version {resolved} is retired and cannot be used.",
            500,
        )
    return prompt


def list_prompts() -> list[dict[str, str | bool]]:
    return [PROMPT_VERSIONS[key].to_dict() for key in sorted(PROMPT_VERSIONS)]
