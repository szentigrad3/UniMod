#!/usr/bin/env python3
"""Run under xvfb-run: this is a smoke test, not a full end-user GUI test."""
import tempfile, json, time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
import unimod

with tempfile.TemporaryDirectory() as root:
    game=Path(root)/'Stardew Valley'; mods=game/'Mods'/'Example';mods.mkdir(parents=True)
    (mods/'manifest.json').write_text(json.dumps({'Name':'Example','Version':'1.0.0','UniqueID':'author.example','UpdateKeys':['Nexus:123']}))
    with patch.object(unimod,'CONFIG',Path(root)/'games.json'), patch.object(unimod,'SOURCE_OVERRIDES',Path(root)/'sources.json'):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App();app.update()
        tab_names=[app.tabs.tab(t,'text').strip() for t in app.tabs.tabs()]
        assert 'Nexus Updates' in tab_names,tab_names
        assert 'Overview' in tab_names and 'Packages & Loose DLLs' in tab_names,tab_names
        assert app.nav_list.size()==len(app.primary_workspaces)==6
        assert app.stat_labels['Indexed IDs'].cget('text')=='1'
        # New icon rail replaces the legacy hidden workspace list.
        app.show_page('Installed Mods')
        assert app.tabs.index('current')==tab_names.index('Installed Mods')
        app.focus_filter()
        assert app.tabs.index('current')==tab_names.index('Installed Mods')
        assert 'Update Inbox' in tab_names,tab_names
        assert len(app.rows)==1,app.rows
        assert len(app.nexus_tree.get_children())==1,app.nexus_tree.get_children()
        assert not app.nexus_key.get()
        dl=Path(root)/'Downloads';dl.mkdir()
        import zipfile
        with zipfile.ZipFile(dl/'update.zip','w') as z:
            z.writestr('Example/manifest.json',json.dumps({'Name':'Example','UniqueID':'author.example','Version':'2.0.0'}))
        app.inbox_folder.set(str(dl));app.inbox_scan()
        app.after(1000,app.quit)
        app.mainloop()
        assert not app.inbox_busy
        assert app.inbox_results[0]['status']=='Ready to update',app.inbox_results
        assert len(app.inbox_tree.get_children())==1
        app.nexus_key.set('a-key-not-to-store')
        with patch.object(unimod,'check_nexus_updates',return_value={app.rows[0]['path']:{'status':'Update available','version':'2.0.0','url':'https://www.nexusmods.com/stardewvalley/mods/123'}}):
            app.after(10,lambda:app.nexus_start(app.rows[:1]))
            app.after(750,app.quit)
            app.mainloop()
        assert app.nexus_results[app.rows[0]['path']]['status']=='Update available'
        app.nexus_key.set('')

        # BepInEx fixture: scan and display a metadata-owned nested plugin without writes.
        bep_game=Path(root)/'Graveyard Keeper 2'
        plugin=bep_game/'BepInEx'/'plugins'/'Mods'/'PluginA';plugin.mkdir(parents=True)
        (plugin/'manifest.json').write_text(json.dumps({'name':'PluginA','author':'Example','version_number':'1.0.0','website_url':'https://github.com/Example/PluginA'}))
        (plugin/'bin').mkdir()
        (plugin/'bin'/'PluginA.dll').write_bytes(b'placeholder fixture')
        bep_zip=dl/'plugin-update.zip'
        with zipfile.ZipFile(bep_zip,'w') as z:
            z.writestr('manifest.json',json.dumps({'name':'PluginA','author':'Example','version_number':'2.0.0','website_url':'https://github.com/Example/PluginA'}))
            z.writestr('BepInEx/plugins/bin/PluginA.dll',b'update')
        result=unimod.scan_update_inbox({'name':'Graveyard Keeper 2','kind':'bepinex','root':str(bep_game)},dl)
        row=next(x for x in result if x['archive']==str(bep_zip))
        assert row['status']=='Ready to update',row
        assert (plugin/'bin'/'PluginA.dll').read_bytes()==b'placeholder fixture'
        app.update();app.destroy()
    assert 'a-key-not-to-store' not in (Path(root)/'games.json').read_text()
print('GUI SMOKE PASSED: startup, SMAPI/BepInEx inbox, Nexus background callback, session key unsaved')
