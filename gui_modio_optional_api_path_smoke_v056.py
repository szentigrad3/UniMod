"""Xvfb: optional mod.io API path stays session-only and report stays redacted."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import unimod

KEY='fake-private-key-is-never-printed'
PATH='https://u-456.modapi.io/v1'


def find(widget,cls):
    result=[]
    for child in widget.winfo_children():
        if child.winfo_class()==cls:
            result.append(child)
        result.extend(find(child,cls))
    return result


with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp)
    game={'name':'Unlisted Game','kind':'smapi','root':str(base/'Game')}
    (base/'Game').mkdir()
    with patch.object(unimod,'CONFIG',base/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[game]})
        app=unimod.App()
        try:
            app.provider_modio_aio()
            dialog=next(w for w in app.winfo_children()
                        if w.winfo_class()=='Toplevel' and 'Run All Tests' in w.title())
            buttons={w.cget('text'):w for w in find(dialog,'TButton')}
            assert len(find(dialog,'TEntry'))==1
            toggle=buttons['Account API path (optional)  ▸']
            toggle.invoke();app.update()
            entries=find(dialog,'TEntry')
            assert len(entries)==2
            entries[0].delete(0,'end')
            entries[0].insert(0,KEY)
            entries[1].insert(0,PATH)
            assert entries[1].winfo_ismapped()
            assert buttons['Run All Tests'].winfo_ismapped()
            calls=[]
            fake={'offline':'Passed','catalogue':'Passed',
                  'game':'Not available','metadata':'Not available',
                  'download':'Not available','reason':'provider_api_access_required',
                  'scope':'Provider-only (different game)'}
            def work(*args,**kwargs):
                calls.append(kwargs)
                return fake
            with patch.object(unimod.modio_aio,'run_aio',side_effect=work), \
                 patch.object(unimod.messagebox,'askyesno',return_value=True):
                buttons['Run All Tests'].invoke()
                stop=time.monotonic()+8
                while app._modio_aio_running and time.monotonic()<stop:
                    app.update()
                    time.sleep(.025)
            assert len(calls)==1 and calls[0]['api_path']==PATH
            assert calls[0]['api_key']==KEY
            buttons['Copy safe report'].invoke()
            report=app.clipboard_get()
            assert 'account-specific API path' in report
            assert KEY not in report and PATH not in report
            assert str(base) not in report
            buttons['Close'].invoke()
            app.provider_modio_aio()
            dialog=next(w for w in app.winfo_children()
                        if w.winfo_class()=='Toplevel' and 'Run All Tests' in w.title())
            assert len(find(dialog,'TEntry'))==1, 'API path must not persist'
            assert buttons['Run All Tests'].winfo_exists()==0
            print('UNIMOD_MODIO_OPTIONAL_API_PATH_GUI_OK',flush=True)
        finally:
            app.destroy()
