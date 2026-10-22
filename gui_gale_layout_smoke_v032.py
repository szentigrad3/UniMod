"""v0.32: compact navigation, list-first layout, details drawer and safe toggle."""
import tempfile,json
from pathlib import Path
from unittest.mock import patch
import unimod
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);game=root/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    for i in range(29):
        d=mods/f'Folder{i:02}';d.mkdir()
        (d/'manifest.json').write_text(json.dumps({'Name':f'Mod {i:02}', 'UniqueID':f'developer.mod{i:02}',
                                                   'Version':'1.1.0','UpdateKeys':['Nexus:456'] if i%2 else []}))
    with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'overrides.json'),patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App();app.update()
        assert app.tabs.tab(app.tabs.select(),'text').strip()=='Installed Mods'
        assert set(app.rail_buttons)=={'Installed Mods','All Games & Mods','Mod Websites','Update Inbox','Overview','Updates Available'}
        assert app.game_combo.get()=='Stardew Valley'
        assert app.tree['displaycolumns']==('author','source','version','status')
        assert len(app.tree.get_children(''))==29
        assert not app.details_visible.get()
        assert str(app.detail_pane) not in app.mod_body.panes()
        app.toggle_details();app.update()
        assert app.details_visible.get() and str(app.detail_pane) in app.mod_body.panes()
        app.toggle_details();app.update()
        assert not app.details_visible.get()
        app.query.set('Mod 06');app.update()
        assert len(app.tree.get_children(''))==1
        app.query.set('');app.update()
        app.show_page('Overview');app.update()
        assert app.rail_buttons['Overview'].cget('style')=='RailActive.TButton'
        app.show_page('Installed Mods');app.update()
        assert app.rail_buttons['Installed Mods'].cget('style')=='RailActive.TButton'
        # Clicking a family label should never trigger a filesystem action.
        app.destroy()
print('UNIMOD_V032_GALE_GUI_OK')
