# Web console and complete-cost worksheet

## Start locally

Use Python 3.10+ and install the project following RUN_GUIDE.md. Copy `.env.cloud.example` to `.env`
and fill the fields available to you. Start from the project directory:

```sh
python -m eastco_benchmark.web
```

Open http://127.0.0.1:8765. Upload SampleData.zip, select dry/live and a method, and run.
Connections & costs accepts the same settings as `.env`. Blank browser fields preserve server
settings. Model names can be changed separately for vision and text. Keys entered in the browser
are held only for the run, never saved to browser storage or returned in results. Password inputs
are cleared after dispatch. Download settings is an explicit exception: it creates a private .env
file containing the values still entered on screen. Configure durable credentials on the server.

Results include a comparison table, costs, accuracy, speed, failures, fallbacks, provider usage,
and downloads of summary JSON and per-submission JSONL. Billing refresh does not repeat inference.
Uploads are chunked below Cloud Run's HTTP/1 request limit. The full ZIP limit is 500 MB; expanded
archive limit is 2 GB. Each browser session owns its runs. One benchmark runs at a time; others queue.
Uploaded ZIPs are deleted when their jobs finish. Results expire after four hours on the next request;
delete a completed run immediately using Delete run. Results are not durable across server restarts.

## Cost settings to collect from your manager

All of the following have fields in `.env.cloud.example` and the web interface:

| Settings | Purpose |
| --- | --- |
| GEMINI_API_KEY, GEMINI_VLM_MODEL, GEMINI_LLM_MODEL | AI Studio credentials and exact model IDs |
| PADDLE_OCR_URL, PADDLE_VL_URL, corresponding TOKEN fields | Deployed OCR origins and optional ID tokens |
| COST_CURRENCY | Currency used consistently for all estimated rates and overhead |
| VLM/LLM_INPUT/OUTPUT_PER_MILLION | Contract token rates per million tokens |
| OCR_ACTIVE_PER_SECOND, VL_ACTIVE_PER_SECOND | Allocated combined active CPU, memory and GPU rate |
| IDLE_COST, STORAGE_COST, NETWORK_COST, LOGGING_COST | Entire-run overhead allocations, excluding active charges already priced |
| BUILD_COST, OTHER_COST, TAX_COST | Additional entire-run allocations; explicit zero if not applicable |
| BILLING_QUERY_PROJECT, BILLING_TABLE, BILLING_LOCATION | BigQuery project, project.dataset.table, dataset location |
| BILLING_PROJECT_IDS | Comma-separated billed projects, including Gemini and hosting projects |
| BILLING_SCOPE | dedicated or shared |
| BILLING_ALLOCATION_FRACTION | Shared-project charge fraction between 0 and 1; blank leaves it unallocated |
| BILLING_START, BILLING_END | Optional allocation window as timezone-aware ISO timestamps |
| BILLING_ACCESS_TOKEN | Optional short-lived OAuth access token; otherwise server ADC |
| BILLING_AUTO_REFRESH | true to query billing after each live run |

No current provider prices are invented. Environment prices override JSON pricing for their stage.
Missing prices/usage/overhead keep the total unknown. Complete configured estimates include every
listed category, with overhead allocated among compared methods by measured method wall time.
This is a declared allocation convention, not proof that a method caused those infrastructure charges.
Cached usage, token tiers and provider-specific discounts still require billing reconciliation.

## What billing reconciliation does and does not establish

Uses standard or detailed Cloud Billing export to query all services for the selected projects and time
window. Reads cost, credits, currency, service and export timestamp. Cost is reported before credits,
credits separately, and net. Mixed currencies are never summed. Charges spanning the window boundary
are allocated proportionally by overlap time. Shared-project scope requires your chosen allocation
fraction before an allocated net is shown. Dedicated scope allocates 100% of selected-project charges.

Exports are delayed: empty results mean pending, not zero. All returned charges remain provisional;
the system cannot certify that late charges have all arrived. Invoice-level/projectless taxes or
adjustments, charges outside the selected projects/window, or billing exports enabled too late may be
missing. Billing totals are shown alongside estimates, NEVER added to them. Billing does not provide
per-request attribution or reliable per-method actuals. A longer explicit window can include idle time.
Query costs occur after the queried run and can appear in a later refresh. Queries have a configurable
bytes-billed cap (1 GB default). No billing-account-wide permission is required if a dataset reader is
granted access: the caller needs BigQuery Job User on the query project and Data Viewer on the export.
Cloud Run invocation separately needs Run Invoker on each OCR service.

CLI billing refresh:

```sh
python -m eastco_benchmark.billing_cli results/RUN_ID/summary.json
```

Google references:
- https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery
- https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
- https://docs.cloud.google.com/run/quotas

## Deploy the web console to Cloud Run

No deployment has been performed. This project needs your Google Cloud project, registry, region,
service account and billing permissions first. Build Dockerfile.web with your preferred container
builder and push it to your Artifact Registry. Do not include .env or datasets in the image.
Use Secret Manager for WEB_PASSWORD and GEMINI_API_KEY. WEB_PASSWORD must be at least 16 characters
when the app binds externally. The console should also remain behind Cloud Run IAM; access it through
an authenticated proxy or your organization's access gateway. Use HTTPS and WEB_SECURE_COOKIE=true.

This is a single-instance pilot, not a durable multi-user job platform. Configure one warm instance,
maximum one instance, session affinity and instance-based CPU allocation (no CPU throttling), because
jobs continue after the HTTP response. Allow sufficient RAM for ZIPs and benchmark subprocesses.
Example once your image and secrets exist:

```sh
gcloud run deploy eastco-benchmark --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/eastco-web:demo --region REGION --service-account ACCOUNT@PROJECT.iam.gserviceaccount.com --cpu 2 --memory 4Gi --min-instances 1 --max-instances 1 --no-cpu-throttling --session-affinity --timeout 3600 --no-allow-unauthenticated --set-env-vars WEB_HOST=0.0.0.0,WEB_SECURE_COOKIE=true --set-secrets WEB_PASSWORD=eastco-web-password:latest,GEMINI_API_KEY=eastco-gemini-key:latest
```

The authenticated caller also needs Run Invoker on the web service. Cloud Run restarts can lose
in-progress jobs/results; download results promptly. Warm-instance web hosting has a cost even when
no benchmark runs. Include it in your overhead allocation and billed project selection.
