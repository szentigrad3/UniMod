"""GUI smoke for v0.52 unified provider inbox. Requires X11/Xvfb."""
import unittest
import tkinter as tk
from tkinter import ttk
import unimod

class ProviderInboxSmoke(unittest.TestCase):
    def test_inbox_controls_exist_and_do_not_auto_install(self):
        app=unimod.App()
        app.withdraw()
        try:
            app.show_page('Provider Inbox')
            self.assertEqual(app.tabs.tab(app.tabs.select(),'text').strip(),'Provider Inbox')
            names=[]
            def walk(w):
                if isinstance(w,ttk.Button):names.append(w.cget('text'))
                for c in w.winfo_children():walk(c)
            walk(app.provider_inbox_tab)
            self.assertIn('Review & install selected…',names)
            self.assertIn('Refresh downloaded files',names)
            self.assertEqual(app.provider_stage_tree.get_children(),())
        finally:app.destroy()

if __name__=='__main__':unittest.main()
