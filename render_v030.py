import json,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import ImageGrab
import unimod
with tempfile.TemporaryDirectory() as tmp:
    home=Path(tmp); game=home/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    for i in range(29):
        folder=mods/f'Mod{i:02}';folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({'Name':(['Content Patcher','Stardew Valley Expanded','SpaceCore','East Scarp','Generic Mod Config Menu'][i] if i<5 else f'Example Mod {i+1}'),'UniqueID':f'example.mod{i}','Version':'1.2.0','UpdateKeys':['Nexus:123'] if i%3==0 else []}))
    with patch.object(unimod,'CONFIG',home/'games.json'),patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','kind':'smapi','root':str(game)}]})
        app=unimod.App();app.geometry('1360x820+0+0');app.update();app.after(350,app.quit);app.mainloop()
        app.update();ImageGrab.grab(bbox=(0,0,1360,820)).save('/mnt/data/UniMod-0.30-Workspace-preview.png')
        app.show_page('Installed Mods');app.update();app.after(250,app.quit);app.mainloop()
        app.update();ImageGrab.grab(bbox=(0,0,1360,820)).save('/mnt/data/UniMod-0.30-Installed-Mods-preview.png')
        app.destroy()
