"""Headless UI smoke: available source lookup stays on the correct game and tab."""
import tkinter as tk
import unimod
app=unimod.App()
try:
    app.update_idletasks();app.update()
    app.show_page('Updates Available');app.update()
    assert 'Updates Available' in app.tabs.tab(app.tabs.select(),'text')
    assert hasattr(app,'unified_tree')
    assert hasattr(app,'unified_info')
    assert 'Updates Available' in app.rail_buttons
finally:
    app.destroy()
print('UNIMOD_V044_SOURCES_GUI_OK')
