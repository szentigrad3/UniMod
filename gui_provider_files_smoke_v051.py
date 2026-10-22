"""Offline GUI smoke: select Modrinth result -> list files -> download reviewed file."""
import io, time, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import provider_downloads
import unimod

class ProviderFileDialogSmoke(unittest.TestCase):
    def test_modrinth_file_dialog(self):
        app=unimod.App()
        app.withdraw()
        try:
            app.show_page('Mod Websites')
            app.provider_show_results([{'provider':'Modrinth','identity':'AA12BB34','title':'Map Tweaks',
                'url':'https://modrinth.com/mod/AA12BB34','author':'x','version':'','description':'a'}], 'Modrinth')
            app.provider_tree.selection_set('0')
            with tempfile.TemporaryDirectory() as folder:
                app.inbox_folder.set(folder)
                with patch('provider_downloads.list_files',return_value=[{
                  'provider':'Modrinth','identity':'AA12BB34','version':'1.0.0',
                  'filename':'tweaks.jar','size':123,'url':'https://cdn.modrinth.com/data/AA12BB34/versions/V/tweaks.jar',
                  'hashes':{},'loaders':['fabric'],'game_versions':['1.21.1'],'dependencies':[]}]),\
                    patch('provider_staging.stage_download',return_value=Path(folder)/'tweaks.jar') as download,\
                    patch('unimod.messagebox.askyesno',return_value=True):
                    app.provider_files_dialog()
                    dialog=[x for x in app.winfo_children() if isinstance(x,tk.Toplevel) and x is not app][-1]
                    buttons=[]
                    def find(widget):
                        for item in widget.winfo_children():
                            if isinstance(item,ttk.Button):buttons.append(item)
                            find(item)
                    find(dialog)
                    def click(title):
                        btn=next(b for b in buttons if b.cget('text')==title)
                        btn.invoke()
                    click('Fetch files')
                    limit=time.monotonic()+4
                    while time.monotonic()<limit:
                        app.update();time.sleep(.02)
                        trees=[x for x in dialog.winfo_children() if isinstance(x,ttk.Frame)]
                        candidates=[]
                        def gather(w):
                            for c in w.winfo_children():
                                if isinstance(c,ttk.Treeview):candidates.append(c)
                                gather(c)
                        gather(dialog)
                        if candidates and candidates[0].get_children():break
                    self.assertEqual(len(candidates[0].get_children()),1)
                    candidates[0].selection_set('0')
                    click('Download selected to inbox')
                    until=time.monotonic()+4
                    while time.monotonic()<until and not download.called:
                        app.update();time.sleep(.02)
                    self.assertTrue(download.called)
                    self.assertEqual(download.call_args.args[1],Path(folder))
                    dialog.destroy()
        finally:
            app.destroy()
if __name__=='__main__':unittest.main()
