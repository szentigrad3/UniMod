"""Read-only synthetic Heroic/Lutris discovery coverage for v0.22."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod


class LauncherDiscoveryV022(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.cfg=self.base/'heroic'
        self.db=self.base/'pga.db'

    def game(self, name, kind='bepinex'):
        root=self.base/'games'/name
        if kind=='bepinex':
            folder=root/'BepInEx'/'plugins'/'Example'
            folder.mkdir(parents=True)
            (folder/'example.dll').write_bytes(b'DONT-TOUCH')
        elif kind=='smapi':
            folder=root/'Mods'/'Example'
            folder.mkdir(parents=True)
            (folder/'manifest.json').write_text(json.dumps({'Name':'Example','UniqueID':'test.example','Version':'1.0'}))
        else:
            folder=root/'MelonLoader'
            folder.mkdir(parents=True)
            (root/'Mods').mkdir(parents=True)
        return root

    def write_json(self,relative,data):
        path=self.cfg/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data),encoding='utf-8')
        return path

    def scan_heroic(self):
        return unimod.heroic_game_inventory([(self.cfg,'Heroic')])

    def test_heroic_epic_installed_and_unmodded_not_imported(self):
        root=self.game('EpicModded')
        unmodded=self.base/'games'/'EpicUnmodded';unmodded.mkdir()
        self.write_json('legendaryConfig/legendary/installed.json',{
            'epic-game':{'title':'Epic Game','install_path':str(root)},
            'unmodded':{'title':'Unmodded','install_path':str(unmodded)},
            'deleted':{'title':'Deleted','install_path':str(self.base/'no-game')}})
        found=self.scan_heroic()
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['name'],'Epic Game')
        self.assertEqual(found[0]['store'],'Epic')
        self.assertEqual((root/'BepInEx/plugins/Example/example.dll').read_bytes(),b'DONT-TOUCH')

    def test_heroic_gog_installed_wrapper_and_smapi(self):
        root=self.game('Stardew Valley','smapi')
        self.write_json('gog_store/installed.json',{'installed':[
            {'appName':'12345','title':'Stardew Valley','install_path':str(root)}]})
        found=self.scan_heroic()
        self.assertEqual([(g['launcher'],g['store'],g['kind']) for g in found],[('Heroic','GOG','smapi')])

    def test_heroic_amazon_array_and_dlc(self):
        root=self.game('SomeGame','melonloader')
        self.write_json('nile_config/nile/installed.json',[
            {'id':'amz1','name':'Some Game','path':str(root)},
            {'id':'dlc','path':str(root),'is_dlc':True}])
        found=self.scan_heroic()
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['store'],'Amazon')
        self.assertEqual(found[0]['kind'],'melonloader')

    def test_deduplicated_heroic_sources(self):
        root=self.game('SameGame')
        self.write_json('legendaryConfig/legendary/installed.json',{'1':{'install_path':str(root)}})
        self.write_json('gog_store/installed.json',{'installed':[{'install_path':str(root)}]})
        self.assertEqual(len(self.scan_heroic()),1)

    def test_invalid_malicious_broken_and_large_index_rejected(self):
        root=self.game('Valid')
        f=self.write_json('legendaryConfig/legendary/installed.json',{'1':{'install_path':str(root)}})
        f.write_text('{not-json')
        self.assertEqual(self.scan_heroic(),[])
        f.write_text('x'*(8*1024*1024+1))
        self.assertEqual(self.scan_heroic(),[])
        # Values should not point to an ambiguous relative location.
        self.write_json('legendaryConfig/legendary/installed.json',{'1':{'install_path':'../Valid'}})
        self.assertEqual(self.scan_heroic(),[])

    def test_symlink_game_directory_ignored(self):
        root=self.game('Valid')
        alias=self.base/'alias';alias.symlink_to(root,target_is_directory=True)
        self.write_json('legendaryConfig/legendary/installed.json',{'1':{'install_path':str(alias)}})
        self.assertEqual(self.scan_heroic(),[])

    def make_db(self,rows,fields='standard'):
        with sqlite3.connect(self.db) as conn:
            if fields=='standard':
                conn.execute('CREATE TABLE games (id INTEGER,name TEXT,directory TEXT,runner TEXT,installed INTEGER,configpath TEXT)')
                conn.executemany('INSERT INTO games VALUES (?,?,?,?,?,?)',rows)
            elif fields=='minimal':
                conn.execute('CREATE TABLE games (name TEXT,directory TEXT,installed INTEGER)')
                conn.executemany('INSERT INTO games VALUES (?,?,?)',rows)
            else:conn.execute('CREATE TABLE other (name TEXT)')

    def test_lutris_installed_and_existing_layout_only(self):
        game=self.game('LutrisGame')
        other=self.game('NotInstalled')
        self.make_db([(1,'Lutris Modded',str(game),'wine',1,'something'),
                      (2,'Not Installed',str(other),'wine',0,'something')])
        found=unimod.lutris_game_inventory([self.db])
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['name'],'Lutris Modded')
        self.assertEqual(found[0]['store'],'wine')
        self.assertEqual(found[0]['launcher'],'Lutris')

    def test_lutris_minimal_schema(self):
        game=self.game('Minimal')
        self.make_db([('Minimal',str(game),1)],'minimal')
        self.assertEqual(len(unimod.lutris_game_inventory([self.db])),1)

    def test_lutris_unknown_schema_or_corrupt_db(self):
        self.make_db([],'broken')
        self.assertEqual(unimod.lutris_game_inventory([self.db]),[])
        self.db.unlink();self.db.write_bytes(b'Not a SQLite database')
        self.assertEqual(unimod.lutris_game_inventory([self.db]),[])

    def test_lutris_skips_database_symlinks(self):
        game=self.game('Example')
        self.make_db([(1,'Example',str(game),'wine',1,'config')])
        link=self.base/'db-alias';link.symlink_to(self.db)
        self.assertEqual(unimod.lutris_game_inventory([link]),[])

    def test_combined_dedup_steam_preferred(self):
        root=self.game('Overlap')
        self.write_json('legendaryConfig/legendary/installed.json',{'1':{'install_path':str(root)}})
        self.make_db([(1,'Overlap',str(root),'wine',1,'config')])
        rows=unimod.launcher_game_inventory([(self.cfg,'Heroic')],[self.db])
        with patch.object(unimod,'steam_roots',return_value=[]),\
             patch.object(unimod,'GAME_HINTS',{}),\
             patch.object(unimod,'launcher_game_inventory',return_value=rows):
            found=unimod.detect_games()
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['launcher'],'Heroic')

    def test_missing_index_does_not_raise(self):
        self.assertEqual(unimod.heroic_game_inventory([(self.base/'missing','Heroic')]),[])
        self.assertEqual(unimod.lutris_game_inventory([self.base/'missing.db']),[])

if __name__=='__main__':unittest.main()
