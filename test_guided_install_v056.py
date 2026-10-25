"""No reimplementation or unguarded install path in the guided Downloads UI."""
import ast
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name('unimod.py').read_text(encoding='utf-8')

class DownloadsInstallTests(unittest.TestCase):
    def test_compiles(self):ast.parse(SOURCE)

    def test_review_invokes_existing_preflight(self):
        review=SOURCE.split('def downloads_check_selected(self):')[1].split('def _downloads_review_finished(self')[0]
        self.assertIn('provider_install_preflight(game,receipt)',review)
        self.assertNotIn('install_zip(',review)
        self.assertNotIn('provider_install_reviewed(',review)

    def test_install_hands_off_to_existing_confirm_and_recheck(self):
        start=SOURCE.split('def downloads_install_selected(self):')[1].split('def provider_stage_refresh(self):')[0]
        self.assertIn('self.provider_stage_install()',start)
        self.assertNotIn('install_zip(',start)
        self.assertNotIn('provider_install_reviewed(',start)
        self.assertIn('self.provider_stage_refresh()',start)

    def test_token_and_selection_guards(self):
        method=SOURCE.split('def _downloads_review_finished(self')[1].split('def downloads_install_selected(self)')[0]
        self.assertIn('token!=self._downloads_review_ticket',method)
        self.assertIn('self._download_receipt_identity(receipt)!=identity',method)
        self.assertIn("state='normal'",method)
        self.assertIn("state='disabled'",method)

if __name__=='__main__':unittest.main()
