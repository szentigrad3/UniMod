#!/usr/bin/env python3
"""Xvfb regression: the everyday UI starts simple and retains safe navigation."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import unimod

with tempfile.TemporaryDirectory() as folder, \
     patch.object(unimod, 'CONFIG', Path(folder) / 'games.json'), \
     patch.object(unimod, 'SOURCE_OVERRIDES', Path(folder) / 'sources.json'), \
     patch.object(unimod, 'detect_games', return_value=[]):
    unimod.cfg_save({'games': []})
    app = unimod.App()
    try:
        app.update()
        assert app.tabs.tab(app.tabs.select(), 'text').strip() == 'Overview'
        assert app.more_button.winfo_ismapped(), 'More menu must be visible'
        assert not app.profile_menu.winfo_ismapped(), 'Profiles belong in More'
        assert app.tools_button.winfo_ismapped(), 'Advanced menu must remain accessible'
        expected = {
            'Overview', 'Installed Mods', 'Mod Websites',
            'Updates Available', 'Update Inbox', 'All Games & Mods'
        }
        assert expected.issubset(app.rail_buttons)
        assert all(len(app.rail_buttons[name].cget('text').strip()) > 3 for name in expected)
        actions = [
            app.more_menu.entrycget(i, 'label')
            for i in range(app.more_menu.index('end') + 1)
            if app.more_menu.type(i) != 'separator'
        ]
        for label in ('Install a downloaded ZIP…', 'Rescan selected game',
                      'Check My Mods', 'Check for updates',
                      'Find installed games', 'Profiles and backups'):
            assert label in actions, (label, actions)
        assert app.winfo_width() <= app.winfo_screenwidth()
        assert app.winfo_height() <= app.winfo_screenheight()
        app.rail_buttons['Installed Mods'].invoke()
        app.update()
        assert app.tabs.tab(app.tabs.select(), 'text').strip() == 'Installed Mods'
        app.rail_buttons['Overview'].invoke()
        app.update()
        assert app.tabs.tab(app.tabs.select(), 'text').strip() == 'Overview'
        print('UNIMOD_BEGINNER_HOME_GUI_OK')
    finally:
        app.destroy()
