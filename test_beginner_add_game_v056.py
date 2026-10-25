"""Read-only Add Game planning: detect, refuse guesses, and reject duplicates."""
import tempfile
import unittest
from pathlib import Path
import unimod


class BeginnerAddGameTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder=Path(tmp.name)/'My Game'
        self.folder.mkdir()

    def test_bepinex_detected_without_guessing(self):
        (self.folder/'BepInEx/plugins').mkdir(parents=True)
        candidate=unimod.plan_game_registration(str(self.folder))
        self.assertEqual(candidate['kind'],'bepinex')
        self.assertEqual(candidate['name'],'My Game')

    def test_smapi_detected_from_real_manifest(self):
        mod=self.folder/'Mods'/'Example'
        mod.mkdir(parents=True)
        (mod/'manifest.json').write_text(
            '{"UniqueID":"Tests.Example","Name":"Example","Version":"1.0"}')
        self.assertEqual(unimod.plan_game_registration(self.folder)['kind'],'smapi')

    def test_unrecognised_game_is_not_falsely_called_bepinex(self):
        candidate=unimod.plan_game_registration(self.folder)
        self.assertIsNone(candidate['kind'])
        self.assertIsNone(candidate['existing_index'])

    def test_duplicate_same_resolved_folder(self):
        existing=[{'name':'My Game','root':str(self.folder),'kind':'generic'}]
        self.assertEqual(unimod.plan_game_registration(self.folder,existing)['existing_index'],0)

    def test_symlinks_and_missing_directories_rejected(self):
        alias=self.folder.parent/'alias'
        alias.symlink_to(self.folder,target_is_directory=True)
        with self.assertRaises(ValueError):
            unimod.plan_game_registration(alias)
        with self.assertRaises(ValueError):
            unimod.plan_game_registration(self.folder/'does-not-exist')

    def test_preview_has_no_file_writes(self):
        before=sorted(p.relative_to(self.folder) for p in self.folder.rglob('*'))
        unimod.plan_game_registration(self.folder)
        after=sorted(p.relative_to(self.folder) for p in self.folder.rglob('*'))
        self.assertEqual(before,after)


if __name__ == '__main__':
    unittest.main()
