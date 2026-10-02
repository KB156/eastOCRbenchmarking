from __future__ import annotations

from eastco_benchmark.pipelines.base import BasePipeline
from eastco_benchmark.pipelines.direct_vlm import DirectVLMPipeline
from eastco_benchmark.pipelines.ocr_llm import OCRThenLLMPipeline
from eastco_benchmark.schemas import DocumentInput, ExtractionResult


class ConfidenceHybridPipeline(BasePipeline):
    name = "method_5_confidence_hybrid"
    pricing_keys = ("ocr_api", "llm_api", "direct_vlm")

    def __init__(
        self,
        primary_pipeline: OCRThenLLMPipeline,
        fallback_pipeline: DirectVLMPipeline,
        confidence_threshold: float,
    ):
        self.primary_pipeline = primary_pipeline
        self.fallback_pipeline = fallback_pipeline
        self.confidence_threshold = confidence_threshold

    def run(self, document: DocumentInput) -> ExtractionResult:
        primary = self.primary_pipeline.run(document)
        should_fallback = (
            primary.confidence < self.confidence_threshold
            or not primary.normalized_json_valid
        )
        if not should_fallback:
            primary.metadata["pipeline"] = self.name
            primary.metadata["hybrid_route"] = "primary_ocr_llm"
            primary.metadata["fallback_used"] = False
            return primary

        fallback = self.fallback_pipeline.run(document)
        fallback.usage = primary.usage.add(fallback.usage)
        fallback.warnings = [
            *primary.warnings,
            f"Hybrid fallback used because primary confidence was {primary.confidence:.2f}.",
            *fallback.warnings,
        ]
        fallback.metadata["pipeline"] = self.name
        fallback.metadata["hybrid_route"] = "vlm_fallback"
        fallback.metadata["fallback_used"] = True
        fallback.metadata["primary_confidence"] = primary.confidence
        return fallback
