#!/usr/bin/env python3
"""Offline GUI smoke: mod.io session-key, user API path, game identity."""
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

with TemporaryDirectory() as temp:
    root=Path(temp)
    with patch.object(unimod,'CONFIG',root/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.provider_choice.set('mod.io')
            app.provider_query.set('testmod')
            app.provider_scope.set('123')
            app.modio_user_id.set('456')
            app.provider_key.set('mock-key-that-is-not-real')
            app.provider_begin_search()
            assert 'Verify and confirm' in app.provider_info.get(),app.provider_info.get()
            with patch.object(unimod.provider_catalogues,'modio_game',return_value={'id':'123','name':'Test Game'}),patch.object(unimod.messagebox,'askyesno',return_value=True):
                app.provider_verify_modio_game()
                deadline=time.monotonic()+8
                while app.modio_verified is None and time.monotonic()<deadline:
                    app.update();time.sleep(0.04)
            assert app.modio_verified[0:2]==('123','456')
            with patch.object(unimod.provider_catalogues,'search',return_value=[{
                'provider':'mod.io','title':'Test Mod','author':'Developer',
                'version':'','url':'https://mod.io/g/test-game/m/test-mod',
                'identity':'123/22','description':'demo'}]) as search:
                app.provider_begin_search()
                deadline=time.monotonic()+8
                while app.provider_loading and time.monotonic()<deadline:
                    app.update();time.sleep(0.04)
                assert search.call_args.kwargs['user_id']=='456'
            assert len(app.provider_results)==1
            app.provider_key.set('changed-mock-key')
            app.provider_begin_search()
            assert 'Verify and confirm' in app.provider_info.get()
            app.provider_key.set('mock-key-that-is-not-real')
            app.modio_user_id.set('457')
            app.provider_begin_search()
            assert 'Verify and confirm' in app.provider_info.get()
            assert not (root/'sources.json').exists()
            print('PASS: mod.io user API path, explicit game verification, changed-key/ID invalidation, no source writes')
        finally:
            app.destroy()
