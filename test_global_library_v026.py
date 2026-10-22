"""Cross-game inventory tests using only temporary local mock mods."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod

class GlobalLibraryV026Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.game=self.base/'Stardew Valley'
        def create(folder,name,uid,version='1.0.0',keys=()):
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':uid,'Version':version,'UpdateKeys':list(keys)}))
        create(self.game/'Mods'/'A','A Stardew Mod','demo.a',keys=('Nexus:100',))
        create(self.game/'Mods'/'Collection'/'Inner','Nested Pack','demo.b')
        create(self.game/'Mods'/"=INJECTED()",'=INJECTED()','demo.c')
        create(self.game/'.unimod-disabled'/'Hidden','Disabled Mod','demo.d')
        self.bep=self.base/'GK2';base=self.bep/'BepInEx'/'plugins'
        (base/'Managed'/'lib').mkdir(parents=True)
        (base/'Managed'/'Main.dll').write_bytes(b'dll')
        (base/'Managed'/'lib'/'Helper.dll').write_bytes(b'dll')
        (base/'Managed'/'manifest.json').write_text(json.dumps({'name':'MyPlugin','version_number':'2.1.0',
             'website_url':'https://thunderstore.io/c/valheim/p/sample/MyPlugin/'}))
        (base/'Other.dll').write_bytes(b'dll')
        self.games=[{'name':'Stardew Valley','kind':'smapi','root':str(self.game)},
                    {'name':'Graveyard Keeper 2','kind':'bepinex','root':str(self.bep)}]
        self.patcher=patch.object(unimod,'SOURCE_OVERRIDES',self.base/'user-sources.json')
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_combined_inventory_and_grouped_dlls(self):
        report=unimod.global_mod_library(self.games)
        self.assertEqual(report['games_scanned'],2)
        self.assertEqual(len(report['mods']),7)
        self.assertEqual(report['enabled'],5)
        managed=next(row for row in report['mods'] if row['mod']=='MyPlugin')
        self.assertEqual(managed['dll_count'],2)
        self.assertEqual(managed['source'],'Thunderstore')
        self.assertEqual(managed['version'],'2.1.0')
        self.assertEqual(report['unmanaged'],1)
        self.assertEqual(report['linked'],2)
        self.assertTrue(any(row['mod']=='Nested Pack' for row in report['mods']))

    def test_unmatched_and_disabled_are_visible(self):
        report=unimod.global_mod_library(self.games)
        disabled=next(row for row in report['mods'] if row['mod']=='Disabled Mod')
        self.assertFalse(disabled['enabled'])
        self.assertEqual(disabled['source_status'],'Unmatched')
        loose=next(row for row in report['mods'] if row['mod']=='Other')
        self.assertEqual(loose['source_status'],'Unmanaged')
        self.assertFalse(loose['source_url'])

    def test_missing_and_duplicate_paths(self):
        report=unimod.global_mod_library(self.games+[dict(self.games[0]),
              {'name':'Lost game','kind':'smapi','root':str(self.base/'does-not-exist')}])
        self.assertEqual(report['games_scanned'],2)
        self.assertEqual(len(report['mods']),7)
        self.assertEqual(len(report['problems']),1)

    def test_invalid_registration_and_input(self):
        report=unimod.global_mod_library([{'name':'Bad','kind':'smapi','root':'relative'},
                                         {'name':'Bad2','kind':'evil','root':str(self.game)}])
        self.assertEqual(len(report['problems']),2)
        with self.assertRaises(ValueError):unimod.global_mod_library('not a list')

    def test_no_online_name_matching(self):
        report=unimod.global_mod_library(self.games)
        unlinked=next(x for x in report['mods'] if x['mod']=='Nested Pack')
        self.assertEqual(unlinked['source_status'],'Unmatched')
        self.assertEqual(unlinked['source_url'],'')

    def test_csv_is_spreadsheet_safe(self):
        report=unimod.global_mod_library(self.games)
        target=self.base/'global.csv'
        count=unimod.export_global_mod_library(target,report)
        self.assertEqual(count,len(report['mods']))
        with target.open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertTrue(any(r['mod']=="'=INJECTED()" for r in rows))
        self.assertEqual(len(rows),len(report['mods']))

    def test_scanner_limit(self):
        report=unimod.global_mod_library(self.games,max_games=1)
        self.assertEqual(report['games_scanned'],1)
        self.assertEqual(len(report['mods']),5)

if __name__=='__main__':unittest.main()
