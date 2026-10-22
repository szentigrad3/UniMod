"""v0.35 normal-user find-sources dialog smoke test using local ZIP evidence."""
import json,zipfile,tempfile,time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import unimod

def walk(w):
    yield w
    for child in w.winfo_children():yield from walk(child)

with tempfile.TemporaryDirectory() as td:
    home=Path(td);game=home/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    downloads=home/'Downloads';downloads.mkdir()
    for name,uid,keys in [('Content Patcher','Pathoschild.ContentPatcher',['Nexus:1915']),
                          ('Better Crafting','Sample.BetterCrafting',[])]:
        folder=mods/name.replace(' ','_');folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({'UniqueID':uid,'Name':name,'Version':'1.0','UpdateKeys':keys}))
    with zipfile.ZipFile(downloads/'BetterCrafting-11115-2-18-0-100.zip','w') as z:
        z.writestr('BetterCrafting/manifest.json',json.dumps({'UniqueID':'Sample.BetterCrafting','Name':'Better Crafting'}))
    with (patch.object(unimod,'CONFIG',home/'games.json'),
          patch.object(unimod,'SOURCE_OVERRIDES',home/'sources.json'),
          patch.object(unimod,'COLLECTION_SOURCES',home/'origins.json'),
          patch.object(unimod,'steam_roots',return_value=[])):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','kind':'smapi','root':str(game)}]})
        app=unimod.App();app.update();app.inbox_folder.set(str(downloads))
        app.find_sources_easy()
        dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
        for _ in range(80):
            app.update();time.sleep(0.02)
            info=[x for x in walk(dialog) if isinstance(x,ttk.Treeview)]
            if info and len(info[0].get_children())==2:break
        else:raise AssertionError('Find sources did not populate after background scan')
        tree=info[0];rows=[tree.item(x,'values') for x in tree.get_children()]
        assert any(r[0]=='Better Crafting' and r[-1]=='Review candidate' for r in rows),rows
        assert any(r[0]=='Content Patcher' and r[-1]=='Already identified' for r in rows),rows
        assert not (home/'sources.json').exists(),'Scanning must be read only'
        app.destroy()
print('UNIMOD_V035_FIND_SOURCES_GUI_OK')
