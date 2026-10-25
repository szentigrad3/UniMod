"""Review-first update interaction: no blind 'current' claims or automatic deployment."""
import ast
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name('unimod.py').read_text(encoding='utf-8')


class OneClickUpdatesTests(unittest.TestCase):
    def test_syntax(self):
        ast.parse(SOURCE)

    def test_aio_check_includes_local_and_online(self):
        method=SOURCE.split('def check_all_updates(self):')[1].split('def unified_review_ready(self):')[0]
        self.assertIn('self.unified_scan_downloads(silent=True)',method)
        self.assertIn('self.unified_check()',method)
        self.assertNotIn('apply_downloaded_update(',method)
        self.assertNotIn('install_zip(',method)

    def test_review_existing_single_and_batch_engines(self):
        method=SOURCE.split('def unified_review_ready(self):')[1].split('def unified_scan_downloads(self,',1)[0]
        self.assertIn("get('download_status')=='Ready for review'",method)
        self.assertIn('self.unified_review_install()',method)
        self.assertIn('self.unified_review_batch()',method)
        self.assertIn('len(ready)>30',method)
        self.assertNotIn('execute_update_batch(',method)
        self.assertNotIn('apply_downloaded_update(',method)

    def test_ui_has_download_filter_and_truthful_status(self):
        self.assertIn("'Downloaded ZIP ready'",SOURCE)
        self.assertIn('Some mods may still need online checking',SOURCE)
        self.assertIn('No verified newer ZIPs ready',SOURCE)


if __name__=='__main__':
    unittest.main()
