"""Single-instance web console; jobs use isolated subprocess environments."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse
from .app import load_dotenv
from .costing import refresh_billing, OVERHEAD, RATE_KEYS

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / 'static'
ALLOWED = {
    'GEMINI_API_KEY', 'GEMINI_VLM_MODEL', 'GEMINI_LLM_MODEL', 'PADDLE_OCR_URL', 'PADDLE_VL_URL',
    'PADDLE_OCR_TOKEN', 'PADDLE_VL_TOKEN', 'MAX_RETRIES', 'REQUEST_TIMEOUT', 'HYBRID_THRESHOLD',
    'VERIFIED_DATES', 'COST_CURRENCY', 'OCR_ACTIVE_PER_SECOND', 'VL_ACTIVE_PER_SECOND',
    'BILLING_TABLE', 'BILLING_QUERY_PROJECT', 'BILLING_PROJECT_IDS', 'BILLING_LOCATION',
    'BILLING_ACCESS_TOKEN', 'BILLING_SCOPE', 'BILLING_ALLOCATION_FRACTION', 'BILLING_START',
    'BILLING_END', 'BILLING_MAX_BYTES', 'BILLING_AUTO_REFRESH', *OVERHEAD,
    *(key for keys in RATE_KEYS.values() for key in keys)}
SECRETS = {'GEMINI_API_KEY', 'PADDLE_OCR_TOKEN', 'PADDLE_VL_TOKEN', 'BILLING_ACCESS_TOKEN'}
JOBS, SESSIONS = {}, {}
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1)
MAX_UPLOAD = 500 * 1024 * 1024
MAX_CHUNK = 8 * 1024 * 1024
TTL = 4 * 3600


def config_values(values):
    if not isinstance(values, dict) or set(values) - ALLOWED:
        raise ValueError('Unknown configuration field')
    if any(not isinstance(v, str) or len(v) > 4096 for v in values.values()):
        raise ValueError('Invalid configuration value')
    return values


def child_environment(settings, directory):
    # Server-side secrets remain on the server; browser blanks preserve configured defaults.
    env = {k: v for k, v in os.environ.items() if k in ALLOWED or k in
           {'PATH', 'HOME', 'SYSTEMROOT', 'SSL_CERT_FILE', 'GOOGLE_APPLICATION_CREDENTIALS'}}
    env.update({k: v for k, v in settings.items() if v.strip()})
    env.update(PYTHONPATH=str(ROOT), RESULTS_DIR=str(directory / 'results'),
               PRICING_FILE=str(ROOT / 'pricing.live.json'), PYTHONUNBUFFERED='1')
    return env


def worker(job, settings, options):
    job['status'] = 'running'
    directory = job['directory']
    command = [sys.executable, '-m', 'eastco_benchmark.app', '--input', str(directory / 'input.zip'),
               '--mode', options['mode'], '--method', options['method'], '--repeat', str(options['repeat']),
               '--concurrency', str(options['concurrency']), '--limit', str(options['limit'])]
    if options.get('date'):
        command += ['--date', options['date']]
    try:
        process = subprocess.Popen(command, cwd=directory, env=child_environment(settings, directory),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        job['process'] = process
        _, stderr = process.communicate(timeout=3600)
        if job['status'] == 'cancelled':
            return
        if process.returncode:
            # Only show known validation failures, never a raw traceback or provider payload.
            last = stderr.decode(errors='replace').strip().splitlines()[-1:] or ['Run failed']
            message = last[0]
            job['error'] = message if message.startswith(('ValueError: Set environment', 'ValueError: Invalid', 'ValueError: Prices', 'ValueError: BILLING')) else 'Run failed. Check dataset format, model names, credentials and endpoint configuration.'
            job['status'] = 'failed'
            return
        summary = next((directory / 'results').glob('*/summary.json'))
        job['summary_path'] = summary
        job['summary'] = json.loads(summary.read_text())
        job['status'] = 'complete'
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        job.update(status='failed', error='Run exceeded the one-hour limit')
    except Exception:
        job.update(status='failed', error='Unable to complete this run')
    finally:
        job.pop('process', None)
        (directory / 'input.zip').unlink(missing_ok=True)
        settings.clear()


def cleanup():
    with LOCK:
        now = time.time()
        for key, job in list(JOBS.items()):
            if now - job['created'] > TTL and job['status'] not in ('running', 'queued'):
                shutil.rmtree(job['directory'], ignore_errors=True)
                del JOBS[key]
        for key, created in list(SESSIONS.items()):
            if now - created > TTL:
                del SESSIONS[key]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value, mime='application/json', extra=None):
        data = json.dumps(value).encode() if mime == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def session(self):
        cookie = cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except cookies.CookieError:
            return None
        token = cookie.get('eastco_session')
        token = token.value if token else None
        return token if token in SESSIONS and time.time() - SESSIONS[token] < TTL else None

    def body(self, limit=65536):
        size = int(self.headers.get('Content-Length', '-1'))
        if size < 0 or size > limit:
            raise ValueError('Request exceeds size limit')
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError('Incomplete upload')
        return data

    def owned_job(self, job_id):
        job = JOBS.get(job_id)
        if not job or job['owner'] != self.session():
            raise KeyError('Run not found')
        return job

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': 'Invalid host'})
        cleanup()
        path = urlparse(self.path).path
        if path in ('/', '/app.js', '/style.css', '/mark.svg'):
            file = STATIC / ('index.html' if path == '/' else path[1:])
            mime = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml'}[file.suffix]
            return self.send(200, file.read_bytes(), mime)
        if not self.session():
            return self.send(401, {'error': 'Sign in required'})
        try:
            if path == '/api/config':
                public = {k: os.environ.get(k, '') for k in ALLOWED - SECRETS}
                return self.send(200, {'values': public, 'configured_secrets': [k for k in SECRETS if os.getenv(k)]})
            parts = path.strip('/').split('/')
            if len(parts) >= 3 and parts[:2] == ['api', 'jobs']:
                job = self.owned_job(parts[2])
                if len(parts) == 4 and parts[3] in ('summary', 'details') and job['status'] == 'complete':
                    file = job['summary_path'] if parts[3] == 'summary' else job['summary_path'].with_name('details.jsonl')
                    return self.send(200, file.read_bytes(), 'application/octet-stream',
                                     {'Content-Disposition': f'attachment; filename="{file.name}"'})
                return self.send(200, {k: job.get(k) for k in ('id', 'status', 'received', 'size', 'error', 'summary')})
            self.send(404, {'error': 'Not found'})
        except KeyError:
            self.send(404, {'error': 'Run not found'})

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def mutate(self):
        # Custom header and same-host origin prevent cross-site requests. No CORS is enabled.
        origin = self.headers.get('Origin')
        if not self.valid_host() or self.headers.get('X-Eastco-Request') != '1' or (origin and urlparse(origin).netloc != self.headers.get('Host')):
            return self.send(403, {'error': 'Invalid request origin'})
        path = urlparse(self.path).path
        try:
            if path == '/api/login':
                body = json.loads(self.body())
                expected = os.getenv('WEB_PASSWORD', '')
                if expected and not hmac.compare_digest(str(body.get('password', '')), expected):
                    return self.send(401, {'error': 'Incorrect password'})
                token = secrets.token_urlsafe(32)
                if len(SESSIONS) >= 1000:
                    return self.send(429, {'error': 'Session limit reached'})
                SESSIONS[token] = time.time()
                secure = '; Secure' if os.getenv('WEB_SECURE_COOKIE') == 'true' else ''
                return self.send(200, {'ok': True}, extra={'Set-Cookie': f'eastco_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={TTL}{secure}'})
            if not self.session():
                return self.send(401, {'error': 'Sign in required'})
            if path == '/api/uploads':
                body = json.loads(self.body())
                size = int(body['size'])
                if not 0 < size <= MAX_UPLOAD:
                    raise ValueError('ZIP must be between 1 byte and 500 MB')
                with LOCK:
                    if len(JOBS) >= 8:
                        raise ValueError('Run capacity reached; delete a previous run')
                    key = secrets.token_hex(16)
                    directory = Path(tempfile.mkdtemp(prefix='eastco-'))
                    JOBS[key] = {'id': key, 'owner': self.session(), 'directory': directory, 'created': time.time(),
                                 'status': 'uploading', 'received': 0, 'size': size, 'lock': threading.Lock()}
                return self.send(200, {'id': key})
            parts = path.strip('/').split('/')
            if len(parts) != 4 or parts[:2] != ['api', 'jobs']:
                return self.send(404, {'error': 'Not found'})
            job = self.owned_job(parts[2])
            action = parts[3]
            if action == 'chunk':
                data = self.body(MAX_CHUNK)
                with job['lock']:
                    if job['status'] != 'uploading' or int(self.headers.get('X-Upload-Offset', '-1')) != job['received'] or job['received'] + len(data) > job['size']:
                        raise ValueError('Upload offset or state mismatch')
                    with (job['directory'] / 'input.zip').open('ab') as handle:
                        handle.write(data)
                    job['received'] += len(data)
                return self.send(200, {'received': job['received']})
            body = json.loads(self.body())
            if action == 'run':
                settings = config_values(body.get('settings', {}))
                options = body['options']
                if options.get('mode') not in ('dry', 'live') or options.get('method') not in ('all', '1', '3', '4', '5'):
                    raise ValueError('Invalid mode or method')
                for key, low, high in [('repeat', 1, 10), ('concurrency', 1, 8), ('limit', 0, 1000)]:
                    if type(options.get(key)) is not int or not low <= options[key] <= high:
                        raise ValueError('Invalid run limits')
                if options.get('date') and not __import__('re').fullmatch(r'\d{8}', options['date']):
                    raise ValueError('Date must be YYYYMMDD')
                with job['lock']:
                    if job['status'] != 'uploading' or job['received'] != job['size']:
                        raise ValueError('Upload is incomplete or run already started')
                    job['status'] = 'queued'
                    POOL.submit(worker, job, settings, options)
                return self.send(202, {'id': job['id']})
            if action == 'billing':
                if job['status'] != 'complete':
                    raise ValueError('Run is not complete')
                values = {**os.environ, **{k: v for k, v in config_values(body.get('settings', {})).items() if v.strip()}}
                if job['summary']['mode'] == 'dry':
                    raise ValueError('Billing refresh is available only for live runs')
                try:
                    billing = refresh_billing(job['summary'], values)
                except Exception as exc:
                    billing = {'status': 'unavailable', 'message': f'Billing access failed ({type(exc).__name__}); check settings and permissions.'}
                job['summary']['billing'] = billing
                job['summary_path'].write_text(json.dumps(job['summary'], indent=2))
                return self.send(200, billing)
            if action == 'delete':
                process = job.get('process')
                if job['status'] in ('running', 'queued'):
                    raise ValueError('Wait for the active run before deleting')
                shutil.rmtree(job['directory'], ignore_errors=True)
                with LOCK:
                    JOBS.pop(job['id'], None)
                return self.send(200, {'ok': True})
            self.send(404, {'error': 'Not found'})
        except KeyError:
            self.send(404, {'error': 'Run or required field not found'})
        except (ValueError, TypeError) as exc:
            self.send(400, {'error': str(exc)})
        except Exception:
            self.send(500, {'error': 'Request failed'})

    def valid_host(self):
        if self.server.server_address[0] in ('127.0.0.1', '::1'):
            return self.headers.get('Host', '').split(':')[0] in ('127.0.0.1', 'localhost')
        return True


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=os.getenv('WEB_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8765')))
    args = parser.parse_args()
    if args.host not in ('127.0.0.1', 'localhost', '::1') and len(os.getenv('WEB_PASSWORD', '')) < 16:
        raise SystemExit('Set WEB_PASSWORD to at least 16 characters before exposing the web app')
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'East.Co console: http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
