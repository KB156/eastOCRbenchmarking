from __future__ import annotations

from eastco_benchmark.adapters.base import AdapterUnavailable
from eastco_benchmark.adapters.mock import MockCloudHostedOCRAdapter
from eastco_benchmark.config import Settings


def build_cloud_hosted_adapter(settings: Settings) -> MockCloudHostedOCRAdapter:
    if settings.dry_run or not settings.cloud_ocr_api_key:
        return MockCloudHostedOCRAdapter("mock_cloud_hosted_open_source", dry_run=True)
    raise AdapterUnavailable(
        "Real hosted-model calls belong here. Use this for SageMaker, Vertex AI, Azure ML, or Cloud Run endpoints."
    )
