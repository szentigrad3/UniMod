"""GUI smoke test: virtual display required (xvfb-run -a python gui_thunderstore_smoke_v023.py)."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unimod

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)/'ExampleGame'
    mod=root/'BepInEx/plugins/TestPlugin';mod.mkdir(parents=True)
    (mod/'plugin.dll').write_bytes(b'mock')
    (mod/'manifest.json').write_text(json.dumps({'name':'CoolMod','author':'Tester',
        'version_number':'1.0.0','website_url':'https://thunderstore.io/c/valheim/p/Tester/CoolMod/'}))
    game={'root':str(root),'kind':'bepinex','name':'Example Game'}
    with patch.object(unimod,'cfg_load',return_value={'games':[game]}), \
         patch.object(unimod,'cfg_save',return_value=None), \
         patch.object(unimod,'detect_games',return_value=[]), \
         patch.object(unimod,'inventory_update',return_value=None):
        app=unimod.App()
        app.update_idletasks()
        app.ts_community.set('valheim')
        app.ts_loaded([{'owner':'Tester','name':'CoolMod','version':'2.0.0','url':
            'https://thunderstore.io/c/valheim/p/Tester/CoolMod/','description':'Test','downloads':1}],None,'valheim')
        app.ts_compare_local()
        assert len(app.ts_local_rows)==1,app.ts_local_rows
        assert app.ts_local_rows[0]['status']=='Update available',app.ts_local_rows
        assert len(app.ts_local_tree.get_children())==1
        app.update_idletasks();app.destroy()
print('UNIMOD_V023_GUI_OK')
