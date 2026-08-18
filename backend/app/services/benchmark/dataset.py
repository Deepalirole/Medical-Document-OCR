"""Labelled benchmark case loading.

Expected layout — a ``kind`` subdirectory per document class, each holding an image and a
sidecar ground-truth text file with the same stem::

    dataset/
      printed/      page-01.png  page-01.txt
      handwritten/  note-01.png  note-01.txt

A flat directory of image/text pairs is also accepted and treated as ``printed``.
"""

from pathlib import Path

from app.core.errors import AppError
from app.services.benchmark.harness import BenchmarkCase

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
KNOWN_KINDS = ("printed", "handwritten")


def load_cases(root: Path) -> list[BenchmarkCase]:
    if not root.is_dir():
        raise AppError(
            "BENCHMARK_DATASET_MISSING",
            f"Benchmark dataset directory not found: {root}",
            400,
        )
    cases: list[BenchmarkCase] = []
    for kind in KNOWN_KINDS:
        cases.extend(_load_directory(root / kind, kind))
    cases.extend(_load_directory(root, "printed"))
    if not cases:
        raise AppError(
            "BENCHMARK_NO_CASES",
            f"No image/ground-truth pairs found under {root}.",
            400,
        )
    return sorted(cases, key=lambda case: (case.kind, case.name))


def _load_directory(directory: Path, kind: str) -> list[BenchmarkCase]:
    if not directory.is_dir():
        return []
    cases: list[BenchmarkCase] = []
    for image_path in sorted(directory.iterdir()):
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        ground_truth = image_path.with_suffix(".txt")
        if not ground_truth.is_file():
            continue
        cases.append(
            BenchmarkCase(
                name=image_path.stem,
                png_bytes=image_path.read_bytes(),
                expected_text=ground_truth.read_text(encoding="utf-8"),
                kind=kind,
            )
        )
    return cases
