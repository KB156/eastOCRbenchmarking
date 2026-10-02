from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    dry_run: bool
    dataset_dir: Path
    ground_truth_path: Path
    pricing_config_path: Path
    results_dir: Path
    max_retries: int
    hybrid_confidence_threshold: float

    vlm_provider: str
    vlm_api_key: str | None
    vlm_model: str | None

    ocr_provider: str
    ocr_api_key: str | None
    ocr_model: str | None

    llm_provider: str
    llm_api_key: str | None
    llm_model: str | None

    cloud_ocr_provider: str
    cloud_ocr_endpoint_url: str | None
    cloud_ocr_api_key: str | None
    cloud_ocr_model: str | None


def load_settings(project_root: Path) -> Settings:
    return Settings(
        dry_run=env_bool("EASTCO_DRY_RUN", True),
        dataset_dir=project_root / os.getenv("EASTCO_DATASET_DIR", "data/documents"),
        ground_truth_path=project_root / os.getenv("EASTCO_GROUND_TRUTH", "data/ground_truth.jsonl"),
        pricing_config_path=project_root / os.getenv("EASTCO_PRICING_CONFIG", "pricing.example.json"),
        results_dir=project_root / os.getenv("EASTCO_RESULTS_DIR", "results"),
        max_retries=int(os.getenv("EASTCO_MAX_RETRIES", "2")),
        hybrid_confidence_threshold=float(os.getenv("EASTCO_HYBRID_CONFIDENCE_THRESHOLD", "0.88")),
        vlm_provider=os.getenv("VLM_PROVIDER", "mock_vlm"),
        vlm_api_key=os.getenv("VLM_API_KEY") or None,
        vlm_model=os.getenv("VLM_MODEL") or None,
        ocr_provider=os.getenv("OCR_PROVIDER", "mock_ocr"),
        ocr_api_key=os.getenv("OCR_API_KEY") or None,
        ocr_model=os.getenv("OCR_MODEL") or None,
        llm_provider=os.getenv("LLM_PROVIDER", "mock_llm"),
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL") or None,
        cloud_ocr_provider=os.getenv("CLOUD_OCR_PROVIDER", "mock_cloud_hosted_ocr"),
        cloud_ocr_endpoint_url=os.getenv("CLOUD_OCR_ENDPOINT_URL") or None,
        cloud_ocr_api_key=os.getenv("CLOUD_OCR_API_KEY") or None,
        cloud_ocr_model=os.getenv("CLOUD_OCR_MODEL") or None,
    )


def load_pricing(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
