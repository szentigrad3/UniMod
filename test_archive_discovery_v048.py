"""Offline checks for automatic, bounded and opt-in discovery of mod ZIPs."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from archive_discovery import find_archives, common_download_roots
import unimod

class ArchiveDiscoveryTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = Path(t.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.downloads = self.home / 'Downloads'
        self.downloads.mkdir()
        self.custom = self.base / 'custom'
        self.custom.mkdir()
        self.game = {'name': 'Stardew Valley', 'kind': 'smapi', 'root':str(self.base/'game')}
        self.source_patch=patch.object(unimod,'SOURCE_OVERRIDES',self.base/'sources.json')
        self.source_patch.start();self.addCleanup(self.source_patch.stop)
        self.mods = [{'name':'Demo', 'uid':'Author.Demo', 'version':'1.0.0',
                      'update_keys':[], 'path':str(self.base / 'game' / 'Mods' / 'Demo')}]

    def archive(self, path, uid='Author.Demo'):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('Demo/manifest.json',json.dumps({'UniqueID':uid,'Name':'Demo'}))
        return path

    def test_nested_archives_inside_selected_directory(self):
        item=self.archive(self.custom / 'pack' / 'mods' / 'Demo-1234-1-0-0-123456.zip')
        result=find_archives(self.custom)
        self.assertEqual(result,[item])
        rows=unimod.simple_source_preview(self.game,self.mods,self.custom)
        self.assertEqual(rows[0]['status'],'Review candidate')
        self.assertEqual(rows[0]['candidate']['mod_id'],'1234')

    def test_recursion_depth_limit(self):
        item=self.archive(self.custom / 'a' / 'b' / 'c' / 'd' / 'Demo-1234-1-0-0-123456.zip')
        self.assertNotIn(item,find_archives(self.custom,max_depth=3))
        self.assertIn(item,find_archives(self.custom/'a',max_depth=3))

    def test_opt_in_common_download_roots(self):
        self.archive(self.downloads / 'Nexus' / 'Demo-5678-1-0-0-2222.zip')
        self.assertEqual(find_archives(self.custom,include_common=False,home=self.home),[])
        paths=find_archives(self.custom,include_common=True,home=self.home)
        self.assertEqual(len(paths),1)
        rows=unimod.simple_source_preview(self.game,self.mods,self.custom,include_common=True,home=self.home)
        self.assertEqual(rows[0]['candidate']['mod_id'],'5678')

    def test_downloads_without_primary_path(self):
        item=self.archive(self.downloads / 'Demo-1234-1-0-0-3333.zip')
        self.assertEqual(find_archives(None,include_common=True,home=self.home),[item])

    def test_no_search_entire_home_or_installed_game(self):
        self.archive(self.home/'Games'/'Stardew Valley'/'Mods'/'Demo-9999-1-0-0-1234.zip')
        self.assertEqual(find_archives(self.custom,include_common=True,home=self.home),[])

    def test_symlink_directories_and_archives_skipped(self):
        item=self.archive(self.base/'external'/'Demo-9999-1-0-0-1234.zip')
        (self.custom/'linkdir').symlink_to(item.parent,target_is_directory=True)
        (self.custom/'link.zip').symlink_to(item)
        self.assertEqual(find_archives(self.custom),[])
        self.assertEqual(find_archives(self.custom/'linkdir'),[])

    def test_deduplicate_common_and_custom_root(self):
        self.archive(self.downloads/'Nexus'/'Demo-3333-1-0-0-22.zip')
        self.assertEqual(len(find_archives(self.downloads,include_common=True,home=self.home)),1)

    def test_limited_newest_archive_count(self):
        import os
        files=[]
        for i in range(10):
            path=self.archive(self.custom/f'Demo-{1000+i}-1-0-0-2222.zip')
            os.utime(path,(i+100,i+100))
            files.append(path)
        self.assertEqual(find_archives(self.custom,max_archives=3),files[-1:-4:-1])
        with self.assertRaises(ValueError):find_archives(self.custom,max_archives=100000)

    def test_does_not_trust_a_unrelated_mod_in_zip(self):
        self.archive(self.downloads/'Other-3333-1-0-0-2222.zip',uid='Other.Mod')
        rows=unimod.simple_source_preview(self.game,self.mods,self.downloads,include_common=True,home=self.home)
        self.assertEqual(rows[0]['status'],'Needs source')

    def test_mo2_sidecar_in_nested_folder(self):
        file=self.archive(self.downloads/'Nexus'/'renamed.zip')
        file.with_name(file.name+'.meta').write_text('[General]\ngameName=Stardew Valley\nmodID=7286\nfileID=123\n')
        rows=unimod.simple_source_preview(self.game,self.mods,self.custom,include_common=True,home=self.home)
        self.assertEqual(rows[0]['candidate']['mod_id'],'7286')
        self.assertIn('MO2 archive',rows[0]['evidence'])

    def test_conflicting_nested_downloads_fail_closed(self):
        self.archive(self.downloads/'A'/'Demo-1111-1-0-0-1234.zip')
        self.archive(self.downloads/'B'/'Demo-2222-1-0-0-1234.zip')
        rows=unimod.simple_source_preview(self.game,self.mods,self.custom,include_common=True,home=self.home)
        self.assertEqual(rows[0]['status'],'Conflicting archive hints')

if __name__=='__main__':unittest.main()
