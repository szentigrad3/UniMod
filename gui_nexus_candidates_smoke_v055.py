#!/usr/bin/env python3
"""Game-scoped Nexus candidate review must never update game files without consent."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unimod

with TemporaryDirectory() as temp:
    root=Path(temp)
    a=root/'Graveyard Keeper'; b=root/'Graveyard Keeper 2'
    dll=a/'BepInEx/plugins/LongerDays.dll'; dll.parent.mkdir(parents=True);dll.write_bytes(b'unchanged original')
    (b/'BepInEx/plugins').mkdir(parents=True)
    games=[{'name':'Graveyard Keeper','kind':'bepinex','root':str(a)},
           {'name':'Graveyard Keeper 2','kind':'bepinex','root':str(b)}]
    with patch.object(unimod,'CONFIG',root/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'detect_games',return_value=[]):
        unimod.cfg_save({'games':games})
        app=unimod.App()
        try:
            app.selected=0;app.fill_games();app.update()
            app.source_tree.selection_set('0')
            with patch.object(app,'provider_begin_search') as search:
                app.source_search_candidates();search.assert_called_once()
            assert app.provider_choice.get()=='Nexus Mods'
            assert app.provider_scope.get()=='graveyardkeeper'
            candidate={'provider':'Nexus Mods','title':'Longer Days','author':'Author',
                       'url':'https://www.nexusmods.com/graveyardkeeper2/mods/11',
                       'identity':'graveyardkeeper2/11','version':'1.1','description':''}
            app.provider_show_results([candidate],'Nexus Mods');app.provider_tree.selection_set('0')
            with patch.object(unimod.messagebox,'showwarning') as reject:
                app.provider_assign_reviewed_source();reject.assert_called_once()
            assert not (root/'sources.json').exists()
            candidate['url']='https://www.nexusmods.com/graveyardkeeper/mods/11'
            with patch.object(unimod.messagebox,'askyesno',return_value=False) as confirm:
                app.provider_assign_reviewed_source(); confirm.assert_called_once()
            assert not (root/'sources.json').exists()
            with patch.object(unimod.messagebox,'askyesno',return_value=True):
                app.provider_assign_reviewed_source()
            assert unimod.assigned_source(games[0],app.rows[0])['url']==candidate['url']
            assert dll.read_bytes()==b'unchanged original'
            print('PASS: Nexus discovery scoped to Graveyard Keeper; wrong game rejected; consent required; DLL unchanged')
        finally:app.destroy()
