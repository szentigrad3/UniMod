"""Simple default mod view must never hide installed mods or alter their state."""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).with_name('unimod.py').read_text(encoding='utf-8')


class MyModsViewTests(unittest.TestCase):
    def test_syntax(self):
        ast.parse(SOURCE)

    def test_default_mod_columns(self):
        self.assertIn("displaycolumns=('version','status')",SOURCE)
        self.assertIn("self.mod_advanced_visible=tk.BooleanVar(value=False)",SOURCE)
        self.assertIn('self.mod_advanced_tools=ttk.Frame(installed)',SOURCE)

    def test_click_uses_current_display_order(self):
        part=SOURCE.split('def installed_status_click(self,event):')[1].split('def installed_toggle_key(self,event):')[0]
        self.assertIn("self.tree.cget('displaycolumns')",part)
        self.assertIn("visible_columns.index('status')",part)
        self.assertNotIn("identify_column(event.x)!='#4'",part)
        self.assertIn('self.toggle()',part)

    def test_no_installation_in_view_switch(self):
        part=SOURCE.split('def toggle_mod_advanced(self):')[1].split('def installed_status_click(self,event):')[0]
        self.assertNotIn('shutil.',part)
        self.assertNotIn('install_zip(',part)
        self.assertIn("displaycolumns=('author','source','version','status','update','id')",part)


if __name__=='__main__':
    unittest.main()
