"""Regression: restoring a previous mod can be reversed using the GUI backups list."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import unimod


class ReversibleRestoreTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base=Path(temp.name)
        self.game={'name':'Stardew Valley','root':str(self.base/'Game'),'kind':'smapi'}
        self.folder=Path(self.game['root'])/'Mods'/'Example'
        self.folder.mkdir(parents=True)
        self.manifest={'Name':'Example','UniqueID':'test.example','Version':'1.0'}
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest))
        self.zip=self.base/'Example.zip'
        with zipfile.ZipFile(self.zip,'w') as archive:
            archive.writestr('Example/manifest.json',
                             json.dumps({**self.manifest,'Version':'2.0'}))
        override=patch.object(unimod,'APP',self.base/'config')
        override.start();self.addCleanup(override.stop)
        self.match=unimod.match_downloaded_smapi_archive(self.game,self.zip)
        self.assertEqual(self.match['status'],'Ready to update')

    def installed_version(self):
        return json.loads((self.folder/'manifest.json').read_text())['Version']

    def test_update_restore_and_reverse_restore(self):
        unimod.apply_downloaded_update(self.game,self.match)
        self.assertEqual(self.installed_version(),'2.0')
        first=unimod.backups_for_game(self.game)
        self.assertEqual(len(first),1)
        self.assertEqual(first[0]['mod_uid'],'test.example')

        prior=unimod.restore_backup(self.game,first[0])
        self.assertTrue(prior.is_dir())
        self.assertEqual(self.installed_version(),'1.0')
        to_redo=unimod.backups_for_game(self.game)
        self.assertEqual(unimod.smapi_manifest(prior)['uid'],'test.example')
        self.assertTrue(prior.with_name(prior.name+'.unimod.json').is_file(),
                        'Displaced copy is missing its new backup metadata')
        self.assertEqual(len(to_redo),1,
                         [p.name for p in (self.base/'config'/'backups').iterdir()])
        self.assertEqual(to_redo[0]['backup_path'],str(prior))
        self.assertEqual(to_redo[0]['kind'],'smapi')
        self.assertEqual(unimod.smapi_manifest(prior)['version'],'2.0')

        # The recorded displaced version is valid input to existing restore.
        unimod.restore_backup(self.game,to_redo[0])
        self.assertEqual(self.installed_version(),'2.0')
        self.assertEqual(len(unimod.backups_for_game(self.game)),1)
        self.assertEqual(unimod.smapi_manifest(
            Path(unimod.backups_for_game(self.game)[0]['backup_path']))['version'],'1.0')

    def test_displaced_unknown_identity_not_offered_as_restore(self):
        unimod.apply_downloaded_update(self.game,self.match)
        current=json.loads((self.folder/'manifest.json').read_text())
        current['UniqueID']='different.package'
        (self.folder/'manifest.json').write_text(json.dumps(current))
        prior=unimod.restore_backup(self.game,unimod.backups_for_game(self.game)[0])
        self.assertTrue(prior.is_dir())
        self.assertEqual(self.installed_version(),'1.0')
        self.assertEqual(unimod.backups_for_game(self.game),[])
        self.assertTrue((prior/'manifest.json').is_file())

    def test_unrelated_game_cannot_use_registered_reversal(self):
        unimod.apply_downloaded_update(self.game,self.match)
        unimod.restore_backup(self.game,unimod.backups_for_game(self.game)[0])
        entry=unimod.backups_for_game(self.game)[0]
        wrong={**self.game,'root':str(self.base/'Another Game')}
        self.assertEqual(unimod.backups_for_game(wrong),[])
        with self.assertRaisesRegex(ValueError,'different game'):
            unimod.restore_backup(wrong,entry)


if __name__=='__main__':
    unittest.main()
