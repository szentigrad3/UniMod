"""Pure guards against removing beginner controls or review-first semantics."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).with_name('unimod.py')
SOURCE=ROOT.read_text(encoding='utf-8')

class GuidedDiscoverTests(unittest.TestCase):
    def test_compiles_and_has_find_mods_heading(self):
        ast.parse(SOURCE)
        self.assertIn("text='Find Mods'",SOURCE)

    def test_technical_controls_start_hidden(self):
        self.assertIn('self.provider_advanced=ttk.Frame(sources)',SOURCE)
        self.assertIn('def toggle_provider_setup(self, open=None):',SOURCE)
        self.assertNotIn('self.provider_advanced.pack(fill=',SOURCE.split('def toggle_provider_setup')[0])

    def test_review_step_never_calls_installer(self):
        part=SOURCE.split('def provider_review_downloads(self):')[1].split('def provider_begin_search(self):')[0]
        self.assertIn("self.show_page('Provider Inbox')",part)
        self.assertNotIn('provider_install_reviewed(',part)
        self.assertNotIn('install_zip(',part)

    def test_result_selection_is_informational(self):
        part=SOURCE.split('def update_provider_next_step(self):')[1].split('def provider_review_downloads(self):')[0]
        self.assertNotIn('stage_download(',part)
        self.assertNotIn('install_zip(',part)

if __name__=='__main__':
    unittest.main()
