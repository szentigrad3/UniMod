#!/usr/bin/env python3
"""Virtual Linux GUI smoke for beginner mod.io guide and safe report clipboard."""
import hashlib
import tempfile
import time
import modio_selftest
from pathlib import Path
from unittest.mock import patch

import unimod


def widgets(widget, kind):
    for child in widget.winfo_children():
        if child.winfo_class()==kind:
            yield child
        yield from widgets(child,kind)


KEY='mock-local-api-key-please-hide'

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    game_dir=root/'Stardew'
    game_dir.mkdir()
    game={'name':'Stardew Valley','kind':'smapi','root':str(game_dir)}
    with patch.object(unimod,'CONFIG',root/'config.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.current=lambda:game
            app.provider_choice.set('mod.io')
            app.provider_scope.set('123')
            app.modio_user_id.set('456')
            app.provider_key.set(KEY)
            app.modio_verified=('123','456',hashlib.sha256(KEY.encode()).digest(),'Stardew Valley')
            app.provider_results=[{'provider':'mod.io','identity':'123/77','title':'Example'}]
            app.provider_tree.insert('','end',iid='0',values=('Example','','','mod.io',''))
            app.provider_tree.selection_set('0')
            app.provider_modio_test_guide()
            guide=next(x for x in app.winfo_children()
                       if x.winfo_class()=='Toplevel' and 'easy testing guide' in x.title())
            buttons={b.cget('text'):b for b in widgets(guide,'TButton')}
            expected={'Choose game','Set up / verify','Search mods',
                      'Run metadata check','Open release files','Open Provider Inbox',
                      'Copy safe test report','Run built-in safety test','Refresh steps','Close'}
            assert expected.issubset(buttons), sorted(expected-set(buttons))
            buttons['Copy safe test report'].invoke()
            report=app.clipboard_get()
            assert 'Game verified: Yes' in report
            assert 'mod.io mod selected: Yes' in report
            assert 'Temporary download check: Not tested' in report
            assert KEY not in report and str(game_dir) not in report and '123/77' not in report
            guide.destroy()

            # Successful results only belong to the verified session.
            context=(str(game_dir.resolve()),'123/77','456',hashlib.sha256(KEY.encode()).digest())
            app._modio_test_results={'metadata':{'context':context,'result':'Passed'},
                                     'download':{'context':context,'result':'Passed'}}
            app.provider_modio_test_guide()
            guide=next(x for x in app.winfo_children()
                       if x.winfo_class()=='Toplevel' and 'easy testing guide' in x.title())
            buttons={b.cget('text'):b for b in widgets(guide,'TButton')}
            buttons['Copy safe test report'].invoke()
            assert 'Metadata check: Passed' in app.clipboard_get()
            assert 'Temporary download check: Passed' in app.clipboard_get()
            app.provider_key.set(KEY+'changed')
            buttons['Refresh steps'].invoke()
            buttons['Copy safe test report'].invoke()
            assert 'Metadata check: Not tested' in app.clipboard_get()
            assert 'Temporary download check: Not tested' in app.clipboard_get()
            # A tester can run the existing headless safety check without the terminal.
            pass_checks={name:1 for name in ('installed','updated','backups','tamper_refused',
               'wrong_game_refused','bad_download_refused','failed_update_restored',
               'secrets_not_persisted')}
            with patch.object(modio_selftest,'run',return_value=pass_checks) as run:
                buttons['Run built-in safety test'].invoke()
                until=time.monotonic()+6
                while app._modio_offline_busy and time.monotonic()<until:
                    app.update();time.sleep(.04)
                assert not app._modio_offline_busy and run.called
            buttons['Copy safe test report'].invoke()
            assert 'Built-in offline safety test: Passed' in app.clipboard_get()
            with patch.object(modio_selftest,'run',side_effect=ValueError('simulated')) as run:
                buttons['Run built-in safety test'].invoke()
                until=time.monotonic()+6
                while app._modio_offline_busy and time.monotonic()<until:
                    app.update();time.sleep(.04)
                assert not app._modio_offline_busy and run.called
            buttons['Copy safe test report'].invoke()
            assert 'Built-in offline safety test: Failed' in app.clipboard_get()
            assert KEY not in app.clipboard_get()
            buttons['Close'].invoke()
            print('PASS: beginner guide, one-click offline safety check, and redacted report')
        finally:
            app.destroy()
