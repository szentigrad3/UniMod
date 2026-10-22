"""Xvfb GUI smoke: Minecraft install action exists and fails closed without a file."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
import unimod

class MinecraftGUI(unittest.TestCase):
    def test_provider_profile_action_visible_and_no_file_does_not_write(self):
        app=unimod.App()
        app.withdraw()
        try:
            app.show_page('Provider Inbox')
            names=[]
            def walk(widget):
                if isinstance(widget,ttk.Button):names.append(widget.cget('text'))
                for item in widget.winfo_children():walk(item)
            walk(app.provider_inbox_tab)
            self.assertIn('Install Modrinth JAR + required dependencies…',names)
            self.assertIn('Inspect .mrpack…',names)
            with patch.object(unimod.messagebox,'showinfo') as show:
                app.minecraft_profile_install()
                show.assert_called_once()
            self.assertFalse(app._stage_running)
        finally:app.destroy()

if __name__=='__main__':unittest.main()
