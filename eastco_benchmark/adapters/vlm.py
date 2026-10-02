from __future__ import annotations

from eastco_benchmark.adapters.base import AdapterUnavailable
from eastco_benchmark.adapters.mock import MockVLMAdapter
from eastco_benchmark.config import Settings


def build_vlm_adapter(settings: Settings) -> MockVLMAdapter:
    if settings.dry_run or not settings.vlm_api_key:
        return MockVLMAdapter("mock_direct_vlm", dry_run=True)
    raise AdapterUnavailable(
        "Real VLM calls are intentionally left behind this adapter boundary. "
        "Add the selected provider SDK call here, then map provider usage into Usage."
    )
