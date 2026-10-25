"""No network, no secrets: read-only mod.io session account path validation."""
import unittest
from urllib.parse import urlsplit,parse_qs
import provider_catalogues as p

KEY='synthetic-fake-token-for-testing-only'
class ModioUserPath(unittest.TestCase):
    def test_resolves_game_using_unique_user_api_host(self):
        seen=[]
        actual=p.modio_game('123',KEY,user_id='456',fetch=lambda u,h:(seen.append((u,h)) or {'id':123,'name':'My Game'}))
        self.assertEqual(actual,{'id':'123','name':'My Game'})
        self.assertEqual(urlsplit(seen[0][0]).hostname,'u-456.modapi.io')
        self.assertEqual(urlsplit(seen[0][0]).path,'/v1/games/123')
        self.assertNotIn(KEY,repr(actual))
    def test_wrong_game_is_rejected(self):
        with self.assertRaises(p.ProviderError):
            p.modio_game(123,KEY,user_id=456,fetch=lambda *_:{'id':111,'name':'Other'})
    def test_insecure_account_path_rejected(self):
        for bad in ('0','abc','1/../../','https://evil.example','-1','123?foo=1'):
            with self.subTest(bad=bad),self.assertRaises(p.ProviderError):
                p.modio_game(123,KEY,user_id=bad,fetch=lambda *_:self.fail('Network'))
    def test_blank_key_cannot_request_game(self):
        with self.assertRaises(p.ProviderError):
            p.modio_game(123,'',user_id=456,fetch=lambda *_:self.fail('Network'))
    def test_search_uses_user_host_and_game_scope(self):
        seen=[]
        r=p.search_modio('Some mod',123,KEY,user_id=456,fetch=lambda u,h:(seen.append((u,h)) or {'data':[{'id':88,'game_id':123,'name_id':'nice-mod','name':'Nice Mod','profile_url':'https://mod.io/g/my-game/m/nice-mod'}]}))
        self.assertEqual(len(r),1)
        u=urlsplit(seen[0][0]);self.assertEqual(u.hostname,'u-456.modapi.io')
        self.assertEqual(u.path,'/v1/games/123/mods')
        self.assertEqual(parse_qs(u.query)['api_key'],[KEY])
        self.assertNotIn(KEY,repr(r))
    def test_blocks_wrong_game_in_response(self):
        r=p.search_modio('Some mod',123,KEY,user_id=456,fetch=lambda *_:{'data':[{'id':88,'game_id':987,'name_id':'nice-mod','name':'Wrong','profile_url':'https://mod.io/g/wrong/m/nice-mod'}]})
        self.assertEqual(r,[])
    def test_rejects_profile_with_query_token(self):
        r=p.search_modio('Some mod',123,KEY,user_id=456,fetch=lambda *_:{'data':[{'id':88,'game_id':123,'name_id':'nice-mod','profile_url':'https://mod.io/g/my-game/m/nice-mod?token=abc'}]})
        self.assertEqual(r,[])
    def test_rejects_profile_credential_host(self):
        r=p.search_modio('Some mod',123,KEY,user_id=456,fetch=lambda *_:{'data':[{'id':88,'game_id':123,'name_id':'nice-mod','profile_url':'https://evil@mod.io/g/my-game/m/nice-mod'}]})
        self.assertEqual(r,[])
    def test_rejects_invalid_response(self):
        with self.assertRaises(p.ProviderError):
            p.search_modio('Some mod',123,KEY,user_id=456,fetch=lambda *_:{'data':'bad'})
    def test_host_allowlist_accepts_unique_user_endpoint(self):
        self.assertEqual(p.fetch_json('https://u-456.modapi.io/v1/games/123',fetch=lambda *_:{'ok':True}),{'ok':True})
    def test_allow_documented_public_read_only_host(self):
        self.assertEqual(p.fetch_json('https://api.mod.io/v1/games',fetch=lambda *_:{'data':[]}),{'data':[]})
    def test_host_allowlist_rejects_impostors(self):
        for hostname in ('u-0.modapi.io','u-123.modapi.io.evil.com','api.mod.io.evil.net','u-123.modapi.io.evil.net'):
            with self.subTest(hostname=hostname),self.assertRaises(p.ProviderError):
                p.fetch_json('https://'+hostname+'/v1/games/1',fetch=lambda *_:self.fail('network'))
    def test_search_router_passes_user_id(self):
        seen=[]
        r=p.search('mod.io','Some mod',game_id=123,key=KEY,user_id=456,fetch=lambda u,h:(seen.append(u) or {'data':[]}))
        self.assertEqual(r,[])
        self.assertIn('u-456.modapi.io',seen[0])

if __name__=='__main__':unittest.main()
