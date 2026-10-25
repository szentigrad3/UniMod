"""Xvfb: beginner Updates & backup restoration, including confirmation refusal."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from unittest.mock import patch
import zipfile

import unimod


def find_widgets(widget, cls):
    for child in widget.winfo_children():
        if isinstance(child,cls):
            yield child
        yield from find_widgets(child,cls)


with TemporaryDirectory() as temp:
    base=Path(temp)
    game_root=base/'Stardew Valley'
    moddir=game_root/'Mods'/'Example'
    moddir.mkdir(parents=True)
    manifest={'Name':'Example','UniqueID':'Tests.Example','Version':'1.0'}
    (moddir/'manifest.json').write_text(json.dumps(manifest))
    game={'name':'Stardew Valley','root':str(game_root),'kind':'smapi'}
    newzip=base/'New.zip'
    with zipfile.ZipFile(newzip,'w') as archive:
        archive.writestr('Example/manifest.json',json.dumps({**manifest,'Version':'2.0'}))
    with patch.object(unimod,'APP',base/'app'), \
         patch.object(unimod,'CONFIG',base/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        appdir=base/'app';appdir.mkdir()
        match=unimod.match_downloaded_smapi_archive(game,newzip)
        assert match['status']=='Ready to update',match
        unimod.apply_downloaded_update(game,match)
        assert len(unimod.backups_for_game(game))==1
        assert json.loads((moddir/'manifest.json').read_text())['Version']=='2.0'

        unimod.cfg_save({'games':[game]})
        app=unimod.App()
        try:
            app.show_page('Updates Available')
            app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Updates Available'
            assert not app.updates_advanced.winfo_ismapped()
            primary=[button.cget('text') for button in find_widgets(app.updates_actions,ttk.Button)]
            for name in ('Find downloaded updates','Review selected update…',
                         'Restore a backup…','More update options  ▸'):
                assert name in primary,(name,primary)
            assert len(primary)==4,primary
            app.update_tools_button.invoke();app.update()
            assert app.updates_advanced.winfo_ismapped()
            assert app.unified_source_button.winfo_ismapped()
            app.update_tools_button.invoke();app.update()
            assert not app.updates_advanced.winfo_ismapped()

            app.restore_from_backup()
            app.update()
            dialogs=[w for w in app.winfo_children()
                     if w.winfo_class()=='Toplevel' and 'Restore a mod backup' in w.title()]
            assert len(dialogs)==1
            dialog=dialogs[0]
            tree=next(find_widgets(dialog,ttk.Treeview))
            buttons={b.cget('text'):b for b in find_widgets(dialog,ttk.Button)}
            action=buttons['Restore selected backup']
            assert action.instate(['disabled'])
            assert len(tree.get_children())==1
            assert tree.item('0','values')[1]=='1.0'
            tree.selection_set('0');app.update()
            assert not action.instate(['disabled'])
            with patch.object(unimod.messagebox,'askyesno',return_value=False) as prompt:
                action.invoke()
                assert prompt.call_count==1
            assert json.loads((moddir/'manifest.json').read_text())['Version']=='2.0'
            # Change to another game while the dialog is open: no restore.
            other=base/'Other';other.mkdir()
            app.data['games'].append({'name':'Other','root':str(other),'kind':'generic'})
            app.selected=1
            with patch.object(unimod.messagebox,'showwarning') as warn, \
                 patch.object(unimod.messagebox,'askyesno',
                              side_effect=AssertionError('Game switched')):
                action.invoke()
                warn.assert_called_once()
            assert json.loads((moddir/'manifest.json').read_text())['Version']=='2.0'
            app.selected=0
            with patch.object(unimod.messagebox,'askyesno',return_value=True), \
                 patch.object(unimod.messagebox,'showinfo') as info:
                action.invoke()
                assert info.called
            assert json.loads((moddir/'manifest.json').read_text())['Version']=='1.0'
            assert len([p for p in (base/'app'/'backups').glob('*-pre-restore-*') if p.is_dir()])==1
            assert len(unimod.backups_for_game(game))==1
            print('UNIMOD_SIMPLE_UPDATES_RESTORE_GUI_OK')
        finally:
            app.destroy()
