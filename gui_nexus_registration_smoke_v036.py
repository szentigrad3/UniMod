#!/usr/bin/env python3
"""Offline GUI test for the Nexus registration candidate."""
import os, tempfile
from pathlib import Path
from unittest.mock import patch
import unimod

app=unimod.App()
app.update_idletasks()
assert app.nexus_key.get()==''
assert unimod.nexus_integr.registered_app_slug({}) is None
assert hasattr(app,'nexus_download_selected')
assert hasattr(app,'nexus_sso_connect')
assert hasattr(app,'nexus_download_nxm')
assert 'Nexus Updates' in [app.tabs.tab(tab,'text').strip() for tab in app.tabs.tabs()]
app.show_page('Nexus Updates')
app.update()
app.destroy()
print('UNIMOD_NEXUS_REGISTRATION_GUI_OK')
