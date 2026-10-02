from __future__ import annotations

from eastco_benchmark.adapters.base import BaseAdapter
from eastco_benchmark.pipelines.base import BasePipeline
from eastco_benchmark.schemas import DocumentInput, ExtractionResult


class CloudHostedOpenSourcePipeline(BasePipeline):
    name = "method_4_cloud_hosted_open_source"
    pricing_keys = ("cloud_hosted_model",)

    def __init__(self, hosted_adapter: BaseAdapter):
        self.hosted_adapter = hosted_adapter

    def run(self, document: DocumentInput) -> ExtractionResult:
        result = self.hosted_adapter.extract(document)
        result.metadata["pipeline"] = self.name
        return result
