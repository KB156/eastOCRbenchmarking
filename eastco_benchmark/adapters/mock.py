from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from eastco_benchmark.adapters.base import BaseAdapter
from eastco_benchmark.schemas import DocumentInput, ExtractionResult, Usage


def read_document_text(document: DocumentInput) -> str:
    return Path(document.path).read_text(encoding="utf-8")


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.35))


def parse_fields(text: str) -> dict[str, Any]:
    def find(pattern: str, default: str = "") -> str:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else default

    fields: dict[str, Any] = {
        "client_id": find(r"Client ID:\s*([A-Z0-9-]+)"),
        "document_date": find(r"Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})"),
        "merchant_or_site": find(r"(?:Merchant|Site):\s*([^\n]+)"),
        "total_amount": None,
        "currency": find(r"Currency:\s*([A-Z]{3})", "JPY"),
        "summary": find(r"Summary:\s*([^\n]+)"),
    }
    amount = find(r"Total:\s*([0-9,.]+)")
    if amount:
        fields["total_amount"] = float(amount.replace(",", ""))

    line_items = []
    for item, quantity, amount_value in re.findall(
        r"^\s*-\s*([^\n|]+)\|\s*qty=([0-9.]+)\s*\|\s*amount=([0-9,.]+)",
        text,
        re.MULTILINE,
    ):
        line_items.append(
            {
                "description": item.strip(),
                "quantity": float(quantity),
                "amount": float(amount_value.replace(",", "")),
            }
        )
    fields["line_items"] = line_items
    return fields


def required_fields_present(fields: dict[str, Any]) -> bool:
    required = ["client_id", "document_date", "merchant_or_site", "currency"]
    return all(bool(fields.get(name)) for name in required) and fields.get("total_amount") is not None


class MockVLMAdapter(BaseAdapter):
    def extract(self, document: DocumentInput) -> ExtractionResult:
        text = read_document_text(document)
        time.sleep(0.04)
        fields = parse_fields(text)
        confidence = 0.96 if "handwritten" not in text.lower() else 0.9
        input_tokens = estimate_tokens(text) + 420
        output_tokens = estimate_tokens(str(fields))
        return ExtractionResult(
            document_id=document.document_id,
            document_type=document.document_type,
            fields=fields,
            confidence=confidence,
            normalized_json_valid=required_fields_present(fields),
            usage=Usage(
                api_calls=1,
                pages=document.pages,
                images=document.pages,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
            provider=self.provider,
            raw_text=text,
            metadata={"mode": "dry_run", "method": "direct_vlm"},
        )


class MockOCRAdapter(BaseAdapter):
    def extract(self, document: DocumentInput) -> ExtractionResult:
        text = read_document_text(document)
        time.sleep(0.025)
        noisy_text = text
        confidence = 0.91
        warnings: list[str] = []
        if "handwritten" in text.lower():
            noisy_text = noisy_text.replace("Total:", "T0tal:")
            confidence = 0.72
            warnings.append("Simulated OCR uncertainty for handwritten document.")
        return ExtractionResult(
            document_id=document.document_id,
            document_type=document.document_type,
            fields={"ocr_text": noisy_text},
            confidence=confidence,
            normalized_json_valid=True,
            usage=Usage(api_calls=1, pages=document.pages),
            provider=self.provider,
            raw_text=noisy_text,
            warnings=warnings,
            metadata={"mode": "dry_run", "method": "ocr_api"},
        )


class MockLLMAdapter(BaseAdapter):
    def extract_text(self, document: DocumentInput, text: str, upstream_confidence: float) -> ExtractionResult:
        time.sleep(0.03)
        fields = parse_fields(text)
        valid = required_fields_present(fields)
        confidence = min(0.95, upstream_confidence + 0.03) if valid else min(0.78, upstream_confidence)
        input_tokens = estimate_tokens(text) + 180
        output_tokens = estimate_tokens(str(fields))
        return ExtractionResult(
            document_id=document.document_id,
            document_type=document.document_type,
            fields=fields,
            confidence=confidence,
            normalized_json_valid=valid,
            usage=Usage(api_calls=1, input_tokens=input_tokens, output_tokens=output_tokens),
            provider=self.provider,
            raw_text=text,
            warnings=[] if valid else ["Required fields missing after OCR to LLM extraction."],
            metadata={"mode": "dry_run", "method": "llm_structuring"},
        )

    def extract(self, document: DocumentInput) -> ExtractionResult:
        text = read_document_text(document)
        return self.extract_text(document, text, 0.9)


class MockCloudHostedOCRAdapter(BaseAdapter):
    def extract(self, document: DocumentInput) -> ExtractionResult:
        text = read_document_text(document)
        time.sleep(0.035)
        fields = parse_fields(text)
        if "daily_report" in document.document_type:
            fields["processing_notes"] = "Hosted open-source OCR/model returned structured report fields."
        confidence = 0.88 if required_fields_present(fields) else 0.66
        return ExtractionResult(
            document_id=document.document_id,
            document_type=document.document_type,
            fields=fields,
            confidence=confidence,
            normalized_json_valid=required_fields_present(fields),
            usage=Usage(api_calls=1, pages=document.pages, inference_seconds=0.35, gpu_seconds=0.0),
            provider=self.provider,
            raw_text=text,
            warnings=[] if confidence >= 0.8 else ["Cloud-hosted model returned low-confidence extraction."],
            metadata={"mode": "dry_run", "method": "cloud_hosted_open_source"},
        )
