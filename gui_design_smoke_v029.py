"""Design regression for the new overview and split-panel installed library."""
import json, tempfile
from pathlib import Path
from unittest.mock import patch
import unimod
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    game=root/'Stardew Valley';(game/'Mods').mkdir(parents=True)
    for i in range(29):
        mod=game/'Mods'/f'Folder{i:02}';mod.mkdir()
        (mod/'manifest.json').write_text(json.dumps({'Name':f'Mod {i:02}', 'Version':'1.2.3',
            'UniqueID':f'developer.mod{i:02}', 'UpdateKeys':['Nexus:123'] if i%2 else []}))
    with patch.object(unimod,'CONFIG',root/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App();app.update()
        assert app.stat_labels['Mod folders'].cget('text')=='29'
        assert len(app.overview_tree.get_children())==29
        app.tabs.select(1);app.update()
        assert app.tree['displaycolumns']==('author','source','version','status'),app.tree['displaycolumns']
        assert len(app.tree.get_children())==29
        assert app.detail_name.get()=='Mod 00',app.detail_name.get()
        app.tree.selection_set('10');app.describe_selected();assert app.detail_name.get()=='Mod 10'
        app.sort_installed_table('name');assert app.detail_name.get()=='Mod 10'
        app.query.set('Mod 02');app.update()
        assert len(app.tree.get_children())==1
        assert app.detail_name.get()=='Mod 02'
        app.query.set('');app.update()
        assert len(app.tree.get_children())==29
        app.destroy()
print('UNIMOD_V029_GUI_DESIGN_OK')
