from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentInput:
    document_id: str
    path: str
    document_type: str
    pages: int = 1


@dataclass
class Usage:
    api_calls: int = 0
    pages: int = 0
    images: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    inference_seconds: float = 0.0
    gpu_seconds: float = 0.0

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            api_calls=self.api_calls + other.api_calls,
            pages=self.pages + other.pages,
            images=self.images + other.images,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            inference_seconds=self.inference_seconds + other.inference_seconds,
            gpu_seconds=self.gpu_seconds + other.gpu_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ExtractionResult:
    document_id: str
    document_type: str
    fields: dict[str, Any]
    confidence: float
    normalized_json_valid: bool
    usage: Usage
    provider: str
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_type": self.document_type,
            "fields": self.fields,
            "confidence": self.confidence,
            "normalized_json_valid": self.normalized_json_valid,
            "usage": self.usage.to_dict(),
            "provider": self.provider,
            "raw_text": self.raw_text,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class PipelineRunResult:
    pipeline: str
    document: DocumentInput
    extraction: ExtractionResult | None
    latency_ms: float
    retries: int
    failed: bool
    error: str | None = None
    cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "document_id": self.document.document_id,
            "document_type": self.document.document_type,
            "pages": self.document.pages,
            "latency_ms": self.latency_ms,
            "retries": self.retries,
            "failed": self.failed,
            "error": self.error,
            "cost": self.cost,
            "extraction": self.extraction.to_dict() if self.extraction else None,
        }
