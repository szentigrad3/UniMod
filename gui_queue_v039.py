"""GUI smoke for stream status, cancellation, retry and inbox handoff."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from unimod import App
import nexus_integration as nx

with tempfile.TemporaryDirectory() as t:
    app=App()
    try:
        a=app.nexus_queue.add_file('stardewvalley','3753','111','one.zip')
        b=app.nexus_queue.add_file('stardewvalley','7286','222','two.zip')
        app.nexus_queue_refresh()
        app.nexus_key.set('fake-api-key-only-for-tests')
        app.inbox_folder.set(t)
        def cancelled_download(url,folder,name,**kw):
            kw['progress'](2048,4096)
            kw['cancel_event'].set()
            raise nx.DownloadCancelled('test cancelled')
        with patch('unimod.messagebox.askyesno',return_value=True),\
             patch('unimod.nexus_api_json',return_value=[{'URI':'https://files.nexus-cdn.com/mod.zip'}]),\
             patch('unimod.nexus_integr.download_archive',side_effect=cancelled_download):
            app.nexus_queue_download_all()
            stop=time.monotonic()+12
            while app.nexus_running and time.monotonic()<stop:
                app.update();time.sleep(.02)
        assert not app.nexus_running
        assert [e.status for e in app.nexus_queue._items]==['Cancelled','Cancelled']
        app.nexus_queue_tree.selection_set(str(a.id))
        app.nexus_queue_retry()
        assert a.status=='Ready to review'
        # Successful download and reviewed handoff
        saved=Path(t)/'one.zip'; saved.write_bytes(b'PK\x03\x04test')
        def good_download(url,folder,name,**kw):
            kw['progress'](4096,4096)
            return saved
        with patch('unimod.messagebox.askyesno',return_value=True),\
             patch('unimod.nexus_api_json',return_value=[{'URI':'https://files.nexus-cdn.com/mod.zip'}]),\
             patch('unimod.nexus_integr.download_archive',side_effect=good_download):
            app.nexus_queue_download()
            stop=time.monotonic()+12
            while app.nexus_running and time.monotonic()<stop:
                app.update();time.sleep(.02)
        assert a.status=='Downloaded'
        assert app.nexus_queue_progress['value']==0
        with patch.object(app,'inbox_scan') as mock_scan:
            app.nexus_queue_review()
            mock_scan.assert_called_once()
        assert app.inbox_folder.get()==t
        print('UNIMOD_V039_GUI_QUEUE_OK')
    finally:
        app.destroy()
