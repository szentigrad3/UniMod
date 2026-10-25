"""Xvfb smoke: Downloads is a clear hub for two existing review queues."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from tkinter import ttk
import unimod

def buttons(widget):
    for child in widget.winfo_children():
        if isinstance(child,ttk.Button):
            yield child
        yield from buttons(child)

with TemporaryDirectory() as temp:
    root=Path(temp)
    with patch.object(unimod,'CONFIG',root/'games.json'), \
         patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod.provider_staging,'read_staged',return_value=[
             {'provider':'Modrinth','filename':'example.jar','version':'1.0','game_root':''}]), \
         patch.object(unimod,'provider_install_reviewed',side_effect=AssertionError('Unexpected install')):
        unimod.cfg_save({'games':[]})
        app=unimod.App()
        try:
            app.rail_buttons['Downloads'].invoke()
            app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Downloads'
            assert '1 downloaded provider file(s)' in app.downloads_provider_summary.get()
            home=app.nametowidget(app._tab_with_name('Downloads'))
            labels={x.cget('text'):x for x in buttons(home)}
            assert 'Check selected file' in labels
            assert 'Review & install…' in labels
            assert labels['Review & install…'].instate(['disabled'])
            assert 'More download options…' in labels
            assert 'Review Nexus / ZIP downloads' in labels

            labels['More download options…'].invoke()
            app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Provider Inbox'
            app.show_page('Downloads')
            labels['Review Nexus / ZIP downloads'].invoke()
            app.update()
            assert app.tabs.tab(app.tabs.select(),'text').strip()=='Update Inbox'

            # Nothing installed merely from navigating to a review queue.
            assert not (root/'sources.json').exists()
            print('UNIMOD_DOWNLOADS_HOME_GUI_OK')
        finally:
            app.destroy()
