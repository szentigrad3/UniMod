"""Review-first handoff and archive-change regressions for v0.41."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import unimod


class UnifiedHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = {'name': 'Stardew Valley', 'root': str(self.root), 'kind': 'smapi'}
        self.installed = self.root/'Mods'/'SpaceCore'
        self.installed.mkdir(parents=True)
        self.manifest={'Name':'SpaceCore','UniqueID':'Example.SpaceCore','Version':'1.0.0','Dependencies':[]}
        (self.installed/'manifest.json').write_text(json.dumps(self.manifest))
        self.mod = {**unimod.smapi_manifest(self.installed),'path':str(self.installed),'enabled':True}
        self.archive = self.root/'SpaceCore.zip'

    def make_zip(self, version='2.0.0', dependencies=None, variant=1):
        data={**self.manifest,'Version':version,'Dependencies':dependencies or [],'Description':str(variant)}
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('SpaceCore/manifest.json',json.dumps(data))
            z.writestr('SpaceCore/SpaceCore.dll',b'sample mod (test only)')
        return unimod.match_downloaded_smapi_archive(self.game,self.archive,[self.mod])

    def get_group(self):
        return [{'name':'SpaceCore','paths':[str(self.installed)],'status':'Not checked','components':1}]

    def test_single_ready_zip_appears_on_updates_screen(self):
        rec=self.make_zip()
        self.assertEqual(rec['status'],'Ready to update')
        rows=unimod.match_update_downloads(self.get_group(),[rec])
        self.assertEqual(rows[0]['download_status'],'Ready for review')
        self.assertEqual(rows[0]['local_archive']['archive'],str(self.archive))

    def test_ambiguous_archives_are_not_directly_installable(self):
        rec=self.make_zip()
        rows=unimod.match_update_downloads(self.get_group(),[rec,rec])
        self.assertIsNone(rows[0]['local_archive'])
        self.assertIn('Multiple archives',rows[0]['download_status'])

    def test_unmatched_zip_cannot_bind_by_name(self):
        rec=self.make_zip()
        rec['target_path']=str(self.root/'Mods'/'Other')
        self.assertIsNone(unimod.match_update_downloads(self.get_group(),[rec])[0]['local_archive'])

    def test_new_dependency_warning_is_reported(self):
        rec=self.make_zip(dependencies=[{'UniqueID':'Missing.Framework','IsRequired':True,'MinimumVersion':'2.0.0'}])
        report=unimod.update_dependency_preflight(self.game,rec,[self.mod])
        self.assertEqual(len(report['new_issues']),1)
        self.assertEqual(report['new_issues'][0]['dependency'],'Missing.Framework')
        self.assertEqual(report['new_issues'][0]['status'],'Missing')

    def test_existing_dependency_issue_not_reported_as_new(self):
        self.mod['dependencies']=[{'uid':'Missing.Framework','required':True,'minimum_version':''}]
        rec=self.make_zip(dependencies=[{'UniqueID':'Missing.Framework','IsRequired':True}])
        report=unimod.update_dependency_preflight(self.game,rec,[self.mod])
        self.assertFalse(report['new_issues'])

    def test_changed_archive_fingerprint_blocks_update(self):
        rec=self.make_zip(variant=1)
        before=rec['sha256']
        self.make_zip(variant=2)
        self.assertNotEqual(before,unimod.match_downloaded_smapi_archive(self.game,self.archive,[self.mod])['sha256'])
        with self.assertRaisesRegex(ValueError,'changed since scan'):
            unimod.apply_downloaded_smapi_update(self.game,rec)
        self.assertEqual(json.loads((self.installed/'manifest.json').read_text())['Version'],'1.0.0')

    def test_unrelated_newer_version_is_not_available(self):
        rec=self.make_zip(version='0.9.0')
        rows=unimod.match_update_downloads(self.get_group(),[rec])
        self.assertIsNone(rows[0]['local_archive'])

    def test_review_is_read_only(self):
        rec=self.make_zip()
        unimod.update_dependency_preflight(self.game,rec,[self.mod])
        self.assertEqual(json.loads((self.installed/'manifest.json').read_text())['Version'],'1.0.0')

    def test_case_insensitive_json5_manifest_archive(self):
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('SpaceCore/Manifest.JSON',"// legal SMAPI comments\n{'uniqueid':'Example.SpaceCore','name':'SpaceCore','version':'2.1.0',}")
        rec=unimod.match_downloaded_smapi_archive(self.game,self.archive,[self.mod])
        self.assertEqual(rec['status'],'Ready to update')
        report=unimod.update_dependency_preflight(self.game,rec,[self.mod])
        self.assertEqual(report['new_issues'],[])

if __name__=='__main__':unittest.main()
