"""v0.19 profile regression suite: no partial updates, grouped files and strict preflight."""
import json
import tempfile
import unittest
from pathlib import Path
import unimod


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game={'name':'Stardew Valley','kind':'smapi','root':str(self.root/'Game')}

    def smapi(self, name, unique_id, enabled=True, nested=''):
        root=unimod.mod_root(self.game) if enabled else unimod.disabled_root(self.game)
        folder=root/name
        if nested:folder/=nested
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':unique_id,'Version':'1.0'}))
        return folder

    def test_profiles_save_grouped_folder_once(self):
        self.smapi('Pack','Author.One',nested='part1')
        self.smapi('Pack','Author.Two',nested='part2')
        profile=unimod.profile_document(self.game)
        self.assertEqual(profile['mods'],{'Pack':True})
        self.assertEqual(profile['schema'],2)
        self.assertEqual(unimod.profile_inventory(self.game)['Pack']['mod_count'],2)
        profile['mods']={'Pack':False}
        plan=unimod.plan_profile_switch(self.game,profile)
        self.assertEqual(plan['changes'][0]['mod_count'],2)
        self.assertEqual(len(plan['changes']),1)
        self.assertEqual(unimod.apply_profile_plan(plan),1)
        self.assertFalse((unimod.mod_root(self.game)/'Pack').exists())
        self.assertTrue((unimod.disabled_root(self.game)/'Pack/part2/manifest.json').is_file())
        self.assertEqual({m['enabled'] for m in unimod.items(self.game)},{False})

    def test_bepinex_nested_folder_and_loose_dll(self):
        self.game['kind']='bepinex'
        plugin=unimod.mod_root(self.game)
        path=plugin/'Tools'/'bin';path.mkdir(parents=True)
        (path/'Mod.dll').write_bytes(b'mod')
        (path/'Shared.dll').write_bytes(b'shared')
        (plugin/'Loose.dll').write_bytes(b'loose')
        profile=unimod.profile_document(self.game)
        self.assertEqual(profile['mods'],{'Tools':True,'Loose.dll':True})
        profile['mods']={'Tools':False,'Loose.dll':False}
        plan=unimod.plan_profile_switch(self.game,profile)
        self.assertEqual(len(plan['changes']),2)
        self.assertEqual(unimod.apply_profile_plan(plan),2)
        self.assertEqual((unimod.disabled_root(self.game)/'Tools/bin/Shared.dll').read_bytes(),b'shared')
        self.assertEqual((unimod.disabled_root(self.game)/'Loose.dll').read_bytes(),b'loose')

    def test_profile_preview_read_only(self):
        folder=self.smapi('Hello','Author.Hello')
        profile=unimod.profile_document(self.game)
        profile['mods']['Hello']=False
        before=(folder/'manifest.json').stat().st_mtime_ns
        plan=unimod.plan_profile_switch(self.game,profile)
        self.assertEqual(plan['changes'][0]['name'],'Hello')
        self.assertEqual((folder/'manifest.json').stat().st_mtime_ns,before)
        self.assertTrue(folder.is_dir())
        self.assertFalse(unimod.disabled_root(self.game).exists())

    def test_preflight_conflict_aborts_all_moves(self):
        a=self.smapi('A','Author.A')
        b=self.smapi('B','Author.B')
        # Existing unrelated destination payload must never be overwritten.
        out=unimod.disabled_root(self.game)/'B';out.mkdir(parents=True)
        (out/'note.txt').write_text('keep')
        profile=unimod.profile_document(self.game)
        profile['mods']={'A':False,'B':False}
        with self.assertRaisesRegex(ValueError,'Both enabled and disabled|conflict'):
            unimod.plan_profile_switch(self.game,profile)
        self.assertTrue(a.is_dir());self.assertTrue(b.is_dir())
        self.assertEqual((out/'note.txt').read_text(),'keep')

    def test_partial_failure_rollback(self):
        a=self.smapi('A','Author.A')
        b=self.smapi('B','Author.B')
        profile=unimod.profile_document(self.game)
        profile['mods']={'A':False,'B':False}
        plan=unimod.plan_profile_switch(self.game,profile)
        moves=[]
        def unreliable(source,target):
            moves.append(source.name)
            if source.name=='B' and len(moves)==2:
                raise OSError('simulated I/O failure')
            source.rename(target)
        with self.assertRaisesRegex(RuntimeError,'rolled back'):
            unimod.apply_profile_plan(plan,move=unreliable)
        self.assertTrue(a.is_dir());self.assertTrue(b.is_dir())
        self.assertFalse((unimod.disabled_root(self.game)/'A').exists())
        self.assertEqual([m['enabled'] for m in unimod.items(self.game)],[True,True])

    def test_preflight_at_apply_checks_all_before_any_move(self):
        a=self.smapi('A','Author.A')
        b=self.smapi('B','Author.B')
        profile=unimod.profile_document(self.game)
        profile['mods']={'A':False,'B':False}
        plan=unimod.plan_profile_switch(self.game,profile)
        conflict=unimod.disabled_root(self.game)/'B';conflict.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'changed since preview'):
            unimod.apply_profile_plan(plan)
        self.assertTrue(a.is_dir());self.assertTrue(b.is_dir())

    def test_disable_and_reenable_profile(self):
        self.smapi('Pack','Author.Pack')
        original=unimod.profile_document(self.game)
        disable={**original,'mods':{'Pack':False}}
        unimod.apply_profile_plan(unimod.plan_profile_switch(self.game,disable))
        self.assertEqual(unimod.profile_document(self.game)['mods']['Pack'],False)
        unimod.apply_profile_plan(unimod.plan_profile_switch(self.game,original))
        self.assertEqual(unimod.profile_document(self.game)['mods']['Pack'],True)

    def test_missing_not_installed_and_unmentioned_preserved(self):
        self.smapi('Installed','Author.Installed')
        original=unimod.profile_document(self.game)
        original['mods']={'Unknown':True}
        plan=unimod.plan_profile_switch(self.game,original)
        self.assertEqual(plan['missing'],['Unknown'])
        self.assertEqual(plan['unmanaged'],['Installed'])
        self.assertEqual(unimod.apply_profile_plan(plan),0)
        self.assertTrue((unimod.mod_root(self.game)/'Installed').is_dir())

    def test_old_profile_readable(self):
        self.smapi('Legacy','Author.Legacy')
        legacy={'game':str(Path(self.game['root']).resolve()),'mods':{'Legacy':False}}
        plan=unimod.plan_profile_switch(self.game,legacy)
        self.assertEqual(len(plan['changes']),1)

    def test_reject_wrong_game_and_kind(self):
        self.smapi('Test','Author.Test')
        doc=unimod.profile_document(self.game)
        doc['game']='/tmp/other'
        with self.assertRaisesRegex(ValueError,'different game'):unimod.plan_profile_switch(self.game,doc)
        doc['game']=str(Path(self.game['root']).resolve());doc['kind']='bepinex'
        with self.assertRaisesRegex(ValueError,'different mod framework'):unimod.plan_profile_switch(self.game,doc)

    def test_reject_malicious_profile_names_and_wrong_types(self):
        self.smapi('Safe','Author.Safe')
        for name in ('../Outside','/tmp/anything','X/Y','..','\\outside','.internal'):
            doc=unimod.profile_document(self.game);doc['mods']={name:False}
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Invalid profile entry'):
                unimod.plan_profile_switch(self.game,doc)
        doc=unimod.profile_document(self.game);doc['mods']={'Safe':'false'}
        with self.assertRaisesRegex(ValueError,'states must be booleans'):unimod.plan_profile_switch(self.game,doc)

    def test_symlink_blocked(self):
        self.smapi('Safe','Author.Safe')
        dest=unimod.disabled_root(self.game)
        target=self.root/'outside';target.mkdir()
        dest.symlink_to(target,target_is_directory=True)
        doc=unimod.profile_document(self.game);doc['mods']={'Safe':False}
        with self.assertRaisesRegex(ValueError,'symbolic links'):unimod.plan_profile_switch(self.game,doc)

if __name__=='__main__':unittest.main()
