"""Xvfb: guided Downloads reviews real staged ZIP receipts without modifying mods."""
import hashlib
import json
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import unimod


def spin(app, condition, seconds=8):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        app.update()
        if condition():return
        time.sleep(.025)
    raise AssertionError('Download review did not finish')


with tempfile.TemporaryDirectory() as temp:
    base=Path(temp)
    root=base/'Stardew Valley'
    mods=root/'Mods'
    mods.mkdir(parents=True)
    archive=base/'Example.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('Example/manifest.json',json.dumps({
            'Name':'Example','UniqueID':'Tests.Example','Version':'1.0.0'}))
    receipt={
        'provider':'GitHub','identity':'example','archive':str(archive),
        'filename':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'bytes':archive.stat().st_size,'game_root':str(root),
        'version':'1.0.0','dependencies':[]}
    rowset=[receipt]
    with patch.object(unimod,'CONFIG',base/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod.provider_staging,'read_staged',side_effect=lambda _:list(rowset)), \
         patch.object(unimod,'provider_install_reviewed',
                      side_effect=AssertionError('Installation must require approval')):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(root),'kind':'smapi'}]})
        app=unimod.App()
        try:
            app.show_page('Downloads')
            app.update()
            assert len(app.downloads_tree.get_children())==1
            assert app.downloads_install_button.instate(['disabled'])
            app.downloads_tree.selection_set('0')
            app.downloads_check_selected()
            spin(app,lambda:not app._downloads_review_busy)
            assert 'New mod can be installed' in app.downloads_info.get(),app.downloads_info.get()
            assert not app.downloads_install_button.instate(['disabled'])
            assert list(mods.iterdir())==[], 'Review must not write game files'

            # The reviewed button must route to the established rechecking installer,
            # never directly install the staged file.
            with patch.object(app,'provider_stage_install') as handoff:
                app.downloads_install_selected()
                handoff.assert_called_once()
                assert app.provider_stage_tree.selection()==('0',)
                assert app.downloads_install_button.instate(['disabled'])
            assert not list(mods.iterdir())

            # A missing dependency is a hard block, never an enabled install.
            rowset[0]={**receipt,'dependencies':[{'id':'missing-source','type':'required'}]}
            app.show_page('Downloads')
            app.downloads_tree.selection_set('0')
            app.downloads_check_selected()
            spin(app,lambda:not app._downloads_review_busy)
            assert app.downloads_install_button.instate(['disabled'])
            assert 'Cannot install' in app.downloads_info.get()

            # Changing games after reviewing must never use old authorization.
            rowset[0]=receipt
            app.show_page('Downloads')
            app.downloads_tree.selection_set('0')
            app.downloads_check_selected()
            spin(app,lambda:not app._downloads_review_busy)
            assert not app.downloads_install_button.instate(['disabled'])
            other=base/'Other Game';other.mkdir()
            app.data['games'].append({'name':'Other Game','root':str(other),'kind':'bepinex'})
            app.selected=1
            with patch.object(unimod.messagebox,'showwarning') as warning, \
                 patch.object(app,'provider_stage_install') as handoff:
                app.downloads_install_selected()
                warning.assert_called_once()
                handoff.assert_not_called()
            assert not list(mods.iterdir())
            print('UNIMOD_GUIDED_INSTALL_GUI_OK')
        finally:
            app.destroy()
