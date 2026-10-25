"""Beginner My Mods: basic columns, reversible advanced view, correct On/Off click."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import unimod


def displayed(app):
    return tuple(app.tk.splitlist(app.tree.cget('displaycolumns')))


with TemporaryDirectory() as temp:
    root=Path(temp)
    game=root/'Stardew Valley'
    folder=game/'Mods'/'Example'
    folder.mkdir(parents=True)
    manifest=folder/'manifest.json'
    manifest.write_text(json.dumps({
        'Name':'Example','UniqueID':'Tests.Example','Version':'1.0.0'
    }))
    with patch.object(unimod,'CONFIG',root/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App()
        try:
            app.show_page('Installed Mods')
            app.update()
            assert displayed(app)==('version','status')
            assert not app.mod_advanced_tools.winfo_ismapped()
            assert not app.mod_horizontal_scroll.winfo_ismapped()
            assert app.mod_advanced_button.cget('text')=='Advanced view  ▸'
            assert app.tree.exists('0'),app.tree.get_children()
            assert not app.details_visible.get()
            assert manifest.is_file()

            def click(column):
                fake=SimpleNamespace(x=10,y=10)
                with patch.object(app.tree,'identify_region',return_value='cell'), \
                     patch.object(app.tree,'identify_column',return_value=column), \
                     patch.object(app.tree,'identify_row',return_value='0'), \
                     patch.object(app,'toggle') as toggle:
                    app.installed_status_click(fake)
                    return toggle.call_count

            assert click('#1')==0, 'Version clicks must not change mod state'
            assert click('#2')==1, 'Simple On/Off column must be clickable'
            app.mod_advanced_button.invoke()
            app.update()
            assert app.mod_advanced_visible.get()
            assert displayed(app)==('author','source','version','status','update','id')
            assert app.mod_advanced_tools.winfo_ismapped()
            assert app.mod_horizontal_scroll.winfo_ismapped()
            assert click('#2')==0, 'Source is not an On/Off cell'
            assert click('#4')==1, 'Advanced On/Off column must work'
            app.mod_advanced_button.invoke()
            app.update()
            assert not app.mod_advanced_visible.get()
            assert displayed(app)==('version','status')
            assert not app.mod_advanced_tools.winfo_ismapped()
            assert not app.mod_horizontal_scroll.winfo_ismapped()
            assert click('#2')==1
            assert json.loads(manifest.read_text())['Version']=='1.0.0'
            print('UNIMOD_SIMPLE_MY_MODS_GUI_OK')
        finally:
            app.destroy()
