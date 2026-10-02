from __future__ import annotations

import statistics
from typing import Any

from eastco_benchmark.schemas import PipelineRunResult, Usage


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def summarize_results(results: list[dict[str, Any]], run_results: list[PipelineRunResult]) -> dict[str, Any]:
    by_pipeline: dict[str, list[dict[str, Any]]] = {}
    raw_by_pipeline: dict[str, list[PipelineRunResult]] = {}
    for row, raw in zip(results, run_results):
        by_pipeline.setdefault(row["pipeline"], []).append(row)
        raw_by_pipeline.setdefault(raw.pipeline, []).append(raw)

    summaries = {}
    for pipeline, rows in by_pipeline.items():
        raw_rows = raw_by_pipeline[pipeline]
        latencies = [row["latency_ms"] for row in rows]
        costs = [row["cost"] for row in rows]
        accuracies = [row["accuracy"]["field_accuracy"] for row in rows if "accuracy" in row]
        failures = sum(1 for row in rows if row["failed"])
        total_usage = Usage()
        fallback_count = 0
        for raw in raw_rows:
            if raw.extraction:
                total_usage = total_usage.add(raw.extraction.usage)
                if raw.extraction.metadata.get("fallback_used"):
                    fallback_count += 1
        total_latency_seconds = sum(latencies) / 1000.0
        success_count = max(0, len(rows) - failures)
        summaries[pipeline] = {
            "documents": len(rows),
            "successes": success_count,
            "failures": failures,
            "failure_rate": round(failures / len(rows), 4) if rows else 0.0,
            "latency_ms_p50": round(percentile(latencies, 50), 2),
            "latency_ms_p95": round(percentile(latencies, 95), 2),
            "latency_ms_mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "throughput_docs_per_second": round(success_count / total_latency_seconds, 4) if total_latency_seconds else 0.0,
            "estimated_total_cost": round(sum(costs), 8),
            "estimated_cost_per_document": round(sum(costs) / len(rows), 8) if rows else 0.0,
            "field_accuracy_mean": round(statistics.mean(accuracies), 4) if accuracies else 0.0,
            "fallback_rate": round(fallback_count / len(rows), 4) if rows else 0.0,
            "usage": total_usage.to_dict(),
        }
    return summaries
