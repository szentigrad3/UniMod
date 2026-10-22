#!/usr/bin/env python3
"""GUI profile dialog smoke test. Run under xvfb-run; never alters real game files."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import unimod


def descend(widget):
    yield widget
    for child in widget.winfo_children():yield from descend(child)

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    game=root/'Stardew Valley'
    a=game/'Mods'/'ModPack'/'A';a.mkdir(parents=True)
    b=game/'Mods'/'ModPack'/'B';b.mkdir(parents=True)
    (a/'manifest.json').write_text(json.dumps({'Name':'A','UniqueID':'test.A'}))
    (b/'manifest.json').write_text(json.dumps({'Name':'B','UniqueID':'test.B'}))
    configured={'name':'Stardew Valley','kind':'smapi','root':str(game)}
    with patch.object(unimod,'CONFIG',root/'games.json'), patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'):
        unimod.cfg_save({'games':[configured]})
        app=unimod.App();app.update()
        doc=unimod.profile_document(configured)
        assert doc['mods']=={'ModPack':True}
        doc['mods']={'ModPack':False}
        plan=unimod.plan_profile_switch(configured,doc)
        app.profile_preview_window(configured,doc,plan,'test.json')
        app.update()
        windows=[w for w in app.winfo_children() if isinstance(w,tk.Toplevel)]
        assert len(windows)==1
        window=windows[0]
        rows=[w for w in descend(window) if isinstance(w,ttk.Treeview)]
        assert len(rows)==1 and len(rows[0].get_children())==1
        buttons=[w for w in descend(window) if isinstance(w,ttk.Button) and w.cget('text')=='Apply reviewed changes']
        assert len(buttons)==1
        with patch.object(unimod.messagebox,'showinfo'):
            buttons[0].invoke()
        app.update()
        assert (game/'.unimod-disabled'/'ModPack'/'A'/'manifest.json').exists()
        assert (game/'.unimod-disabled'/'ModPack'/'B'/'manifest.json').exists()
        assert not (game/'Mods'/'ModPack').exists()
        assert not window.winfo_exists()
        app.destroy()
print('UNIMOD_PROFILE_DIALOG_SMOKE_OK')
