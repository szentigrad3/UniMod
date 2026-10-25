"""Static regression guards for UniMod's beginner-first navigation."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name('unimod.py').read_text(encoding='utf-8')


class BeginnerHomeTests(unittest.TestCase):
    def test_source_remains_parseable(self):
        ast.parse(SOURCE)

    def test_labels_are_visible_not_icon_only(self):
        for label in ('NAVIGATION', 'My Mods', 'Find Mods', 'Advanced tools', 'Home'):
            self.assertIn(label, SOURCE)
        self.assertIn("text=f'{glyph}  {title}'", SOURCE)

    def test_default_screen_is_home(self):
        self.assertIn('self.tabs.select(dashboard)\n        self.sync_workspace()', SOURCE)

    def test_home_offers_three_clear_actions(self):
        for label in ('1  My Mods', '2  Find Mods', '3  Check My Mods'):
            self.assertIn(label, SOURCE)

    def test_old_operations_still_connected(self):
        for action in ("command=self.show_game_health", "command=self.refresh",
                       "command=self.install_archive", "command=self.auto_detect"):
            self.assertIn(action, SOURCE)


if __name__ == '__main__':
    unittest.main()
