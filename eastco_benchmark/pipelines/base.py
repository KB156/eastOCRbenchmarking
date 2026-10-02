from __future__ import annotations

from abc import ABC, abstractmethod

from eastco_benchmark.schemas import DocumentInput, ExtractionResult


class BasePipeline(ABC):
    name: str
    pricing_keys: tuple[str, ...]

    @abstractmethod
    def run(self, document: DocumentInput) -> ExtractionResult:
        raise NotImplementedError
