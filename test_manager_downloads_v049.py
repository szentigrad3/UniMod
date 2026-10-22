"""Unit tests for manager download discovery and user-owned extra folders."""
import json, os, stat, tempfile, unittest, zipfile
from pathlib import Path
from archive_discovery import (known_manager_download_roots,common_download_roots,
    find_archives,load_extra_download_roots,save_extra_download_roots)

class ManagerSourcesTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
  self.home=Path(t.name)/'home';self.home.mkdir()
  self.app=self.home/'.config'/'unimod'
  self.own=self.home/'my_downloads';self.own.mkdir()
 def archive(self,path):
  path.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(path,'w') as z:z.writestr('Sample/manifest.json',json.dumps({'UniqueID':'Example.Sample'}))
  return path
 def test_known_vortex_download_folder_included(self):
  p=self.archive(self.home/'.config'/'Vortex'/'downloads'/'stardewvalley'/'pack-111-1.zip')
  self.assertIn(p,find_archives(include_common=True,home=self.home,app_dir=self.app))
 def test_known_wine_download_folder_included(self):
  p=self.archive(self.home/'.wine'/'drive_c'/'users'/self.home.name/'AppData'/'Roaming'/'Vortex'/'downloads'/'stardewvalley'/'pack-222-1.zip')
  self.assertIn(p,find_archives(include_common=True,home=self.home,app_dir=self.app))
 def test_no_implicit_scanning_of_games(self):
  p=self.archive(self.home/'Games'/'stardewvalley'/'Mods'/'pack-333-1.zip')
  self.assertNotIn(p,find_archives(include_common=True,home=self.home,app_dir=self.app))
 def test_saved_extra_folder_found_without_manual_selection(self):
  p=self.archive(self.own/'pack-444-1.zip')
  save_extra_download_roots([self.own],app_dir=self.app)
  self.assertEqual(load_extra_download_roots(app_dir=self.app),[self.own])
  self.assertIn(p,find_archives(include_common=True,home=self.home,app_dir=self.app))
 def test_extra_folder_is_opt_in(self):
  p=self.archive(self.own/'pack-555-1.zip')
  self.assertNotIn(p,find_archives(include_common=True,home=self.home,app_dir=self.app))
 def test_saved_locations_have_private_permissions(self):
  save_extra_download_roots([self.own],app_dir=self.app)
  self.assertEqual(stat.S_IMODE((self.app/'download-locations.json').stat().st_mode),0o600)
 def test_reject_extra_root_symlink(self):
  link=self.home/'link';link.symlink_to(self.own,target_is_directory=True)
  with self.assertRaises(ValueError):save_extra_download_roots([link],app_dir=self.app)
 def test_reject_config_symlink(self):
  self.app.mkdir(parents=True)
  out=self.home/'other.json';out.write_text('untouched')
  (self.app/'download-locations.json').symlink_to(out)
  self.assertEqual(load_extra_download_roots(app_dir=self.app),[])
  with self.assertRaises(ValueError):save_extra_download_roots([self.own],app_dir=self.app)
  self.assertEqual(out.read_text(),'untouched')
 def test_bad_json_ignored(self):
  self.app.mkdir(parents=True)
  (self.app/'download-locations.json').write_text('not json')
  self.assertEqual(load_extra_download_roots(app_dir=self.app),[])
 def test_reject_too_many_roots(self):
  with self.assertRaises(ValueError):save_extra_download_roots([self.own]*11,app_dir=self.app)
 def test_ignore_manager_download_symlink(self):
  outside=self.home/'external';p=self.archive(outside/'pack-123.zip')
  spot=self.home/'.config'/'Vortex';spot.mkdir(parents=True)
  (spot/'downloads').symlink_to(outside,target_is_directory=True)
  self.assertNotIn(p,find_archives(include_common=True,home=self.home,app_dir=self.app))

if __name__=='__main__':unittest.main()
