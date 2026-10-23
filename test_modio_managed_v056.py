"""Offline managed mod.io provenance and reviewed release checks for v0.56."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import modio_managed as managed
import provider_staging
import unimod


def make_zip(path, version):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Example/manifest.json',
            json.dumps({'UniqueID': 'Example.Modio', 'Name': 'Example', 'Version': version}))
    return path


class ManagedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.root = self.home / 'Stardew'
        self.folder = self.root / 'Mods' / 'Example'
        self.folder.mkdir(parents=True)
        self.manifest = self.folder / 'manifest.json'
        self.manifest.write_text(json.dumps({'UniqueID': 'Example.Modio', 'Version': '1.0.0'}))
        self.game = {'kind': 'smapi', 'name': 'Stardew Valley', 'root': str(self.root)}
        self.source = {'provider': 'mod.io', 'identity': '123/77', 'version_id': '88', 'version': '1.0.0'}

    def record(self):
        return {'game': str(self.root.resolve()), 'package': 'mod.io:123/77',
                'version': '1.0.0', 'paths': [str(self.folder.resolve())],
                **managed.provenance(self.game, [str(self.folder)], self.source)}

    def stage(self, archive, version_id='90'):
        return {'provider': 'mod.io', 'identity': '123/77', 'version_id': version_id,
                'version': '2.0.0', 'archive': str(archive),
                'sha256': provider_staging.file_sha256(archive),
                'bytes': archive.stat().st_size, 'game_root': str(self.root.resolve()),
                'dependencies': []}

    def test_exact_identity_game_and_file_id(self):
        row = self.record()
        found = managed.managed_installs(self.game, [row], game_id='123')
        self.assertEqual(found[0]['version_id'], '88')
        self.assertEqual(found[0]['identity'], '123/77')
        self.assertEqual(managed.managed_installs(self.game, [row], game_id='124'), [])
        self.assertEqual(managed.managed_installs(dict(self.game, root=str(self.home)), [row], game_id='123'), [])

    def test_modified_manifest_rejected(self):
        old = self.record()
        self.manifest.write_text(json.dumps({'UniqueID': 'Different.Package', 'Version': '1.0.0'}))
        self.assertEqual(managed.managed_installs(self.game, [old], game_id='123'), [])

    def test_reject_invalid_and_malformed_receipts(self):
        self.assertFalse(managed.provenance(self.game, [str(self.folder)],
                         dict(self.source, identity='123/../77')))
        self.assertFalse(managed.provenance(self.game, [str(self.folder)],
                         dict(self.source, version_id='bad')))
        self.assertFalse(managed.provenance(self.game, [str(self.folder), str(self.folder)], self.source))
        old = self.record()
        for bad in ([{'path': [], 'manifest_sha256': 'bad'}],
                    [{'path': {}, 'manifest_sha256': 'a' * 64}]):
            row = dict(old, modio_evidence=bad)
            self.assertEqual(managed.managed_installs(self.game, [row], game_id='123'), [])
        self.assertEqual(managed.managed_installs(self.game, [dict(old, paths=[{}])], game_id='123'), [])

    def test_symlinks_and_outside_packages_rejected(self):
        external = self.home / 'External'
        external.mkdir()
        (external / 'manifest.json').write_text('{}')
        self.assertFalse(managed.provenance(self.game, [str(external)], self.source))
        linked = self.root / 'Mods' / 'Linked'
        linked.symlink_to(external, target_is_directory=True)
        self.assertFalse(managed.provenance(self.game, [str(linked)], self.source))

    def test_untracked_latest_receipt_cannot_reuse_old_provenance(self):
        old = self.record()
        changed = dict(old, version_id=None, modio_evidence=None)
        self.assertEqual(managed.managed_installs(self.game, [old, changed], game_id='123'), [])

    def test_release_file_ids_only_generate_review_candidates(self):
        current = managed.managed_installs(self.game, [self.record()], game_id='123')[0]
        alternate = {'provider': 'mod.io', 'identity': '123/77', 'version_id': '89', 'version': '2.0.0'}
        rows = [dict(alternate, version_id='88'), dict(alternate, identity='123/99'),
                dict(alternate, provider='GitHub'), dict(alternate, version_id='bad'),
                alternate, alternate]
        self.assertEqual(managed.release_candidates(current, rows), [{
            'identity': '123/77', 'installed_file_id': '88',
            'available_file_id': '89', 'version': '2.0.0'}])
        # Numeric file-ID ordering does not establish semantic version order.
        self.assertEqual(managed.release_candidates(current,
                         [dict(alternate, version_id='87')])[0]['available_file_id'], '87')

    def test_successful_managed_update_records_file_id_and_backup(self):
        archive = make_zip(self.home / 'update.zip', '2.0.0')
        with patch.object(unimod, 'APP', self.home / 'app'), \
             patch.object(unimod, 'INSTALL_RECEIPTS', self.home / 'install.json'):
            self.assertEqual(unimod.provider_install_preflight(self.game, self.stage(archive))['status'],
                             'Update existing')
            result = unimod.provider_install_reviewed(self.game, self.stage(archive))
            self.assertEqual(result['action'], 'updated')
            self.assertTrue(Path(result['backup']).exists())
            history = unimod.read_receipts()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['version_id'], '90')
            self.assertEqual(history[0]['package'], 'mod.io:123/77')
            self.assertEqual(managed.managed_installs(self.game, history, game_id='123')[0]['version_id'], '90')

    def test_new_managed_install_records_file_id(self):
        archive = make_zip(self.home / 'install.zip', '2.0.0')
        self.manifest.unlink()
        self.folder.rmdir()
        with patch.object(unimod, 'APP', self.home / 'app'), \
             patch.object(unimod, 'INSTALL_RECEIPTS', self.home / 'install.json'):
            result = unimod.provider_install_reviewed(self.game, self.stage(archive))
            self.assertEqual(result['action'], 'installed')
            current = managed.managed_installs(self.game, unimod.read_receipts(), game_id='123')
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0]['version_id'], '90')


if __name__ == '__main__':
    unittest.main()
