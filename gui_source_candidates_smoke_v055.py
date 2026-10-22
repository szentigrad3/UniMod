#!/usr/bin/env python3
"""v0.55 Test 3: source-link review actions use selected game, never names alone."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

with TemporaryDirectory() as td:
    home=Path(td)
    gamepath=home/'Graveyard Keeper'
    dll=gamepath/'BepInEx'/'plugins'/'LongerDays.dll'
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b'existing game mod - do not modify')
    other=home/'Stardew Valley'
    (other/'Mods').mkdir(parents=True)
    games=[{'name':'Graveyard Keeper','kind':'bepinex','root':str(gamepath)},
           {'name':'Stardew Valley','kind':'smapi','root':str(other)}]
    with patch.object(unimod,'CONFIG',home/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',home/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':games})
        app=unimod.App()
        try:
            app.selected=0;app.fill_games();app.update()
            assert len(app.rows)==1,app.rows
            assert app.source_rows[0]['status']=='Unmatched'
            app.source_tree.selection_set('0')
            with patch.object(app,'provider_begin_search') as search:
                app.source_search_candidates()
                search.assert_called_once_with()
            assert app.provider_choice.get()=='Nexus Mods'
            assert app.provider_scope.get()=='graveyardkeeper'
            assert app.provider_query.get()=='LongerDays'
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Mod Websites'
            assert app.source_candidate_target['game_name']=='Graveyard Keeper'
            sample={'provider':'GitHub','title':'LongerDays','author':'Dev',
                    'url':'https://github.com/Dev/LongerDays', 'identity':'Dev/LongerDays','version':'', 'description':''}
            app.provider_show_results([sample],'GitHub')
            app.provider_tree.selection_set('0')
            with patch.object(unimod.messagebox,'askyesno',return_value=False) as confirm:
                app.provider_assign_reviewed_source()
                assert confirm.called
            assert not (home/'sources.json').exists()
            # A changed game must not accidentally link the old game mod.
            app.selected=1
            with patch.object(unimod.messagebox,'showwarning') as warning:
                app.provider_assign_reviewed_source()
                warning.assert_called_once()
            assert not (home/'sources.json').exists()
            app.selected=0
            # Invalid source URLs from manipulated provider data are rejected.
            app.provider_results[0]['url']='https://other.invalid/Dev/LongerDays'
            with patch.object(unimod.messagebox,'showwarning') as warning:
                app.provider_assign_reviewed_source()
                warning.assert_called_once()
            assert not (home/'sources.json').exists()
            app.provider_results[0]={**sample,'url':'https://github.com/Dev/LongerDays'}
            with patch.object(unimod.messagebox,'askyesno',return_value=True):
                app.provider_assign_reviewed_source()
            assert unimod.assigned_source(games[0],app.rows[0])['url']=='https://github.com/Dev/LongerDays'
            assert dll.read_bytes()==b'existing game mod - do not modify'
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Source Matching'
            assert app.source_rows[0]['status']=='Assigned by user'
            assert app.source_candidate_target is None
            print('PASS: Game-scoped BepInEx source candidate review, explicit approval, URL gating, unchanged game files')
        finally:
            app.destroy()
