#!/usr/bin/env python3
"""Virtual Linux GUI smoke: mod.io managed-release checks are review-only."""
import hashlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import modio_managed
import unimod


def spin(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(.04)
    raise AssertionError('Managed mod.io GUI check did not finish')


with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    game_root = base / 'Stardew'
    folder = game_root / 'Mods' / 'Example'
    folder.mkdir(parents=True)
    manifest = folder / 'manifest.json'
    manifest.write_text(json.dumps({'UniqueID': 'Example.Modio', 'Version': '1.0.0'}))
    game = {'name': 'Stardew Valley', 'kind': 'smapi', 'root': str(game_root)}
    source = {'provider': 'mod.io', 'identity': '123/77',
              'version_id': '88', 'version': '1.0.0'}
    record = {'package': 'mod.io:123/77', 'game': str(game_root.resolve()),
              'paths': [str(folder.resolve())],
              **modio_managed.provenance(game, [str(folder)], source)}
    key = 'local-gui-mock-key'
    alternate = {'provider': 'mod.io', 'identity': '123/77', 'version_id': '89', 'version': '1.2.0'}
    with patch.object(unimod, 'CONFIG', base / 'config.json'), \
         patch.object(unimod, 'SOURCE_OVERRIDES', base / 'sources.json'), \
         patch.object(unimod, 'detect_games', return_value=[]):
        unimod.cfg_save({'games': []})
        app = unimod.App()
        try:
            app.current = lambda: game
            app.provider_choice.set('mod.io')
            app.provider_scope.set('123')
            app.modio_user_id.set('456')
            app.provider_key.set(key)
            app.modio_verified = ('123', '456', hashlib.sha256(key.encode()).digest(), 'Stardew Valley')
            notices = []
            with patch.object(unimod, 'read_receipts', return_value=[record]), \
                 patch.object(unimod.modio_files, 'list_modfiles', return_value=[alternate]) as lookup, \
                 patch.object(unimod.messagebox, 'showinfo', side_effect=lambda *args, **kwargs: notices.append(args)):
                app.provider_check_modio_updates()
                spin(app, lambda: not app._modio_check_busy and bool(notices))
                assert lookup.call_count == 1
                assert lookup.call_args.args[0] == '123/77'
                assert '89' in str(notices)
                assert 'review' in str(notices).lower()
            with patch.object(unimod.messagebox, 'showwarning') as warning, \
                 patch.object(unimod.modio_files, 'list_modfiles') as lookup:
                app.provider_key.set('different-session-key')
                app.provider_check_modio_updates()
                assert warning.called and not lookup.called
            assert manifest.exists()
            print('PASS: mod.io managed release GUI review only; changed-key refusal')
        finally:
            app.destroy()
