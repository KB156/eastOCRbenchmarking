from __future__ import annotations

from eastco_benchmark.adapters.base import AdapterUnavailable
from eastco_benchmark.adapters.mock import MockOCRAdapter
from eastco_benchmark.config import Settings


def build_ocr_adapter(settings: Settings) -> MockOCRAdapter:
    if settings.dry_run or not settings.ocr_api_key:
        return MockOCRAdapter("mock_ocr_api", dry_run=True)
    raise AdapterUnavailable(
        "Real OCR API calls belong here. Map provider pages, calls, confidence, and raw text into ExtractionResult."
    )
