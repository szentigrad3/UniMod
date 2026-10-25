"""Read-only local ZIP review and no-write failure tests."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import unimod


class LocalZipReviewTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.dir=Path(temporary.name)
        self.game=self.dir/'Stardew Valley'
        self.mods=self.game/'Mods'
        self.mods.mkdir(parents=True)
        self.file=self.dir/'Example.zip'
        self.makezip()
        self.settings={'name':'Stardew Valley','root':str(self.game),'kind':'smapi'}

    def makezip(self, deps=None):
        content={'Name':'Test Mod','UniqueID':'Tests.Example','Version':'1.0.0'}
        if deps is not None:content['Dependencies']=deps
        with zipfile.ZipFile(self.file,'w') as out:
            out.writestr('Example/manifest.json',json.dumps(content))

    def test_new_smapi_zip_previews_read_only(self):
        before=list(self.mods.iterdir())
        review=unimod.manual_zip_review(self.settings,self.file)
        self.assertEqual(review['status'],'Install new',review)
        self.assertEqual(before,list(self.mods.iterdir()))
        self.assertEqual(review['receipt']['game_root'],str(self.game))

    def test_missing_dependency_blocked(self):
        self.makezip([{'UniqueID':'Needed.Dependency','IsRequired':True}])
        review=unimod.manual_zip_review(self.settings,self.file)
        self.assertEqual(review['status'],'Blocked')
        self.assertEqual(list(self.mods.iterdir()),[])

    def test_existing_id_routes_to_update(self):
        installed=self.mods/'Existing'
        installed.mkdir()
        (installed/'manifest.json').write_text(json.dumps({
            'Name':'Test Mod','UniqueID':'Tests.Example','Version':'0.9'}))
        review=unimod.manual_zip_review(self.settings,self.file)
        self.assertEqual(review['status'],'Update existing',review)

    def test_invalid_and_symlink_zip_refused(self):
        self.file.write_text('not a zip')
        self.assertEqual(unimod.manual_zip_review(self.settings,self.file)['status'],'Blocked')
        link=self.dir/'Linked.zip'
        link.symlink_to(self.file)
        self.assertEqual(unimod.manual_zip_review(self.settings,link)['status'],'Blocked')

    def test_generic_review_discloses_unverified_identity(self):
        generic={**self.settings,'kind':'generic'}
        report=unimod.manual_zip_review(generic,self.file)
        self.assertEqual(report['status'],'Manual review only')
        self.assertIn('unverified',report['detail'])

    def test_melonloader_not_misrepresented_as_supported(self):
        unsupported={**self.settings,'kind':'melonloader'}
        self.assertEqual(unimod.manual_zip_review(unsupported,self.file)['status'],'Blocked')

    def test_bad_zip_cannot_create_missing_mod_directory(self):
        not_installed=self.dir/'Other Game'
        not_installed.mkdir()
        broken=self.dir/'Invalid.zip'
        broken.write_text('bad zip')
        with self.assertRaises(zipfile.BadZipFile):
            unimod.install_zip({'root':str(not_installed),'kind':'generic'},broken)
        self.assertFalse((not_installed/'Mods').exists())


if __name__=='__main__':unittest.main()
