"""Collection provenance, Nexus error diagnostics and safe API use."""
import io, json, socket, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
import unimod

class NexusOriginTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.base=Path(t.name)
        self.g={'name':'Stardew Valley','kind':'smapi','root':str(self.base/'Stardew Valley')}
        self.m={'name':'Unlinked','uid':'demo.unlinked','path':str(self.base/'Stardew Valley'/'Mods'/'Unlinked'),
                'version':'1.0.0','update_keys':[],'enabled':True}
        patches=[patch.object(unimod,'COLLECTION_SOURCES',self.base/'collection-sources.json'),
                 patch.object(unimod,'SOURCE_OVERRIDES',self.base/'source-overrides.json')]
        for p in patches:p.start();self.addCleanup(p.stop)
    def test_site_only_not_id(self):
        self.assertIsNone(unimod.nexus_reference(self.g,self.m))
        unimod.set_nexus_collection_origin(self.g,True)
        self.assertTrue(unimod.nexus_collection_origin(self.g))
        row=unimod.reconcile_source(self.g,self.m)
        self.assertEqual(row['source'],'Nexus Mods')
        self.assertEqual(row['status'],'Nexus origin — page ID needed')
        self.assertEqual(row['url'],'')
        self.assertIsNone(unimod.nexus_reference(self.g,self.m))
        self.assertEqual(unimod.source_report(self.g,[self.m])[0]['match_type'], 'Owner-declared origin; link needed')
    def test_site_preference_persistence_and_reversible(self):
        unimod.set_nexus_collection_origin(self.g,True)
        self.assertEqual(json.loads(unimod.COLLECTION_SOURCES.read_text())[unimod.collection_source_key(self.g)],'Nexus Mods')
        unimod.set_nexus_collection_origin(self.g,False)
        self.assertFalse(unimod.nexus_collection_origin(self.g))
        self.assertEqual(unimod.reconcile_source(self.g,self.m)['status'],'Unmatched')
    def test_explicit_page_retained_over_origin(self):
        unimod.set_nexus_collection_origin(self.g,True)
        unimod.save_source_assignment(self.g,self.m,'https://www.nexusmods.com/stardewvalley/mods/123')
        self.assertEqual(unimod.nexus_reference(self.g,self.m)['mod_id'],'123')
        self.assertEqual(unimod.reconcile_source(self.g,self.m)['status'],'Assigned by user')
    def test_other_games_unchanged(self):
        self.assertFalse(unimod.nexus_collection_origin({'kind':'bepinex','root':str(self.base)}))
        with self.assertRaises(ValueError):unimod.set_nexus_collection_origin({'kind':'bepinex','root':str(self.base)},True)
    def test_api_validation_and_credential_not_exposed(self):
        got=[]
        self.assertTrue(unimod.nexus_validate_key('private-key-123',fetch=lambda u,h:(got.append((u,h)) or {'user_id':55})))
        self.assertEqual(got[0][0],'https://api.nexusmods.com/v1/users/validate.json')
        self.assertEqual(got[0][1]['Application-Version'],'0.54.0')
        self.assertEqual(got[0][1]['apikey'],'private-key-123')
        with self.assertRaises(ValueError):unimod.nexus_validate_key('private-key-123',fetch=lambda u,h:{'unexpected':'response'})
    def test_network_failure_is_actionable(self):
        reason=urllib.error.URLError(socket.gaierror(-3, 'Temporary failure in name resolution'))
        with patch.object(unimod.urllib.request,'build_opener') as builder:
            builder.return_value.open.side_effect=reason
            with self.assertRaisesRegex(ValueError,'DNS'):
                unimod.nexus_mod_info('stardewvalley','123','secret-key')
    def test_http_codes_meaningful_and_safe(self):
        for code,term in [(401,'Authentication'),(403,'Access denied'),(404,'not found'),(429,'Rate limit'),(502,'server unavailable')]:
            error=urllib.error.HTTPError('https://api.nexusmods.com/v1/x',code,'no',{},io.BytesIO(b''))
            with patch.object(unimod.urllib.request,'build_opener') as builder:
                builder.return_value.open.side_effect=error
                with self.assertRaises(ValueError) as caught:
                    unimod.nexus_mod_info('stardewvalley','123','secret-key')
            self.assertIn(term.lower(),str(caught.exception).lower())
            self.assertNotIn('secret-key',str(caught.exception))
    def test_stop_after_shared_network_failure(self):
        a={**self.m,'path':'/first','update_keys':['Nexus:123']}
        b={**self.m,'path':'/second','update_keys':['Nexus:321']}
        fetches=[]
        def failure(url,headers):
            fetches.append(url)
            raise ValueError('Network connection failed. Check DNS, internet access, proxy and firewall settings.')
        result=unimod.check_nexus_updates(self.g,[a,b],'key',fetch= failure)
        self.assertEqual(len(fetches),1)
        self.assertEqual(len(result),1)
        self.assertEqual(result[a['path']]['status'],'Check failed')

if __name__=='__main__':unittest.main()
