"""Explicit estimates and separately reported, delayed billing-export allocations."""
from datetime import datetime, timezone
import json
import math
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

OVERHEAD = ('IDLE_COST', 'STORAGE_COST', 'NETWORK_COST', 'LOGGING_COST',
            'BUILD_COST', 'OTHER_COST', 'TAX_COST')
RATE_KEYS = {
    'gemini_vlm': ('VLM_INPUT_PER_MILLION', 'VLM_OUTPUT_PER_MILLION'),
    'gemini_llm': ('LLM_INPUT_PER_MILLION', 'LLM_OUTPUT_PER_MILLION')}


def number(env, key):
    value = env.get(key, '').strip()
    if not value or value.startswith('REPLACE'):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{key} must be a finite nonnegative number')
    return value


def environment_prices(pricing, env=None):
    env = os.environ if env is None else env
    prices = json.loads(json.dumps(pricing))
    for stage, keys in RATE_KEYS.items():
        if any(env.get(k, '').strip() for k in keys):
            prices[stage] = {metric: None if number(env, key) is None else number(env, key) / 1_000_000
                             for metric, key in zip(('input_tokens', 'output_tokens'), keys)}
    for stage, key in [('paddle_ocr', 'OCR_ACTIVE_PER_SECOND'), ('paddle_vl', 'VL_ACTIVE_PER_SECOND')]:
        if env.get(key, '').strip():
            prices[stage] = {'inference_seconds': number(env, key)}
    return prices


def estimate(summary, env=None):
    env = os.environ if env is None else env
    result = {'currency': env.get('COST_CURRENCY', 'USD'), 'status': 'incomplete',
              'basis': 'Configured rates and overhead allocations; not an invoice', 'methods': {}}
    overhead = {key.lower(): number(env, key) for key in OVERHEAD}
    result['overhead_for_entire_run'] = overhead
    missing = [k for k, value in overhead.items() if value is None]
    result['missing_overhead'] = missing
    result['allocation_rule'] = 'Entire-run overhead allocated by each method wall time'
    total_time = sum(m['wall_seconds'] for m in summary['methods'].values())
    total = 0
    for method, values in summary['methods'].items():
        direct = values['cost_per_submission']
        direct = direct * values['submissions'] if direct is not None else None
        fraction = values['wall_seconds'] / total_time if total_time else 0
        allocated = sum(v for v in overhead.values() if v is not None) * fraction
        complete = direct is not None and not missing and summary['mode'] == 'live'
        cost = direct + allocated if complete else None
        result['methods'][method] = {'processing_estimate': direct,
            'known_processing_cost': values['known_cost'], 'allocated_known_overhead': allocated,
            'estimated_total': cost, 'estimated_per_submission': cost / values['submissions'] if cost is not None else None,
            'estimated_per_image': cost / values['image_count'] if cost is not None and values.get('image_count') else None}
        if cost is not None:
            total += cost
    complete = bool(result['methods']) and all(m['estimated_total'] is not None for m in result['methods'].values())
    result['status'] = 'estimate_complete' if complete else ('dry_run' if summary['mode'] == 'dry' else 'incomplete')
    result['estimated_total'] = total if complete else None
    return result


