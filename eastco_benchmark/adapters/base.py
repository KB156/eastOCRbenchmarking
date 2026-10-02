from __future__ import annotations

from abc import ABC, abstractmethod

from eastco_benchmark.schemas import DocumentInput, ExtractionResult


class AdapterUnavailable(RuntimeError):
    pass


class BaseAdapter(ABC):
    def __init__(self, provider: str, dry_run: bool = True):
        self.provider = provider
        self.dry_run = dry_run

    @abstractmethod
    def extract(self, document: DocumentInput) -> ExtractionResult:
        raise NotImplementedError
