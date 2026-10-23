#!/usr/bin/env python3
"""Virtual Linux GUI regression for private mod.io API diagnostics."""
import hashlib
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import unimod

KEY = 'gui-mock-session-key'


def until(app, predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.update()
        if predicate():
            return
        time.sleep(.04)
    raise AssertionError('Timed out waiting for mod.io diagnostic')


with tempfile.TemporaryDirectory() as tmp:
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
            app.modio_verified = ('123', '456', hashlib.sha256(KEY.encode()).digest(), 'Stardew Valley')
            app.provider_results = [{'provider': 'mod.io', 'identity': '123/77', 'title': 'Test Mod'}]
            app.provider_tree.insert('', 'end', iid='0', values=('Test Mod', '', '', 'mod.io', ''))
            app.provider_tree.selection_set('0')
            fake = {'game_id': '123', 'mod_id': '77', 'status': 'Verified metadata access',
                    'eligible_zip_files': 1, 'checked_file_id': '88',
                    'exact_file_verified': True, 'downloaded': False}
            seen = []
            with patch.object(unimod.modio_diagnostics, 'check_modio_access', return_value=fake) as call, \
                 patch.object(unimod.messagebox, 'showinfo', side_effect=lambda *args, **kwargs: seen.append(args)):
                app.provider_modio_diagnostic()
                until(app, lambda: not app._modio_diagnostic_busy and bool(seen))
                assert call.call_args.args == ('123/77',)
                assert call.call_args.kwargs['user_id'] == '456'
                assert call.call_args.kwargs['api_key'] == KEY
                assert '88' in str(seen)
                assert KEY not in str(seen)
            with patch.object(unimod.messagebox, 'showwarning') as warn, \
                 patch.object(unimod.modio_diagnostics, 'check_modio_access') as call:
                app.provider_key.set('changed-private-key')
                app.provider_modio_diagnostic()
                assert warn.called and not call.called
            app.provider_key.set(KEY)
            seen = []
            with patch.object(unimod.modio_diagnostics, 'check_modio_access', return_value=fake), \
                 patch.object(unimod.messagebox, 'showinfo', side_effect=lambda *args, **kwargs: seen.append(args)):
                app.provider_modio_diagnostic()
                app.provider_tree.selection_remove('0')
                until(app, lambda: not app._modio_diagnostic_busy)
                assert not seen
                assert 'discarded' in app.provider_info.get().lower()
            print('PASS: mod.io diagnostic read-only GUI, changed-key and stale-selection checks')
        finally:
            app.destroy()
