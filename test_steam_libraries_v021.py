"""v0.21 read-only mounted Steam library discovery and manual registration."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod

class SteamLibrariesV021(unittest.TestCase):
    @staticmethod
    def make_game(base):
        apps=base/'steamapps'
        mod=apps/'common'/'ModdedGame'/'BepInEx'/'plugins'/'Existing'
        mod.mkdir(parents=True)
        (mod/'Existing.dll').write_bytes(b'untouched')
        (apps/'appmanifest_40312.acf').write_text(
            '"AppState"\n{\n"appid" "40312"\n"name" "Modded Game"\n"installdir" "ModdedGame"\n}\n', encoding='utf-8')
        return apps,mod/'Existing.dll'

    def test_nested_mnt_steam_library_detected_without_mod_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mount=Path(d)/'mnt'
            apps,dll=self.make_game(mount/'games'/'Steam')
            found=unimod.mounted_steam_libraries([mount])
            self.assertEqual(found,[apps.resolve()])
            self.assertEqual(dll.read_bytes(),b'untouched')
            with patch.object(unimod,'steam_roots',return_value=found):
                games=unimod.detect_games()
            self.assertEqual([(g['appid'],g['name']) for g in games],[('40312','Modded Game')])

    def test_media_user_drive_depth_and_no_symlink_walk(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'media'
            apps,_=self.make_game(root/'user'/'disk'/'SteamLibrary')
            self.assertIn(apps.resolve(),unimod.mounted_steam_libraries([root]))
            (root/'linked').symlink_to(apps.parent,target_is_directory=True)
            self.assertEqual(unimod.mounted_steam_libraries([root]).count(apps.resolve()),1)

    def test_explicit_path_normalization_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);apps,_=self.make_game(base/'external-disk'/'some-deep'/'SteamLibrary')
            storage=base/'config'/'steam-libraries.json'
            with patch.object(unimod,'STEAM_LIBRARY_CONFIG',storage),patch.object(unimod,'mounted_steam_libraries',return_value=[]):
                self.assertEqual(unimod.normalize_steam_library(apps.parent),apps.resolve())
                self.assertEqual(unimod.normalize_steam_library(apps),apps.resolve())
                self.assertIsNone(unimod.normalize_steam_library(base/'missing'))
                saved=unimod.save_custom_steam_libraries([str(apps),str(apps.parent)])
                self.assertEqual(saved,[str(apps.resolve())])
                self.assertEqual(unimod.load_custom_steam_libraries(),[str(apps.resolve())])
                inventory=unimod.steam_library_inventory()
                self.assertTrue(any(i['path']==str(apps.resolve()) and 'Custom' in i['origin'] for i in inventory))
                self.assertIn(apps.resolve(),unimod.steam_roots())

    def test_invalid_and_stale_persisted_locations_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            storage=Path(d)/'steam-libraries.json'
            with patch.object(unimod,'STEAM_LIBRARY_CONFIG',storage),patch.object(unimod,'mounted_steam_libraries',return_value=[]):
                storage.write_text('invalid json',encoding='utf-8')
                self.assertEqual(unimod.load_custom_steam_libraries(),[])
                storage.write_text(json.dumps(['nonexistent',{},'../unknown']),encoding='utf-8')
                self.assertFalse(any(x['path']=='../unknown' for x in unimod.steam_library_inventory()))

    def test_nested_game_with_unsafe_manifest_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            mount=Path(d)/'mnt'; apps,dll=self.make_game(mount/'data'/'Steam')
            (apps/'appmanifest_40312.acf').write_text('"appid" "40312"\n"installdir" "../evil"\n"name" "Bad"\n')
            found=unimod.mounted_steam_libraries([mount])
            with patch.object(unimod,'steam_roots',return_value=found):
                self.assertEqual(unimod.steam_appmanifest_games(apps),[])
                self.assertEqual(unimod.detect_games(),[])
            self.assertEqual(dll.read_bytes(),b'untouched')

if __name__=='__main__':unittest.main()
