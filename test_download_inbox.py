import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import unimod


class InboxTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.game={'root':str(self.root/'game'),'kind':'smapi','name':'Stardew Valley'}
        self.moddir=Path(self.game['root'])/'Mods'/'Fancy Mod'
        self.moddir.mkdir(parents=True)
        self.write_installed('1.0.0')
        self.inbox=self.root/'Downloads'
        self.inbox.mkdir()

    def write_installed(self,version):
        (self.moddir/'manifest.json').write_text(json.dumps({'UniqueID':'author.fancy','Name':'Fancy Mod','Version':version}))
        (self.moddir/'original.txt').write_text('old data')

    def archive(self,filename,version='2.0.0',uid='author.fancy',extras=None):
        path=self.inbox/filename
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('zipdir/manifest.json',json.dumps({'UniqueID':uid,'Name':'Fancy Mod','Version':version}))
            z.writestr('zipdir/new.txt','new data')
            for key,value in extras or []:
                z.writestr(key,value)
        return path

    def test_exact_uid_not_filename_and_apply_backup(self):
        # Filename deliberately does not describe the mod.
        archive=self.archive('not-a-mod-name.zip')
        report=unimod.scan_download_inbox(self.game,self.inbox)
        self.assertEqual(len(report),1)
        self.assertEqual(report[0]['status'],'Ready to update')
        back=unimod.apply_downloaded_smapi_update(self.game,report[0],self.root/'backups')
        self.assertEqual(unimod.smapi_manifest(self.moddir)['version'],'2.0.0')
        self.assertEqual((self.moddir/'new.txt').read_text(),'new data')
        self.assertEqual((back/'original.txt').read_text(),'old data')

    def test_same_or_older_version_blocked(self):
        current=self.archive('current.zip','1.0.0')
        old=self.archive('old.zip','0.9.0')
        for file,status in [(current,'Already current'),(old,'Archive older')]:
            result=unimod.match_downloaded_smapi_archive(self.game,file)
            self.assertEqual(result['status'],status)
            with self.assertRaises(ValueError):unimod.apply_downloaded_smapi_update(self.game,result)

    def test_unknown_identity_not_matched(self):
        archive=self.archive('other.zip','2.0.0','other.mod')
        result=unimod.match_downloaded_smapi_archive(self.game,archive)
        self.assertEqual(result['status'],'No installed match')

    def test_multi_mod_archive_blocked(self):
        archive=self.archive('collection.zip',extras=[('another/manifest.json',json.dumps({'UniqueID':'another.mod','Version':'1'}))])
        result=unimod.match_downloaded_smapi_archive(self.game,archive)
        self.assertEqual(result['status'],'Multi-mod ZIP')

    def test_duplicate_installed_copy_blocked(self):
        folder=Path(self.game['root'])/'Mods'/'Dup'
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text((self.moddir/'manifest.json').read_text())
        report=unimod.match_downloaded_smapi_archive(self.game,self.archive('update.zip'))
        self.assertEqual(report['status'],'Duplicate installed ID')

    def test_archive_change_after_scan_refused(self):
        archive=self.archive('update.zip')
        result=unimod.match_downloaded_smapi_archive(self.game,archive)
        self.archive('update.zip','3.0.0')
        with self.assertRaisesRegex(ValueError,'changed'):
            unimod.apply_downloaded_smapi_update(self.game,result,self.root/'backups')
        self.assertEqual(unimod.smapi_manifest(self.moddir)['version'],'1.0.0')

    def test_bogus_paths_and_archive_symlinks_rejected(self):
        attack=self.inbox/'escape.zip'
        with zipfile.ZipFile(attack,'w') as z:
            z.writestr('../bad/manifest.json',json.dumps({'UniqueID':'author.fancy'}))
        self.assertEqual(unimod.match_downloaded_smapi_archive(self.game,attack)['status'],'Invalid / unsafe ZIP')
        link=self.inbox/'link.zip'
        info=zipfile.ZipInfo('badlink')
        info.create_system=3
        info.external_attr=(0o120777<<16)
        with zipfile.ZipFile(link,'w') as z:
            z.writestr(info,'/etc/passwd')
            z.writestr('mod/manifest.json',json.dumps({'UniqueID':'author.fancy'}))
        self.assertEqual(unimod.match_downloaded_smapi_archive(self.game,link)['status'],'Invalid / unsafe ZIP')

    def test_unknown_versions_review_without_automatic_guess(self):
        archive=self.archive('prerelease.zip','2.0-beta1')
        self.assertEqual(unimod.match_downloaded_smapi_archive(self.game,archive)['status'],'Review version')

    def test_non_smapi_and_broken_zip(self):
        with zipfile.ZipFile(self.inbox/'random.zip','w') as z:z.writestr('readme.txt','Hello')
        (self.inbox/'broken.zip').write_bytes(b'not a zip')
        actual={Path(r['archive']).name:r['status'] for r in unimod.scan_download_inbox(self.game,self.inbox)}
        self.assertEqual(actual['random.zip'],'Not SMAPI')
        self.assertEqual(actual['broken.zip'],'Invalid / unsafe ZIP')

    def test_preview_scan_does_not_change_installed_files(self):
        self.archive('update.zip')
        before=(self.moddir/'manifest.json').read_bytes()
        unimod.scan_download_inbox(self.game,self.inbox)
        self.assertEqual((self.moddir/'manifest.json').read_bytes(),before)
        self.assertTrue((self.moddir/'original.txt').exists())


if __name__=='__main__':unittest.main()
