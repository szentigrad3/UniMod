"""AIO unsupported-game results and independent provider-only ZIP tests.

All API/CDN responses are mocked. The installed game is never modified.
"""
import hashlib
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import modio_aio

KEY='dummy-private-mod-io-key-for-tests'
GAME={'name':'Unlisted Local Game','kind':'smapi','root':'/tmp/unrelated-local-game'}
SIGNED='https://api.mod.io/v1/games/900/mods/70/files/80/download/TestSignedHashABCDE'

def archive():
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        z.writestr('Example/manifest.json','{"UniqueID":"AIO.Test","Version":"1.0"}')
    return output.getvalue()

class Reply(io.BytesIO):
    def __init__(self,contents):
        super().__init__(contents)
        self.headers={}
    def geturl(self):return SIGNED

class Opener:
    def __init__(self,contents):
        self.contents=contents
        self.calls=0
    def open(self,req,timeout=30):
        self.calls+=1
        return Reply(self.contents)

class UnsupportedGameTests(unittest.TestCase):
    def setUp(self):
        self.contents=archive()
        self.opener=Opener(self.contents)
        self.requests=[]
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fetch(self,url,headers):
        parts=urlsplit(url)
        self.assertEqual(parts.hostname,'api.mod.io')
        params=parse_qs(parts.query)
        self.assertEqual(params.get('api_key'),[KEY])
        self.requests.append((parts.path,params))
        if parts.path=='/v1/games' and '_q' in params:
            return {'data':[{'id':700,'name':'Other Game'}],'result_total':1}
        if parts.path=='/v1/games':
            return {'data':[{'id':900,'name':'Supported Game'}],'result_total':1}
        if parts.path=='/v1/games/900/mods':
            return {'data':[{'id':70,'game_id':900,'name':'Official Test Mod'}]}
        row={'id':80,'game_id':900,'mod_id':70,'filename':'Example.zip',
             'filesize':len(self.contents),'version':'1.0',
             'date_added':1900000000,'virus_status':1,'virus_positive':0,
             'filehash':{'md5':hashlib.md5(self.contents).hexdigest()},
             'download':{'binary_url':SIGNED,'date_expires':int(time.time())+600}}
        if parts.path=='/v1/games/900/mods/70/files':
            return {'data':[row]}
        if parts.path=='/v1/games/900/mods/70/files/80':
            return row
        self.fail('Unexpected endpoint: '+parts.path)

    def run_test(self,**override):
        kwargs=dict(game=GAME,api_key=KEY,allow_transfer=False,
                    fetch=self.fetch,opener=self.opener,temp_parent=self.tmp.name,
                    offline_run=lambda:{x:1 for x in modio_aio.REQUIRED})
        kwargs.update(override)
        return modio_aio.run_aio(**kwargs)

    def assert_clean(self):
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[])

    def test_unsupported_game_does_not_mark_api_key_failed(self):
        result=self.run_test()
        self.assertEqual(result['offline'],'Passed')
        self.assertEqual(result['catalogue'],'Passed')
        self.assertEqual(result['game'],'Not available')
        self.assertEqual(result['metadata'],'Not available')
        self.assertEqual(result['download'],'Not available')
        self.assertEqual(result['reason'],'game_not_found')
        self.assertEqual(self.opener.calls,0)
        report=modio_aio.public_report(result)
        self.assertIn('Public mod.io catalogue access: Passed',report)
        self.assertIn('Official game verification: Not available',report)
        self.assertNotIn(KEY,report)

    def test_opted_in_probe_uses_different_game_and_deletes_zip(self):
        result=self.run_test(allow_transfer=True)
        self.assertEqual(result['offline'],'Passed')
        self.assertEqual(result['catalogue'],'Passed')
        self.assertEqual(result['game'],'Not available')
        self.assertEqual(result['metadata'],'Passed')
        self.assertEqual(result['download'],'Passed')
        self.assertEqual(result['scope'],'Provider-only (different game)')
        self.assertEqual(result['reason'],'provider_only_complete')
        self.assertEqual(self.opener.calls,1)
        self.assert_clean()
        report=modio_aio.public_report(result)
        self.assertIn('Test scope: Provider-only (different game)',report)
        self.assertIn('Real-game installation: Not attempted',report)
        for private in (KEY,SIGNED,GAME['root'],'900/70'):
            self.assertNotIn(private,report)

    def test_independent_fallback_checks_active_game_beyond_first_four(self):
        def later_game(url, headers):
            parts=urlsplit(url)
            params=parse_qs(parts.query)
            if parts.path=='/v1/games' and '_q' not in params:
                self.assertEqual(params.get('_sort'),['-mods_count_total'])
                self.assertEqual(params.get('_limit'),['30'])
                return {'data':[
                    {'id':901,'name':'No public mods 1'},
                    {'id':902,'name':'No public mods 2'},
                    {'id':903,'name':'No public mods 3'},
                    {'id':904,'name':'No public mods 4'},
                    {'id':900,'name':'Established test game'}],
                    'result_total':5}
            if parts.path in ('/v1/games/901/mods','/v1/games/902/mods',
                              '/v1/games/903/mods','/v1/games/904/mods'):
                return {'data':[]}
            return self.fetch(url,headers)
        result=self.run_test(fetch=later_game,allow_transfer=True)
        self.assertEqual(result['reason'],'provider_only_complete')
        self.assertEqual(result['download'],'Passed')
        self.assertEqual(result['game'],'Not available')
        self.assertEqual(self.opener.calls,1)
        self.assert_clean()
        for secret in (KEY,SIGNED,GAME['root'],'900/70'):
            self.assertNotIn(secret,modio_aio.public_report(result))

    def test_failed_cdn_transfer_never_claims_selected_game_compatibility(self):
        self.opener=Opener(self.contents+b'corrupt')
        result=self.run_test(allow_transfer=True)
        self.assertEqual(result['reason'],'provider_only_download_failed')
        self.assertEqual(result['download'],'Failed')
        self.assertEqual(result['game'],'Not available')
        self.assert_clean()

    def test_provider_has_no_suitable_zip_does_not_fail_key(self):
        def empty(url,headers):
            path=urlsplit(url).path
            if path.endswith('/files'):
                return {'data':[]}
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=empty)
        self.assertEqual(result['catalogue'],'Passed')
        self.assertEqual(result['game'],'Not available')
        self.assertEqual(result['metadata'],'Not available')
        self.assertEqual(result['reason'],'provider_no_eligible_zip')
        self.assertGreater(result['probe_file_lists'],0)
        self.assertEqual(self.opener.calls,0)

    def test_deeper_api_restriction_reported_instead_of_no_zip(self):
        import provider_catalogues
        def denied(url,headers):
            path=urlsplit(url).path
            if path.startswith('/v1/games/900/mods'):
                raise provider_catalogues.ProviderError(
                    'Provider authentication or API access is required.')
            return self.fetch(url,headers)
        report=self.run_test(allow_transfer=True,fetch=denied)
        self.assertEqual(report['game'],'Not available')
        self.assertEqual(report['catalogue'],'Passed')
        self.assertEqual(report['reason'],'provider_api_access_required')
        self.assertEqual(report['probe_games'],1)
        self.assertEqual(report['probe_file_lists'],0)
        self.assertEqual(self.opener.calls,0)
        safe=modio_aio.public_report(report)
        self.assertIn('account-specific API path',safe)
        self.assertIn('Public sample: checked 1 game(s)',safe)
        self.assertNotIn(KEY,safe)
        self.assertNotIn(SIGNED,safe)
        self.assert_clean()

    def test_rate_limit_distinguished_from_no_public_modfiles(self):
        import provider_catalogues
        def limited(url,headers):
            path=urlsplit(url).path
            if path.startswith('/v1/games/900/mods'):
                raise provider_catalogues.ProviderError('Provider rate limit reached. Try later.')
            return self.fetch(url,headers)
        report=self.run_test(allow_transfer=True,fetch=limited)
        self.assertEqual(report['reason'],'provider_rate_limited')
        self.assertEqual(report['download'],'Not available')
        self.assertEqual(self.opener.calls,0)
        self.assert_clean()

    def test_public_test_game_sample_block_distinguished(self):
        import provider_catalogues
        def limited(url,headers):
            path=urlsplit(url).path
            if path=='/v1/games' and '_q' not in parse_qs(urlsplit(url).query):
                raise provider_catalogues.ProviderError('Provider authentication or API access is required.')
            return self.fetch(url,headers)
        report=self.run_test(allow_transfer=True,fetch=limited)
        self.assertEqual(report['reason'],'provider_api_path_required')
        self.assertEqual(report['probe_games'],0)
        self.assertNotIn(KEY,modio_aio.public_report(report))
        self.assertEqual(self.opener.calls,0)

    def test_unknown_provider_exception_is_redacted(self):
        def crashed(url,headers):
            if urlsplit(url).path=='/v1/games/900/mods':
                raise RuntimeError('private '+KEY+' '+SIGNED)
            return self.fetch(url,headers)
        report=self.run_test(allow_transfer=True,fetch=crashed)
        self.assertEqual(report['reason'],'provider_request_failed')
        safe=modio_aio.public_report(report)
        self.assertNotIn(KEY,safe)
        self.assertNotIn(SIGNED,safe)
        self.assertEqual(self.opener.calls,0)

    def test_denied_download_does_not_contact_other_games(self):
        result=self.run_test(allow_transfer=False)
        self.assertTrue(all('/900/' not in path for path,_ in self.requests))
        self.assertEqual(result['scope'],'Not selected')

    def test_unsupported_key_path_never_false_passes(self):
        def blocked(url,headers):
            raise RuntimeError('Never print the secret '+KEY)
        result=self.run_test(fetch=blocked,allow_transfer=True)
        self.assertEqual(result['catalogue'],'Not tested')
        self.assertEqual(result['game'],'Failed')
        self.assertEqual(result['reason'],'key_path_required')
        self.assertEqual(self.opener.calls,0)
        self.assertNotIn(KEY,modio_aio.public_report(result))


if __name__=='__main__':
    unittest.main()
