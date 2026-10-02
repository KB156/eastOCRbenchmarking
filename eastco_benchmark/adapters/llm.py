from __future__ import annotations

from eastco_benchmark.adapters.base import AdapterUnavailable
from eastco_benchmark.adapters.mock import MockLLMAdapter
from eastco_benchmark.config import Settings


def build_llm_adapter(settings: Settings) -> MockLLMAdapter:
    if settings.dry_run or not settings.llm_api_key:
        return MockLLMAdapter("mock_llm_api", dry_run=True)
    raise AdapterUnavailable(
        "Real LLM calls belong here. Convert OCR text to the common schema and map token usage into Usage."
    )
