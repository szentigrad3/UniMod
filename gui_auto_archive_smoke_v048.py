"""Virtual X11 test: Find Sources reads nested common download folders on first scan."""
import json, tempfile, time, zipfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import unimod
import archive_discovery

def children(widget):
    yield widget
    for item in widget.winfo_children():
        yield from children(item)

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    game=root/'Game'
    mods=game/'Mods'/'Sample'
    mods.mkdir(parents=True)
    (mods/'manifest.json').write_text(json.dumps({'Name':'Sample Mod','UniqueID':'Vendor.Sample','Version':'1.0.0'}))
    nested=root/'Downloads'/'Nexus'/'Modpack'
    nested.mkdir(parents=True)
    with zipfile.ZipFile(nested/'Sample-4321-1-0-0-12345.zip','w') as arc:
        arc.writestr('Sample/manifest.json',json.dumps({'Name':'Sample Mod','UniqueID':'Vendor.Sample'}))
    selected=root/'empty'; selected.mkdir()
    with (patch.object(unimod,'CONFIG',root/'games.json'),
          patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),
          patch.object(unimod,'COLLECTION_SOURCES',root/'origins.json'),
          patch.object(unimod,'steam_roots',return_value=[]),
          patch.object(archive_discovery,'common_download_roots',return_value=[root/'Downloads'])):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','kind':'smapi','root':str(game)}]})
        app=unimod.App()
        try:
            app.update()
            app.inbox_folder.set(str(selected))
            app.find_sources_easy()
            dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
            assert any(isinstance(x,ttk.Checkbutton) for x in children(dialog))
            for _ in range(120):
                app.update();time.sleep(.02)
                view=[w for w in children(dialog) if isinstance(w,ttk.Treeview)]
                if view and len(view[0].get_children())==1:break
            else:raise AssertionError('Automatic common-directory scan never completed')
            row=view[0].item(view[0].get_children()[0],'values')
            assert row[0]=='Sample Mod' and row[1]=='#4321' and row[-1]=='Review candidate',row
            assert not (root/'sources.json').exists(),'Scan must not modify source assignments'
            print('UNIMOD_V048_GUI_COMMON_DOWNLOADS_OK')
        finally:app.destroy()
