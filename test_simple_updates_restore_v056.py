"""Structural regression: Updates retains advanced functions but keeps them collapsed."""
import ast
import unittest
from pathlib import Path
source=Path(__file__).with_name('unimod.py').read_text(encoding='utf-8')

class SimpleUpdatesTests(unittest.TestCase):
    def test_python_syntax(self):ast.parse(source)

    def test_beginner_actions_and_expandable_advanced_tools(self):
        start=source.index("updates=ttk.Frame(self.tabs,padding=(16,12))")
        end=source.index("# Update inbox: browser-downloaded archives",start)
        page=source[start:end]
        self.assertIn('Review selected update…',page)
        self.assertIn('Restore a backup…',page)
        self.assertIn('More update options  ▸',page)
        self.assertIn('self.updates_advanced=ttk.Frame(updates)',page)
        self.assertNotIn('self.updates_advanced.pack(',page)
        for name in ('self.unified_review_batch','self.unified_choose_file',
                     'self.unified_identify_sources','self.unified_select_ready'):
            self.assertIn(name,page)

    def test_restore_uses_existing_implementation_and_checks_game(self):
        piece=source.split('def restore_from_backup(self):')[1].split('def selected_inventory_row(self):')[0]
        self.assertIn('backups_for_game(game)',piece)
        self.assertIn('still_there=any(',piece)
        self.assertIn("messagebox.askyesno(",piece)
        self.assertIn('restore_backup(current,entry)',piece)

if __name__=='__main__':
    unittest.main()
