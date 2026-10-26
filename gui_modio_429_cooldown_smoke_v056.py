"""Xvfb: an API 429 imposes a cooldown in Run All Tests without network retries."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from tkinter import ttk
import unimod


def find(widget,cls):
    out=[]
    for child in widget.winfo_children():
        if isinstance(child,cls):out.append(child)
        out.extend(find(child,cls))
    return out


with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)
    game={'name':'Stardew Valley','root':str(path/'Game'),'kind':'smapi'}
    (path/'Game').mkdir()
    with patch.object(unimod,'CONFIG',path/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',path/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[game]})
        app=unimod.App()
        try:
            app.provider_modio_aio()
            app.update()
            dialog=next(x for x in app.winfo_children()
                        if x.winfo_class()=='Toplevel' and 'Run All Tests' in x.title())
            buttons={b.cget('text'):b for b in find(dialog,ttk.Button)}
            entries=find(dialog,ttk.Entry)
            entries[0].insert(0,'test-only-key-not-real')
            fake={'offline':'Passed','catalogue':'Passed','game':'Not available',
                  'metadata':'Not available','download':'Not available',
                  'reason':'provider_rate_limited','retry_after_seconds':97,
                  'scope':'Provider-only (different game)'}
            with patch.object(unimod.modio_aio,'run_aio',return_value=fake) as run, \
                 patch.object(unimod.messagebox,'askyesno',return_value=False):
                buttons['Run All Tests'].invoke()
                end=time.monotonic()+6
                while time.monotonic()<end:
                    app.update()
                    if run.called and not app._modio_aio_running:break
                    time.sleep(.02)
                assert run.call_count==1
                assert app._modio_aio_rate_limit_until-time.monotonic()>80
                buttons['Run All Tests'].invoke()
                app.update()
                assert run.call_count==1, 'second attempt must not access mod.io'
                buttons['Copy safe report'].invoke()
                report=app.clipboard_get()
                assert 'Provider cooldown: at least 97 second(s)' in report
                assert 'test-only-key-not-real' not in report
            buttons['Close'].invoke()
            print('UNIMOD_MODIO_429_GUI_OK')
        finally:
            app.destroy()
