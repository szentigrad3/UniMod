"""AIO tests are fully offline: mocked mod.io API and temporary ZIP bytes."""
import hashlib
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import modio_aio
import modio_live_probe

KEY = 'fixture-only-secret-for-tests'
SIGNED = 'https://u-456.modapi.io/v1/games/123/mods/77/files/88/download/OfflineToken999AA'
GAME = {'kind':'smapi','root':'/private/local/game','name':'Stardew Valley'}
STAGES = []

def good_offline():
    return {k:1 for k in modio_aio.REQUIRED}

def zip_body():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('Example/manifest.json', '{"UniqueID":"AIO.Example","Version":"1.0"}')
    return out.getvalue()

class Response(io.BytesIO):
    def __init__(self, contents):
        super().__init__(contents)
        self.headers={}
    def geturl(self):return SIGNED

class Opener:
    def __init__(self, contents):
        self.contents=contents
        self.calls=0
    def open(self, request, timeout=30):
        self.calls+=1
        return Response(self.contents)

class AllInOneTests(unittest.TestCase):
    def setUp(self):
        self.data=zip_body()
        self.calls=[]
        self.opener=Opener(self.data)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fetch(self, url, headers):
        parsed=urlsplit(url)
        self.assertEqual(parsed.hostname,'u-456.modapi.io')
        self.assertIn('api_key=',parsed.query)
        self.calls.append(parsed.path)
        if parsed.path=='/v1/games/123':
            return {'id':123,'name':'Stardew Valley'}
        if parsed.path=='/v1/games/123/mods':
            return {'data':[{'id':77,'game_id':123,'name':'Example'}]}
        record={'id':88,'game_id':123,'mod_id':77,'filename':'Example.zip',
                'filesize':len(self.data),'version':'1.0.0','date_added':1900000000,
                'filehash':{'md5':hashlib.md5(self.data).hexdigest()},
                'virus_status':1,'virus_positive':0,
                'download':{'binary_url':SIGNED,'date_expires':int(time.time())+900}}
        if parsed.path=='/v1/games/123/mods/77/files':
            return {'data':[record]}
        if parsed.path=='/v1/games/123/mods/77/files/88':
            return record
        self.fail('Unexpected API path')

    def run_flow(self, **changes):
        args={'game':GAME,'game_id':'123','user_id':'456','api_key':KEY,
              'mod_id':'77','allow_transfer':True,'fetch':self.fetch,
              'opener':self.opener,'offline_run':good_offline,
              'temp_parent':self.tmp.name,'progress':STAGES.append}
        args.update(changes)
        STAGES.clear()
        return modio_aio.run_aio(**args)

    def assert_clean(self):
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_explicit_mod_full_integrity_flow(self):
        r=self.run_flow()
        self.assertEqual((r['offline'],r['game'],r['metadata'],r['download']),
                         ('Passed',)*4)
        self.assertEqual(r['reason'],'complete')
        self.assertEqual(r['selection'],'Selected mod')
        self.assertEqual(r['verified_bytes'],len(self.data))
        self.assertEqual(STAGES,['offline','game','metadata','download'])
        self.assert_clean()
        for secret in (KEY,'123/77',SIGNED,GAME['root']):
            self.assertNotIn(secret,modio_aio.public_report(r))

    def test_one_click_auto_picks_only_verified_public_game_release(self):
        r=self.run_flow(mod_id='')
        self.assertEqual(r['reason'],'complete')
        self.assertEqual(r['selection'],'Automatic public test mod')
        self.assertIn('/v1/games/123/mods',self.calls)
        self.assert_clean()

    def test_no_credentials_still_runs_offline(self):
        r=self.run_flow(api_key='',user_id='',mod_id='')
        self.assertEqual(r['offline'],'Passed')
        self.assertEqual(r['reason'],'connect')
        self.assertEqual(r['game'],'Not tested')
        self.assertEqual(self.calls,[])
        self.assertEqual(self.opener.calls,0)

    def test_no_game_still_runs_offline(self):
        r=self.run_flow(game=None)
        self.assertEqual(r['offline'],'Passed')
        self.assertEqual(r['reason'],'choose_game')
        self.assertEqual(self.calls,[])

    def test_wrong_game_blocks_all_mod_or_download_requests(self):
        r=self.run_flow(game=dict(GAME,name='Wrong Game'))
        self.assertEqual(r['game'],'Failed')
        self.assertEqual(r['reason'],'wrong_game')
        self.assertEqual(self.calls,['/v1/games/123'])
        self.assertEqual(self.opener.calls,0)

    def test_no_transfer_consent_means_no_bytes(self):
        r=self.run_flow(allow_transfer=False)
        self.assertEqual(r['metadata'],'Passed')
        self.assertEqual(r['reason'],'transfer_not_approved')
        self.assertEqual(r['download'],'Not tested')
        self.assertEqual(self.opener.calls,0)
        self.assert_clean()

    def test_no_mod_or_consent_requires_selection(self):
        r=self.run_flow(mod_id='',allow_transfer=False)
        self.assertEqual(r['reason'],'choose_mod')
        self.assertEqual(r['offline'],'Passed')
        self.assertEqual(r['game'],'Passed')
        self.assertEqual(self.opener.calls,0)

    def test_corrupted_download_failed_and_cleaned(self):
        self.opener=Opener(self.data+b'bad')
        r=self.run_flow()
        self.assertEqual(r['download'],'Failed')
        self.assertEqual(r['reason'],'download_failed')
        self.assert_clean()

    def test_invalid_credentials_not_reported(self):
        r=self.run_flow(user_id='0')
        self.assertEqual(r['reason'],'connect')
        self.assertNotIn(KEY,modio_aio.public_report(r))
        self.assert_clean()

    def test_failed_offline_does_not_fake_success(self):
        r=self.run_flow(offline_run=lambda:dict(good_offline(),backups=0),
                        allow_transfer=False)
        self.assertEqual(r['offline'],'Failed')
        self.assertEqual(r['download'],'Not tested')

    def test_report_escapes_untrusted_values(self):
        report=modio_aio.public_report({'offline':KEY,'game':SIGNED,
                                        'selection':GAME['root'],'reason':KEY,
                                        'download':'Passed'})
        for secret in (KEY,SIGNED,GAME['root']):self.assertNotIn(secret,report)
        self.assertIn('Not tested',report)

if __name__=='__main__':
    unittest.main()
