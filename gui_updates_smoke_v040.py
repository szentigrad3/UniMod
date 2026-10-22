import tkinter as tk
from unittest.mock import patch
import unimod

app=unimod.App()
app.update()
app.show_page('Updates Available')
app.update()
assert app.tabs.tab(app.tabs.select(),'text').strip()=='Updates Available'
assert hasattr(app,'unified_tree')
# Controlled fixture, no network and no actual game writes.
fixture={'name':'Stardew Valley','root':'/tmp/unimod-v040-fixture','kind':'smapi'}
app.data={'games':[fixture]};app.selected=0
app.rows=[{'name':'SpaceCore','version':'1.0.0','uid':'some.spacecore',
           'path':'/tmp/unimod-v040-fixture/Mods/SpaceCore','update_keys':['Nexus:1348']}]
with patch.object(unimod,'smapi_folder_entries',return_value=[]):
    app.unified_render()
assert app.unified_tree.get_children(), 'Missing updates list'
first=app.unified_tree.item(app.unified_tree.get_children()[0],'values')
assert 'Not checked' in first,first
app.unified_filter.set('Updates available');app.update()
assert not app.unified_tree.get_children(), 'Must not pretend unchecked is available'
app.unified_nexus[app.rows[0]['path']]={'status':'Update available','version':'1.1.0'}
with patch.object(unimod,'smapi_folder_entries',return_value=[]):
    app.unified_render()
assert len(app.unified_tree.get_children())==1
app.destroy()
print('UNIMOD_V040_UPDATES_GUI_OK')
