import os, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import nexus_integration as nx
from nexus_queue import NexusDownloadQueue
from nxm_handler import build_entry,install

NXM='nxm://stardewvalley/mods/3753/files/123456?key=token12345&expires=9999999999&user_id=17'

class FakeResponse:
    def __init__(self,data,url):self.data,self.url,self.offset=data,url,0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def geturl(self):return self.url
    def read(self,n):
        p=self.data[self.offset:self.offset+n] if isinstance(self.offset,int) else self.data[:n]
        if not isinstance(self.offset,int):self.offset=0;p=self.data[:n]
        self.offset+=len(p);return p

class FakeOpener:
    def __init__(self,data):self.data=data
    def open(self,req,timeout):return FakeResponse(self.data,req.full_url)

class QueueTests(unittest.TestCase):
    def test_nxm_token_memory_only_public_rows(self):
        q=NexusDownloadQueue();q.add_nxm(NXM)
        self.assertNotIn('token12345',str(q.public_rows()))
        self.assertNotIn('user_id',str(q.public_rows()))
        self.assertEqual(q.public_rows()[0]['mod'],'3753')
    def test_duplicate_nxm_queued_once_and_token_refreshed(self):
        q=NexusDownloadQueue();first=q.add_nxm(NXM)
        q.add_nxm(NXM.replace('token12345','token54321'))
        self.assertEqual(len(q.public_rows()),1)
        self.assertEqual(first.nxm['key'],'token54321')
    def test_reject_expired_nxm(self):
        with self.assertRaises(ValueError):NexusDownloadQueue().add_nxm(NXM.replace('9999999999','1'))
    def test_mark_downloaded_erases_token(self):
        q=NexusDownloadQueue();entry=q.add_nxm(NXM)
        q.mark_downloaded(entry,Path('/tmp/mod.zip'))
        self.assertIsNone(entry.nxm)
        self.assertEqual(entry.status,'Downloaded')
    def test_remove_only_not_downloading(self):
        q=NexusDownloadQueue();entry=q.add_nxm(NXM)
        entry.status='Downloading';self.assertFalse(q.remove(entry.id))
        entry.status='Ready to review';self.assertTrue(q.remove(entry.id))
    def test_source_queue_validated(self):
        q=NexusDownloadQueue();q.add_file('stardewvalley','42','7','mod.zip')
        with self.assertRaises(ValueError):q.add_file('../unsafe','42','7','x.zip')
    def test_error_redacts_auth_tokens(self):
        s=nx.redacted_error(RuntimeError('bad URL ?key=token12345&expires=9999999999'),'token12345')
        self.assertNotIn('token12345',s);self.assertNotIn('9999999999',s)
    def test_archive_must_be_valid(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'recognised mod archive'):
                nx.download_archive('https://files.nexus-cdn.com/a.zip',t,'mod.zip',opener=FakeOpener(b'<html>Error</html>'),verify_archive=True)
            self.assertEqual(list(Path(t).iterdir()),[])
    def test_archive_type_corrects_nxm_extension(self):
        with tempfile.TemporaryDirectory() as t:
            saved=nx.download_archive('https://files.nexus-cdn.com/a.zip',t,'nexus-1.zip',
                 opener=FakeOpener(b'7z\xbc\xaf\x27\x1c'+b'\x00'*20),verify_archive=True)
            self.assertEqual(saved.suffix,'.7z')
    def test_opt_in_handler_writes_no_token(self):
        with tempfile.TemporaryDirectory() as t:
            app=Path(t)/'UniMod.appimage';app.write_bytes(b'ELF')
            app.chmod(0o755)
            calls=[]
            desk=install(app,data_home=Path(t)/'data',mime_runner=lambda:calls.append(True))
            self.assertIn('x-scheme-handler/nxm;',desk.read_text())
            self.assertIn('--nxm %u',desk.read_text())
            self.assertNotIn('token12345',desk.read_text())
            self.assertTrue(calls)
    def test_handler_rejects_non_appimage(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'bad.exe';f.write_bytes(b'x');f.chmod(0o755)
            with self.assertRaises(ValueError):build_entry(f)

if __name__=='__main__':unittest.main()
