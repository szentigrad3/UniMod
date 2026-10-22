#!/usr/bin/env python3
"""GUI regression for game-sensitive source identification (virtual display)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

with TemporaryDirectory() as tmp:
    folder=Path(tmp)
    smapi=folder/'Stardew Valley'; (smapi/'Mods').mkdir(parents=True)
    keeper=folder/'Graveyard Keeper';(keeper/'BepInEx'/'plugins').mkdir(parents=True)
    games=[{'name':'Stardew Valley','root':str(smapi),'kind':'smapi'},
           {'name':'Graveyard Keeper','root':str(keeper),'kind':'bepinex'}]
    with patch.object(unimod,'CONFIG',folder/'games.json'), patch.object(unimod,'SOURCE_OVERRIDES',folder/'sources.json'), patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':games})
        app=unimod.App()
        try:
            app.selected=1;app.fill_games();app.update()
            assert app.current()['name']=='Graveyard Keeper'
            assert app.unified_source_button.cget('text')=='Resolve sources for this game…'
            with patch.object(app,'identify_smapi_sources') as smapi_call,patch.object(app,'show_page') as page,patch.object(unimod.messagebox,'showinfo') as popup:
                app.unified_identify_sources()
                page.assert_called_once_with('Source Matching')
                smapi_call.assert_not_called()
                popup.assert_not_called()
            app.selected=0;app.fill_games();app.update()
            assert app.unified_source_button.cget('text')=='Identify SMAPI sources automatically'
            with patch.object(app,'identify_smapi_sources') as smapi_call,patch.object(app,'show_page') as page:
                app.unified_identify_sources()
                smapi_call.assert_called_once_with()
                page.assert_not_called()
            app.selected=1;app.fill_games();app.update()
            assert app.unified_source_button.cget('text')=='Resolve sources for this game…'
            print('PASS: Graveyard Keeper routes to Source Matching, Stardew to SMAPI, game switch updates button.')
        finally:
            app.destroy()
