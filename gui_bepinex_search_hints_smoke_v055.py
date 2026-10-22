#!/usr/bin/env python3
"""GUI: safe fallback creates scoped Nexus search, not assignments or downloads."""
import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def btn(root,text):
    return next(x for x in descendants(root) if isinstance(x,ttk.Button) and x.cget('text')==text)

with TemporaryDirectory() as t:
    root=Path(t);gk=root/'Graveyard Keeper';gk2=root/'Graveyard Keeper 2'
    dll=gk/'BepInEx/plugins/LongerDays.dll';dll.parent.mkdir(parents=True)
    payload=os.urandom(1000);dll.write_bytes(payload)
    (gk2/'BepInEx/plugins').mkdir(parents=True)
    games=[{'name':'Graveyard Keeper','kind':'bepinex','root':str(gk)},
           {'name':'Graveyard Keeper 2','kind':'bepinex','root':str(gk2)}]
    with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':games})
        app=unimod.App()
        try:
            app.selected=0;app.fill_games();app.update()
            btn(app,'Search without Nexus ZIP…')
            app.bepinex_source_hints_dialog()
            dlg=next(x for x in app.winfo_children() if isinstance(x,tk.Toplevel) and 'Nexus search hints' in x.title())
            tree=next(x for x in descendants(dlg) if isinstance(x,ttk.Treeview))
            assert len(tree.get_children())==1
            assert tree.item('0','values')[1]=='Longer Days'
            tree.selection_set('0')
            app.selected=1;app.fill_games();app.update()
            with patch.object(unimod.messagebox,'showwarning') as warning:
                btn(dlg,'Search selected on Nexus').invoke();warning.assert_called_once()
            assert dlg.winfo_exists(), 'wrong-game attempt should not close dialog'
            app.selected=0;app.fill_games();app.update()
            with patch.object(app,'provider_begin_search') as search:
                btn(dlg,'Search selected on Nexus').invoke();search.assert_called_once()
            assert app.provider_choice.get()=='Nexus Mods'
            assert app.provider_scope.get()=='graveyardkeeper'
            assert app.provider_query.get()=='Longer Days'
            assert app.source_candidate_target['game_root']==str(gk.resolve())
            assert dll.read_bytes()==payload
            assert not (root/'sources.json').exists()
            # Even after catalogue search, changed DLLs must not be linked.
            app.provider_results=[{'provider':'Nexus Mods','url':'https://www.nexusmods.com/graveyardkeeper/mods/321',
                                   'title':'Longer Days','author':'unknown'}]
            app.provider_tree.insert('','end',iid='0',values=('Longer Days',))
            app.provider_tree.selection_set('0')
            dll.write_bytes(os.urandom(len(payload)))
            with patch.object(unimod.messagebox,'showwarning') as warning,patch.object(unimod.messagebox,'askyesno',return_value=True) as consent:
                app.provider_assign_reviewed_source()
                warning.assert_called_once()
                consent.assert_not_called()
            assert not (root/'sources.json').exists()
            dll.write_bytes(payload)
            print('PASS: no-archive hint searches Nexus GK1, rejects game switching, never assigns or changes DLL')
        finally:
            app.destroy()
