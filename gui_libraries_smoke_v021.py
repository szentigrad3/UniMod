"""Small GUI smoke test of the Steam Libraries workspace under xvfb."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as temp:
    home=Path(temp)
    apps=home/'SteamLibrary'/'steamapps'
    (apps/'common').mkdir(parents=True)
    library_file=home/'steam-libraries.json'
    config=home/'games.json'
    with patch.object(unimod,'STEAM_LIBRARY_CONFIG',library_file),patch.object(unimod,'CONFIG',config),patch.object(unimod,'mounted_steam_libraries',return_value=[]):
        unimod.cfg_save({'games':[]})
        unimod.save_custom_steam_libraries([str(apps)])
        app=unimod.App()
        try:
            names=[app.tabs.tab(t,'text').strip() for t in app.tabs.tabs()]
            assert 'Steam Libraries' in names,names
            app.tabs.select(names.index('Steam Libraries'))
            app.update()
            entries=[app.library_tree.item(x,'values') for x in app.library_tree.get_children()]
            assert any(x[0]==str(apps) and 'Custom' in x[1] for x in entries),entries
            assert 'Installed Mods' in app.rail_buttons and 'Overview' in app.rail_buttons and len(app.primary_workspaces)==6
        finally:app.destroy()
print('UNIMOD_STEAM_LIBRARIES_GUI_SMOKE_OK')
