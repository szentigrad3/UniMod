#!/usr/bin/env python3
"""Test 8 virtual-display regression for approved, game-scoped local Nexus evidence."""
import os
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import unimod
import bepinex_nexus_evidence

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def btn(root, name):
    return next(x for x in descendants(root) if isinstance(x,ttk.Button) and x.cget('text')==name)

with TemporaryDirectory() as work:
    root=Path(work);gk=root/'Graveyard Keeper';gk2=root/'Graveyard Keeper 2';zip_dir=root/'Downloads'
    dll=gk/'BepInEx/plugins/LongerDays.dll';dll.parent.mkdir(parents=True)
    content=os.urandom(512);dll.write_bytes(content)
    (gk2/'BepInEx/plugins').mkdir(parents=True);zip_dir.mkdir()
    zip_file=zip_dir/'LongerDays.zip'
    with zipfile.ZipFile(zip_file,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('BepInEx/plugins/LongerDays.dll',content)
    (zip_dir/'LongerDays.zip.meta').write_text('[General]\ngameName=graveyardkeeper\nmodID=321\nfileID=654\n')
    games=[{'name':'Graveyard Keeper','kind':'bepinex','root':str(gk)},
           {'name':'Graveyard Keeper 2','kind':'bepinex','root':str(gk2)}]
    original=bepinex_nexus_evidence.preview_archive_evidence
    def from_fixture(game,mods,folder,**kw):
        return original(game,mods,zip_dir,**kw)
    with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]),patch.object(bepinex_nexus_evidence,'preview_archive_evidence',side_effect=from_fixture):
        unimod.cfg_save({'games':games})
        app=unimod.App()
        try:
            app.selected=0;app.fill_games();app.update()
            btn(app,'Match downloaded Nexus ZIPs…')
            app.bepinex_nexus_archive_dialog()
            dlg=next(c for c in app.winfo_children() if isinstance(c,tk.Toplevel) and 'Review local Nexus' in c.title())
            tree=next(x for x in descendants(dlg) if isinstance(x,ttk.Treeview))
            for _ in range(80):
                app.update()
                if tree.get_children():break
                time.sleep(0.025)
            assert len(tree.get_children())==1,(len(tree.get_children()),tree.get_children())
            assert tree.item('0','values')[1]=='Review candidate'
            tree.selection_set('0')
            with patch.object(unimod.messagebox,'askyesno',return_value=False) as consent:
                btn(dlg,'Save reviewed source links').invoke()
                consent.assert_called_once()
            assert not (root/'sources.json').exists()
            # Another registered game is never allowed to receive GK1 candidates.
            app.selected=1;app.fill_games();app.update()
            with patch.object(unimod.messagebox,'showwarning') as warning:
                btn(dlg,'Save reviewed source links').invoke()
                warning.assert_called_once()
            assert not (root/'sources.json').exists()
            app.selected=0;app.fill_games();app.update()
            with patch.object(unimod.messagebox,'askyesno',return_value=True):
                btn(dlg,'Save reviewed source links').invoke()
            assert '/graveyardkeeper/mods/321' in (root/'sources.json').read_text()
            assert dll.read_bytes()==content
            print('PASS: GK1 ZIP matches shown; consent and game-change guards; reviewed assignment only; DLL unchanged')
        finally:
            app.destroy()
