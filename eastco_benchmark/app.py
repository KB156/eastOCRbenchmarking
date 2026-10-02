import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import statistics
import time
import shlex
from .dataset import FIELDS, read_dataset
from .providers import Remote
from .costing import environment_prices, estimate, refresh_billing


def load_dotenv():
    """Load literal KEY=value settings; never execute shell expressions."""
    path = Path('.env')
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key.strip()):
            raise ValueError('Invalid .env assignment')
        tokens = shlex.split(value, comments=True)
        os.environ.setdefault(key.strip(), ' '.join(tokens))


def normalize_ocr(pages, mapping):
    """Conservative normalization; ambiguous register arithmetic remains null."""
    result = {}
    for key, label in FIELDS.items():
        labels = {label}
        alias = mapping.get('labels', {}).get(key)
        if alias and '\n' not in str(alias):
            labels.add(str(alias))
        found = []
        for page in pages:
            for line in page['text'].splitlines():
                for label in labels:
                    match = re.fullmatch(re.escape(label) + r'\s*[:：]?\s*[¥￥]?\s*(-?[\d,]+)\s*(?:円|人|客|名)?', line.strip())
                    if match:
                        found.append((int(match[1].replace(',', '')), page['source'], line))
                        break
        result[key] = {'value': found[0][0] if len(found) == 1 else None,
                       'evidence': json.dumps(found, ensure_ascii=False) if found else 'No unambiguous match'}
    return result


def quality(extraction):
    complete = sum(v['value'] is not None and bool(v['evidence']) for v in extraction.values()) / len(FIELDS)
    v = {k: x['value'] for k, x in extraction.items()}
    issues = []
    if v['customer_count'] is not None and v['customer_count'] < 0:
        issues.append('Negative customer count')
    if all(v[k] is not None for k in ('gross_sales', 'consumption_tax', 'sales_deductions', 'net_sales')):
        if v['gross_sales'] - v['consumption_tax'] - v['sales_deductions'] != v['net_sales']:
            issues.append('Gross minus tax and deductions differs from net; review tenant accounting')
    return {'completeness': complete, 'issues': issues, 'needs_review': complete < 1 or bool(issues)}


