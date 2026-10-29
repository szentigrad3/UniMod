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

    def test_independent_fallback_stays_within_three_games(self):
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
        self.assertEqual(result['reason'],'provider_sample_unavailable')
        self.assertEqual(result['probe_games'],3)
        self.assertEqual(result['download'],'Not available')
        self.assertEqual(result['game'],'Not available')
        self.assertEqual(self.opener.calls,0)
        self.assert_clean()
        for secret in (KEY,SIGNED,GAME['root'],'900/70'):
            self.assertNotIn(secret,modio_aio.public_report(result))

    def test_collection_without_signed_url_refreshes_exact_file_safely(self):
        # A modfile collection can have no usable short-lived binary_url while
        # the exact read-only file endpoint issues a current signed URL.
        def unsigned_collection(url,headers):
            from urllib.parse import urlsplit
            if urlsplit(url).path.endswith('/files'):
                listing=self.fetch(url,headers)
                entry=dict(listing['data'][0])
                entry['download']={'binary_url':'','date_expires':0}
                return {'data':[entry]}
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=unsigned_collection)
        self.assertEqual(result['reason'],'provider_only_complete',result)
        self.assertEqual(result['download'],'Passed')
        self.assertEqual(result['probe_file_lists'],1)
        self.assertEqual(result['probe_file_records'],1)
        self.assertEqual(result['probe_preview_candidates'],1)
        self.assertEqual(result['probe_exact_checked'],1)
        self.assertEqual(self.opener.calls,1)
        self.assert_clean()
        report=modio_aio.public_report(result)
        self.assertIn('readable release list(s)',report)
        self.assertIn('File screening:',report)
        for secret in (KEY,SIGNED,GAME['root'],'900/70'):
            self.assertNotIn(secret,report)

    def test_collection_with_expired_url_refreshes_exact_file(self):
        def expired_collection(url,headers):
            if urlsplit(url).path.endswith('/files'):
                listing=self.fetch(url,headers)
                row=dict(listing['data'][0])
                row['download']={'binary_url':SIGNED,'date_expires':5}
                return {'data':[row]}
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=expired_collection)
        self.assertEqual(result['reason'],'provider_only_complete')
        self.assertEqual(self.opener.calls,1)
        self.assert_clean()

    def test_changed_exact_file_hash_is_never_downloaded(self):
        def changed_exact(url,headers):
            if urlsplit(url).path.endswith('/files/80'):
                row=dict(self.fetch(url,headers))
                row['filehash']={'md5':'f'*32}
                return row
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=changed_exact)
        self.assertEqual(result['reason'],'provider_exact_unverified')
        self.assertEqual(result['probe_exact_checked'],0)
        self.assertEqual(result['probe_rejection_reasons'],{'changed_metadata':1})
        self.assertIn('changed metadata 1',modio_aio.public_report(result))
        self.assertEqual(self.opener.calls,0)
        self.assert_clean()

    def test_exact_file_missing_download_url_is_reported_safely(self):
        def no_url(url,headers):
            if urlsplit(url).path.endswith('/files/80'):
                record=dict(self.fetch(url,headers))
                record['download']={}
                return record
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=no_url)
        self.assertEqual(result['reason'],'provider_exact_unverified')
        self.assertEqual(result['probe_rejection_reasons'],{'missing_download_url':1})
        self.assertEqual(self.opener.calls,0)
        rendered=modio_aio.public_report(result)
        self.assertIn('missing download url 1',rendered)
        self.assertNotIn(KEY,rendered)
        self.assertNotIn(SIGNED,rendered)
        self.assert_clean()

    def test_exact_file_provider_failure_is_reported_without_secrets(self):
        import provider_catalogues
        def broken_endpoint(url,headers):
            if urlsplit(url).path.endswith('/files/80'):
                raise provider_catalogues.ProviderError('Provider request failed (HTTP 500).')
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=broken_endpoint)
        self.assertEqual(result['reason'],'provider_request_failed')
        self.assertEqual(result['probe_rejection_reasons'],{'provider_failure':1})
        self.assertEqual(self.opener.calls,0)
        report=modio_aio.public_report(result)
        self.assertIn('provider failure 1',report)
        self.assertNotIn(KEY,report)
        self.assertNotIn(SIGNED,report)
        self.assert_clean()

    def test_unscanned_release_is_not_downloaded(self):
        def unscanned(url,headers):
            if urlsplit(url).path.endswith('/files'):
                listing=self.fetch(url,headers)
                row=dict(listing['data'][0])
                row['virus_status']=0
                return {'data':[row]}
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=unscanned)
        self.assertEqual(result['reason'],'provider_no_eligible_zip')
        self.assertEqual(result['probe_file_records'],1)
        self.assertEqual(result['probe_preview_candidates'],0)
        self.assertEqual(self.opener.calls,0)
        self.assert_clean()

    def test_partial_access_denial_does_not_obscure_valid_empty_list(self):
        import provider_catalogues
        def partly_denied(url,headers):
            if urlsplit(url).path.endswith('/files'):
                listing=self.fetch(url,headers)
                return {'data':[]}
            if urlsplit(url).path.endswith('/mods') and '/v1/games/901/' in urlsplit(url).path:
                raise provider_catalogues.ProviderError('Provider authentication or API access is required.')
            if urlsplit(url).path=='/v1/games' and '_q' not in parse_qs(urlsplit(url).query):
                return {'data':[{'id':900},{'id':901}]}
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=partly_denied)
        self.assertEqual(result['reason'],'provider_no_eligible_zip')
        self.assertEqual(result['probe_file_lists'],1)
        self.assertEqual(self.opener.calls,0)

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

    def test_stops_immediately_on_first_exact_file_429(self):
        import provider_catalogues
        def rate_limited(url,headers):
            if urlsplit(url).path.endswith('/files/80'):
                raise provider_catalogues.ProviderRateLimited(97)
            return self.fetch(url,headers)
        result=self.run_test(allow_transfer=True,fetch=rate_limited)
        self.assertEqual(result['reason'],'provider_rate_limited')
        self.assertEqual(result['retry_after_seconds'],97)
        self.assertEqual(result['probe_exact_attempts'],1)
        self.assertEqual(result['probe_requests'],4)
        self.assertEqual(result['probe_exact_checked'],0)
        self.assertEqual(self.opener.calls,0)
        self.assertIn('Provider cooldown: at least 97 second(s)',modio_aio.public_report(result))
        self.assert_clean()

    def test_bounded_requests_cannot_exhaust_60_per_minute_key(self):
        import provider_catalogues
        def never_verified(url,headers):
            uri=urlsplit(url)
            params=parse_qs(uri.query)
            if uri.path=='/v1/games' and '_q' in params:
                return {'data':[{'id':700,'name':'Other Game'}],'result_total':1}
            if uri.path=='/v1/games':
                return {'data':[{'id':900+i} for i in range(8)],'result_total':8}
            if uri.path.endswith('/mods'):
                return {'data':[{'id':70+i} for i in range(5)]}
            if uri.path.endswith('/files'):
                parts=uri.path.split('/')
                game,mod=parts[3],parts[5]
                return {'data':[{
                    'id':80,'mod_id':int(mod),'game_id':int(game),
                    'filename':'Example.zip','filesize':len(self.contents),
                    'version':'1.0','filehash':{'md5':__import__('hashlib').md5(self.contents).hexdigest()},
                    'virus_status':1,'virus_positive':0
                }]}
            if uri.path.endswith('/files/80'):
                # The precise file has no valid signed link; never accept it.
                return {'id':80,'mod_id':int(uri.path.split('/')[5]),
                        'game_id':int(uri.path.split('/')[3]),
                        'filename':'Example.zip','filesize':len(self.contents),
                        'filehash':{'md5':__import__('hashlib').md5(self.contents).hexdigest()},
                        'virus_status':1,'virus_positive':0,
                        'download':{'binary_url':''}}
            self.fail('unexpected test endpoint: '+uri.path)
        result=self.run_test(allow_transfer=True,fetch=never_verified)
        self.assertEqual(result['reason'],'provider_exact_unverified',result)
        self.assertEqual(result['probe_games'],3)
        self.assertEqual(result['probe_mods'],6)
        self.assertEqual(result['probe_requests'],16)
        self.assertLessEqual(result['probe_requests']+1,19)
        self.assertGreater(result['probe_exact_attempts'],0)
        self.assertEqual(result['probe_exact_checked'],0)
        self.assertEqual(self.opener.calls,0)
        self.assertIn('Request safety:',modio_aio.public_report(result))
        self.assert_clean()

    def test_limited_sample_request_is_not_mislabeled_bad_api_path(self):
        import provider_catalogues
        def rate_sample(url,headers):
            if (urlsplit(url).path=='/v1/games' and
                    '_q' not in parse_qs(urlsplit(url).query)):
                raise provider_catalogues.ProviderRateLimited(0)
            return self.fetch(url,headers)
        report=self.run_test(allow_transfer=True,fetch=rate_sample)
        self.assertEqual(report['reason'],'provider_rate_limited')
        self.assertEqual(report['retry_after_seconds'],60)
        self.assertEqual(report['probe_requests'],1)
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
