"""Virtual X11 smoke for the integrated Updates -> ZIP -> reviewed install UI."""
import json
import tempfile
import time
from pathlib import Path
import zipfile
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as home:
    root = Path(home)
    game = {'name':'Stardew Valley','root':str(root),'kind':'smapi'}
    folder=root/'Mods'/'SpaceCore';folder.mkdir(parents=True)
    manifest={'Name':'SpaceCore','UniqueID':'test.SpaceCore','Version':'1.0.0'}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    archive=root/'SpaceCore.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('SpaceCore/manifest.json',json.dumps({**manifest,'Version':'1.2.0'}))
    app=unimod.App()
    try:
        app.data={'games':[game]};app.selected=0
        app.inbox_folder.set(str(root))
        app.rows=unimod.items(game)
        app.show_page('Updates Available');app.unified_render();app.update()
        assert app.unified_tree.get_children()
        app.unified_scan_downloads()
        end=time.monotonic()+8
        while app.unified_download_busy and time.monotonic()<end:
            app.update();time.sleep(.03)
        assert not app.unified_download_busy
        assert app.unified_rows[0]['download_status']=='Ready for review',app.unified_rows
        app.unified_tree.selection_set('0')
        # Verify the complete review step, then decline so no game files can change.
        with patch('unimod.messagebox.askyesno',return_value=False) as confirm:
            app.unified_review_install();app.update()
        assert confirm.call_count==1
        assert 'SpaceCore.zip' in confirm.call_args.args[1]
        assert json.loads((folder/'manifest.json').read_text())['Version']=='1.0.0'
        print('UNIMOD_V041_UPDATES_REVIEW_GUI_OK')
    finally:
        app.destroy()
