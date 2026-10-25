#!/usr/bin/env python3
"""Virtual Linux GUI smoke for UniMod one-click all-in-one tester."""
import hashlib
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unimod

KEY='test-aio-session-secret-not-for-logs'

def controls(widget, cls):
    for c in widget.winfo_children():
        if c.winfo_class()==cls:
            yield c
        yield from controls(c,cls)

def spin(app, predicate, seconds=10):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        app.update()
        if predicate():return
        time.sleep(.035)
    raise AssertionError('AIO GUI timed out')


with TemporaryDirectory() as temp:
    base=Path(temp)
    game_root=base/'Stardew'
    game_root.mkdir()
    game={'kind':'smapi','name':'Stardew Valley','root':str(game_root)}
    with patch.object(unimod,'CONFIG',base/'config.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.current=lambda:game
            app.provider_modio_aio()
            dialog=next(w for w in app.winfo_children()
                        if w.winfo_class()=='Toplevel' and 'Run All Tests' in w.title())
            buttons={b.cget('text'):b for b in controls(dialog,'TButton')}
            entries=list(controls(dialog,'TEntry'))
            assert {'Run All Tests','Copy safe report','Close'}.issubset(buttons)
            assert len(entries)==1, len(entries)
            passed={'offline':'Passed','game':'Passed','metadata':'Passed',
                    'download':'Passed','reason':'complete','selection':'Automatic public test mod'}
            entries[0].delete(0,'end')
            entries[0].insert(0,KEY)
            calls=[]
            def aio(*args, **kw):
                calls.append((args,kw))
                return passed
            with patch.object(unimod.modio_aio,'run_aio',side_effect=aio), \
                 patch.object(unimod.messagebox,'askyesno',return_value=True) as confirm:
                buttons['Run All Tests'].invoke()
                spin(app,lambda:not app._modio_aio_running)
            assert confirm.called, 'No approval for automatic public download'
            assert len(calls)==1 and calls[0][1]['allow_transfer'] is True
            assert calls[0][1]['mod_id']==''
            assert calls[0][1]['game_id']==''
            assert calls[0][1]['user_id']==''
            assert calls[0][1]['api_key']==KEY
            buttons['Copy safe report'].invoke()
            copied=app.clipboard_get()
            assert 'Offline install/update/rollback: Passed' in copied
            assert 'Temporary ZIP download: Passed' in copied
            assert KEY not in copied and str(game_root) not in copied
            assert app.modio_verified is None, 'Never invent an account ID from an API key'
            buttons['Close'].invoke()

            # A changed game while the background worker runs discards the
            # private remote results rather than showing a false success.
            app.provider_modio_aio()
            dialog=next(w for w in app.winfo_children()
                        if w.winfo_class()=='Toplevel' and 'Run All Tests' in w.title())
            buttons={b.cget('text'):b for b in controls(dialog,'TButton')}
            entries=list(controls(dialog,'TEntry'))
            entries[0].delete(0,'end')
            entries[0].insert(0,KEY)
            def delayed(*args, **kw):
                time.sleep(.20)
                return passed
            with patch.object(unimod.modio_aio,'run_aio',side_effect=delayed), \
                 patch.object(unimod.messagebox,'askyesno',return_value=True):
                buttons['Run All Tests'].invoke()
                app.current=lambda:{**game,'name':'Changed Game'}
                spin(app,lambda:not app._modio_aio_running)
            buttons['Copy safe report'].invoke()
            copied=app.clipboard_get()
            assert 'Official game verification: Not tested' in copied
            assert 'Temporary ZIP download: Not tested' in copied
            assert KEY not in copied
            buttons['Close'].invoke()
            print('PASS: one-click AIO, opt-in auto selection, safe report, stale game refusal')
        finally:
            app.destroy()
