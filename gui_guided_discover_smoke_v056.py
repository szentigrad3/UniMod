"""Offline Xvfb regression: Find Mods is useful without reading API jargon."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import unimod


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    with patch.object(unimod, 'CONFIG', root/'games.json'), \
         patch.object(unimod, 'SOURCE_OVERRIDES', root/'sources.json'), \
         patch.object(unimod, 'detect_games', return_value=[]):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.show_page('Mod Websites')
            app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Mod Websites'
            assert app.provider_search_box.winfo_ismapped()
            assert app.provider_setup_button.winfo_ismapped()
            assert not app.provider_advanced.winfo_ismapped()
            assert app.provider_choice.get()=='Modrinth'
            assert 'Nothing has been downloaded' in app.provider_next_step.get()

            # Basic catalogue browsing doesn't modify installed files or stage a download.
            result={'provider':'Modrinth','title':'Example','author':'A',
                    'version':'1.0','identity':'testid','url':'https://modrinth.com/mod/testid',
                    'description':'Example text'}
            with patch.object(unimod.provider_staging,'stage_download',
                              side_effect=AssertionError('unexpected download')), \
                 patch.object(unimod,'provider_install_reviewed',
                              side_effect=AssertionError('unexpected install')):
                app.provider_show_results([result],'Modrinth')
                app.provider_tree.selection_set('0')
                app.update()
                assert 'Browse release files' in app.provider_next_step.get()
                app.provider_review_downloads()
                app.update()
                assert app.tabs.tab(app.tabs.select(),'text').strip()=='Provider Inbox'

            # The advanced panel opens and closes without erasing private state.
            app.show_page('Mod Websites')
            app.provider_setup_button.invoke()
            app.update()
            assert app.provider_advanced.winfo_ismapped()
            app.provider_key.set('session-only-placeholder')
            app.provider_setup_button.invoke()
            app.update()
            assert not app.provider_advanced.winfo_ismapped()
            assert app.provider_key.get()=='session-only-placeholder'

            # Protected providers reveal setup, clear old search hits.
            app.provider_choice.set('mod.io')
            app.provider_changed()
            app.update()
            assert app.provider_advanced.winfo_ismapped()
            assert not app.provider_tree.get_children()
            assert len(app.provider_results)==0
            assert app.provider_key.get()=='session-only-placeholder'
            app.provider_choice.set('Nexus Mods')
            app.provider_changed()
            app.provider_show_results([{
                'provider':'Nexus Mods','title':'Another','author':'Someone',
                'version':'','url':'https://www.nexusmods.com/stardewvalley/mods/1',
                'description':'Test'}],'Nexus Mods')
            app.provider_tree.selection_set('0')
            app.update()
            assert 'not supported' in app.provider_next_step.get()

            assert not (root/'sources.json').exists()
            print('UNIMOD_GUIDED_DISCOVER_GUI_OK')
        finally:
            app.destroy()
