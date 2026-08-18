"""Run the OCR/HTR benchmark from the command line.

    python -m app.services.benchmark ./benchmark-data
    python -m app.services.benchmark ./benchmark-data --kind handwritten

Engines are built from the current environment, so an unconfigured provider is reported as a
failed engine rather than skipped silently — that visibility is the point of the benchmark.
"""

import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.benchmark.dataset import load_cases
from app.services.benchmark.harness import BenchmarkEngine, BenchmarkHarness
from app.services.htr.unconfigured import UnconfiguredHTREngine
from app.services.ocr.tesseract import TesseractEngine


def build_engines() -> list[BenchmarkEngine]:
    settings = get_settings()
    return [TesseractEngine(settings.tesseract_cmd), UnconfiguredHTREngine()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.services.benchmark")
    parser.add_argument("dataset", type=Path, help="Directory of labelled benchmark cases")
    parser.add_argument("--kind", choices=("printed", "handwritten"), default=None)
    parser.add_argument("--output", type=Path, default=None, help="Write the JSON report here")
    args = parser.parse_args(argv)

    try:
        report = BenchmarkHarness(load_cases(args.dataset)).run(build_engines(), args.kind)
    except AppError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1

    payload = json.dumps(report.to_dict(), indent=2)
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
