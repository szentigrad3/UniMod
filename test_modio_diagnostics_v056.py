"""Offline live-diagnostic contract: read-only API calls and redacted summaries."""
import time
import unittest
from urllib.parse import urlsplit, parse_qs

import modio_diagnostics as diagnostic
import modio_files
import provider_catalogues

KEY = 'example-key-must-never-be-logged'
SIGNED = 'https://u-456.modapi.io/v1/games/123/mods/77/files/88/download/abc123XYZtoken'


def modfile(*, file_id=88, game_id=123, mod_id=77, version='1.2.0'):
    return {
        'id': file_id, 'mod_id': mod_id, 'game_id': game_id,
        'filename': 'Example.zip', 'version': version, 'filesize': 1024,
        'filehash': {'md5': 'b' * 32},
        'download': {'binary_url': SIGNED, 'date_expires': int(time.time()) + 300},
        'virus_status': 1, 'virus_positive': 0, 'date_added': 1700000000,
    }


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.urls = []

    def api(self, url, headers):
        self.urls.append(url)
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'u-456.modapi.io')
        self.assertEqual(parse_qs(parsed.query)['api_key'], [KEY])
        self.assertFalse(headers.get('Authorization'))
        if parsed.path == '/v1/games/123':
            return {'id': 123, 'name': 'Test Game'}
        if parsed.path == '/v1/games/123/mods/77/files':
            return {'data': [modfile()]}
        if parsed.path == '/v1/games/123/mods/77/files/88':
            return modfile()
        self.fail('Unexpected endpoint: ' + parsed.path)

    def test_three_gets_with_redacted_summary(self):
        report = diagnostic.check_modio_access('123/77', user_id='456', api_key=KEY, fetch=self.api)
        self.assertEqual(len(self.urls), 3)
        self.assertEqual(report['status'], 'Verified metadata access')
        self.assertEqual(report['eligible_zip_files'], 1)
        self.assertTrue(report['exact_file_verified'])
        self.assertEqual(report['checked_file_id'], '88')
        for sensitive in (KEY, SIGNED, 'u-456', '/files/88/download'):
            self.assertNotIn(sensitive, repr(report))
        self.assertFalse(report['downloaded'])

    def test_no_eligible_zip_files_skips_exact_lookup(self):
        def empty(url, headers):
            self.urls.append(url)
            if '/mods/77/files?' in url:
                return {'data': []}
            return {'id': 123, 'name': 'Test Game'}
        result = diagnostic.check_modio_access('123/77', user_id='456', api_key=KEY, fetch=empty)
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(result['eligible_zip_files'], 0)
        self.assertFalse(result['exact_file_verified'])

    def test_wrong_game_stops_before_file_query(self):
        def wrong(url, headers):
            self.urls.append(url)
            return {'id': 999, 'name': 'Wrong game'}
        with self.assertRaises(provider_catalogues.ProviderError):
            diagnostic.check_modio_access('123/77', user_id='456', api_key=KEY, fetch=wrong)
        self.assertEqual(len(self.urls), 1)

    def test_wrong_file_metadata_refused(self):
        def wrong_file(url, headers):
            if urlsplit(url).path.endswith('/files/88'):
                return modfile(mod_id=999)
            return self.api(url, headers)
        with self.assertRaises(modio_files.ModioError):
            diagnostic.check_modio_access('123/77', user_id='456', api_key=KEY, fetch=wrong_file)

    def test_changed_file_on_refresh_refused(self):
        def changed_file(url, headers):
            if urlsplit(url).path.endswith('/files/88'):
                return modfile(version='9.9.9')
            return self.api(url, headers)
        with self.assertRaises(modio_files.ModioError):
            diagnostic.check_modio_access('123/77', user_id='456', api_key=KEY, fetch=changed_file)

    def test_invalid_inputs_refused_before_network(self):
        for identity in ('0/77', '123/../77', '123/77/1', 'fake'):
            with self.subTest(identity=identity), self.assertRaises(modio_files.ModioError):
                diagnostic.check_modio_access(identity, user_id='456', api_key=KEY, fetch=self.api)
        self.assertEqual(self.urls, [])


if __name__ == '__main__':
    unittest.main()
