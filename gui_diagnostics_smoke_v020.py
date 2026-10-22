#!/usr/bin/env python3
"""Headless GUI smoke of v0.20 diagnostics tab, callbacks, game selection."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as temp:
    home=Path(temp)
    game=home/'Stardew Valley'
    mod=game/'Mods'/'Sample';mod.mkdir(parents=True)
    (mod/'manifest.json').write_text(json.dumps({'Name':'Sample','Version':'1.2.0','UniqueID':'x.sample'}))
    app_cfg=home/'games.json'
    with patch.object(unimod,'CONFIG',app_cfg), patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App()
        try:
            names=[app.tabs.tab(t,'text').strip() for t in app.tabs.tabs()]
            assert 'Game Diagnostics' in names,names
            assert 'Installed Mods' in app.rail_buttons and 'Overview' in app.rail_buttons and len(app.primary_workspaces)==6
            app.tabs.select(names.index('Game Diagnostics'))
            app.run_game_diagnostics()
            app.after(2500,app.quit)
            app.mainloop()
            assert app.diagnostic_report,app.diag_info.get()
            rows=[app.diag_tree.item(x,'values') for x in app.diag_tree.get_children()]
            assert any(x[0]=='SMAPI loader' and x[1]=='Warning' for x in rows),rows
            assert any(x[0]=='Existing mod entries' and '1 discovered' in x[2] for x in rows),rows
            assert app.diagnostic_game_root==str(game)
            assert app.diag_tree.get_children()
        finally:
            app.destroy()
print('UNIMOD_DIAGNOSTICS_GUI_SMOKE_OK')
