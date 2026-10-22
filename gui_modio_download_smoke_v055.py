#!/usr/bin/env python3
"""Virtual Linux GUI smoke for reviewed mod.io file selection and game binding."""
import hashlib
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unimod

KEY='local-only-test-key'

def find_buttons(widget):
    stack=[widget];out=[]
    while stack:
        x=stack.pop()
        try:
            if x.winfo_class()=='TButton':out.append(x)
            stack.extend(x.winfo_children())
        except Exception:continue
    return out

def spin(app,predicate,timeout=8):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.update();time.sleep(.04)
    assert predicate(),'Timeout waiting for GUI event'

with TemporaryDirectory() as tmp:
    root=Path(tmp)
    game_dir=root/'Game';game_dir.mkdir();downloads=root/'Downloads';downloads.mkdir()
    game={'name':'Stardew Valley','kind':'smapi','root':str(game_dir)}
    with patch.object(unimod,'CONFIG',root/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[]});app=unimod.App()
        try:
            app.current=lambda:game
            app.provider_choice.set('mod.io');app.provider_scope.set('123')
            app.modio_user_id.set('456');app.provider_key.set(KEY)
            app.inbox_folder.set(str(downloads))
            app.modio_verified=('123','456',hashlib.sha256(KEY.encode()).digest(),'Stardew Valley')
            app.provider_results=[{'provider':'mod.io','title':'Test File','version':'',
               'identity':'123/77','url':'https://mod.io/g/stardew/m/test-mod','description':'demo','author':'tester'}]
            app.provider_tree.insert('','end',iid='0',values=('Test File','','','mod.io','demo'))
            app.provider_tree.selection_set('0')
            app.provider_files_dialog()
            dialog=[x for x in app.winfo_children() if x.winfo_class()=='Toplevel' and 'release files' in x.title()][0]
            buttons=find_buttons(dialog)
            fetch=next(x for x in buttons if x.cget('text')=='Fetch files')
            download=next(x for x in buttons if x.cget('text')=='Download selected to inbox')
            fake={'provider':'mod.io','identity':'123/77','version_id':'88','filename':'Test.zip',
                'size':123,'version':'1.5.0','hashes':{'md5':'a'*32},
                'game_versions':[],'loaders':[],'dependencies':[],'url':'https://u-456.modapi.io/v1/games/123/mods/77/files/88/download/abcdefghijkl'}
            with patch.object(unimod.modio_files,'list_modfiles',return_value=[fake]) as source:
                fetch.invoke()
                spin(app,lambda:bool(source.called and download.instate(['!disabled'])))
            tree=[x for x in dialog.winfo_children() if x.winfo_class()=='Frame']
            # Select the only file row by traversing the dialog.
            def trees(w):
                for child in w.winfo_children():
                    if child.winfo_class()=='Treeview':yield child
                    yield from trees(child)
            widget=next(trees(dialog))
            spin(app,lambda:len(widget.get_children())==1)
            widget.selection_set('0')
            calls=[]
            def staged(record,where,receipt_path,*,game_root,downloader):
                calls.append((record,game_root,callable(downloader)))
                return downloads/'Test.zip'
            with patch.object(unimod.messagebox,'askyesno',return_value=True),patch.object(unimod.provider_staging,'stage_download',side_effect=staged):
                download.invoke()
                spin(app,lambda:len(calls)==1)
                spin(app,lambda:download.instate(['!disabled']))
            assert calls[0][1]==str(game_dir)
            assert calls[0][2]
            assert calls[0][0]['identity']=='123/77'
            app.provider_key.set('changed-key')
            before=len(calls)
            with patch.object(unimod.messagebox,'showwarning') as warn:
                download.invoke()
                spin(app,lambda:warn.called)
            assert len(calls)==before
            assert not (root/'sources.json').exists()
            dialog.destroy()
            print('PASS: mod.io game-bound file review, staging approval, key-change rejection')
        finally:app.destroy()
