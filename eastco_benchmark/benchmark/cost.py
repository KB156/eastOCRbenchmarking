from __future__ import annotations

from eastco_benchmark.schemas import Usage


def cost_for_usage(usage: Usage, pricing_blocks: list[dict]) -> float:
    total = 0.0
    for pricing in pricing_blocks:
        total += usage.api_calls * float(pricing.get("per_api_call", 0.0))
        total += usage.pages * float(pricing.get("per_page", 0.0))
        total += usage.images * float(pricing.get("per_image", 0.0))
        total += (usage.input_tokens / 1000.0) * float(pricing.get("per_1k_input_tokens", 0.0))
        total += (usage.output_tokens / 1000.0) * float(pricing.get("per_1k_output_tokens", 0.0))
        total += usage.inference_seconds * float(pricing.get("per_inference_second", 0.0))
        total += usage.gpu_seconds * float(pricing.get("per_gpu_second", 0.0))
    return round(total, 8)
