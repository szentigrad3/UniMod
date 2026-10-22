"""Xvfb GUI smoke: Heroic and Lutris inventory and importing an existing game."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as directory:
    base=Path(directory)
    config=base/'games.json'
    game=base/'game'/'Some Modded Game'
    plugin=game/'BepInEx'/'plugins'/'Example'
    plugin.mkdir(parents=True)
    (plugin/'Example.dll').write_bytes(b'keep')
    source={'name':'Some Modded Game','kind':'bepinex','root':str(game),
            'launcher':'Heroic','store':'GOG','launcher_ref':'abc'}
    with patch.object(unimod,'CONFIG',config),\
         patch.object(unimod,'detect_games',return_value=[source]),\
         patch.object(unimod,'launcher_game_inventory',return_value=[source]),\
         patch.object(unimod,'steam_library_inventory',return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            labels=[app.tabs.tab(tab,'text').strip() for tab in app.tabs.tabs()]
            assert 'Other Launchers' in labels,labels
            app.tabs.select(labels.index('Other Launchers'))
            app.show_other_launchers()
            app.update()
            values=[app.launcher_tree.item(x,'values') for x in app.launcher_tree.get_children()]
            assert len(values)==1 and values[0][1]=='Heroic',values
            assert values[0][4]=='Yes',values
            app.import_other_launchers()
            assert len(app.data['games'])==1
            assert (plugin/'Example.dll').read_bytes()==b'keep'
            assert 'Installed Mods' in app.rail_buttons and 'Overview' in app.rail_buttons and len(app.primary_workspaces)==6
        finally:app.destroy()
print('UNIMOD_LAUNCHERS_GUI_SMOKE_OK')
