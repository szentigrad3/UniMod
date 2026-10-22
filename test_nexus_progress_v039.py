"""Deterministic tests for reviewed Nexus stream cancellation and UI-safe queue state."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

import nexus_integration as nx
from nexus_queue import NexusDownloadQueue

URL = 'https://files.nexus-cdn.com/download/sample.zip'
ARCHIVE = b'PK\x03\x04' + b'X' * (1024 * 24)

class Reply:
    def __init__(self, payload, size=None):
        self.payload = payload
        self.pos = 0
        self.headers = {'Content-Length': str(len(payload) if size is None else size)} if size is not False else {}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def geturl(self):return URL
    def read(self, size):
        # tiny chunks simulate slow network connections
        result=self.payload[self.pos:self.pos+4096]
        self.pos+=len(result)
        return result

class Downloader:
    def __init__(self, reply):self.reply=reply
    def open(self, req, timeout):return self.reply

class StreamingTests(unittest.TestCase):
    def test_progress_bytes_and_known_total(self):
        seen=[]
        with tempfile.TemporaryDirectory() as folder:
            saved=nx.download_archive(URL,folder,'example.zip',opener=Downloader(Reply(ARCHIVE)),
                progress=lambda received,total: seen.append((received,total)),verify_archive=True)
            self.assertEqual(saved.read_bytes(),ARCHIVE)
            self.assertEqual(seen[-1],(len(ARCHIVE),len(ARCHIVE)))
            self.assertFalse(list(Path(folder).glob('.unimod-*.part')))

    def test_progress_without_content_length(self):
        seen=[]
        with tempfile.TemporaryDirectory() as folder:
            nx.download_archive(URL,folder,'example.zip',opener=Downloader(Reply(ARCHIVE,False)),
                progress=lambda received,total: seen.append((received,total)),verify_archive=True)
            self.assertTrue(seen)
            self.assertEqual(seen[-1][1],0)

    def test_cancel_during_read_discards_partial(self):
        cancel=threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(nx.DownloadCancelled):
                nx.download_archive(URL,folder,'example.zip',opener=Downloader(Reply(ARCHIVE)),
                    cancel_event=cancel,progress=lambda received,total: cancel.set())
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_cancel_before_request_skips_network(self):
        cancel=threading.Event();cancel.set()
        opener=Mock()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(nx.DownloadCancelled):
                nx.download_archive(URL,folder,'example.zip',opener=opener,cancel_event=cancel)
            opener.open.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_too_large_header_rejected_without_part_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'exceeds configured'):
                nx.download_archive(URL,folder,'example.zip',opener=Downloader(Reply(ARCHIVE,120)),max_size=100)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_retry_only_explicit_for_fail_or_cancel(self):
        q=NexusDownloadQueue()
        a=q.add_file('stardewvalley','3753','20','test.zip')
        b=q.add_file('stardewvalley','3753','21','test2.zip')
        a.status='Cancelled';a.received=200;a.total=1000
        b.status='Downloading'
        self.assertTrue(q.retry(a.id))
        self.assertFalse(q.retry(b.id))
        self.assertEqual((a.status,a.received,a.total),('Ready to review',0,0))
        self.assertIn(a,q.ready_items())

    def test_no_token_or_uri_in_public_progress_rows(self):
        q=NexusDownloadQueue()
        entry=q.add_nxm('nxm://stardewvalley/mods/3753/files/123456?key=token12345&expires=9999999999&user_id=17')
        entry.status='Downloading';entry.received=8192;entry.total=16384
        representation=str(q.public_rows())
        for secret in ('token12345','expires','user_id','nxm://'):
            self.assertNotIn(secret,representation)

if __name__=='__main__':unittest.main()
