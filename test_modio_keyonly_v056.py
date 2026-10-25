"""API-key-only mod.io game lookup and AIO download tests (mock API, no secrets)."""
import hashlib
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import modio_keyonly
import modio_aio

KEY='temporary-mock-api-key-never-post'
GAME={'kind':'smapi','name':'Stardew Valley','root':'/private/game'}
SIGNED='https://api.mod.io/v1/games/123/mods/77/files/88/download/TokenABC12345'


def archive():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('Example/manifest.json','{"UniqueID":"Example.Mod","Version":"1.0"}')
    return buf.getvalue()


class Reply(io.BytesIO):
    def __init__(self,data):
        super().__init__(data)
        self.headers={}
    def geturl(self):
        return SIGNED


class Opener:
    def __init__(self,data):
        self.data=data
        self.calls=0
    def open(self,req,timeout=30):
        self.calls+=1
        return Reply(self.data)


class KeyOnlyTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.body=archive()
        self.opener=Opener(self.body)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fetch(self,url,headers):
        p=urlsplit(url)
        self.assertEqual(p.hostname,'api.mod.io')
        self.assertEqual(parse_qs(p.query)['api_key'],[KEY])
        self.calls.append(p.path)
        if p.path=='/v1/games':
            return {'data':[{'id':123,'name':'Stardew Valley'},
                            {'id':32,'name':'Stardew Valley Expansion'}],
                    'result_total':2}
        if p.path=='/v1/games/123/mods':
            return {'data':[{'id':77,'game_id':123,'name':'Test Mod'}]}
        file={'id':88,'game_id':123,'mod_id':77,'filename':'Example.zip',
              'filesize':len(self.body),'version':'1.0.0',
              'filehash':{'md5':hashlib.md5(self.body).hexdigest()},
              'date_added':1900000000,'virus_status':1,'virus_positive':0,
              'download':{'binary_url':SIGNED,'date_expires':int(time.time())+400}}
        if p.path=='/v1/games/123/mods/77/files':
            return {'data':[file]}
        if p.path=='/v1/games/123/mods/77/files/88':
            return file
        self.fail('Unexpected request: '+p.path)

    def test_exact_public_game_name_no_user_id(self):
        self.assertEqual(modio_keyonly.resolve_game(GAME,KEY,fetch=self.fetch),'123')
        self.assertEqual(self.calls,['/v1/games'])

    def test_single_key_runs_offline_and_live_temporary_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=modio_aio.run_aio(
                GAME,api_key=KEY,allow_transfer=True,fetch=self.fetch,
                opener=self.opener,temp_parent=tmp,
                offline_run=lambda:{k:1 for k in modio_aio.REQUIRED})
            self.assertEqual((result['offline'],result['game'],result['metadata'],
                              result['download']),('Passed',)*4)
            self.assertEqual(result['selection'],'Automatic public test mod')
            self.assertEqual(list(Path(tmp).iterdir()),[])
            self.assertEqual(self.opener.calls,1)
            for private in (KEY,SIGNED,GAME['root'],'123/77'):
                self.assertNotIn(private,modio_aio.public_report(result))

    def test_ambiguous_exact_match_refused(self):
        def duplicate(url,h):
            return {'data':[{'id':123,'name':'Stardew Valley'},
                            {'id':999,'name':'Stardew Valley'}],'result_total':2}
        with self.assertRaisesRegex(modio_keyonly.ResolutionError,'ambiguous_game'):
            modio_keyonly.resolve_game(GAME,KEY,fetch=duplicate)

    def test_partial_results_refused(self):
        def truncated(url,h):
            return {'data':[{'id':123,'name':'Stardew Valley'}],'result_total':150}
        with self.assertRaisesRegex(modio_keyonly.ResolutionError,'ambiguous_game'):
            modio_keyonly.resolve_game(GAME,KEY,fetch=truncated)

    def test_missing_game_refused(self):
        def absent(url,h):
            return {'data':[{'id':5,'name':'Wrong Game'}],'result_total':1}
        with self.assertRaisesRegex(modio_keyonly.ResolutionError,'game_not_found'):
            modio_keyonly.resolve_game(GAME,KEY,fetch=absent)

    def test_error_is_redacted_and_does_not_guess_user_id(self):
        def broken(url,h):
            raise RuntimeError('BAD REQUEST '+KEY)
        r=modio_aio.run_aio(
            GAME,api_key=KEY,allow_transfer=True,fetch=broken,
            offline_run=lambda:{k:1 for k in modio_aio.REQUIRED})
        self.assertEqual(r['reason'],'key_path_required')
        self.assertEqual(r['game'],'Failed')
        self.assertEqual(r['download'],'Not tested')
        self.assertNotIn(KEY,modio_aio.public_report(r))

    def test_no_key_still_runs_offline(self):
        r=modio_aio.run_aio(GAME,api_key='',offline_run=lambda:{
            k:1 for k in modio_aio.REQUIRED})
        self.assertEqual(r['reason'],'connect')
        self.assertEqual(r['offline'],'Passed')
        self.assertEqual(self.calls,[])


if __name__=='__main__':
    unittest.main()
