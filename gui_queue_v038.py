"""Virtual desktop smoke: links reach existing GUI, batch runs with mocked Nexus API."""
from pathlib import Path
from unittest.mock import patch
import tempfile, time
from unimod import App
from instance_bridge import SingleInstance, send_to_running
from nexus_queue import NexusDownloadQueue

NXM='nxm://stardewvalley/mods/3753/files/123456?key=token12345&expires=9999999999&user_id=17'
with tempfile.TemporaryDirectory() as t:
    bridge=SingleInstance(Path(t)/'run');assert bridge.acquire();bridge.start()
    app=App(bridge=bridge)
    try:
        assert send_to_running(bridge.folder,NXM)
        until=time.monotonic()+7
        while time.monotonic()<until and not app.nexus_queue.public_rows():
            app.update();time.sleep(.04)
        assert len(app.nexus_queue.public_rows())==1
        assert app.nexus_queue.public_rows()[0]['mod']=='3753'
        assert app.tabs.select()==str(app.inbox_tab)
        app.nexus_queue.add_file('stardewvalley','7286','22','test.zip')
        app.nexus_queue_refresh()
        app.nexus_key.set('private-test-secret-that-is-not-logged')
        app.inbox_folder.set(t)
        with patch('unimod.messagebox.askyesno',return_value=True),\
             patch('unimod.nexus_api_json',return_value=[{'URI':'https://files.nexus-cdn.com/test.zip'}]),\
             patch('unimod.nexus_integr.download_archive',side_effect=lambda _url,_folder,name,**kw: Path(t)/name):
            app.nexus_queue_download_all()
            until=time.monotonic()+7
            while time.monotonic()<until and app.nexus_running:
                app.update();time.sleep(.04)
        assert not app.nexus_running, 'Batch did not finish'
        assert [x['status'] for x in app.nexus_queue.public_rows()]==['Downloaded','Downloaded']
        assert all(x.nxm is None for x in app.nexus_queue._items)
        assert 'token12345' not in str(app.nexus_queue.public_rows())
        print('UNIMOD_V038_GUI_QUEUE_OK')
    finally:app.destroy();bridge.close()
