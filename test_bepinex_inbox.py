"""BepInEx v0.17: package IDs, archive safety, transaction recovery."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import unimod


class BepInExInboxTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name)
        self.game={'name':'Graveyard Keeper 2','kind':'bepinex','root':str(self.base/'GK2')}
        self.plugins=unimod.mod_root(self.game)
        self.package=self.plugins/'author'/'MegaAutomation'
        self.package.mkdir(parents=True)
        self.manifest(self.package,version='1.0.0')
        (self.package/'MegaAutomation.dll').write_bytes(b'old-dll')
        self.downloads=self.base/'Downloads';self.downloads.mkdir()
        p=patch.object(unimod,'APP',self.base/'cfg')
        p.start();self.addCleanup(p.stop)

    def manifest(self,path,name='MegaAutomation',version='2.0.0',owner='Creator',site='https://github.com/Creator/MegaAutomation'):
        (path/'manifest.json').write_text(json.dumps({'name':name,'version_number':version,'author':owner,'website_url':site}))

    def zip(self,filename='update.zip',name='MegaAutomation',version='2.0.0',owner='Creator',site='https://github.com/Creator/MegaAutomation',layout='flat',extras=()):
        output=self.downloads/filename
        manifest=json.dumps({'name':name,'version_number':version,'author':owner,'website_url':site})
        with zipfile.ZipFile(output,'w') as z:
            z.writestr('manifest.json',manifest)
            if layout=='thunderstore':z.writestr('BepInEx/plugins/MegaAutomation/MegaAutomation.dll',b'new-dll')
            else:z.writestr('MegaAutomation.dll',b'new-dll')
            for key,value in extras:z.writestr(key,value)
        return output

    def test_finds_nested_package_and_matches_owner(self):
        found=unimod.discover_bepinex_packages(self.game)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['version'],'1.0.0')
        result=unimod.match_downloaded_bepinex_archive(self.game,self.zip())
        self.assertEqual(result['status'],'Ready to update')
        self.assertEqual(result['target_path'],str(self.package))

    def test_read_only_preview_and_apply_backup(self):
        z=self.zip(layout='thunderstore')
        before=(self.package/'MegaAutomation.dll').read_bytes()
        scan=unimod.scan_update_inbox(self.game,self.downloads)
        self.assertEqual(scan[0]['status'],'Ready to update')
        self.assertEqual((self.package/'MegaAutomation.dll').read_bytes(),before)
        backup=unimod.apply_downloaded_update(self.game,scan[0])
        self.assertEqual((backup/'MegaAutomation.dll').read_bytes(),before)
        self.assertEqual((self.package/'MegaAutomation'/'MegaAutomation.dll').read_bytes(),b'new-dll')
        self.assertFalse((self.package/'BepInEx').exists())  # strip Thunderstore prefix
        self.assertEqual(unimod._read_package_manifest(self.package/'manifest.json')['version'],'2.0.0')

    def test_backup_restoration_keeps_updated_copy(self):
        scan=unimod.match_downloaded_bepinex_archive(self.game,self.zip())
        unimod.apply_downloaded_update(self.game,scan)
        entries=unimod.backups_for_game(self.game)
        self.assertEqual(len(entries),1)
        previous=unimod.restore_backup(self.game,entries[0])
        self.assertTrue(previous.is_dir())
        self.assertEqual((self.package/'MegaAutomation.dll').read_bytes(),b'old-dll')
        self.assertEqual((previous/'MegaAutomation.dll').read_bytes(),b'new-dll')
        self.assertEqual(unimod.backups_for_game(self.game),[])

    def test_wrong_author_and_wrong_site_rejected(self):
        self.assertEqual(unimod.match_downloaded_bepinex_archive(self.game,self.zip(owner='Impostor'))['status'],'No installed match')
        self.assertEqual(unimod.match_downloaded_bepinex_archive(self.game,self.zip(site='https://other.example/mod'))['status'],'No installed match')

    def test_missing_metadata_and_loose_dll_not_matched(self):
        (self.package/'manifest.json').unlink()
        self.assertEqual(unimod.match_downloaded_bepinex_archive(self.game,self.zip())['status'],'No installed match')
        self.assertTrue((self.package/'MegaAutomation.dll').exists())
        self.manifest(self.package,owner='',site='')
        self.assertEqual(unimod.match_downloaded_bepinex_archive(self.game,self.zip())['status'],'No installed match')

    def test_duplicate_installed_packages_blocked(self):
        duplicate=self.plugins/'Another'
        duplicate.mkdir()
        self.manifest(duplicate,version='0.9.0')
        (duplicate/'Another.dll').write_bytes(b'copy')
        self.assertEqual(unimod.match_downloaded_bepinex_archive(self.game,self.zip())['status'],'Duplicate installed ID')

    def test_disabled_package_detected_and_remains_disabled(self):
        disabled=unimod.disabled_root(self.game)/'MegaAutomation'
        disabled.parent.mkdir(parents=True)
        self.package.rename(disabled)
        r=unimod.match_downloaded_bepinex_archive(self.game,self.zip())
        self.assertEqual(r['status'],'Ready to update')
        unimod.apply_downloaded_bepinex_update(self.game,r)
        self.assertFalse(self.package.exists())
        self.assertTrue((disabled/'MegaAutomation.dll').exists())

    def test_zip_changed_after_preview_refused(self):
        z=self.zip()
        scan=unimod.match_downloaded_bepinex_archive(self.game,z)
        self.zip(extras=[('README.md','changed')]) # same identity + version, different SHA
        with self.assertRaisesRegex(ValueError,'changed'):
            unimod.apply_downloaded_bepinex_update(self.game,scan)
        self.assertEqual((self.package/'MegaAutomation.dll').read_bytes(),b'old-dll')

    def test_old_version_and_current_version_blocked(self):
        for version,status in [('1.0.0','Already current'),('0.9.0','Archive older')]:
            r=unimod.match_downloaded_bepinex_archive(self.game,self.zip(version=version))
            self.assertEqual(r['status'],status)
            with self.assertRaises(ValueError):unimod.apply_downloaded_bepinex_update(self.game,r)

    def test_archive_with_multiple_mods_blocked(self):
        r=unimod.match_downloaded_bepinex_archive(self.game,self.zip(extras=[('Another/manifest.json',json.dumps({'name':'Other','version_number':'3','author':'Creator'})),('Another/Other.dll',b'other')]))
        self.assertEqual(r['status'],'Multi-package ZIP')

    def test_core_file_symlink_and_traversal_blocked(self):
        for rel in ('BepInEx/core/BepInEx.dll','../victim.dll','BepInEx/config/config.cfg'):
            r=unimod.match_downloaded_bepinex_archive(self.game,self.zip(extras=[(rel,b'danger')]))
            self.assertEqual(r['status'],'Invalid / unsafe ZIP',r)
        z=self.zip()
        symlink=zipfile.ZipInfo('Unsafe')
        symlink.create_system=3
        symlink.external_attr=0o120777<<16
        with zipfile.ZipFile(z,'a') as out:out.writestr(symlink,'/etc/passwd')
        self.assertEqual(unimod.match_downloaded_bepinex_archive(self.game,z)['status'],'Invalid / unsafe ZIP')

    def test_copy_failure_recovers_old_files(self):
        r=unimod.match_downloaded_bepinex_archive(self.game,self.zip())
        original=unimod.shutil.copytree
        def fail(src,dst,*a,**kw):
            if str(dst)==str(self.package):
                raise OSError('simulated copy error')
            return original(src,dst,*a,**kw)
        with patch.object(unimod.shutil,'copytree',side_effect=fail):
            with self.assertRaisesRegex(OSError,'simulated'):
                unimod.apply_downloaded_bepinex_update(self.game,r)
        self.assertEqual((self.package/'MegaAutomation.dll').read_bytes(),b'old-dll')


if __name__=='__main__':unittest.main()

class ManagedBepinexInstallTests(unittest.TestCase):
    def test_managed_install_preserves_manifest_for_future_update(self):
        with tempfile.TemporaryDirectory() as td:
            game={'root':td+'/game','kind':'bepinex','name':'Fixture'}
            archive=Path(td)/'install.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('manifest.json',json.dumps({'name':'Example','version_number':'1.0.0','author':'Dev','website_url':'https://github.com/Dev/Example'}))
                z.writestr('BepInEx/plugins/Example.dll','old DLL')
            names=unimod.install_zip(game,archive)
            self.assertEqual(names,['Example'])
            package=unimod.mod_root(game)/'Example'
            self.assertTrue((package/'manifest.json').exists())
            self.assertTrue((package/'Example.dll').exists())
            self.assertEqual(len(unimod.discover_bepinex_packages(game)),1)
            self.assertEqual(len(unimod.items(game)),1)
            self.assertEqual(unimod.items(game)[0]['version'],'1.0.0')
            with self.assertRaisesRegex(ValueError,'already installed'):
                unimod.install_zip(game,archive)
            self.assertEqual(len(unimod.discover_bepinex_packages(game)),1)