def run_one(s, method, dry, pricing, verified):
    calls = []
    remote = Remote(calls, pricing)
    started = time.perf_counter()
    row = {'submission_id': s['id'], 'method': method, 'mode': 'mock' if dry else 'live',
           'images': len(s['images']), 'calls': calls, 'failed': False, 'fallback_used': False, 'extraction': None}
    try:
        if dry:
            extraction = {k: {'value': None, 'evidence': 'Dry run: no inference performed'} for k in FIELDS}
            row['fallback_used'] = method == '5'
        elif method == '1':
            extraction = remote.gemini(s, images=True)
        elif method == '4':
            extraction = normalize_ocr(remote.ocr(s, vl=True), s['mapping'])
        else:
            error = None
            try:
                extraction = remote.gemini(s, ocr=remote.ocr(s))
            except Exception as exc:
                if method != '5':
                    raise
                error, extraction = type(exc).__name__, None
            assessment = quality(extraction) if extraction else None
            if method == '5' and (error or assessment['needs_review'] or assessment['completeness'] < float(os.getenv('HYBRID_THRESHOLD', '1'))):
                row.update(primary_extraction=extraction, fallback_reason=error or assessment, fallback_used=True)
                extraction = remote.gemini(s, images=True)
        row['extraction'] = extraction
        row['quality'] = quality(extraction)
    except Exception as exc:
        row.update(failed=True, error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
    row['latency_ms'] = round((time.perf_counter() - started) * 1000, 2)
    row['retries'] = sum(c['attempt'] > 1 for c in calls)
    costs = [c['cost'] for c in calls if c['cost'] is not None]
    row['known_cost'] = sum(costs)
    row['cost'] = sum(costs) if calls and len(costs) == len(calls) else None
    row['reference_status'] = 'verified' if s['date'] in verified else 'unverified'
    if s['reference'] and not dry:
        predicted = row['extraction'] or {}
        row['comparison'] = {k: {'expected': v, 'actual': predicted.get(k, {}).get('value'),
                                 'match': predicted.get(k, {}).get('value') == v} for k, v in s['reference'].items()}
        if s['date'] in verified:
            row['accuracy'] = sum(v['match'] for v in row['comparison'].values()) / len(FIELDS)
    return row


def preflight(methods):
    required = set()
    if set(methods) & {'1', '3', '5'}:
        required.add('GEMINI_API_KEY')
    if set(methods) & {'1', '5'}:
        required.add('GEMINI_VLM_MODEL')
    if set(methods) & {'3', '5'}:
        required.update(('GEMINI_LLM_MODEL', 'PADDLE_OCR_URL'))
    if '4' in methods:
        required.add('PADDLE_VL_URL')
    missing = [k for k in sorted(required) if not os.getenv(k) or 'REPLACE' in os.getenv(k, '')]
    if missing:
        raise ValueError('Set environment variables: ' + ', '.join(missing))
    for k in required & {'PADDLE_OCR_URL', 'PADDLE_VL_URL'}:
        if not re.fullmatch(r'https://[A-Za-z0-9.-]+\.run\.app', os.environ[k]):
            raise ValueError(k + ' must be a Cloud Run HTTPS origin (*.run.app)')


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description='East.Co tenant/day cloud benchmark')
    p.add_argument('--input', default=os.getenv('INPUT_ZIP'))
    p.add_argument('--method', choices=['all', '1', '3', '4', '5'], default='all')
    p.add_argument('--mode', choices=['dry', 'live'], default=os.getenv('BENCHMARK_MODE', 'dry'))
    p.add_argument('--date', help='YYYYMMDD')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--repeat', type=int, default=1)
    p.add_argument('--concurrency', type=int, default=1)
    p.add_argument('--inspect', action='store_true')
    args = p.parse_args()
    if not args.input or args.repeat < 1 or args.concurrency < 1 or args.limit < 0:
        p.error('Provide input ZIP, positive repeat/concurrency, nonnegative limit')
    data = read_dataset(args.input)
    if args.date:
        data = [s for s in data if s['date'] == args.date]
    if args.limit:
        data = data[:args.limit]
    if not data:
        p.error('No matching tenant/date submissions')
    inventory = [{'id': s['id'], 'images': len(s['images']), 'has_mapping': bool(s['mapping']),
                  'has_reference': s['reference'] is not None} for s in data]
    if args.inspect:
        print(json.dumps(inventory, indent=2))
        return
    methods = ['1', '3', '4', '5'] if args.method == 'all' else [args.method]
    if args.mode == 'live':
        preflight(methods)
    path = Path(os.getenv('PRICING_FILE', 'pricing.live.json'))
    pricing = environment_prices(json.loads(path.read_text()) if path.exists() else {})
    for stage, rates in pricing.items():
        if not stage.startswith('_') and any(v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0) for v in rates.values()):
            raise ValueError('Prices must be nonnegative numeric values or null')
    verified = set(os.getenv('VERIFIED_DATES', '20260801').split(','))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = Path(os.getenv('RESULTS_DIR', 'results')) / run_id
    output.mkdir(parents=True)
    summary = {'run_id': run_id, 'started_at': datetime.now(timezone.utc).isoformat(), 'mode': args.mode, 'repeat': args.repeat, 'concurrency': args.concurrency,
               'pricing': pricing, 'verified_dates': sorted(verified),
               'models': {k: os.getenv(k) for k in ('GEMINI_VLM_MODEL', 'GEMINI_LLM_MODEL')},
               'dataset': [{**i, 'mapping': s['mapping'], 'sources': [{k: im[k] for k in ('name', 'sha256')} for im in s['images']]} for i, s in zip(inventory, data)],
               'methods': {}}
    with (output / 'details.jsonl').open('w') as handle:
        for method in methods:
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                rows = list(pool.map(lambda s: run_one(s, method, args.mode == 'dry', pricing, verified), data * args.repeat))
            elapsed = time.perf_counter() - start
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            latency = sorted(r['latency_ms'] for r in rows)
            accuracy = [r['accuracy'] for r in rows if 'accuracy' in r]
            costs = [r['cost'] for r in rows if r['cost'] is not None]
            summary['methods'][method] = {'submissions': len(rows), 'failures': sum(r['failed'] for r in rows),
                'image_count': sum(r['images'] for r in rows),
                'needs_review': sum(r.get('quality', {}).get('needs_review', True) for r in rows),
                'latency_p50_ms': statistics.median(latency), 'latency_p95_ms': latency[math.ceil(.95 * len(latency)) - 1],
                'throughput_successful_submissions_per_second': sum(not r['failed'] for r in rows) / elapsed,
                'wall_seconds': elapsed, 'cost_per_submission': sum(costs) / len(rows) if len(costs) == len(rows) else None,
                'known_cost': sum(r['known_cost'] for r in rows), 'accuracy': statistics.mean(accuracy) if accuracy else None,
                'scored_submissions': len(accuracy), 'fallbacks': sum(r['fallback_used'] for r in rows),
                'retries': sum(r['retries'] for r in rows), 'api_attempts': sum(len(r['calls']) for r in rows)}
            usage = {}
            for row in rows:
                for call in row['calls']:
                    stage = usage.setdefault(call['stage'], {})
                    for key, value in call['usage'].items():
                        if isinstance(value, (int, float)):
                            stage[key] = stage.get(key, 0) + value
            summary['methods'][method]['observed_usage_by_stage'] = usage
            if args.mode == 'dry':
                for key in ('latency_p50_ms', 'latency_p95_ms', 'throughput_successful_submissions_per_second'):
                    summary['methods'][method][key] = None
    summary['finished_at'] = datetime.now(timezone.utc).isoformat()
    summary['cost_report'] = estimate(summary)
    if args.mode == 'live' and os.getenv('BILLING_AUTO_REFRESH', 'false').lower() == 'true':
        try:
            summary['billing'] = refresh_billing(summary)
        except Exception as exc:
            summary['billing'] = {'status': 'unavailable', 'message': type(exc).__name__}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({'results': str(output.resolve()), 'summary': summary['methods']}, indent=2))


if __name__ == '__main__':
    main()
