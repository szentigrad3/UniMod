"""Real Tk import-preview smoke test: exact user AIO link, safe bulk apply."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import unimod
with tempfile.TemporaryDirectory() as td:
    root=Path(td);game=root/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    for folder,name,uid,keys in (
        ('Craft','Better Crafting','demo.craft',[]),
        ('Core','Content Patcher','demo.cp',['Nexus:1915']),
        ('East','East Scarp: C#','demo.es',[]),
        ('Unrelated','Different Mod','demo.other',[]),
    ):
        path=mods/folder;path.mkdir()
        (path/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':uid,'Version':'1.0','UpdateKeys':keys}))
    with patch.object(unimod,'CONFIG',root/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'COLLECTION_SOURCES',root/'origins.json'),patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','kind':'smapi','root':str(game)}]})
        app=unimod.App();app.update()
        app.show_page('Nexus Updates');app.update()
        app.nexus_import_aio();app.update()
        dlg=next((w for w in app.winfo_children() if isinstance(w,tk.Toplevel)),None)
        assert dlg is not None,'AIO import dialog not open'
        def descend(widget):
            yield widget
            for child in widget.winfo_children():yield from descend(child)
        table=next(w for w in descend(dlg) if isinstance(w,ttk.Treeview))
        assert len(table.get_children())==4
        selected=[table.item(i,'values') for i in table.selection()]
        assert len(selected)==1 and selected[0][0]=='Better Crafting',selected
        with patch.object(unimod.messagebox,'askyesno',return_value=True),patch.object(unimod.messagebox,'showinfo',return_value=None):
            button=next(w for w in descend(dlg) if isinstance(w,ttk.Button) and w.cget('text')=='Apply selected links')
            button.invoke();app.update()
        assert unimod.nexus_reference(app.current(),next(m for m in app.rows if m['name']=='Better Crafting'))['mod_id']=='11115'
        assert unimod.nexus_reference(app.current(),next(m for m in app.rows if m['name']=='East Scarp: C#')) is None
        assert (mods/'Craft'/'manifest.json').exists()
        app.destroy()
print('UNIMOD_V034_AIO_GUI_OK')
