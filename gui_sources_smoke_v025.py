"""Run with xvfb-run -a python gui_sources_smoke_v025.py"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as td:
    game_root=Path(td)/'Stardew Valley'
    for name,uid,keys in [('Source Found','Example.Linked',['Nexus:100']),
                          ('Needs Help','Example.Unlinked',[])]:
        folder=game_root/'Mods'/name
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':uid,
                                                        'Version':'1.0.0','UpdateKeys':keys}))
    game={'name':'Stardew Valley','root':str(game_root),'kind':'smapi'}
    with patch.object(unimod,'SOURCE_OVERRIDES',Path(td)/'assigned.json'), \
         patch.object(unimod,'cfg_load',return_value={'games':[game]}), \
         patch.object(unimod,'cfg_save',return_value=None), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod,'inventory_update',return_value=None):
        app=unimod.App()
        app.update_idletasks()
        assert len(app.source_tree.get_children())==2
        assert sum(bool(r['url']) for r in app.source_rows)==1
        app.source_filter.set('Needs matching');app.fill_source_table()
        assert len(app.source_tree.get_children())==1
        row=app.source_tree.get_children()[0]
        app.source_tree.selection_set(row)
        assert app.source_table_mod()['uid']=='Example.Unlinked'
        with patch.object(unimod.simpledialog,'askstring',return_value='https://github.com/exact/mod'):
            app.assign_source_from_table()
        assert sum(bool(r['url']) for r in app.source_rows)==2
        app.source_filter.set('Assigned by user');app.fill_source_table()
        assert len(app.source_tree.get_children())==1
        app.source_tree.selection_set(app.source_tree.get_children()[0])
        app.clear_source_from_table()
        assert sum(bool(r['url']) for r in app.source_rows)==1
        app.source_filter.set('Linked');app.fill_source_table()
        assert len(app.source_tree.get_children())==1
        app.source_search.set('NO-MATCH');app.update_idletasks()
        assert len(app.source_tree.get_children())==0
        app.source_search.set('');app.source_filter.set('All');app.fill_source_table()
        app.sort_source_table('source')
        assert len(app.source_tree.get_children())==2
        app.update_idletasks();app.destroy()
print('UNIMOD_V025_GUI_OK')
