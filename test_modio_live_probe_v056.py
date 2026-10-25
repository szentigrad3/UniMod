"""Offline tests for the private temporary mod.io CDN download probe."""
import hashlib
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import modio_live_probe
import provider_downloads

KEY = 'offline-throwaway-secret-do-not-store'
SIGNED = 'https://u-456.modapi.io/v1/games/123/mods/77/files/88/download/OfflineTokenABC123'


def archive():
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as z:
        z.writestr('Example/manifest.json', '{"UniqueID":"Example.Probe","Version":"1.0"}')
    return memory.getvalue()


class Response(io.BytesIO):
    def __init__(self, data, url=SIGNED):
        super().__init__(data)
        self.url = url
        self.headers = {}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, data, url=SIGNED):
        self.data, self.url = data, url
        self.calls = 0

    def open(self, request, timeout=30):
        self.calls += 1
        return Response(self.data, self.url)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = archive()
        self.filename = 'Example-v1.zip'
        self.record = {'provider': 'mod.io', 'identity': '123/77',
                       'version_id': '88', 'filename': self.filename,
                       'version': '1.0', 'size': len(self.body),
                       'hashes': {'md5': hashlib.md5(self.body).hexdigest()}}
        self.opener = Opener(self.body)
        self.calls = []

    def fetch(self, url, headers):
        self.calls.append(url)
        self.assertEqual(urlsplit(url).hostname, 'u-456.modapi.io')
        self.assertIn('api_key=', url)
        return {'id': 88, 'mod_id': 77, 'game_id': 123,
                'filename': self.filename, 'version': '1.0',
                'filesize': len(self.body),
                'filehash': {'md5': hashlib.md5(self.body).hexdigest()},
                'download': {'binary_url': SIGNED,
                             'date_expires': int(time.time()) + 1000},
                'virus_status': 1, 'virus_positive': 0}

    def run_probe(self, record=None, opener=None):
        return modio_live_probe.probe_download(
            self.record if record is None else record,
            user_id='456', api_key=KEY, fetch=self.fetch,
            opener=self.opener if opener is None else opener,
            temp_parent=self.tmp.name)

    def assert_clean(self):
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_success_redacted_and_deleted(self):
        result = self.run_probe()
        self.assertEqual(result['file_id'], '88')
        self.assertEqual(result['bytes_verified'], len(self.body))
        self.assertEqual(result['sha256'], hashlib.sha256(self.body).hexdigest())
        self.assertFalse(result['installed'])
        self.assertFalse(result['staged'])
        for value in (KEY, SIGNED, 'u-456', 'OfflineToken', self.tmp.name):
            self.assertNotIn(value, repr(result))
        self.assertEqual(self.opener.calls, 1)
        self.assertEqual(len(self.calls), 1)
        self.assert_clean()

    def test_changed_source_hash_rejected_without_download(self):
        changed = dict(self.record, hashes={'md5': 'a' * 32})
        with self.assertRaises(ValueError):
            self.run_probe(changed)
        self.assertEqual(self.opener.calls, 0)
        self.assert_clean()

    def test_corrupt_download_rejected_and_cleaned(self):
        other = archive() + b'corrupt'
        with self.assertRaises(provider_downloads.DownloadError):
            self.run_probe(opener=Opener(other))
        self.assert_clean()

    def test_oversize_fails_without_network(self):
        with self.assertRaisesRegex(modio_live_probe.ProbeError, '64 MiB'):
            self.run_probe(dict(self.record, size=modio_live_probe.MAX_PROBE_BYTES+1))
        self.assertEqual(self.calls, [])
        self.assert_clean()

    def test_wrong_provider_or_identity_rejected(self):
        for replacement in ({'provider': 'GitHub'}, {'identity': '123/../77'}, {'version_id': 'bad'}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                self.run_probe({**self.record, **replacement})
        self.assertEqual(self.calls, [])
        self.assert_clean()

    def test_wrong_redirect_refused_and_cleanup(self):
        with self.assertRaises(provider_downloads.DownloadError):
            self.run_probe(opener=Opener(self.body, 'https://untrusted.example.com/evil.zip'))
        self.assert_clean()

    def test_invalid_max_limit_refused(self):
        with self.assertRaises(modio_live_probe.ProbeError):
            modio_live_probe.probe_download(self.record, user_id='456', api_key=KEY,
                fetch=self.fetch, opener=self.opener, max_bytes=True, temp_parent=self.tmp.name)
        self.assert_clean()


if __name__ == '__main__':
    unittest.main()
