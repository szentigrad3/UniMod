"""Xvfb: one check finds actual downloaded SMAPI ZIP updates, with no installation."""
import json
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unimod


def spin(app, done, seconds=8):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        app.update()
        if done():
            app.update()
            return
        time.sleep(.02)
    raise AssertionError('Local update checking never completed')


def make_mod(root,downloads,name,uid):
    folder=root/'Mods'/name
    folder.mkdir(parents=True)
    original={'Name':name,'UniqueID':uid,'Version':'1.0.0'}
    (folder/'manifest.json').write_text(json.dumps(original))
    with zipfile.ZipFile(downloads/(name+'.zip'),'w') as z:
        z.writestr(name+'/manifest.json',json.dumps({**original,'Version':'1.5.0'}))
    return folder


with TemporaryDirectory() as temp:
    base=Path(temp)
    root=base/'Stardew Valley'
    downloads=base/'Downloads'; downloads.mkdir()
    first=make_mod(root,downloads,'SpaceCore','test.spacecore')
    game={'name':'Stardew Valley','root':str(root),'kind':'smapi'}
    with patch.object(unimod,'CONFIG',base/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[game]})
        app=unimod.App()
        try:
            app.show_page('Updates Available')
            app.inbox_folder.set(str(downloads))
            with patch.object(app,'unified_check') as online:
                app.check_all_updates()
                online.assert_called_once_with()
            spin(app,lambda:not app.unified_download_busy)
            ready=[r for r in app.unified_rows if r.get('download_status')=='Ready for review']
            assert len(ready)==1,ready
            assert '1 exact downloaded update' in app.updates_guidance.get()
            assert json.loads((first/'manifest.json').read_text())['Version']=='1.0.0'

            app.unified_filter.set('Downloaded ZIP ready')
            app.update()
            assert len(app.unified_tree.get_children(''))==1
            with patch.object(app,'unified_review_install') as single, \
                 patch.object(app,'unified_review_batch') as batch:
                app.unified_review_ready()
                single.assert_called_once_with()
                batch.assert_not_called()
            assert json.loads((first/'manifest.json').read_text())['Version']=='1.0.0'

            # Two exact ZIP updates take the established, confirmation-gated
            # batch preflight, never a new automatic deployment method.
            second=make_mod(root,downloads,'ContentPatcher','test.cp')
            app.refresh()
            app.unified_filter.set('All')
            with patch.object(app,'unified_check') as online:
                app.check_all_updates()
                online.assert_called_once_with()
            spin(app,lambda:not app.unified_download_busy)
            ready=[r for r in app.unified_rows if r.get('download_status')=='Ready for review']
            assert len(ready)==2,ready
            with patch.object(app,'unified_review_install') as single, \
                 patch.object(app,'unified_review_batch') as batch:
                app.unified_review_ready()
                batch.assert_called_once_with()
                single.assert_not_called()
            assert len(app.unified_tree.selection())==2

            app.unified_filter.set('Not checked')
            app.update()
            with patch.object(unimod.messagebox,'showinfo') as info, \
                 patch.object(app,'unified_review_install') as single, \
                 patch.object(app,'unified_review_batch') as batch:
                app.unified_review_ready()
                info.assert_called_once()
                single.assert_not_called()
                batch.assert_not_called()
            assert json.loads((first/'manifest.json').read_text())['Version']=='1.0.0'
            assert json.loads((second/'manifest.json').read_text())['Version']=='1.0.0'
            print('UNIMOD_ONE_CLICK_UPDATES_GUI_OK')
        finally:
            app.destroy()
