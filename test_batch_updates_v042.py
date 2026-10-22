"""Batch install preflight and recovery tests for UniMod 0.42."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
import unimod


class BatchUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game={'name':'Stardew Valley', 'root':str(self.root/'Stardew Valley'),'kind':'smapi'}
        self.moddir=Path(self.game['root'])/'Mods'
        self.moddir.mkdir(parents=True)
        self.zipdir=self.root/'Downloads';self.zipdir.mkdir()
        patcher=patch.object(unimod,'APP',self.root/'config')
        patcher.start();self.addCleanup(patcher.stop)

    def mod(self,name,uid,installed='1.0.0',incoming='2.0.0'):
        folder=self.moddir/name;folder.mkdir()
        original={'Name':name,'UniqueID':uid,'Version':installed}
        (folder/'manifest.json').write_text(json.dumps(original))
        archive=self.zipdir/f'{name}.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr(f'{name}/manifest.json',json.dumps({**original,'Version':incoming}))
        match=unimod.match_downloaded_smapi_archive(self.game,archive)
        row={'name':name,'paths':[str(folder)],'local_archive':match,
             'download_status':'Ready for review'}
        self.assertEqual(match['status'],'Ready to update',match)
        return row,folder,archive

    def test_two_mods_preflight_then_install_with_backups(self):
        a,fa,_=self.mod('SpaceCore','test.space')
        b,fb,_=self.mod('ContentPatcher','test.cp')
        plan=unimod.prepare_update_batch(self.game,[a,b])
        self.assertEqual([x['name'] for x in plan['updates']],['SpaceCore','ContentPatcher'])
        self.assertEqual(json.loads((fa/'manifest.json').read_text())['Version'],'1.0.0')
        result=unimod.execute_update_batch(self.game,plan)
        self.assertEqual(result['count'],2)
        self.assertEqual(json.loads((fa/'manifest.json').read_text())['Version'],'2.0.0')
        self.assertEqual(json.loads((fb/'manifest.json').read_text())['Version'],'2.0.0')
        self.assertTrue(all(Path(x).is_dir() for x in result['backups']))
        self.assertEqual(len(unimod.backups_for_game(self.game)),2)

    def test_failed_second_update_rolls_back_first(self):
        a,fa,_=self.mod('SpaceCore','test.space')
        b,fb,_=self.mod('ContentPatcher','test.cp')
        plan=unimod.prepare_update_batch(self.game,[a,b])
        original_apply=unimod.apply_downloaded_update
        count=0
        def failing_apply(game,match):
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('simulated disk failure')
            return original_apply(game,match)
        with self.assertRaisesRegex(RuntimeError,'Rolled back 1/1'):
            unimod.execute_update_batch(self.game,plan,apply_fn=failing_apply)
        self.assertEqual(json.loads((fa/'manifest.json').read_text())['Version'],'1.0.0')
        self.assertEqual(json.loads((fb/'manifest.json').read_text())['Version'],'1.0.0')
        self.assertEqual(len(unimod.backups_for_game(self.game)),0)

    def test_detects_modified_archive_before_any_changes(self):
        a,fa,za=self.mod('SpaceCore','test.space')
        b,fb,zb=self.mod('ContentPatcher','test.cp')
        with zipfile.ZipFile(zb,'w') as z:
            z.writestr('ContentPatcher/manifest.json',json.dumps({'Name':'ContentPatcher','UniqueID':'test.cp','Version':'3.0.0'}))
        with self.assertRaisesRegex(ValueError,'changed'):
            unimod.prepare_update_batch(self.game,[a,b])
        self.assertEqual(json.loads((fa/'manifest.json').read_text())['Version'],'1.0.0')

    def test_duplicate_archive_or_destination_rejected(self):
        a,_,_=self.mod('SpaceCore','test.space')
        with self.assertRaisesRegex(ValueError,'same folder'):
            unimod.prepare_update_batch(self.game,[a,a])

    def test_cannot_batch_ambiguous_or_non_newer(self):
        a,fa,_=self.mod('SpaceCore','test.space')
        a['download_status']='Multiple archives — review in Inbox'
        with self.assertRaisesRegex(ValueError,'review individually'):
            unimod.prepare_update_batch(self.game,[a])

    def test_wrong_game_blocks_transaction(self):
        a,_,_=self.mod('SpaceCore','test.space')
        plan=unimod.prepare_update_batch(self.game,[a])
        with self.assertRaisesRegex(ValueError,'game changed'):
            unimod.execute_update_batch({**self.game,'root':str(self.root/'other')},plan)

    def test_rollback_failure_raises_loud_manual_recovery_warning(self):
        a,_,_=self.mod('SpaceCore','test.space')
        b,_,_=self.mod('ContentPatcher','test.cp')
        plan=unimod.prepare_update_batch(self.game,[a,b])
        count=0
        real_apply=unimod.apply_downloaded_update
        def failing_apply(game,match):
            nonlocal count
            count+=1
            if count==2:raise OSError('out of space')
            return real_apply(game,match)
        def failing_restore(game,entry):
            raise OSError('drive unmounted')
        with self.assertRaisesRegex(RuntimeError,'MANUAL RECOVERY REQUIRED'):
            unimod.execute_update_batch(self.game,plan,apply_fn=failing_apply,restore_fn=failing_restore)

if __name__=='__main__':unittest.main()
