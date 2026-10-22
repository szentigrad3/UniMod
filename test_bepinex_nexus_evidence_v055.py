"""Offline GK1/GK2 archive matching: never infer a source from names alone."""
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import unimod
import bepinex_nexus_evidence as evidence
from source_provenance import read_mo2_sidecar

class NexusArchiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.folder=self.root/'Downloads';self.folder.mkdir()
        self.game_root=self.root/'Graveyard Keeper';self.plugin=self.game_root/'BepInEx/plugins';self.plugin.mkdir(parents=True)
        self.game={'name':'Graveyard Keeper','root':str(self.game_root),'kind':'bepinex'}
        self.dll=self.plugin/'LongerDays.dll';self.payload=os.urandom(2048);self.dll.write_bytes(self.payload)
        self.mod=unimod.discover_bepinex(self.plugin,True)[0]
        patcher=patch.object(unimod,'SOURCE_OVERRIDES',self.root/'assignments.json')
        patcher.start();self.addCleanup(patcher.stop)

    def add_archive(self,name='longer-days.zip',data=None,mod_id='123',game_name='graveyardkeeper',member='BepInEx/plugins/LongerDays.dll',file_id='567',sidecar=True):
        archive=self.folder/name
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr(member,self.payload if data is None else data)
        if sidecar:
            (self.folder/(name+'.meta')).write_text(f'[General]\ngameName={game_name}\nmodID={mod_id}\nfileID={file_id}\n')
        return archive

    def preview(self,mods=None):
        return evidence.preview_archive_evidence(self.game,[self.mod] if mods is None else mods,self.folder,
            known_source=lambda g,m: bool(unimod.reconcile_source(g,m).get('url')),
            identity=unimod.source_identity)

    def test_identical_dll_and_correct_game_sidecar_is_review_candidate(self):
        self.add_archive()
        r=self.preview()
        self.assertEqual(r['reviewable'],1)
        self.assertEqual(r['rows'][0]['status'],'Review candidate')
        self.assertEqual(r['rows'][0]['candidate']['url'],'https://www.nexusmods.com/graveyardkeeper/mods/123')
        self.assertFalse(unimod.SOURCE_OVERRIDES.exists())

    def test_different_bytes_never_match_even_with_same_name(self):
        self.add_archive(data=os.urandom(len(self.payload)))
        self.assertEqual(self.preview()['reviewable'],0)

    def test_wrong_game_rejected(self):
        self.add_archive(game_name='graveyardkeeper2')
        self.assertEqual(self.preview()['reviewable'],0)

    def test_separate_gk2_scoping(self):
        self.game['name']='Graveyard Keeper 2'
        self.add_archive(game_name='graveyard keeper 2',mod_id='88')
        result=self.preview()['rows'][0]
        self.assertEqual(result['candidate']['url'],'https://www.nexusmods.com/graveyardkeeper2/mods/88')
        self.assertIsNone(read_mo2_sidecar(self.folder/'longer-days.zip','graveyardkeeper'))

    def test_untrusted_game_and_ids_validation(self):
        for game_name,mid in [('graveyardkeeper2','5'),('anothergame','5'),('graveyardkeeper','-1'),('graveyardkeeper','0')]:
            p=self.add_archive(game_name=game_name,mod_id=mid)
            self.assertIsNone(read_mo2_sidecar(p,'graveyardkeeper'))
        self.assertEqual(self.preview()['reviewable'],0)

    def test_conflicts_not_guessed(self):
        self.add_archive(name='a.zip',mod_id='31')
        self.add_archive(name='b.zip',mod_id='32')
        result=self.preview()['rows'][0]
        self.assertEqual(result['status'],'Conflicting Nexus IDs')
        self.assertIsNone(result['candidate'])

    def test_same_mod_across_two_archives_not_conflicting(self):
        self.add_archive(name='a.zip',mod_id='31')
        self.add_archive(name='b.zip',mod_id='31',file_id='99')
        result=self.preview()['rows'][0]
        self.assertEqual(result['status'],'Review candidate')
        self.assertIn('/31',result['candidate']['url'])

    def test_different_installed_dll_with_same_hash_is_ambiguous(self):
        self.add_archive()
        dup=self.plugin/'Duplicate.dll';dup.write_bytes(self.payload)
        result=self.preview(unimod.discover_bepinex(self.plugin,True))
        self.assertEqual(len(result['rows']),2)
        self.assertTrue(all(r['status']=='Ambiguous installed DLL' for r in result['rows']))

    def test_no_identity_from_zip_without_sidecar(self):
        self.add_archive(sidecar=False)
        self.assertEqual(self.preview()['reviewable'],0)

    def test_symlinked_meta_and_dll_are_not_matched(self):
        other=self.root/'sidecar.txt';other.write_text('[General]\ngameName=graveyardkeeper\nmodID=9\nfileID=1')
        archive=self.add_archive(sidecar=False)
        (self.folder/(archive.name+'.meta')).symlink_to(other)
        self.assertEqual(self.preview()['reviewable'],0)
        (self.folder/(archive.name+'.meta')).unlink()
        archive=self.add_archive()
        self.dll.unlink();self.dll.symlink_to(other)
        self.assertEqual(self.preview()['rows'][0]['status'],'Not readable')

    def test_zip_slip_member_never_matches(self):
        self.add_archive(member='../BepInEx/plugins/LongerDays.dll')
        self.assertEqual(self.preview()['reviewable'],0)

    def test_symlinked_download_folder_rejected(self):
        folder=self.root/'link';folder.symlink_to(self.folder,target_is_directory=True)
        with self.assertRaises(ValueError):
            evidence.preview_archive_evidence(self.game,[self.mod],folder)

    def test_other_game_bepinex_rejected(self):
        self.game['name']='Stardew Valley'
        with self.assertRaises(ValueError):self.preview()

    def test_approval_saves_setting_only_and_preserves_dll(self):
        self.add_archive()
        row=self.preview()['rows']
        count=unimod.apply_bepinex_archive_candidates(self.game,row,[0])
        self.assertEqual(count,1)
        self.assertEqual(unimod.assigned_source(self.game,self.mod)['url'],row[0]['candidate']['url'])
        self.assertEqual(self.dll.read_bytes(),self.payload)

    def test_changed_dll_blocks_commit(self):
        self.add_archive();rows=self.preview()['rows']
        self.dll.write_bytes(os.urandom(2048))
        with self.assertRaisesRegex(ValueError,'changed'):
            unimod.apply_bepinex_archive_candidates(self.game,rows,[0])
        self.assertFalse(unimod.SOURCE_OVERRIDES.exists())

    def test_game_changed_between_preview_and_commit_blocks(self):
        self.add_archive();rows=self.preview()['rows']
        other=dict(self.game,name='Graveyard Keeper 2')
        with self.assertRaises(ValueError):
            unimod.apply_bepinex_archive_candidates(other,rows,[0])

    def test_existing_assignment_cannot_be_overwritten(self):
        self.add_archive();rows=self.preview()['rows']
        unimod.save_source_assignment(self.game,self.mod,'https://www.nexusmods.com/graveyardkeeper/mods/11')
        with self.assertRaisesRegex(ValueError,'already has'):
            unimod.apply_bepinex_archive_candidates(self.game,rows,[0])
        self.assertIn('/11',unimod.assigned_source(self.game,self.mod)['url'])

    def test_invalid_selection_and_no_partial_commit(self):
        self.add_archive();rows=self.preview()['rows']
        for ids in ([],[0,0],[-1],[1],[True]):
            with self.assertRaises(ValueError):
                unimod.apply_bepinex_archive_candidates(self.game,rows,ids)
        self.assertFalse(unimod.SOURCE_OVERRIDES.exists())

    def test_existing_metadata_link_not_overridden(self):
        self.add_archive()
        mod=dict(self.mod,website_url='https://github.com/owner/project')
        row=self.preview([mod])['rows'][0]
        self.assertEqual(row['status'],'Already linked')
        self.assertIsNone(row['candidate'])

    def test_sidecar_too_large_ignored(self):
        p=self.add_archive()
        (self.folder/(p.name+'.meta')).write_bytes(b'Z'*40000)
        self.assertEqual(self.preview()['reviewable'],0)

if __name__=='__main__': unittest.main()
