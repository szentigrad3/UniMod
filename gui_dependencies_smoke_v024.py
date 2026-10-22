"""Run with xvfb-run -a python gui_dependencies_smoke_v024.py."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'Stardew Valley'
    source=root/'Mods'/'Example';source.mkdir(parents=True)
    (source/'manifest.json').write_text(json.dumps({'Name':'Example','Version':'2.0',
        'UniqueID':'User.Example','Dependencies':[{'UniqueID':'User.Other','MinimumVersion':'3.0'}]}))
    game={'name':'Stardew Valley','root':str(root),'kind':'smapi'}
    with patch.object(unimod,'cfg_load',return_value={'games':[game]}), \
         patch.object(unimod,'cfg_save',return_value=None), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod,'inventory_update',return_value=None):
        app=unimod.App()
        app.update_idletasks()
        assert len(app.dep_rows)==1,app.dep_rows
        assert app.dep_rows[0]['status']=='Missing'
        assert len(app.dep_tree.get_children())==1
        assert len(app.tree.get_children())==1
        app.mod_visibility.set('Disabled');app.fill_mods()
        assert len(app.tree.get_children())==0
        app.mod_visibility.set('Enabled');app.fill_mods()
        assert len(app.tree.get_children())==1
        app.mod_visibility.set('Unknown source');app.fill_mods()
        assert len(app.tree.get_children())==1
        app.mod_visibility.set('Known source');app.fill_mods()
        assert len(app.tree.get_children())==0
        app.mod_visibility.set('All');app.fill_mods()
        app.dep_query.set('nonexistent')
        assert len(app.dep_tree.get_children())==0
        app.dep_query.set('other')
        assert len(app.dep_tree.get_children())==1
        app.update_idletasks();app.destroy()
print('UNIMOD_V024_GUI_OK')
