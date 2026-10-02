import unittest
from unittest.mock import patch
from eastco_benchmark.dataset import FIELDS, validate_extraction
from eastco_benchmark.app import run_one, normalize_ocr, preflight
from eastco_benchmark.providers import Remote


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.s = {'id': '20260801_110201', 'date': '20260801', 'tenant': '110201',
                  'images': [], 'mapping': {}, 'reference': {k: 0 for k in FIELDS}}
        self.output = {k: {'value': 0, 'evidence': 'observed zero'} for k in FIELDS}

    def test_dry_never_scores_reference(self):
        row = run_one(self.s, '1', True, {}, {'20260801'})
        self.assertNotIn('accuracy', row)
        self.assertIsNone(row['cost'])
        self.assertTrue(all(v['value'] is None for v in row['extraction'].values()))

    def test_failed_extraction_counts_as_wrong(self):
        with patch.object(Remote, 'gemini', side_effect=RuntimeError('failure')):
            row = run_one(self.s, '1', False, {}, {'20260801'})
        self.assertTrue(row['failed'])
        self.assertEqual(row['accuracy'], 0)

    def test_primary_error_falls_back(self):
        with patch.object(Remote, 'ocr', side_effect=RuntimeError('failure')), patch.object(Remote, 'gemini', return_value=self.output):
            row = run_one(self.s, '5', False, {}, {'20260801'})
        self.assertTrue(row['fallback_used'])
        self.assertEqual(row['accuracy'], 1)

    def test_unverified_reference_not_accuracy(self):
        with patch.object(Remote, 'gemini', return_value=self.output):
            row = run_one(self.s, '1', False, {}, set())
        self.assertIn('comparison', row)
        self.assertNotIn('accuracy', row)

    def test_repeated_total_not_summed(self):
        result = normalize_ocr([{'text': '総売上 100円\n総売上 100円', 'source': 'a'}], {})
        self.assertIsNone(result['gross_sales']['value'])

    def test_schema_rejects_boolean_amount(self):
        self.output['cash_sales']['value'] = True
        with self.assertRaises(ValueError):
            validate_extraction(self.output)

    def test_unknown_price_and_attempt_ledger(self):
        response = {'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 2}}
        calls = []
        with patch('eastco_benchmark.providers.post_json', return_value=response):
            Remote(calls, {'gemini_vlm': {'input_tokens': 0.1, 'output_tokens': 0.2}}).post('gemini_vlm', 'https://example.test', {}, {})
        self.assertAlmostEqual(calls[0]['cost'], 1.4)
        self.assertEqual(len(calls), 1)

    def test_retry_preserves_failed_attempt(self):
        from urllib.error import HTTPError
        calls = []
        with patch('eastco_benchmark.providers.post_json', side_effect=[HTTPError('https://example.test', 429, 'limited', {}, None), {'usage': {'images': 1}}]), patch('eastco_benchmark.providers.time.sleep'):
            Remote(calls, {'paddle_ocr': {'images': 2}}).post('paddle_ocr', 'https://example.test', {}, {})
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0]['cost'])
        self.assertEqual(calls[1]['cost'], 2)


if __name__ == '__main__':
    unittest.main()
