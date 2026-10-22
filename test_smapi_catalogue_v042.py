import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import smapi_catalogue
import unimod

class CatalogueResolutionTests(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        root=Path(self.home.name)
        self.game={'name':'Stardew Valley','root':str(root/'Stardew Valley'),'kind':'smapi'}
        self.mod={'name':'Custom Mod','uid':'Example.Unique.Mod','version':'1.2.3','path':str(root/'Stardew Valley/Mods/MyMod'), 'update_keys':[], 'enabled':True}
        self.cache=root/'cache.json';self.overrides=root/'overrides.json'
        self.p1=patch.object(unimod,'SMAPI_EXACT_CACHE',self.cache)
        self.p2=patch.object(unimod,'SOURCE_OVERRIDES',self.overrides)
        self.p1.start();self.p2.start();self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop)

    def fetch(self,url,request):
        self.assertEqual(url,smapi_catalogue.URL)
        self.assertEqual(request['mods'][0]['id'],'Example.Unique.Mod')
        self.assertEqual(request['platform'],'Linux')
        return [{'id':'Example.Unique.Mod','metadata':{'id':['Example.Unique.Mod'],'nexusID':1234}}]

    def test_exact_uid_without_nexus_key_and_cache(self):
        matched=smapi_catalogue.resolve_smapi_ids([self.mod],fetch=self.fetch)
        self.assertEqual(matched['example.unique.mod']['nexus_id'],'1234')
        result=unimod.cache_exact_smapi_matches(self.game,[self.mod],matched)
        self.assertEqual(result['added'],1)
        self.assertEqual(unimod.nexus_reference(self.game,self.mod)['mod_id'],'1234')
        self.assertEqual(unimod.reconcile_source(self.game,self.mod)['status'],'SMAPI catalogue exact ID')
        self.assertEqual(unimod.source_report(self.game,[self.mod])[0]['match_type'],'SMAPI catalogue exact ID')
        self.assertEqual(unimod.cache_exact_smapi_matches(self.game,[self.mod],matched)['added'],0)

    def test_rejects_unrelated_uid_and_malicious_id(self):
        for val in [999, 'javascript:alert(1)','-10','',{}]:
            with self.subTest(val=val):
                response=lambda url, body: [{'id':'Example.Unique.Mod','metadata':{'id':['Someone.Else'],'nexusID':val}}]
                self.assertEqual(smapi_catalogue.resolve_smapi_ids([self.mod],fetch=response),{})
        mismatch=lambda url, body: [{'id':'Unknown.Mod','metadata':{'id':['Example.Unique.Mod'],'nexusID':123}}]
        self.assertEqual(smapi_catalogue.resolve_smapi_ids([self.mod],fetch=mismatch),{})

    def test_manual_and_explicit_precedence(self):
        matched={'example.unique.mod':{'nexus_id':'1234'}}
        unimod.save_source_assignment(self.game,self.mod,'https://www.nexusmods.com/stardewvalley/mods/7777')
        self.assertEqual(unimod.cache_exact_smapi_matches(self.game,[self.mod],matched)['added'],0)
        self.assertEqual(unimod.nexus_reference(self.game,self.mod)['mod_id'],'7777')
        unimod.clear_source_assignment(self.game,self.mod)
        explicit={**self.mod,'update_keys':['Nexus:5678']}
        self.assertEqual(unimod.cache_exact_smapi_matches(self.game,[explicit],matched)['added'],0)
        self.assertEqual(unimod.nexus_reference(self.game,explicit)['mod_id'],'5678')

    def test_existing_cache_not_overwritten_by_conflicting_api(self):
        unimod.cache_exact_smapi_matches(self.game,[self.mod],{'example.unique.mod':{'nexus_id':'1234'}})
        result=unimod.cache_exact_smapi_matches(self.game,[self.mod],{'example.unique.mod':{'nexus_id':'9012'}})
        self.assertEqual(result['added'],0)
        self.assertEqual(unimod.nexus_reference(self.game,self.mod)['mod_id'],'1234')

    def test_does_not_send_file_paths_or_names(self):
        def fetch(url,payload):
            raw=json.dumps(payload)
            self.assertNotIn('MyMod',raw)
            self.assertNotIn('Custom Mod',raw)
            self.assertNotIn(str(Path(self.home.name)),raw)
            return []
        self.assertEqual(smapi_catalogue.resolve_smapi_ids([self.mod],fetch=fetch),{})

if __name__=='__main__':unittest.main()
