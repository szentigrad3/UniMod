"""Offline tests for non-destructive foreign profile previews."""
import json
import tempfile
import unittest
from pathlib import Path

import profile_import_preview as importer


class ProfileImportPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.instance = self.home/'.local/share/PrismLauncher/instances/Test'
        self.mods = self.instance/'.minecraft/mods'
        self.mods.mkdir(parents=True)
        (self.instance/'mmc-pack.json').write_text(json.dumps({
            'components': [
                {'uid': 'net.minecraft', 'version': '1.21.1'},
                {'uid': 'net.fabricmc.fabric-loader', 'version': '0.16.9'},
            ]
        }), encoding='utf-8')

    def test_counts_existing_mods_without_changing_them(self):
        (self.mods/'foo.jar').write_bytes(b'mod')
        (self.mods/'bar.jar.disabled').write_bytes(b'disabled')
        before = sorted((p.name, p.read_bytes()) for p in self.mods.iterdir())
        rows = importer.preview(self.home)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['enabled_jars'], rows[0]['disabled_jars']), (1, 1))
        self.assertEqual(rows[0]['action'], 'Review only — not imported')
        self.assertEqual(before, sorted((p.name, p.read_bytes()) for p in self.mods.iterdir()))

    def test_ignores_symlinked_mods(self):
        (self.mods/'outside.jar').symlink_to(self.home/'secret')
        (self.mods/'directory.jar').mkdir()
        self.assertEqual(importer.preview(self.home)[0]['enabled_jars'], 0)

    def test_missing_mods_directory_is_not_created(self):
        self.mods.rmdir()
        rows = importer.preview(self.home)
        self.assertEqual(rows[0]['enabled_jars'], 0)
        self.assertFalse(self.mods.exists())

    def test_copyable_summary_never_leaks_instance_name(self):
        (self.mods/'private-mod.jar').write_bytes(b'mod')
        rows = importer.preview(self.home)
        safe = importer.safe_summary(rows)
        self.assertIn('Enabled JAR files: 1', safe)
        for sensitive in ('private-mod', str(self.home), 'Test', '1.21.1'):
            self.assertNotIn(sensitive, safe)

    def test_rejects_invalid_preview(self):
        with self.assertRaises(ValueError):
            importer.safe_summary('invalid')


if __name__ == '__main__':
    unittest.main()
