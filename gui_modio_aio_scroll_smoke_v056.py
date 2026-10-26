"""Xvfb: Run All Tests footer remains usable when the report is long."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import unimod


def find(root, cls):
    result=[]
    for child in root.winfo_children():
        if child.winfo_class()==cls:result.append(child)
        result.extend(find(child,cls))
    return result


def spin(app):
    stop=time.monotonic()+7
    while time.monotonic()<stop:
        app.update()
        if not app._modio_aio_running:return
        time.sleep(.025)
    raise AssertionError('Safe AIO test did not complete')


with tempfile.TemporaryDirectory() as td:
    base=Path(td)
    game=base/'Stardew Valley';game.mkdir()
    with patch.object(unimod,'CONFIG',base/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',base/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App()
        try:
            app.provider_modio_aio()
            app.update()
            d=next(w for w in app.winfo_children()
                   if w.winfo_class()=='Toplevel' and 'Run All Tests' in w.title())
            buttons={x.cget('text'):x for x in find(d,'TButton')}
            texts=find(d,'Text')
            assert len(texts)==1
            report=texts[0]
            for key in ('Run All Tests','Copy safe report','Close'):
                assert buttons[key].winfo_ismapped(),(key,d.winfo_width(),d.winfo_height())
                assert buttons[key].winfo_rooty()+buttons[key].winfo_height() <= (
                    d.winfo_rooty()+d.winfo_height()+2),key
            assert report.winfo_ismapped()
            assert report.cget('state')=='disabled'
            assert d.winfo_height() <= d.winfo_screenheight()
            entry=find(d,'TEntry')[0]
            entry.insert(0,'unshared-fixture-only-key')
            result={'offline':'Passed','catalogue':'Passed','game':'Not available',
                    'metadata':'Not available','download':'Not available',
                    'scope':'Provider-only (different game)',
                    'selection':'Not selected','reason':'provider_sample_unavailable'}
            with patch.object(unimod.modio_aio,'run_aio',return_value=result), \
                 patch.object(unimod.messagebox,'askyesno',return_value=True):
                buttons['Run All Tests'].invoke()
                spin(app)
            body=report.get('1.0','end-1c')
            assert 'Independent' not in body or 'provider' in body
            assert 'public sample had no verified release lists' in body
            assert 'Real-game installation: Not attempted' in body
            buttons['Copy safe report'].invoke()
            assert 'Real-game installation: Not attempted' in app.clipboard_get()
            buttons['Close'].invoke()
            print('UNIMOD_MODIO_AIO_SCROLL_GUI_OK',flush=True)
        finally:
            app.destroy()
