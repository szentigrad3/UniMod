"""Run with xvfb-run -a python gui_global_smoke_v026.py"""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as td:
    first=Path(td)/'Stardew Valley'
    second=Path(td)/'GK2'
    a=first/'Mods'/'ModA';a.mkdir(parents=True)
    (a/'manifest.json').write_text(json.dumps({'Name':'Mod A','Version':'1.0.0','UniqueID':'Example.ModA','UpdateKeys':['Nexus:42']}))
    b=second/'BepInEx'/'plugins'/'Sample';b.mkdir(parents=True)
    (b/'sample.dll').write_bytes(b'mock')
    games=[{'name':'Stardew Valley','root':str(first),'kind':'smapi'},
           {'name':'Graveyard Keeper 2','root':str(second),'kind':'bepinex'}]
    with patch.object(unimod,'SOURCE_OVERRIDES',Path(td)/'sources.json'), \
         patch.object(unimod,'cfg_load',return_value={'games':games}), \
         patch.object(unimod,'cfg_save',return_value=None), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod,'inventory_update',return_value=None):
        app=unimod.App()
        app.update()
        # Wait for background scanner through the Tk event loop.
        for _ in range(150):
            app.update()
            if app.global_report:break
            time.sleep(.01)
        assert app.global_report is not None, 'Initial global scan did not finish'
        assert len(app.global_tree.get_children())==2
        app.global_query.set('Mod A');app.update()
        assert len(app.global_tree.get_children())==1
        app.global_filter.set('Known source');app.fill_global_library()
        assert len(app.global_tree.get_children())==1
        app.global_filter.set('Needs source');app.fill_global_library()
        assert len(app.global_tree.get_children())==0
        app.global_query.set('');app.global_filter.set('All');app.fill_global_library()
        # Navigate to the second game's unmanaged package from the global list.
        for row in app.global_tree.get_children():
            if app.global_tree.item(row,'values')[0]=='Graveyard Keeper 2':
                app.global_tree.selection_set(row);break
        app.open_global_mod()
        assert app.current()['name']=='Graveyard Keeper 2'
        assert app.tabs.tab(app.tabs.select(),'text').strip()=='Installed Mods'
        app.update_idletasks();app.destroy()
print('UNIMOD_V026_GUI_OK')
