# East.Co cloud submission benchmark

This is the current entry point. The original text-fixture modules and results are legacy examples.
Inference runs only through Gemini AI Studio and deployed Cloud Run services. Local code imports,
groups, validates and scores data; it does not load an OCR or AI model.

## Setup

From this project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.cloud.example .env
```

Edit the placeholders in `.env`. The application automatically loads it; existing exported variables win.
The example Flash model is configurable; confirm it is available to your AI Studio account.
Set separate VLM/LLM models to compare alternatives. Do not commit credentials.

```sh
python -m eastco_benchmark.app --input /path/to/SampleData.zip --inspect
python -m eastco_benchmark.app --input /path/to/SampleData.zip --mode dry
python -m eastco_benchmark.app --mode live --method 1 --date 20260801 --limit 2
python -m eastco_benchmark.app --mode live --method 3
python -m eastco_benchmark.app --mode live --method 4
python -m eastco_benchmark.app --mode live --method 5
python -m eastco_benchmark.app --mode live --method all --repeat 3 --concurrency 2
```

`INPUT_ZIP` supplies the input when `--input` is omitted. Dry mode never sends data or copies reference
answers: it returns null fields and excludes accuracy. Dry timings measure orchestration only.
Live mode fails clearly on missing settings; it never silently switches to mock processing.

## Input contract

The supported real input is the supplied ZIP layout: date folders beginning YYYYMMDD, JPEG/PNG files
named TENANT_SEQUENCE_..., one daily reference PDF per date, and the mapping XLSX. Receipt PDFs as
inference inputs and arbitrary folder layouts are not yet supported. ZIP files are read in memory without
extracting archive paths; uncompressed size is capped at 2 GB. The sample contains 60 submissions and
141 images. All related images are processed together. Each output has exactly eleven fields, each
containing integer `value` or null and text `evidence`. Missing is not zero. No coordinates are invented.

The importer retains tenant labels, payment-category mappings and notes from the workbook. The PDF
reference values are never included in model prompts. VERIFIED_DATES defaults to 20260801 according
to this sample's workbook; change it for a different dataset. August 14/15 comparisons are discrepancies,
not accuracy scores. Versioned source hashes and mapping snapshots are stored in the run summary.

## Pipeline behavior

1. Gemini receives all receipt images and the tenant mapping, returning schema-constrained JSON.
3. Cloud Run PaddleOCR (Japanese recognition) reads every image; Gemini structures the OCR text.
4. Cloud Run PaddleOCR-VL reads images; conservative exact-label normalization produces the schema.
   This baseline deliberately leaves ambiguous/multi-register aggregation null. It does not have Gemini's
   semantic interpretation and must not be described as equally capable extraction.
5. Method 3 runs first. Missing evidence/fields, a gross-tax-deductions/net discrepancy, or primary errors
   cause Gemini vision fallback. The score is completeness, not calibrated probability. OCR confidence
   is preserved in OCR responses but is not currently a calibrated routing signal. Fallback can still
   require review. Primary extraction and fallback reason are retained.

## One-time Cloud Run deployment

The client expects the included `cloud/server.py` contract: POST /predict with base64 `image` and
`mime_type`; response has `text`, `recognition_scores`, `model` and `usage`. An arbitrary Paddle endpoint
will need a matching adapter. Deploy the included image twice with BACKEND=ocr and BACKEND=vl.
The Docker recipe is a deployment starting point; GPU image/model compatibility must be tested in
your cloud project. No cloud resources have been created, and no container build or live inference has
been verified in this workspace. Paddle model weights download on first request; allow cold-start time.

Example commands (replace uppercase placeholders; require billing, APIs, GPU quota and an Artifact
Registry repository). Run from this project directory:

```sh
gcloud builds submit cloud --tag REGION-docker.pkg.dev/PROJECT/REPOSITORY/eastco-paddle:demo
gcloud run deploy eastco-ocr --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/eastco-paddle:demo --region REGION --gpu 1 --gpu-type nvidia-l4 --cpu 4 --memory 16Gi --concurrency 1 --timeout 600 --no-allow-unauthenticated --set-env-vars BACKEND=ocr
gcloud run deploy eastco-vl --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/eastco-paddle:demo --region REGION --gpu 1 --gpu-type nvidia-l4 --cpu 4 --memory 16Gi --concurrency 1 --timeout 600 --no-allow-unauthenticated --set-env-vars BACKEND=vl
```

Set each returned HTTPS service origin in `.env`. Grant your caller `roles/run.invoker`. Provide
short-lived audience-specific ID tokens via PADDLE_OCR_TOKEN/PADDLE_VL_TOKEN, or leave them empty
when running with Google service-account application default credentials capable of minting ID tokens.
An AI Studio key does not authenticate Cloud Run. Tokens expire; use service-account credentials for
long runs. Request timeout is configurable; cold model loading may exceed the default 180 seconds.

## Results and pricing

Each run writes results/TIMESTAMP/summary.json and details.jsonl. Details record every request attempt,
HTTP status, latency, exposed usage, retries, partial known costs, extraction, review flags and comparisons.
Models and settings are recorded without credentials. Failed attempts can have unknown charges; total
cost stays null if any attempt cost is unknown. Pricing is per actual stage, not pooled across stages.
Fill `pricing.live.json` with your contract rates per single token or inference second. Null means unknown.
Use one currency consistently. Output tokens include exposed thinking tokens. Cached token count is
retained; the simple input rate does not implement cache discounts or token-volume pricing tiers.

Cloud inference seconds measure server elapsed processing including initial model loading, not billed
GPU allocation. Idle capacity, startup outside the handler, memory/CPU, network, storage and minimum
billing durations require cloud billing reconciliation. No CPU/RAM/GPU utilization monitoring is included.

Throughput uses actual wall time for the selected concurrency. p95 is nearest-rank; small datasets do not
establish tail performance. Failures count as incorrect on verified reference records; missing references
are excluded and scored counts are reported. Repeated submissions are repeated measurements, not
new independent accuracy examples. Dry-run comparisons are not provider benchmarks.

```sh
python -m unittest discover -s tests -v
```

API references: https://ai.google.dev/api/generate-content and
https://github.com/PaddlePaddle/PaddleOCR/tree/main/docs/version3.x/pipeline_usage
