import unittest
import urllib.parse
from unittest.mock import patch
import provider_catalogues as p

class CatalogueTests(unittest.TestCase):
    def test_registry(self):
        self.assertEqual(set(p.PROVIDERS),{'Nexus Mods','Thunderstore','GitHub','Modrinth','CurseForge','mod.io'})
    def test_reject_too_short(self):
        with self.assertRaises(p.ProviderError):p.clean_search(' ')
    def test_reject_control(self):
        with self.assertRaises(p.ProviderError):p.clean_search('safe\rAuthorization: test')
    def test_reject_thunderstore_slug(self):
        with self.assertRaises(p.ProviderError):p.search_thunderstore('gear','../../etc',fetch=lambda *_:[])
    def test_thunderstore_exact_url(self):
        r=p.search_thunderstore('gear','valheim',fetch=lambda url,headers:[
           {'owner':'Creator','name':'UsefulGear','versions':[{'version_number':'1.3.1','description':'gear enhancement'}], 'total_downloads':120},
           {'owner':'Bad/owner','name':'UsefulGear','versions':[]}])
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['url'],'https://thunderstore.io/c/valheim/p/Creator/UsefulGear/')
    def test_thunderstore_no_unrelated(self):
        self.assertEqual(p.search_thunderstore('gear','valheim',fetch=lambda url,h:[{'owner':'A','name':'B','versions':[]}]),[])
    def test_github_safe_canonical(self):
        r=p.search_github('storm',fetch=lambda url,h:{'items':[
             {'full_name':'maintainer/storm', 'name':'Storm','description':'my mod'},
             {'full_name':'../../phishing', 'name':'danger'},
             {'full_name':'archived/cool', 'archived':True}]})
        self.assertEqual([x['url'] for x in r],['https://github.com/maintainer/storm'])
    def test_github_proper_query(self):
        seen=[]
        p.search_github('test mod',fetch=lambda u,h:(seen.append(u) or {'items':[]}))
        self.assertIn('test+mod',seen[0])
    def test_modrinth_canonical_project_link(self):
        r=p.search_modrinth('fabric',fetch=lambda url,headers:{'hits':[
            {'project_id':'AABB1234','project_type':'mod','title':'Fabric Things','author':'test'},
            {'project_id':'evil/..','project_type':'mod'}]})
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['url'],'https://modrinth.com/mod/AABB1234')
    def test_curseforge_requires_key(self):
        with self.assertRaises(p.ProviderError):p.search_curseforge('better',432,'')
    def test_curseforge_pages_sanitized(self):
        seen=[]
        r=p.search_curseforge('better',432,'private-app-key',fetch=lambda u,h:(seen.append((u,h)) or {'data':[
           {'id':201,'name':'Better Mod','summary':'Fine','links':{'websiteUrl':'https://www.curseforge.com/minecraft/mc-mods/better'}},
           {'id':202,'links':{'websiteUrl':'https://evil.example/mod'}}]}))
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['url'],'https://www.curseforge.com/minecraft/mc-mods/better')
        self.assertEqual(seen[0][1]['x-api-key'],'private-app-key')
        self.assertNotIn('private-app-key',repr(r))
    def test_modio_requires_key(self):
        with self.assertRaises(p.ProviderError):p.search_modio('my mod',14,'')
    def test_modio_only_official_page(self):
        seen=[]
        r=p.search_modio('some mod',14,'private-app-key',fetch=lambda u,h:(seen.append(u) or {'data':[
           {'id':44,'name_id':'test-mod','name':'Test mod','profile_url':'https://mod.io/g/my-game/m/test-mod'},
           {'id':45,'name_id':'bad-mod','profile_url':'https://malware.example/mod'}]}))
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['url'],'https://mod.io/g/my-game/m/test-mod')
        self.assertIn('api_key=private-app-key',seen[0]);self.assertNotIn('private-app-key',str(r))
    def test_keyless_metadata_no_auto_identify(self):
        r=p.search_github('Stardew',fetch=lambda u,h:{'items':[{'full_name':'User/Stardew'}]})
        self.assertNotIn('matched_smapi_id',r[0]);self.assertNotIn('installed',r[0])
    def test_provider_unknown(self):
        with self.assertRaises(p.ProviderError):p.search('ModDB','test')
    def test_github_response_type(self):
        with self.assertRaises(p.ProviderError):p.search_github('thing',fetch=lambda *_:'html')
    def test_readiness_without_slug(self):
        r=p.readiness(websocket_available=True)
        self.assertFalse(r['slug_configured'])
        self.assertTrue(any('OAuth public client ID' in x for x in r['required_from_nexus']))
    def test_readiness_with_slug_not_approval(self):
        r=p.readiness('approved-looking-slug',True)
        self.assertTrue(r['slug_configured'])
        self.assertIn('awaiting Nexus',r['nexus_registration'])
    def test_host_allowlist(self):
        with self.assertRaises(p.ProviderError):p.fetch_json('https://test.example/api',fetch=lambda *_:{})
    def test_https_required(self):
        with self.assertRaises(p.ProviderError):p.fetch_json('http://api.github.com/search/repositories',fetch=lambda *_:{})
    def test_link_no_credentials(self):
        with self.assertRaises(p.ProviderError):p.fetch_json('https://evil@api.github.com/search/repositories',fetch=lambda *_:{})
    def test_numeric(self):
        with self.assertRaises(p.ProviderError):p.numeric('0')
    def test_no_offsite_redirect(self):
        h=p.NoOffsiteRedirect('api.github.com')
        with self.assertRaises(p.ProviderError):h.redirect_request(None,None,302,'',{},'https://evil.example/p')

if __name__=='__main__':unittest.main()
