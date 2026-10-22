"""UniMod v0.18 regression: existing installed mods are read without modification."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod


class SteamAndPackageDiscoveryTests(unittest.TestCase):
    def test_new_steam_games_with_bepinex_and_melonloader(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);apps=home/'steamapps';common=apps/'common'
            g1=common/'GameAlpha';(g1/'BepInEx'/'plugins'/'Utilities').mkdir(parents=True)
            (g1/'BepInEx'/'plugins'/'Utilities'/'hello.dll').write_bytes(b'dummy')
            g2=common/'GameBeta';(g2/'MelonLoader').mkdir(parents=True)
            (g2/'Mods').mkdir()
            (g2/'Mods'/'Example.dll').write_bytes(b'dummy')
            (common/'VanillaGame').mkdir()
            for idx,(folder,name) in enumerate([('GameAlpha','Amazing Game'),('GameBeta','Another Game'),('VanillaGame','Vanilla')],1):
                (apps/f'appmanifest_{idx}.acf').write_text(
                    '\"AppState\"\n{\n \"name\" \"'+name+'\"\n \"installdir\" \"'+folder+'\"\n}\n')
            found=unimod.steam_appmanifest_games(apps)
            self.assertEqual({g['name']:g['kind'] for g in found},{'Amazing Game':'bepinex','Another Game':'melonloader'})
            with patch.object(unimod,'steam_roots',return_value=[apps]):
                detected=unimod.detect_games()
            self.assertEqual(len(detected),2)
            self.assertEqual({g['kind'] for g in detected},{'bepinex','melonloader'})

    def test_untrusted_steam_install_names_and_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            apps=Path(td)/'steamapps';common=apps/'common'
            common.mkdir(parents=True)
            external=Path(td)/'Outside';(external/'BepInEx'/'plugins').mkdir(parents=True)
            (common/'Linked').symlink_to(external,target_is_directory=True)
            for i,name in enumerate(['../Outside','/tmp','Linked'],1):
                (apps/f'appmanifest_{i}.acf').write_text('"AppState"\n{\n"installdir" "'+name+'"\n"name" "Unsafe"\n}\n')
            self.assertEqual(unimod.steam_appmanifest_games(apps),[])

    def test_existing_bepinex_packages_distinguish_unmanaged_and_nested(self):
        with tempfile.TemporaryDirectory() as td:
            game={'name':'Modded Game','kind':'bepinex','root':td}
            plugins=unimod.mod_root(game);plugins.mkdir(parents=True)
            pkg=plugins/'MyMod';(pkg/'bin').mkdir(parents=True)
            (pkg/'manifest.json').write_text(json.dumps({'name':'My Mod','author':'Dev','version_number':'1.0.0','website_url':'https://github.com/Dev/MyMod'}))
            (pkg/'bin'/'Main.dll').write_bytes(b'a')
            (pkg/'bin'/'Dependency.dll').write_bytes(b'b')
            (plugins/'Loose.dll').write_bytes(b'c')
            (plugins/'Other').mkdir();(plugins/'Other'/'Unknown.dll').write_bytes(b'd')
            data=unimod.items(game)
            groups=unimod.mod_packages(game,data)
            self.assertEqual(sum(g['dll_count'] for g in groups),4)
            self.assertEqual(len(groups),3)
            managed=next(g for g in groups if g['name']=='My Mod')
            self.assertEqual(managed['kind'],'Metadata package')
            self.assertEqual(managed['dll_count'],2)
            self.assertIn('Loose DLL',{g['kind'] for g in groups})
            self.assertIn('Unmanaged folder',{g['kind'] for g in groups})
            self.assertEqual(unimod.existing_mod_health(game,data)['unmanaged'],2)
            self.assertEqual((pkg/'bin'/'Main.dll').read_bytes(),b'a')

    def test_melonloader_discovery_is_read_only_and_installs_are_blocked(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            game={'name':'Melon Game','kind':'melonloader','root':str(root)}
            (root/'MelonLoader').mkdir()
            folder=root/'Mods'/'Nested';folder.mkdir(parents=True)
            (folder/'Melon.dll').write_bytes(b'keep me')
            (folder/'ignore.json').write_text('{}')
            (folder/'linked.dll').symlink_to(folder/'Melon.dll')
            found=unimod.items(game)
            self.assertEqual([m['name'] for m in found],['Melon'])
            groups=unimod.mod_packages(game,found)
            self.assertEqual(len(groups),1)
            self.assertEqual(groups[0]['kind'],'MelonLoader unmanaged folder')
            archive=root/'new.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('Mod.dll',b'content')
            with self.assertRaisesRegex(ValueError,'discovery-only'):
                unimod.install_zip(game,archive)
            self.assertEqual((folder/'Melon.dll').read_bytes(),b'keep me')

    def test_known_games_remain_detectable_without_mods(self):
        with tempfile.TemporaryDirectory() as td:
            apps=Path(td)/'steamapps';(apps/'common'/'Stardew Valley').mkdir(parents=True)
            with patch.object(unimod,'steam_roots',return_value=[apps]):
                found=unimod.detect_games()
            self.assertEqual([(g['name'],g['kind']) for g in found],[('Stardew Valley','smapi')])

if __name__=='__main__':unittest.main()

