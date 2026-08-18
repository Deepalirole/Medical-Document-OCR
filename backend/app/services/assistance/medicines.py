"""Medicine dictionary reviewer assistance.

Handwritten drug names are the highest-risk field on a prescription, so this module offers a
reviewer *candidates* and an explicit "not in the dictionary" verdict. It never rewrites a
value, never ranks a suggestion as authoritative, and an absent match is reported as unknown
rather than being resolved to the nearest string — silently snapping ``Losartan`` onto
``Lisinopril`` is precisely the failure this assistance exists to prevent.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.benchmark.metrics import levenshtein

DATA_PATH = Path(__file__).parent / "data" / "medicines.txt"
NON_NAME = re.compile(r"[^a-z ]+")
WHITESPACE = re.compile(r"\s+")
DEFAULT_MIN_SCORE = 0.72  # kept in sync with Settings.medicine_min_similarity
NAME_KEY_CANDIDATES = ("medicine_name", "drug_name", "name")

# Dose forms, strength units and frequency codes are prescription notation rather than parts of
# the drug name. Stripping digits alone would leave the unit stranded ("625mg" -> "mg"), so the
# orphaned units are removed here too.
DOSE_FORMS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules"}
DOSE_FORMS |= {"syr", "syrup", "inj", "injection", "susp", "suspension", "oint", "ointment"}
STRENGTH_UNITS = {"mg", "mgs", "mcg", "ug", "g", "gm", "gms", "ml", "l", "iu", "unit", "units"}
FREQUENCY_CODES = {"od", "bd", "tds", "tid", "qid", "qds", "hs", "sos", "stat", "prn"}
ROUTE_CODES = {"po", "iv", "im", "sc", "sl", "pr"}
STOPWORDS = DOSE_FORMS | STRENGTH_UNITS | FREQUENCY_CODES | ROUTE_CODES


@dataclass(frozen=True)
class MedicineSuggestion:
    name: str
    score: float
    exact: bool


@dataclass(frozen=True)
class MedicineLookup:
    query: str
    normalized_query: str
    known: bool
    suggestions: list[MedicineSuggestion]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "normalized_query": self.normalized_query,
            "known": self.known,
            "requires_reviewer_confirmation": True,
            "suggestions": [
                {"name": s.name, "score": round(s.score, 4), "exact": s.exact}
                for s in self.suggestions
            ],
        }


def normalize_name(value: str) -> str:
    """Drop strengths, forms and punctuation so ``Tab. Augmentin-625mg`` compares as a name."""
    lowered = str(value).lower()
    lowered = NON_NAME.sub(" ", lowered)
    lowered = WHITESPACE.sub(" ", lowered).strip()
    return " ".join(word for word in lowered.split() if word not in STOPWORDS)


class MedicineDictionary:
    def __init__(self, entries: list[str] | None = None, extra_path: str | Path = "") -> None:
        source = list(entries) if entries is not None else list(_load_seed_entries())
        if extra_path:
            source.extend(_read_entries(Path(extra_path)))
        self._by_normalized: dict[str, str] = {}
        for entry in source:
            normalized = normalize_name(entry)
            if normalized:
                self._by_normalized.setdefault(normalized, entry.strip())

    def __len__(self) -> int:
        return len(self._by_normalized)

    @property
    def names(self) -> list[str]:
        return sorted(self._by_normalized.values())

    def lookup(
        self, query: str, limit: int = 5, min_score: float = DEFAULT_MIN_SCORE
    ) -> MedicineLookup:
        normalized = normalize_name(query)
        if not normalized:
            return MedicineLookup(query=query, normalized_query="", known=False, suggestions=[])

        exact = self._by_normalized.get(normalized)
        if exact:
            return MedicineLookup(
                query=query,
                normalized_query=normalized,
                known=True,
                suggestions=[MedicineSuggestion(name=exact, score=1.0, exact=True)],
            )

        scored: list[MedicineSuggestion] = []
        for candidate_normalized, display in self._by_normalized.items():
            score = self._similarity(normalized, candidate_normalized)
            if score >= min_score:
                scored.append(MedicineSuggestion(name=display, score=score, exact=False))
        scored.sort(key=lambda item: (-item.score, item.name))
        return MedicineLookup(
            query=query,
            normalized_query=normalized,
            known=False,
            suggestions=scored[:limit],
        )

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        longest = max(len(left), len(right))
        if not longest:
            return 0.0
        # A large length gap is a different drug, not a misspelling; skip the expensive compare.
        if abs(len(left) - len(right)) / longest > 0.5:
            return 0.0
        return 1.0 - (levenshtein(left, right) / longest)


def medicine_name_paths(definition: dict[str, Any]) -> set[str]:
    """Item keys inside ``medicine_list`` sections that hold the drug name.

    Returns entries like ``medicines.medicine_name`` so a caller can match field paths such as
    ``medicines[0].medicine_name`` without assuming a fixed schema.
    """
    paths: set[str] = set()
    for section in definition.get("sections") or []:
        if not isinstance(section, dict) or section.get("type") != "medicine_list":
            continue
        section_key = section.get("key")
        item_schema = section.get("item_schema")
        if not isinstance(section_key, str) or not isinstance(item_schema, dict):
            continue
        for candidate in NAME_KEY_CANDIDATES:
            if candidate in item_schema:
                paths.add(f"{section_key}.{candidate}")
                break
    return paths


def field_matches_medicine_name(field_path: str, name_paths: set[str]) -> bool:
    """``medicines[0].medicine_name`` matches the ``medicines.medicine_name`` signature."""
    collapsed = re.sub(r"\[\d+\]", "", field_path)
    return collapsed in name_paths


def _read_entries(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


@lru_cache(maxsize=1)
def _load_seed_entries() -> tuple[str, ...]:
    return tuple(_read_entries(DATA_PATH))
