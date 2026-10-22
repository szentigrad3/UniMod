"""Mod-state cell is actionable; family headers are not actionable."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import unimod
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);g=root/'Stardew Valley';mods=g/'Mods';mods.mkdir(parents=True)
    for i in range(3):
        p=mods/f'Example{i}';p.mkdir()
        (p/'manifest.json').write_text(json.dumps({'Name':f'Mod {i}', 'UniqueID':f'example.mod{i}','Version':'1.0.0','Author':'Author'}))
    with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'source.json'), patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(g),'kind':'smapi'}]})
        app=unimod.App();app.update()
        first=app.tree.get_children('')[0];app.tree.see(first);app.update()
        bounds=app.tree.bbox(first,'status')
        assert bounds,bounds
        x,y,w,h=bounds
        # The handler uses the same event fields as a physical click.
        app.installed_status_click(SimpleNamespace(x=x+w//2,y=y+h//2))
        app.update()
        assert (g/'.unimod-disabled'/'Example0').exists(), list((g/'.unimod-disabled').glob('*'))
        assert app.tree.item(app.tree.get_children('')[0],'values')[1] in ('○  Off','●  On')
        app.destroy()
print('UNIMOD_V032_STATUS_TOGGLE_OK')
