# East.Co OCR Benchmark Demo

**Web console:** [WEB_APP.md](WEB_APP.md). Run `python -m eastco_benchmark.web` and open
http://127.0.0.1:8765 to upload a ZIP, enter connection/cost settings and view results.

**Current cloud implementation:** see [RUN_GUIDE.md](RUN_GUIDE.md) and use `.env.cloud.example`.
Run `python -m eastco_benchmark.app --input /path/to/SampleData.zip --mode dry`.
The sections below describe the original synthetic-text prototype, retained for historical context.

This is a runnable demo framework for comparing East.Co document-processing alternatives using the same input documents, normalized output schema, metrics, and cost hooks.

It implements the four cloud/API methods requested:

1. **Method 1: Direct VLM API**
   - Document image/PDF/text fixture -> vision-language model -> normalized JSON.
   - Intended providers: OpenAI, Gemini, Claude, or similar VLM APIs.

2. **Method 3: OCR API -> LLM API**
   - Document -> managed OCR/document API -> extracted text -> LLM -> normalized JSON.
   - Intended providers: Textract, Google Cloud Vision/Document AI, Azure Document Intelligence, Mistral OCR plus an LLM.

3. **Method 4: Open-source OCR/model hosted on cloud inference**
   - Document -> cloud-hosted endpoint -> normalized JSON.
   - Intended hosting: SageMaker, Vertex AI, Azure ML, Cloud Run, or a managed container endpoint serving PaddleOCR, docTR, Tesseract, LayoutLM-style extraction, etc.

4. **Method 5: Confidence-based hybrid router**
   - Primary path: cheaper OCR API -> LLM.
   - Fallback path: direct VLM.
   - If confidence is low or required fields are missing, the router falls back to VLM and records that fallback in the results.

Local and on-premises inference are intentionally excluded.

## What The Demo Measures

Each run produces a detailed JSONL file and a summary JSON file containing:

- estimated cost per document and total estimated cost
- latency p50, p95, and mean
- throughput in documents per second
- API call, page, image, token, inference-second, and GPU-second usage
- retries and failures
- field-level extraction accuracy against ground truth
- normalized JSON validity
- hybrid fallback rate

Provider pricing is **not hardcoded**. The included `pricing.example.json` sets all prices to zero and is clearly marked as an example. Replace it with current provider or contract pricing before using the cost numbers for decisions.

## Project Structure

```text
eastco_ocr_benchmark/
  eastco_benchmark/
    adapters/        # provider boundaries: VLM, OCR, LLM, hosted cloud model
    pipelines/       # method 1, 3, 4, and 5 orchestration
    benchmark/       # runner, cost, accuracy, and metrics
    cli.py           # command-line entry point
  data/
    documents/       # synthetic fixture documents
    ground_truth.jsonl
  results/           # generated benchmark results
  .env.example
  pricing.example.json
```

## Quick Start

From this folder:

```bash
python -m eastco_benchmark.cli --pipeline all
```

The demo uses mock/dry-run adapters by default, so it runs without API credentials.

List available pipelines:

```bash
python -m eastco_benchmark.cli --list-pipelines
```

Run only one method:

```bash
python -m eastco_benchmark.cli --pipeline method_1_direct_vlm
python -m eastco_benchmark.cli --pipeline method_3_ocr_api_then_llm
python -m eastco_benchmark.cli --pipeline method_4_cloud_hosted_open_source
python -m eastco_benchmark.cli --pipeline method_5_confidence_hybrid
```

Run multiple methods:

```bash
python -m eastco_benchmark.cli \
  --pipeline method_1_direct_vlm \
  --pipeline method_5_confidence_hybrid
```

## Configuration

Copy `.env.example` to `.env` if you want to manage settings that way, or export environment variables directly:

```bash
export EASTCO_DRY_RUN=true
export EASTCO_HYBRID_CONFIDENCE_THRESHOLD=0.88
export EASTCO_PRICING_CONFIG=pricing.example.json
python -m eastco_benchmark.cli --pipeline all
```

Important variables:

| Variable | Purpose |
| --- | --- |
| `EASTCO_DRY_RUN` | Use mock adapters when true. Defaults to true. |
| `EASTCO_DATASET_DIR` | Folder containing input documents. |
| `EASTCO_GROUND_TRUTH` | JSONL file containing expected fields. |
| `EASTCO_PRICING_CONFIG` | Pricing config used by cost hooks. |
| `EASTCO_MAX_RETRIES` | Retry attempts per document and pipeline. |
| `EASTCO_HYBRID_CONFIDENCE_THRESHOLD` | Minimum primary confidence before hybrid fallback is skipped. |
| `VLM_API_KEY`, `OCR_API_KEY`, `LLM_API_KEY`, `CLOUD_OCR_API_KEY` | Optional credentials for real adapters. |

## Results Format

The summary file looks like this:

```json
{
  "run_id": "20261003-120000",
  "dry_run": true,
  "pricing_note": "Example only...",
  "pipelines": ["method_1_direct_vlm"],
  "summary": {
    "method_1_direct_vlm": {
      "documents": 3,
      "successes": 3,
      "failures": 0,
      "latency_ms_p50": 40.5,
      "latency_ms_p95": 41.2,
      "throughput_docs_per_second": 24.0,
      "estimated_total_cost": 0.0,
      "estimated_cost_per_document": 0.0,
      "field_accuracy_mean": 1.0,
      "fallback_rate": 0.0,
      "usage": {
        "api_calls": 3,
        "pages": 3,
        "images": 3,
        "input_tokens": 1500,
        "output_tokens": 200,
        "inference_seconds": 0.0,
        "gpu_seconds": 0.0
      }
    }
  }
}
```

The details JSONL file has one record per pipeline-document pair. It includes the normalized extracted JSON, usage, warnings, route metadata, retry count, latency, cost, and field-level accuracy.

## Where To Add Real API Calls

The real provider integration points are intentionally isolated:

- `eastco_benchmark/adapters/vlm.py`
- `eastco_benchmark/adapters/ocr.py`
- `eastco_benchmark/adapters/llm.py`
- `eastco_benchmark/adapters/hosted.py`

When implementing a provider, keep the adapter contract the same:

- return `ExtractionResult`
- map provider usage into `Usage`
- preserve raw OCR text when available
- keep all providers producing the same normalized `fields` JSON
- keep pricing outside code in a config file

This lets the benchmark compare architectures without changing the runner or result format.

## Normalized Output Schema

Each pipeline returns:

```json
{
  "document_id": "receipt__client_a_001",
  "document_type": "receipt",
  "fields": {
    "client_id": "EAST-A001",
    "document_date": "2026-09-28",
    "merchant_or_site": "Tokyo Office Supplies",
    "total_amount": 12400.0,
    "currency": "JPY",
    "summary": "Office consumables receipt for monthly reimbursement.",
    "line_items": [
      {"description": "printer paper", "quantity": 4.0, "amount": 4800.0}
    ]
  },
  "confidence": 0.96,
  "usage": {},
  "provider": "mock_direct_vlm"
}
```

## Suggested Next Step

Replace one mock adapter at a time with a real provider and run the same fixture set:

1. Start with direct VLM because it has the simplest flow.
2. Add one OCR API and one LLM API for Method 3.
3. Add one hosted endpoint for Method 4.
4. Tune the hybrid threshold and compare fallback rate, accuracy, and cost per successful document.
