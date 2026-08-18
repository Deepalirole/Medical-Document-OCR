"""Deterministic accuracy metrics for OCR/HTR provider comparison.

Everything here is pure and dependency-free so a benchmark result is reproducible on any
machine and can be asserted in unit tests.
"""

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str, *, fold_case: bool = True) -> str:
    """Canonicalise text before scoring so provider formatting is not penalised.

    Unicode is NFKC-folded, runs of whitespace collapse to a single space, and the result is
    trimmed. Case folding is on by default because clinical transcription is compared for
    content, not capitalisation.
    """
    normalized = unicodedata.normalize("NFKC", value)
    normalized = WHITESPACE.sub(" ", normalized).strip()
    return normalized.casefold() if fold_case else normalized


def levenshtein(reference: list[str] | str, hypothesis: list[str] | str) -> int:
    """Edit distance over characters or tokens, computed in O(min(n, m)) memory."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    if not hypothesis:
        return len(reference)
    previous = list(range(len(hypothesis) + 1))
    for i, reference_item in enumerate(reference, start=1):
        current = [i]
        for j, hypothesis_item in enumerate(hypothesis, start=1):
            cost = 0 if reference_item == hypothesis_item else 1
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            )
        previous = current
    return previous[-1]


def character_error_rate(expected: str, actual: str) -> float:
    """CER = edit distance / reference length. Returns 0.0 only when both sides are empty."""
    reference = normalize_text(expected)
    hypothesis = normalize_text(actual)
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)


def word_error_rate(expected: str, actual: str) -> float:
    reference = normalize_text(expected).split()
    hypothesis = normalize_text(actual).split()
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)


def expected_calibration_error(
    pairs: list[tuple[float, bool]], bins: int = 10
) -> float | None:
    """How far a provider's stated confidence sits from its observed accuracy.

    ``pairs`` are ``(confidence, was_correct)``. A provider that reports 0.9 confidence on
    tokens it gets right 60% of the time scores badly here even when its CER looks acceptable,
    which is exactly the failure mode that matters for a review queue: over-confident output
    is what slips past a reviewer.

    Returns ``None`` when no provider confidence is available.
    """
    scored = [(confidence, correct) for confidence, correct in pairs if confidence is not None]
    if not scored:
        return None
    total = len(scored)
    error = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [
            (confidence, correct)
            for confidence, correct in scored
            if (confidence > low or (index == 0 and confidence >= low)) and confidence <= high
        ]
        if not bucket:
            continue
        mean_confidence = sum(confidence for confidence, _ in bucket) / len(bucket)
        accuracy = sum(1 for _, correct in bucket if correct) / len(bucket)
        error += (len(bucket) / total) * abs(mean_confidence - accuracy)
    return error
