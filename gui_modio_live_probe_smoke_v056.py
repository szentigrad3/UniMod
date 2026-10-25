#!/usr/bin/env python3
"""Virtual Linux GUI smoke for temporary mod.io ZIP verification."""
import hashlib
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unimod


def controls(widget, kind):
    for child in widget.winfo_children():
        if child.winfo_class() == kind:
            yield child
        yield from controls(child, kind)


def spin(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(.035)
    raise AssertionError('Timed out waiting for mod.io temporary check')


KEY = 'gui-temp-probe-private-key'

with TemporaryDirectory() as tmp:
    root = Path(tmp)
    game_root = root / 'Stardew'
    game_root.mkdir()
    game = {'name': 'Stardew Valley', 'kind': 'smapi', 'root': str(game_root)}
    with patch.object(unimod, 'CONFIG', root / 'config.json'), \
         patch.object(unimod, 'SOURCE_OVERRIDES', root / 'sources.json'), \
         patch.object(unimod, 'detect_games', return_value=[]):
        unimod.cfg_save({'games': []})
        app = unimod.App()
        try:
            app.current = lambda: game
            app.provider_choice.set('mod.io')
            app.provider_scope.set('123')
            app.modio_user_id.set('456')
            app.provider_key.set(KEY)
            app.modio_verified = ('123','456',hashlib.sha256(KEY.encode()).digest(),'Stardew Valley')
            app.provider_results = [{'provider':'mod.io','title':'Test Mod',
                'identity':'123/77','url':'https://mod.io/g/example/m/test'}]
            app.provider_tree.insert('', 'end', iid='0', values=('Test Mod','','','mod.io',''))
            app.provider_tree.selection_set('0')
            app.provider_files_dialog()
            dialog = next(w for w in app.winfo_children()
                          if w.winfo_class() == 'Toplevel' and 'release files' in w.title())
            buttons = {b.cget('text'): b for b in controls(dialog, 'TButton')}
            assert 'Test download (temporary)' in buttons
            fetch = buttons['Fetch files']
            probe = buttons['Test download (temporary)']
            row = {'provider':'mod.io','identity':'123/77','version_id':'88',
                'filename':'Test.zip','size':200,'version':'1.0',
                'hashes':{'md5':'a'*32},'game_versions':[],'loaders':[],
                'dependencies':[], 'url':'https://u-456.modapi.io/v1/games/123/mods/77/files/88/download/OfflineTokenABC'}
            with patch.object(unimod.modio_files, 'list_modfiles', return_value=[row]):
                fetch.invoke()
                spin(app, lambda: not fetch.instate(['disabled']))
            releases = next(controls(dialog, 'Treeview'))
            spin(app, lambda: len(releases.get_children()) == 1)
            releases.selection_set('0')
            result = {'status':'Downloaded and verified; temporary ZIP deleted',
                'game_id':'123','mod_id':'77','file_id':'88','bytes_verified':200,
                'sha256':'a'*64,'installed':False,'staged':False,'temporary':True}
            messages = []
            with patch.object(unimod.modio_live_probe, 'probe_download', return_value=result) as worker, \
                 patch.object(unimod.messagebox, 'askyesno', return_value=True), \
                 patch.object(unimod.messagebox, 'showinfo', side_effect=lambda *a,**k: messages.append(a)):
                probe.invoke()
                spin(app, lambda: bool(messages) and not probe.instate(['disabled']))
                assert worker.call_count == 1
                assert worker.call_args.kwargs['api_key'] == KEY
                assert KEY not in str(messages)
                assert 'SHA-256' in str(messages)
            # The background may have succeeded but its result must be discarded
            # if the user changes selection before the event is processed.
            messages = []
            with patch.object(unimod.modio_live_probe, 'probe_download', return_value=result), \
                 patch.object(unimod.messagebox, 'askyesno', return_value=True), \
                 patch.object(unimod.messagebox, 'showinfo', side_effect=lambda *a,**k: messages.append(a)):
                probe.invoke()
                releases.selection_remove('0')
                spin(app, lambda: not probe.instate(['disabled']))
                assert not messages
            releases.selection_set('0')
            app.provider_key.set('changed-key')
            with patch.object(unimod.messagebox, 'showwarning') as warning, \
                 patch.object(unimod.modio_live_probe, 'probe_download') as worker:
                probe.invoke()
                assert warning.called and not worker.called
            assert not (game_root / 'Mods').exists()
            assert not (root/'sources.json').exists()
            dialog.destroy()
            print('PASS: mod.io temporary GUI verification; stale selection/key rejected')
        finally:
            app.destroy()
