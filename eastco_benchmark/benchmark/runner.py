from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from eastco_benchmark.benchmark.accuracy import load_ground_truth, score_fields
from eastco_benchmark.benchmark.cost import cost_for_usage
from eastco_benchmark.benchmark.metrics import summarize_results
from eastco_benchmark.config import Settings, load_pricing
from eastco_benchmark.pipelines.base import BasePipeline
from eastco_benchmark.schemas import DocumentInput, PipelineRunResult


def discover_documents(dataset_dir: Path) -> list[DocumentInput]:
    documents = []
    for path in sorted(dataset_dir.glob("*.txt")):
        name_parts = path.stem.split("__", 1)
        document_type = name_parts[0] if len(name_parts) == 2 else "unknown"
        documents.append(
            DocumentInput(
                document_id=path.stem,
                path=str(path),
                document_type=document_type,
                pages=1,
            )
        )
    return documents


class BenchmarkRunner:
    def __init__(self, settings: Settings, pipelines: dict[str, BasePipeline]):
        self.settings = settings
        self.pipelines = pipelines
        self.pricing = load_pricing(settings.pricing_config_path)
        self.ground_truth = load_ground_truth(settings.ground_truth_path)

    def run(self, selected_pipeline_names: list[str]) -> dict[str, Path]:
        self.settings.results_dir.mkdir(parents=True, exist_ok=True)
        documents = discover_documents(self.settings.dataset_dir)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        detailed_rows: list[dict[str, Any]] = []
        raw_results: list[PipelineRunResult] = []

        for pipeline_name in selected_pipeline_names:
            pipeline = self.pipelines[pipeline_name]
            for document in documents:
                raw_result = self._run_one(pipeline, document)
                raw_results.append(raw_result)
                row = raw_result.to_dict()
                expected = self.ground_truth.get(document.document_id)
                if expected and raw_result.extraction:
                    row["accuracy"] = score_fields(raw_result.extraction.fields, expected)
                detailed_rows.append(row)

        summary = {
            "run_id": timestamp,
            "dry_run": self.settings.dry_run,
            "pricing_note": self.pricing.get("_note", "Pricing loaded from config."),
            "pipelines": selected_pipeline_names,
            "summary": summarize_results(detailed_rows, raw_results),
        }

        details_path = self.settings.results_dir / f"benchmark_details_{timestamp}.jsonl"
        summary_path = self.settings.results_dir / f"benchmark_summary_{timestamp}.json"
        with details_path.open("w", encoding="utf-8") as handle:
            for row in detailed_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False)
        return {"details": details_path, "summary": summary_path}

    def _run_one(self, pipeline: BasePipeline, document: DocumentInput) -> PipelineRunResult:
        retries = 0
        started = time.perf_counter()
        last_error = None
        while retries <= self.settings.max_retries:
            try:
                extraction = pipeline.run(document)
                latency_ms = (time.perf_counter() - started) * 1000
                pricing_blocks = [self.pricing.get(key, {}) for key in pipeline.pricing_keys]
                cost = cost_for_usage(extraction.usage, pricing_blocks)
                return PipelineRunResult(
                    pipeline=pipeline.name,
                    document=document,
                    extraction=extraction,
                    latency_ms=round(latency_ms, 2),
                    retries=retries,
                    failed=False,
                    cost=cost,
                )
            except Exception as exc:  # intentional benchmark boundary
                last_error = str(exc)
                retries += 1
                time.sleep(0.05 * retries)

        latency_ms = (time.perf_counter() - started) * 1000
        return PipelineRunResult(
            pipeline=pipeline.name,
            document=document,
            extraction=None,
            latency_ms=round(latency_ms, 2),
            retries=max(0, retries - 1),
            failed=True,
            error=last_error,
            cost=0.0,
        )
