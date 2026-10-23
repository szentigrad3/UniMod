"""Offline end-to-end mod.io lifecycle smoke validation."""
import unittest
from modio_selftest import run

class ModioLifecycleTests(unittest.TestCase):
    def test_staging_install_update_and_failure_recovery(self):
        self.assertEqual(run(), {
            'installed': 1, 'updated': 1, 'backups': 1, 'tamper_refused': 1,
            'wrong_game_refused': 1, 'bad_download_refused': 1,
            'failed_update_restored': 1, 'secrets_not_persisted': 1})

if __name__ == '__main__':
    unittest.main()
