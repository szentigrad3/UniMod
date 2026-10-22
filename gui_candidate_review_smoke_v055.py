#!/usr/bin/env python3
"""Offline GUI verification of candidate ordering, wrong-game flag and key help."""
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

def descendants(root):
    for child in root.winfo_children():
        yield child
        yield from descendants(child)

with TemporaryDirectory() as td:
    root=Path(td);gk=root/'Graveyard Keeper'
    dll=gk/'BepInEx/plugins/LongerDays.dll';dll.parent.mkdir(parents=True);dll.write_bytes(b'unchanged')
    game={'name':'Graveyard Keeper','kind':'bepinex','root':str(gk)}
    with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[game]})
        app=unimod.App()
        try:
            app.selected=0;app.fill_games();app.update()
            app.source_tree.selection_set('0')
            with patch.object(app,'provider_begin_search'):
                app.source_search_candidates()
            entries=[]
            for name,domain,mid in [('Unrelated', 'graveyardkeeper', 11),
                                    ('Longer Days', 'graveyardkeeper2', 12),
                                    ('Longer Days', 'graveyardkeeper', 13)]:
                entries.append({'title':name,'author':'unverified','provider':'Nexus Mods','version':'',
                    'description':'', 'identity':f'{domain}/{mid}',
                    'url':f'https://www.nexusmods.com/{domain}/mods/{mid}'})
            app.provider_show_results(entries,'Nexus Mods');app.update()
            assert [x['identity'] for x in app.provider_results]==[
                'graveyardkeeper/13','graveyardkeeper/11','graveyardkeeper2/12']
            assert 'unverified' in app.provider_tree.item('0','values')[-1]
            assert 'Different Nexus game' in app.provider_tree.item('2','values')[-1]
            assert not (root/'sources.json').exists()
            app.provider_choice.set('CurseForge')
            app.provider_key.set('private-session-key')
            button=next(x for x in descendants(app) if isinstance(x,ttk.Button) and
                x.cget('text')=='Provider access requirements…')
            button.invoke();app.update()
            dlg=next(x for x in app.winfo_children() if isinstance(x,tk.Toplevel) and x.title()=='CurseForge — provider access')
            shown=' '.join(x.cget('text') for x in descendants(dlg) if isinstance(x,ttk.Label))
            assert 'approved API key' in shown
            assert 'private-session-key' not in shown
            dlg.destroy()
            print('PASS: ranking, GK2 separation, approval-only linking, session key not displayed')
        finally:app.destroy()
