"""v0.20 regression: Steam manifest matching and read-only local diagnostics."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod


class SteamProtonDiagnosticsTests(unittest.TestCase):
    @staticmethod
    def manifest(apps, appid, folder, title):
        (apps / f'appmanifest_{appid}.acf').write_text(
            f'"AppState"\n{{\n"appid" "{appid}"\n"name" "{title}"\n"installdir" "{folder}"\n}}\n',
            encoding='utf-8')

    def test_detected_steam_app_has_actual_id_and_matching_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            apps=Path(td)/'library/steamapps';game=apps/'common'/'TestTitle'
            (game/'BepInEx'/'plugins').mkdir(parents=True)
            (apps/'compatdata'/'1234'/'pfx').mkdir(parents=True)
            self.manifest(apps,1234,'TestTitle','Example Modded Game')
            with patch.object(unimod,'steam_roots',return_value=[apps]):
                discovered=unimod.detect_games()
                self.assertEqual(len(discovered),1)
                self.assertEqual(discovered[0]['appid'],'1234')
                ctx=unimod.steam_game_context(discovered[0])
            self.assertEqual(ctx['appid'],'1234')
            self.assertTrue(ctx['prefix_exists'])
            self.assertEqual(Path(ctx['proton_prefix']),apps/'compatdata'/'1234'/'pfx')
            self.assertTrue(ctx['steam_detected'])

    def test_vanilla_manifest_path_fallback_and_no_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            apps=Path(td)/'steamapps';game=apps/'common'/'NoMods';game.mkdir(parents=True)
            self.manifest(apps,9999,'NoMods','Vanilla')
            with patch.object(unimod,'steam_roots',return_value=[apps]):
                ctx=unimod.steam_game_context({'name':'Vanilla','root':str(game),'kind':'generic'})
            self.assertEqual(ctx['appid'],'9999')
            self.assertFalse(ctx['prefix_exists'])

    def test_compatdata_can_be_in_another_library(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);apps=root/'primary/steamapps';extra=root/'secondary/steamapps'
            game=apps/'common'/'PluginGame';(game/'BepInEx'/'plugins').mkdir(parents=True)
            (extra/'compatdata'/'77'/'pfx').mkdir(parents=True)
            self.manifest(apps,77,'PluginGame','Plugin Game')
            ctx=unimod.steam_game_context({'name':'Plugin Game','root':str(game),'kind':'bepinex'},[apps,extra])
            self.assertTrue(ctx['compatdata_found_elsewhere'])
            self.assertEqual(ctx['prefix_location'],str(extra))

    def test_read_only_bepinex_diagnostics_and_safe_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'game';(root/'BepInEx'/'plugins'/'A').mkdir(parents=True)
            (root/'BepInEx'/'plugins'/'A'/'A.dll').write_bytes(b'KEEP')
            (root/'BepInEx'/'core').mkdir()
            (root/'BepInEx'/'core'/'BepInEx.dll').write_bytes(b'core')
            (root/'winhttp.dll').write_bytes(b'loader')
            game={'name':'Example','root':str(root),'kind':'bepinex'}
            report=unimod.game_diagnostics(game,[])
            data={x['check']:x for x in report['checks']}
            self.assertEqual(data['BepInEx core']['status'],'OK')
            self.assertEqual(data['Windows proxy loader']['status'],'OK')
            self.assertEqual(data['Steam app ID']['status'],'Info')
            self.assertEqual(data['Existing mod entries']['details'],'1 discovered, 1 enabled')
            filename=Path(td)/'diagnostics.json'
            unimod.export_diagnostics(filename,report)
            self.assertEqual(json.loads(filename.read_text())['schema'],1)
            self.assertNotIn('api_key',filename.read_text())
            self.assertEqual((root/'BepInEx'/'plugins'/'A'/'A.dll').read_bytes(),b'KEEP')

    def test_stardew_smapi_diagnostics_and_no_loader(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'Stardew Valley';mod=root/'Mods'/'Example';mod.mkdir(parents=True)
            (mod/'manifest.json').write_text(json.dumps({'Name':'My Mod','UniqueID':'example.mod','Version':'1.0.0'}))
            game={'name':'Stardew Valley','root':str(root),'kind':'smapi'}
            report=unimod.game_diagnostics(game,[])
            statuses={c['check']:c['status'] for c in report['checks']}
            self.assertEqual(statuses['SMAPI loader'],'Warning')
            self.assertEqual(statuses['SMAPI installation audit'],'OK')
            (root/'StardewModdingAPI').write_bytes(b'')
            updated=unimod.game_diagnostics(game,[])
            self.assertEqual(next(c for c in updated['checks'] if c['check']=='SMAPI loader')['status'],'OK')

    def test_missing_game_is_safe(self):
        with tempfile.TemporaryDirectory() as td:
            game={'name':'Missing','root':str(Path(td)/'gone'),'kind':'bepinex'}
            report=unimod.game_diagnostics(game,[])
            self.assertEqual(report['checks'][0]['status'],'Missing')
            self.assertEqual(len(report['checks']),1)
            self.assertFalse(Path(game['root']).exists())

    def test_reject_traversal_manifest_install_path(self):
        with tempfile.TemporaryDirectory() as td:
            apps=Path(td)/'steamapps';root=apps/'common'/'Safe';root.mkdir(parents=True)
            self.manifest(apps,123,'../Safe','Escaping Game')
            ctx=unimod.steam_game_context({'name':'Escaping Game','root':str(root),'kind':'generic'},[apps])
            self.assertEqual(ctx['appid'],'')

if __name__ == '__main__':unittest.main()
