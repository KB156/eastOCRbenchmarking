import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from eastco_benchmark.costing import estimate, environment_prices, refresh_billing, OVERHEAD
from eastco_benchmark.web import config_values, child_environment
from eastco_benchmark.web import Handler, SESSIONS, JOBS
from email.message import Message
from types import SimpleNamespace
import io
import shutil


class CostTests(unittest.TestCase):
    def setUp(self):
        self.summary = {'mode': 'live', 'started_at': '2026-08-01T00:00:00+00:00',
            'finished_at': '2026-08-01T00:01:00+00:00', 'methods': {
                '1': {'wall_seconds': 10, 'submissions': 2, 'image_count': 4, 'cost_per_submission': 1, 'known_cost': 2},
                '3': {'wall_seconds': 30, 'submissions': 2, 'image_count': 4, 'cost_per_submission': 2, 'known_cost': 4}}}
        self.env = {key: '0' for key in OVERHEAD}

    def test_overhead_is_allocated_once(self):
        self.env['IDLE_COST'] = '8'
        result = estimate(self.summary, self.env)
        self.assertEqual(result['estimated_total'], 14)
        self.assertEqual(result['methods']['1']['estimated_total'], 4)
        self.assertEqual(result['methods']['3']['estimated_total'], 10)

    def test_unknown_is_not_zero(self):
        self.env['NETWORK_COST'] = ''
        self.assertIsNone(estimate(self.summary, self.env)['estimated_total'])
        self.env['NETWORK_COST'] = '0'
        self.summary['methods']['3']['cost_per_submission'] = None
        self.assertIsNone(estimate(self.summary, self.env)['estimated_total'])

    def test_no_dry_run_cost_claim(self):
        self.summary['mode'] = 'dry'
        self.assertIsNone(estimate(self.summary, self.env)['estimated_total'])

    def test_token_unit_conversion(self):
        prices = environment_prices({}, {'VLM_INPUT_PER_MILLION': '2', 'VLM_OUTPUT_PER_MILLION': '8'})
        self.assertEqual(prices['gemini_vlm']['input_tokens'], 0.000002)

    def test_reject_invalid_rates(self):
        for value in ('nan', 'inf', '-1'):
            with self.assertRaises(ValueError):
                environment_prices({}, {'OCR_ACTIVE_PER_SECOND': value})

    def billing_env(self):
        return {'BILLING_TABLE': 'test-project.billing.export', 'BILLING_QUERY_PROJECT': 'test-project',
                'BILLING_PROJECT_IDS': 'ocr-project,gemini-project', 'BILLING_ACCESS_TOKEN': 'secret'}

    def test_empty_export_is_pending(self):
        with patch('eastco_benchmark.costing.billing_request', return_value={'jobComplete': True, 'rows': []}) as call:
            result = refresh_billing(self.summary, self.billing_env())
        self.assertEqual(result['status'], 'pending_export')
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(call.call_args.args[2]['queryParameters'][2]['parameterValue']['arrayValues'][0]['value'], 'ocr-project')

    def test_credits_and_shared_allocation(self):
        payload = {'jobComplete': True, 'rows': [{'f': [{'v': v} for v in ['Cloud Run', 'USD', '10', '-2', '8', '4', 'today']]}]}
        env = {**self.billing_env(), 'BILLING_ALLOCATION_FRACTION': '0.25'}
        with patch('eastco_benchmark.costing.billing_request', return_value=payload):
            result = refresh_billing(self.summary, env)
        self.assertEqual(result['allocated_net_by_currency']['USD'], 2)
        self.assertEqual(result['status'], 'provisional')

    def test_table_injection_rejected(self):
        env = {**self.billing_env(), 'BILLING_TABLE': 'test.billing.table`; DROP TABLE x'}
        with self.assertRaises(ValueError):
            refresh_billing(self.summary, env)

    def test_pending_query_is_resumed_not_resubmitted(self):
        env = self.billing_env()
        with patch('eastco_benchmark.costing.billing_request', return_value={'jobComplete': False, 'jobReference': {'jobId': 'job-123'}}):
            self.summary['billing'] = refresh_billing(self.summary, env)
        with patch('eastco_benchmark.costing.billing_request', return_value={'jobComplete': True, 'rows': []}) as call:
            refresh_billing(self.summary, env)
        self.assertEqual(call.call_args.args[0], 'GET')
        self.assertIn('job-123', call.call_args.args[1])

    def test_settings_cannot_control_subprocess(self):
        with self.assertRaises(ValueError):
            config_values({'PYTHONPATH': '/evil'})
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'server-key', 'WEB_PASSWORD': 'private'}, clear=True):
            child = child_environment({'GEMINI_API_KEY': ''}, Path('/tmp/test'))
            self.assertEqual(child['GEMINI_API_KEY'], 'server-key')
            self.assertNotIn('WEB_PASSWORD', child)


class WebRequestTests(unittest.TestCase):
    def request(self, path, body=None, cookie=None, method='POST', extra=None):
        handler = Handler.__new__(Handler)
        handler.path = path
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        handler.headers = Message()
        handler.headers['Host'] = '127.0.0.1:8765'
        handler.headers['X-Eastco-Request'] = '1'
        if cookie:
            handler.headers['Cookie'] = cookie
        for key, value in (extra or {}).items():
            handler.headers[key] = value
        data = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
        handler.headers['Content-Length'] = str(len(data))
        handler.rfile = io.BytesIO(data)
        captured = {}
        handler.send = lambda status, value, mime='application/json', extra=None: captured.update(status=status, value=value, headers=extra or {})
        handler.do_GET() if method == 'GET' else handler.mutate()
        return captured

    def tearDown(self):
        for job in JOBS.values():
            shutil.rmtree(job['directory'], ignore_errors=True)
        JOBS.clear()
        SESSIONS.clear()

    def test_login_hides_server_keys(self):
        with patch.dict(os.environ, {'WEB_PASSWORD': 'test-password', 'GEMINI_API_KEY': 'sensitive-key'}):
            self.assertEqual(self.request('/api/login', {'password': 'wrong'})['status'], 401)
            login = self.request('/api/login', {'password': 'test-password'})
            cookie = login['headers']['Set-Cookie'].split(';')[0]
            result = self.request('/api/config', cookie=cookie, method='GET')
        self.assertEqual(result['status'], 200)
        self.assertNotIn('sensitive-key', json.dumps(result))
        self.assertIn('GEMINI_API_KEY', result['value']['configured_secrets'])

    def test_upload_ownership_and_offsets(self):
        with patch.dict(os.environ, {'WEB_PASSWORD': ''}):
            cookie = self.request('/api/login')['headers']['Set-Cookie'].split(';')[0]
            other = self.request('/api/login')['headers']['Set-Cookie'].split(';')[0]
        upload = self.request('/api/uploads', {'size': 4}, cookie)
        key = upload['value']['id']
        self.assertEqual(self.request(f'/api/jobs/{key}', cookie=other, method='GET')['status'], 404)
        result = self.request(f'/api/jobs/{key}/chunk', b'zip!', cookie, extra={'X-Upload-Offset': '0'})
        self.assertEqual(result['value']['received'], 4)
        self.assertEqual(self.request(f'/api/jobs/{key}/chunk', b'x', cookie, extra={'X-Upload-Offset': '0'})['status'], 400)
        self.assertEqual(self.request(f'/api/jobs/{key}/delete', {}, cookie)['status'], 200)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.request('/api/login', extra={'Origin': 'https://untrusted.example'})['status'], 403)


if __name__ == '__main__':
    unittest.main()
