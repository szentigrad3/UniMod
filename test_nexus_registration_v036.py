import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import nexus_integration as nx

class FakeSocket:
    def __init__(self, messages):
        self.messages=list(messages);self.sent=[];self.closed=False
    def send(self,v):self.sent.append(json.loads(v))
    def settimeout(self,t):self.timeout=t
    def recv(self):return self.messages.pop(0)
    def close(self):self.closed=True

class FakeResponse:
    def __init__(self, url, data):self.url=url;self.data=data;self.index=0
    def __enter__(self):return self
    def __exit__(self,*x):return False
    def geturl(self):return self.url
    def read(self, size):
        data=self.data[self.index:self.index+size];self.index+=len(data);return data

class FakeOpener:
    def __init__(self,url,data):self.url=url;self.data=data
    def open(self,request,timeout):return FakeResponse(self.url,self.data)

class NexusRegistrationTests(unittest.TestCase):
    def test_slug_requires_registration(self):
        self.assertIsNone(nx.registered_app_slug({}))
        self.assertEqual(nx.registered_app_slug({'UNIMOD_NEXUS_APP_SLUG':'unimod'}),'unimod')
        with self.assertRaises(ValueError):nx.registered_app_slug({'UNIMOD_NEXUS_APP_SLUG':'../vortex'})
    def test_auth_url(self):
        self.assertEqual(nx.authorization_url('550e8400-e29b-41d4-a716-446655440000','unimod'),
                         'https://www.nexusmods.com/sso?id=550e8400-e29b-41d4-a716-446655440000&application=unimod')
    def test_sso_success_no_key_in_sent_frames(self):
        socket=FakeSocket(['{"success":true,"data":{"connection_token":"abc"}}',
                           '{"success":true,"data":{"api_key":"supersecret-session-key-abc"}}'])
        urls=[]
        with patch.object(nx.uuid,'uuid4',return_value=nx.uuid.UUID('550e8400-e29b-41d4-a716-446655440000')):
            result=nx.sso_sign_in('unimod',urls.append,connect=lambda:socket)
        self.assertEqual(result,'supersecret-session-key-abc')
        self.assertEqual(socket.sent[0]['protocol'],2)
        self.assertNotIn(result,json.dumps(socket.sent))
        self.assertTrue(socket.closed)
        self.assertIn('application=unimod',urls[0])
    def test_sso_failure_does_not_echo_secret(self):
        s=FakeSocket(['{"success":false,"error":"key=do-not-echo"}'])
        with self.assertRaisesRegex(RuntimeError,'did not approve') as caught:
            nx.sso_sign_in('unimod',lambda *_:None,connect=lambda:s)
        self.assertNotIn('do-not-echo',str(caught.exception))
    def test_exact_nxm_and_expiry(self):
        link=nx.parse_nxm_link('nxm://stardewvalley/mods/11115/files/123456?key=aBc_1-test&expires=9999999999&user_id=1234')
        self.assertEqual(link['mod_id'],'11115')
        self.assertIn('key=aBc_1-test',nx.download_link_url('stardewvalley','11115','123456',link))
        with self.assertRaises(ValueError):nx.download_link_url('stardewvalley','11115','9',link)
        with self.assertRaises(ValueError):nx.parse_nxm_link('nxm://stardewvalley/mods/11/files/44?key=hello-world&expires=10')
        with self.assertRaises(ValueError):nx.parse_nxm_link('https://evil.example/x')
    def test_file_listing(self):
        x=nx.normalize_files({'files':[{'file_id':42,'name':'Main','file_name':'mod-v2.zip', 'version':'2'}, {'file_id':0}]})
        self.assertEqual(len(x),1);self.assertEqual(x[0]['filename'],'mod-v2.zip')
    def test_safe_download_urls(self):
        self.assertTrue(nx.safe_nexus_url('https://files.nexus-cdn.com/a.zip'))
        for url in ('http://files.nexus-cdn.com/a.zip','https://evil.example/a.zip',
                    'https://nexusmods.com.evil.example/a.zip','https://user:pass@www.nexusmods.com/x'):
            self.assertFalse(nx.safe_nexus_url(url),url)
        self.assertEqual(nx.select_download_url([{'URI':'https://files.nexus-cdn.com/a.zip'}]),'https://files.nexus-cdn.com/a.zip')
    def test_download_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            url='https://files.nexus-cdn.com/test.zip'
            opener=FakeOpener(url,b'not a real ZIP - this tests streaming only')
            p=nx.download_archive(url,tmp,'mod.zip',opener=opener)
            self.assertEqual(p.read_bytes(),opener.data)
            with self.assertRaises(FileExistsError):nx.download_archive(url,tmp,'mod.zip',opener=opener)
    def test_stream_failure_removes_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            url='https://files.nexus-cdn.com/test.zip'
            with self.assertRaises(ValueError):nx.download_archive(url,tmp,'mod.zip',opener=FakeOpener(url,b'x'*1024),max_size=100)
            self.assertEqual(list(Path(tmp).iterdir()),[])
    def test_download_rejects_unsafe_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):nx.download_archive('https://evil.example/mod.zip',tmp,'x.zip')
            with self.assertRaises(ValueError):nx.download_archive('https://files.nexus-cdn.com/a.zip',tmp,'foo.exe')

if __name__=='__main__': unittest.main()
