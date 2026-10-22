"""v0.25 read-only source matching tests: no remote requests or game writes."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod

class SourceReconciliationV025Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.game={'root':str(self.folder/'Stardew Valley'),'name':'Stardew Valley','kind':'smapi'}
        self.patch=patch.object(unimod,'SOURCE_OVERRIDES',self.folder/'sources.json')
        self.patch.start();self.addCleanup(self.patch.stop)
        self.default={'name':'Test Mod','uid':'User.Test','version':'1.2.0',
                      'enabled':True,'path':str(self.folder/'Stardew Valley/Mods/Test'),
                      'relative':'Test','update_keys':[]}

    def test_unmatched_remains_unmatched(self):
        record=unimod.reconcile_source(self.game,self.default)
        self.assertEqual(record['status'],'Unmatched')
        self.assertEqual(record['url'],'')

    def test_exact_nexus_id_uses_game_domain(self):
        record=unimod.reconcile_source(self.game,{**self.default,'update_keys':['Nexus:12345']})
        self.assertEqual(record['status'],'Update key link')
        self.assertEqual(record['url'],'https://www.nexusmods.com/stardewvalley/mods/12345')

    def test_unknown_game_does_not_guess_stardew_domain(self):
        game={**self.game,'name':'Another Game'}
        record=unimod.reconcile_source(game,{**self.default,'update_keys':['Nexus:12345']})
        self.assertEqual(record['status'],'Key only — review needed')
        self.assertFalse(record['url'])

    def test_multiple_github_and_nexus_links(self):
        record=unimod.reconcile_source(self.game,{**self.default,'update_keys':['Nexus:21','GitHub:author/repo']})
        self.assertEqual(record['status'],'Multiple source links')
        self.assertEqual(record['url'],'https://www.nexusmods.com/stardewvalley/mods/21')
        self.assertEqual(record['alternatives'],['https://github.com/author/repo/releases'])

    def test_conflicting_nexus_ids_never_picked(self):
        record=unimod.reconcile_source(self.game,{**self.default,'update_keys':['Nexus:1','Nexus:2']})
        self.assertEqual(record['status'],'Conflicting Nexus keys')
        self.assertFalse(record['url'])

    def test_manual_source_precedes_keys(self):
        unimod.save_source_assignment(self.game,self.default,'https://www.moddb.com/mods/example')
        record=unimod.reconcile_source(self.game,{**self.default,'update_keys':['Nexus:30']})
        self.assertEqual(record['status'],'Assigned by user')
        self.assertEqual(record['source'],'ModDB')
        self.assertIn('moddb.com',record['url'])

    def test_invalid_url_does_not_override_keys(self):
        record=unimod.reconcile_source(self.game,{**self.default,'website_url':'https://github.com.evil.net/x',
                      'update_keys':['GitHub:owner/repo']})
        self.assertEqual(record['source'],'GitHub')
        self.assertEqual(record['url'],'https://github.com/owner/repo/releases')

    def test_metadata_website_precedes_key(self):
        record=unimod.reconcile_source(self.game,{**self.default,'website_url':'https://thunderstore.io/c/valheim/p/a/b/',
                       'update_keys':['GitHub:owner/repo']})
        self.assertEqual(record['source'],'Thunderstore')
        self.assertEqual(record['status'],'Metadata link')

    def test_unrecognised_key_cannot_forge_url(self):
        record=unimod.reconcile_source(self.game,{**self.default,'update_keys':['Nexus:not-an-id']})
        self.assertEqual(record['status'],'Key only — review needed')
        self.assertEqual(record['url'],'')

    def test_existing_bepinex_manifest_link(self):
        game={'name':'Graveyard Keeper 2','root':str(self.folder),'kind':'bepinex'}
        base=self.folder/'BepInEx'/'plugins'
        folder=base/'ExamplePlugin';folder.mkdir(parents=True)
        (folder/'Example.dll').write_bytes(b'placeholder')
        (folder/'manifest.json').write_text(json.dumps({
            'name':'Example','version_number':'1.3.0',
            'website_url':'https://thunderstore.io/c/valheim/p/example/package/'}))
        mods=unimod.discover_bepinex(base,True)
        record=unimod.source_reconciliation(game,mods)[0]
        self.assertEqual(record['status'],'Metadata link')
        self.assertEqual(record['source'],'Thunderstore')
        self.assertEqual(record['version'],'1.3.0')

    def test_disabled_entries_retained(self):
        rows=unimod.source_reconciliation(self.game,[self.default,{**self.default,'name':'Disabled',
                                      'enabled':False,'path':'/somewhere/else'}])
        self.assertEqual(len(rows),2)
        self.assertFalse(rows[1]['enabled'])

    def test_csv_export_preserves_multiple_choices(self):
        output=self.folder/'report.csv'
        count=unimod.export_source_reconciliation(output,self.game,[{**self.default,
                               'update_keys':['Nexus:1','GitHub:owner/repo']}])
        self.assertEqual(count,1)
        with output.open(encoding='utf-8-sig',newline='') as fp:
            rows=list(csv.DictReader(fp))
        self.assertEqual(rows[0]['status'],'Multiple source links')
        self.assertEqual(rows[0]['alternatives'],'https://github.com/owner/repo/releases')

if __name__=='__main__':unittest.main()
