"""GUI regression: Modrinth pack import is gated behind staged selection."""
import unittest
from tkinter import ttk
from unittest.mock import patch
import unimod

class GUIImport(unittest.TestCase):
    def test_button_visible_and_empty_selection_refuses_to_write(self):
        app=unimod.App();app.withdraw()
        try:
            app.show_page('Provider Inbox')
            labels=[]
            def walk(node):
                if isinstance(node,ttk.Button):labels.append(node.cget('text'))
                for kid in node.winfo_children():walk(kid)
            walk(app.provider_inbox_tab)
            self.assertIn('Import .mrpack to Prism/MultiMC…',labels)
            app.provider_stage_tree.selection_remove(app.provider_stage_tree.selection())
            with patch.object(unimod.messagebox,'showinfo') as info:
                app.minecraft_mrpack_import()
            info.assert_called_once()
            self.assertFalse(app._stage_running)
        finally:app.destroy()

if __name__=='__main__':unittest.main()
