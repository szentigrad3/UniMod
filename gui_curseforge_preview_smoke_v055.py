#!/usr/bin/env python3
"""Offline GUI verification of CurseForge scoped, read-only integration."""
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

with TemporaryDirectory() as temp:
    root=Path(temp)
    with patch.object(unimod,'CONFIG',root/'config.json'), patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.provider_choice.set('CurseForge')
            app.provider_query.set('testmod')
            app.provider_scope.set('432')
            app.provider_key.set('approved-test-key')
            app.provider_begin_search()
            assert 'Verify and confirm' in app.provider_info.get(),app.provider_info.get()
            with patch.object(unimod.provider_catalogues,'curseforge_game',return_value={'id':'432','name':'Minecraft','slug':'minecraft'}),patch.object(unimod.messagebox,'askyesno',return_value=True):
                app.provider_verify_curseforge_game()
                deadline=time.monotonic()+7
                while app.curseforge_verified is None and time.monotonic()<deadline:
                    app.update();time.sleep(0.05)
            assert app.curseforge_verified[0]=='432'
            with patch.object(unimod.provider_catalogues,'search',return_value=[{
                'provider':'CurseForge','title':'Test Mod','author':'Developer',
                'version':'','url':'https://www.curseforge.com/minecraft/mc-mods/testmod',
                'identity':'432/22','description':'demo'}]):
                app.provider_begin_search()
                deadline=time.monotonic()+7
                while app.provider_loading and time.monotonic()<deadline:
                    app.update();time.sleep(0.05)
            assert len(app.provider_results)==1
            app.provider_tree.selection_set('0')
            with patch.object(app,'provider_curseforge_files_dialog') as readonly:
                app.provider_files_dialog()
                readonly.assert_called_once()
            app.provider_key.set('changed-test-key')
            app.provider_begin_search()
            assert 'Verify and confirm' in app.provider_info.get()
            assert not (root/'sources.json').exists()
            print('PASS: CurseForge game verification; scoped catalogue; read-only file route; session key rotation blocks search')
        finally:
            app.destroy()
