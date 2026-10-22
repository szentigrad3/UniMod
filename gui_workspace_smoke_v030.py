"""Interactive regression for condensed navigation and all advanced tool routes."""
import json, tempfile
from pathlib import Path
from unittest.mock import patch
import unimod
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); game=root/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    for i in range(29):
        folder=mods/f'Mod{i:02}';folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({'Name':f'Mod {i:02}','UniqueID':f'x.mod{i:02}','Version':'1.0.0'}))
    with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','kind':'smapi','root':str(game)}]})
        app=unimod.App();app.update()
        assert app.nav_list.size()==6,app.nav_list.size()
        assert tuple(app.nav_list.get(0,'end'))==('Mods','Updates','Library','Discover','Downloads','Overview')
        assert app.stat_labels['Indexed IDs'].cget('text')=='29'
        for idx,(_,tab) in enumerate(app.primary_workspaces):
            app.nav_list.selection_clear(0,'end');app.nav_list.selection_set(idx)
            app.select_workspace();app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()==tab
            assert app.nav_list.curselection()==(idx,)
        all_tools=[t for _,items in app.tool_groups for t in items]
        old_tools={app.tabs.tab(t,'text').strip() for t in app.tabs.tabs()}-{target for _,target in app.primary_workspaces}
        assert set(all_tools).issubset({app.tabs.tab(t,'text').strip() for t in app.tabs.tabs()})
        assert 'Provider Inbox' in {app.tabs.tab(t,'text').strip() for t in app.tabs.tabs()}
        for name in all_tools:
            app.show_page(name);app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()==name
        app.show_page('Installed Mods');app.update()
        assert len(app.tree.get_children())==29
        app.destroy()
print('UNIMOD_V030_WORKSPACE_SMOKE_OK')
