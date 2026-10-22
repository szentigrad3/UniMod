"""Regression: 29 Stardew mod directories, of which only 11 contain valid SMAPI manifests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod

class ExistingFoldersTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'Stardew Valley'
        self.mods=self.root/'Mods';self.mods.mkdir(parents=True)
        self.game={'name':'Stardew Valley','kind':'smapi','root':str(self.root)}
        self.names=['TimeSpeed','BetterCrafting','UIInfoSuite2','FarmTypeManager','FTM SVE',
                    'FTM Ridgeside','East Scarp NPCs','East Scarp Core','CP Lumisteria',
                    'SpaceCore','NPCMapLocations','Automate','LookupAnything','GenericModConfigMenu',
                    'ContentPatcher','MappingExtensions','SaveBackup','ConsoleCommands',
                    'CustomCompanions','ESBarberShop','East Scarp FTM','East Scarp C#',
                    'CP HxW Tilesheets','CP Stardew Valley Expanded','Stardew Valley Expanded Code',
                    'CP Ridgeside Village','CC Ridgeside Village','RidgesideVillage','CP Lumisteria Outdoor']
        assert len(self.names)==29
        for i,name in enumerate(self.names):
            folder=self.mods/name;folder.mkdir()
            if i < 11:
                (folder/'manifest.json').write_text(json.dumps({'Name':name+' official',
                    'Version':'1.0.0','UniqueID':f'demo.mod{i}'}))
        patcher=patch.object(unimod,'SOURCE_OVERRIDES',Path(self.tmp.name)/'sources.json')
        patcher.start();self.addCleanup(patcher.stop)

    def test_exhaustive_folder_discovery(self):
        mods=unimod.items(self.game)
        self.assertEqual(len(mods),11)
        groups=unimod.mod_packages(self.game,mods)
        self.assertEqual(len(groups),29)
        self.assertEqual(sum(g['kind']=='SMAPI manifest' for g in groups),11)
        self.assertEqual(sum(g.get('is_folder_only',False) for g in groups),18)
        self.assertEqual(unimod.existing_mod_health(self.game,mods)['unmanaged'],18)
        self.assertEqual(len(unimod.global_mod_library([self.game])['mods']),29)
        self.assertEqual(next(x for x in groups if x['name']=='ESBarberShop')['kind'],'Installed mod folder (metadata not found)')

    def test_container_separate_from_nested_manifest(self):
        p=self.mods/'NestedPack'/'Actual';p.mkdir(parents=True)
        (p/'manifest.json').write_text(json.dumps({'Name':'Embedded','UniqueID':'demo.embedded'}))
        groups=unimod.mod_packages(self.game)
        self.assertEqual(len(groups),31)
        container=next(g for g in groups if g['name']=='NestedPack')
        self.assertIn('Modpack folder',container['kind'])
        self.assertTrue(container['is_folder_only'])
        self.assertEqual(sum(x['name']=='Embedded' for x in groups),1)

    def test_symlink_visible_but_not_recursively_scanned(self):
        outside=Path(self.tmp.name)/'ExternalMod';outside.mkdir()
        (outside/'manifest.json').write_text(json.dumps({'Name':'External','UniqueID':'out'}))
        (self.mods/'LinkedExternal').symlink_to(outside,target_is_directory=True)
        groups=unimod.mod_packages(self.game)
        match=next(g for g in groups if g['name']=='LinkedExternal')
        self.assertEqual(match['kind'],'Linked mod folder (read-only)')
        self.assertFalse(any(g['name']=='External' for g in groups))

if __name__=='__main__':unittest.main()
