from __future__ import annotations

import argparse
import json
from pathlib import Path

from eastco_benchmark.benchmark.runner import BenchmarkRunner
from eastco_benchmark.config import load_settings
from eastco_benchmark.pipelines.registry import build_pipelines


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run East.Co OCR/API benchmark demo.")
    parser.add_argument(
        "--pipeline",
        action="append",
        choices=[
            "all",
            "method_1_direct_vlm",
            "method_3_ocr_api_then_llm",
            "method_4_cloud_hosted_open_source",
            "method_5_confidence_hybrid",
        ],
        default=[],
        help="Pipeline to run. Repeat for multiple pipelines, or use all.",
    )
    parser.add_argument("--list-pipelines", action="store_true", help="List available benchmark pipelines.")
    args = parser.parse_args()

    settings = load_settings(project_root())
    pipelines = build_pipelines(settings)

    if args.list_pipelines:
        print(json.dumps(list(pipelines.keys()), indent=2))
        return

    selected = args.pipeline or ["all"]
    if "all" in selected:
        selected_names = list(pipelines.keys())
    else:
        selected_names = selected

    runner = BenchmarkRunner(settings, pipelines)
    output_paths = runner.run(selected_names)
    print(json.dumps({key: str(value) for key, value in output_paths.items()}, indent=2))


from eastco_benchmark.app import main

if __name__ == "__main__":
    main()
