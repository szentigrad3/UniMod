"""User-issued mod.io API paths are optional, strict, session-only and redacted."""
import hashlib
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

import modio_aio

KEY='fake-key-with-no-real-account-access'
PATH='https://u-456.modapi.io/v1'
GAME={'name':'Unlisted Game','kind':'smapi','root':'/sensitive/test/game'}
SIGNED=PATH+'/games/900/mods/70/files/80/download/VerifiedSafeHash123'


class Response(io.BytesIO):
    def __init__(self,blob):
        super().__init__(blob)
        self.headers={}
    def geturl(self):
        return SIGNED


class FakeOpener:
    def __init__(self,blob):
        self.blob=blob
        self.calls=0
    def open(self,request,timeout=30):
        self.calls+=1
        return Response(self.blob)


class UserApiPathTests(unittest.TestCase):
    def setUp(self):
        with io.BytesIO() as buf:
            with zipfile.ZipFile(buf,'w') as archive:
                archive.writestr('Example/manifest.json','{"UniqueID":"Tests.Example","Version":"1.0"}')
            self.body=buf.getvalue()
        self.opener=FakeOpener(self.body)
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory=Path(temp.name)
        self.calls=[]

    def fetch(self,url,headers):
        p=urlsplit(url)
        self.assertEqual(p.scheme,'https')
        self.assertEqual(p.netloc,'u-456.modapi.io')
        self.assertEqual(parse_qs(p.query).get('api_key'),[KEY])
        self.calls.append(p.path)
        if p.path=='/v1/games':
            if '_q' in parse_qs(p.query):
                return {'data':[{'id':900,'name':'Unrelated Public Game'}],'result_total':1}
            return {'data':[{'id':900,'name':'Unrelated Public Game'}],'result_total':1}
        if p.path=='/v1/games/900/mods':
            return {'data':[{'id':70,'game_id':900,'name':'Test Public Mod'}]}
        row={'id':80,'game_id':900,'mod_id':70,'filename':'Example.zip',
             'filesize':len(self.body),'version':'1.0',
             'date_added':1900000000,'virus_status':1,'virus_positive':0,
             'filehash':{'md5':hashlib.md5(self.body).hexdigest()},
             'download':{'binary_url':SIGNED,'date_expires':int(time.time())+600}}
        if p.path in ('/v1/games/900/mods/70/files',
                      '/v1/games/900/mods/70/files/80'):
            return {'data':[row]} if p.path.endswith('/files') else row
        self.fail('Unknown test path (not a live API request)')

    def test_custom_account_path_allows_exact_provider_only_zip(self):
        result=modio_aio.run_aio(
            GAME,api_key=KEY,api_path=PATH,allow_transfer=True,
            fetch=self.fetch,opener=self.opener,
            temp_parent=str(self.directory),
            offline_run=lambda:{k:1 for k in modio_aio.REQUIRED})
        self.assertEqual(result['reason'],'provider_only_complete',result)
        self.assertEqual(result['game'],'Not available')
        self.assertEqual(result['download'],'Passed')
        self.assertEqual(result['probe_file_lists'],1)
        self.assertEqual(self.opener.calls,1)
        self.assertEqual(list(self.directory.iterdir()),[])
        self.assertTrue(self.calls)
        safe=modio_aio.public_report(result)
        for secret in (KEY,PATH,'456','900','70',SIGNED,GAME['root']):
            self.assertNotIn(secret,safe)

    def test_invalid_path_fail_closed_without_network(self):
        wrong=[
            'http://u-456.modapi.io/v1',
            'https://evil.example/v1',
            'https://u-456.modapi.io/v1?api_key=secret',
            'https://u-456.modapi.io/v1/anything',
            'https://u-0.modapi.io/v1',
            'https://u-456.modapi.io.evil.example/v1'
        ]
        for api_path in wrong:
            with self.subTest(api_path=api_path):
                result=modio_aio.run_aio(GAME,api_key=KEY,api_path=api_path,
                    allow_transfer=True,fetch=self.fetch,
                    offline_run=lambda:{k:1 for k in modio_aio.REQUIRED})
                self.assertEqual(result['reason'],'invalid_api_path')
                self.assertEqual(result['offline'],'Passed')
                self.assertEqual(self.calls,[])
                self.assertEqual(self.opener.calls,0)
                self.assertNotIn(api_path,modio_aio.public_report(result))

    def test_public_key_only_route_is_still_default(self):
        self.assertIsNone(modio_aio.validate_user_api_path(''))
        self.assertIsNone(modio_aio.validate_user_api_path(None))
        self.assertEqual(modio_aio.validate_user_api_path(PATH+'/'),'456')


if __name__=='__main__':unittest.main()