def billing_request(method, url, body, token):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def refresh_billing(summary, env=None):
    env = os.environ if env is None else env
    table = env.get('BILLING_TABLE', '').strip()
    project = env.get('BILLING_QUERY_PROJECT', '').strip()
    projects = [p.strip() for p in env.get('BILLING_PROJECT_IDS', '').split(',') if p.strip()]
    if not table or not project or not projects:
        return {'status': 'not_configured', 'message': 'Set billing table, query project and billed project IDs.'}
    if not re.fullmatch(r'[\w-]+\.[\w]+\.[\w]+', table) or not re.fullmatch(r'[\w-]+', project):
        raise ValueError('Invalid BigQuery table or project identifier')
    start = env.get('BILLING_START', '').strip() or summary['started_at']
    end = env.get('BILLING_END', '').strip() or summary['finished_at']
    times = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in (start, end)]
    if any(t.tzinfo is None for t in times) or times[0] >= times[1]:
        raise ValueError('Billing interval requires timezone-aware start before end')
    if (times[1] - times[0]).days > 32:
        raise ValueError('Billing interval must not exceed 32 days')
    token = env.get('BILLING_ACCESS_TOKEN', '').strip()
    if not token:
        import google.auth
        from google.auth.transport.requests import Request as AuthRequest
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        credentials.refresh(AuthRequest())
        token = credentials.token
    # Standard and detailed export schemas both expose these fields. Parameters protect values;
    # the only interpolated identifier is strictly validated above.
    query = f'''WITH charges AS (
      SELECT service.description AS service, currency, cost,
        IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0) AS credits,
        export_time,
        SAFE_DIVIDE(TIMESTAMP_DIFF(LEAST(usage_end_time,@finish),GREATEST(usage_start_time,@start),MICROSECOND),
          TIMESTAMP_DIFF(usage_end_time,usage_start_time,MICROSECOND)) AS fraction
      FROM `{table}`
      WHERE project.id IN UNNEST(@projects)
        AND usage_start_time < @finish AND usage_end_time > @start
        AND usage_start_time >= TIMESTAMP_SUB(@start, INTERVAL 32 DAY)
    ) SELECT service,currency, SUM(cost*fraction) AS gross,
       SUM(credits*fraction) AS credits, SUM((cost+credits)*fraction) AS net,
       COUNT(*) AS records, CAST(MAX(export_time) AS STRING) AS latest_export
      FROM charges GROUP BY service,currency ORDER BY service'''
    parameters = [{'name': name, 'parameterType': {'type': 'TIMESTAMP'}, 'parameterValue': {'value': value}}
                  for name, value in [('start', start), ('finish', end)]]
    parameters.append({'name': 'projects', 'parameterType': {'type': 'ARRAY', 'arrayType': {'type': 'STRING'}},
                       'parameterValue': {'arrayValues': [{'value': p} for p in projects]}})
    base = f'https://bigquery.googleapis.com/bigquery/v2/projects/{quote(project, safe="")}'
    signature = {'start': start, 'end': end, 'projects': projects, 'table': table, 'query_project': project,
                 'location': env.get('BILLING_LOCATION', 'US')}
    previous = summary.get('billing', {})
    if previous.get('status') == 'query_pending' and previous.get('signature') == signature and previous.get('job', {}).get('jobId'):
        job = previous['job']
        url = base + '/queries/' + quote(job['jobId'], safe='') + '?timeoutMs=10000&maxResults=10000&location=' + quote(signature['location'], safe='')
        payload = billing_request('GET', url, None, token)
    else:
        payload = billing_request('POST', base + '/queries', {'query': query, 'useLegacySql': False,
            'parameterMode': 'NAMED', 'queryParameters': parameters, 'timeoutMs': 10000, 'maxResults': 10000,
            'location': signature['location'],
            'maximumBytesBilled': str(int(env.get('BILLING_MAX_BYTES', '1000000000')))}, token)
    if payload.get('errors'):
        raise ValueError('Billing query failed; check export schema and query permissions')
    if not payload.get('jobComplete'):
        return {'status': 'query_pending', 'message': 'Billing query is still running. Refresh later.',
                'signature': signature, 'job': payload.get('jobReference', previous.get('job'))}
    if payload.get('pageToken'):
        raise ValueError('Billing result exceeds supported rows; narrow the project scope')
    rows = []
    for row in payload.get('rows', []):
        v = [cell.get('v') for cell in row['f']]
        rows.append({'service': v[0], 'currency': v[1], 'gross': float(v[2] or 0),
                     'credits': float(v[3] or 0), 'net': float(v[4] or 0), 'records': int(v[5]), 'latest_export': v[6]})
    dedicated = env.get('BILLING_SCOPE', 'shared') == 'dedicated'
    allocation = 1.0 if dedicated else number(env, 'BILLING_ALLOCATION_FRACTION')
    if allocation is not None and allocation > 1:
        raise ValueError('Billing allocation fraction must be between zero and one')
    totals = {}
    for row in rows:
        currency = totals.setdefault(row['currency'], {'gross': 0, 'credits': 0, 'net': 0})
        for key in currency:
            currency[key] += row[key]
    return {'status': 'provisional' if rows else 'pending_export', 'start': start, 'end': end,
        'queried_at': datetime.now(timezone.utc).isoformat(), 'projects': projects, 'services': rows,
        'observed_project_totals': totals, 'allocation_fraction': allocation,
        'allocated_net_by_currency': {c: t['net'] * allocation for c, t in totals.items()} if allocation is not None else None,
        'message': 'Exported charges prorated by usage-interval overlap. Delayed or projectless charges may be absent. '
                   'Includes all selected-project services, not isolated request charges. Do not add to estimates.',
        'bytes_processed': payload.get('totalBytesProcessed')}
