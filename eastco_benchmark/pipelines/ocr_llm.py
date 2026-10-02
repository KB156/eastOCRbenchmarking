from __future__ import annotations

from eastco_benchmark.adapters.mock import MockLLMAdapter
from eastco_benchmark.adapters.base import BaseAdapter
from eastco_benchmark.pipelines.base import BasePipeline
from eastco_benchmark.schemas import DocumentInput, ExtractionResult


class OCRThenLLMPipeline(BasePipeline):
    name = "method_3_ocr_api_then_llm"
    pricing_keys = ("ocr_api", "llm_api")

    def __init__(self, ocr_adapter: BaseAdapter, llm_adapter: MockLLMAdapter):
        self.ocr_adapter = ocr_adapter
        self.llm_adapter = llm_adapter

    def run(self, document: DocumentInput) -> ExtractionResult:
        ocr_result = self.ocr_adapter.extract(document)
        llm_result = self.llm_adapter.extract_text(document, ocr_result.raw_text, ocr_result.confidence)
        llm_result.usage = ocr_result.usage.add(llm_result.usage)
        llm_result.warnings = [*ocr_result.warnings, *llm_result.warnings]
        llm_result.metadata["pipeline"] = self.name
        llm_result.metadata["ocr_confidence"] = ocr_result.confidence
        return llm_result
