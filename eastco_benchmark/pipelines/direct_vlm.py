from __future__ import annotations

from eastco_benchmark.adapters.base import BaseAdapter
from eastco_benchmark.pipelines.base import BasePipeline
from eastco_benchmark.schemas import DocumentInput, ExtractionResult


class DirectVLMPipeline(BasePipeline):
    name = "method_1_direct_vlm"
    pricing_keys = ("direct_vlm",)

    def __init__(self, vlm_adapter: BaseAdapter):
        self.vlm_adapter = vlm_adapter

    def run(self, document: DocumentInput) -> ExtractionResult:
        result = self.vlm_adapter.extract(document)
        result.metadata["pipeline"] = self.name
        return result
