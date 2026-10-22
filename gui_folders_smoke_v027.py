"""xvfb-run -a python gui_folders_smoke_v027.py"""
import tempfile, json
from pathlib import Path
from unittest.mock import patch
import unimod
with tempfile.TemporaryDirectory() as t:
    g=Path(t)/'Stardew Valley'
    for i in range(29):
        d=g/'Mods'/('Mod-%02d'%i);d.mkdir(parents=True)
        if i<11:(d/'manifest.json').write_text(json.dumps({'Name':f'Mod {i}','UniqueID':f'demo.{i}','Version':'1.0.0'}))
    game={'name':'Stardew Valley','kind':'smapi','root':str(g)}
    with patch.object(unimod,'cfg_load',return_value={'games':[game]}),\
         patch.object(unimod,'cfg_save',return_value=None),\
         patch.object(unimod,'inventory_update',return_value=None),\
         patch.object(unimod,'SOURCE_OVERRIDES',Path(t)/'overrides.json'):
        app=unimod.App();app.update()
        assert len(app.overview_tree.get_children())==29
        assert app.stat_labels['Indexed IDs'].cget('text')=='11'
        assert app.stat_labels['Mod folders'].cget('text')=='29'
        assert app.stat_labels['Metadata pending'].cget('text')=='18'
        assert len(app.tree.get_children())==29
        app.tree.selection_set('11');app.update()
        assert app.picked() is None  # never use a folder-only row as a valid mod
        assert app.selected_inventory_row()['is_folder_only']
        assert 'No changes' in app.detail.get()
        app.tree.selection_set('0');app.update()
        assert app.picked()['uid']=='demo.0'
        app.destroy()
print('UNIMOD_V027_GUI_FOLDER_VISIBILITY_OK')
