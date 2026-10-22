"""Virtual X11 smoke test for NXM deep links, read-only queue and no key."""
import time
import tkinter as tk
from unimod import App

NXM='nxm://stardewvalley/mods/3753/files/123456?key=token12345&expires=9999999999&user_id=17'
app=App(incoming_nxm=NXM)
try:
    stop=time.monotonic()+6
    while time.monotonic()<stop:
        app.update()
        if app.nexus_queue.public_rows():break
        time.sleep(0.04)
    rows=app.nexus_queue.public_rows()
    assert len(rows)==1,rows
    assert rows[0]['mod']=='3753',rows
    assert 'token12345' not in str(rows)
    assert app.tabs.select()==str(app.inbox_tab),app.tabs.select()
    assert app.nexus_queue_tree.get_children(), 'Missing GUI queue row'
    assert app.nexus_key.get()=='', 'Never insert a hidden default API key'
    print('NEXUS_QUEUE_GUI_OK')
finally:
    app.destroy()
