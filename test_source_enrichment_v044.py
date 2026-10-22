"""Local deterministic proof for SMAPI main-page metadata and bundled components."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import smapi_catalogue
import unimod

class V044SourceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.game={'name':'Stardew Valley','kind':'smapi','root':str(base)}
        self.mod={'uid':'OtherAuthor.Example','name':'Example','path':str(base/'Mods'/'Example'),
                  'version':'3.2.1','update_keys':[],'enabled':True}
        self.cache=patch.object(unimod,'SMAPI_EXACT_CACHE',base/'exact-cache.json')
        self.cache.start();self.addCleanup(self.cache.stop)
        self.over=patch.object(unimod,'SOURCE_OVERRIDES',base/'manual-sources.json')
        self.over.start();self.addCleanup(self.over.stop)

    def test_main_page_recognised_even_when_no_update_recommended(self):
        def fetch(url,payload):
            return [{'id':self.mod['uid'],'metadata':{'id':[self.mod['uid']],
               'main':{'version':'3.2.1','url':'https://www.nexusmods.com/stardewvalley/mods/2456'}},
               'suggestedUpdate':None,'errors':[]}]
        result=smapi_catalogue.resolve_smapi_ids([self.mod],fetch=fetch,diagnostics=True)
        self.assertEqual(result['matches']['otherauthor.example']['nexus_id'],'2456')
        self.assertEqual(result['matched_by_main'],1)
        self.assertEqual(unimod.cache_exact_smapi_matches(self.game,[self.mod],result['matches'])['added'],1)
        rows=unimod.unified_update_rows(self.game,[self.mod])
        self.assertEqual(rows[0]['source'],'Nexus')
        self.assertEqual(rows[0]['status'],'Not checked')

    def test_main_page_does_not_accept_other_games_or_lookalike_hosts(self):
        for url in ('https://nexusmods.com/skyrim/mods/55','https://nexusmods.com.evil.org/stardewvalley/mods/55',
                    'http://nexusmods.com/stardewvalley/mods/55','https://nexusmods.com@evil.org/stardewvalley/mods/55'):
            def fetch(*_):return [{'id':self.mod['uid'],'metadata':{'main':{'url':url}}}]
            with self.subTest(url=url):self.assertEqual(smapi_catalogue.resolve_smapi_ids([self.mod],fetch=fetch),{})

    def test_conflicting_main_and_nexus_id_rejected(self):
        def fetch(*_):return [{'id':self.mod['uid'],'metadata':{'nexusID':1234,'main':{'url':'https://www.nexusmods.com/stardewvalley/mods/4321'}}}]
        self.assertEqual(smapi_catalogue.resolve_smapi_ids([self.mod],fetch=fetch),{})

    def test_smapi_bundled_sources_not_reported_as_missing(self):
        for uid in ('SMAPI.ConsoleCommands','SMAPI.SaveBackup'):
            mod={**self.mod,'uid':uid,'name':uid,'path':self.mod['path']+'/'+uid}
            self.assertEqual(unimod.reconcile_source(self.game,mod)['source'],'SMAPI')
            self.assertEqual(unimod.source_report(self.game,[mod])[0]['match_type'],'Bundled with SMAPI')
            self.assertEqual(unimod.unified_update_rows(self.game,[mod])[0]['status'],'Bundled component')
            self.assertEqual(unimod.unified_update_rows(self.game,[mod])[0]['source'],'SMAPI')
            def should_not_call(*_):raise AssertionError('Bundled mod must not be queried')
            result=smapi_catalogue.resolve_smapi_ids([mod],fetch=should_not_call,diagnostics=True)
            self.assertEqual(result['requested'],0)
            self.assertEqual(result['bundled'],1)

    def test_no_false_source_on_missing_catalogue_records(self):
        result=smapi_catalogue.resolve_smapi_ids([self.mod],fetch=lambda *_: [{'id':self.mod['uid'],'metadata':{}}],diagnostics=True)
        self.assertEqual(result['matches'],{})
        self.assertEqual(result['no_nexus'],1)

if __name__=='__main__':unittest.main()
