"""Generate preview on synthetic SMAPI data, never uses real games."""
import os,tempfile,json
from pathlib import Path
from unittest.mock import patch
import unimod
from PIL import ImageGrab
with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);game=root/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
  examples=['Automate','Better Crafting','Content Patcher','Console Commands','Generic Mod Config Menu','Lookup Anything','SpaceCore','Stardew Valley Expanded','NPC Map Locations','Ridgeside Village','TimeSpeed','UI Info Suite 2','Farm Type Manager','East Scarp','Custom Companions','Mapping Extensions and Extra Properties','Save Backup','Better Ranching','Chests Anywhere','Tractor Mod','Luministeria','Ridgeside Village [Content Patcher component]','Ridgeside Village [SMAPI component]','Stardew Valley Expanded','Stardew Valley Expanded Farm Type Manager','More Giant Crops','Machine Progression','Dynamic Night Time','Expanded Preconditions Utility']
  for i,name in enumerate(examples):
    d=mods/f'Mod{i:02}';d.mkdir();(d/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':f'author.mod{i:02}', 'Version':f'{1+i%3}.{i%15}.0','Author':['Pathoschild','Spacechase0','OdinPlus','TheModTeam'][i%4], 'UpdateKeys':['Nexus:12345'] if i%2 else []}))
  with patch.object(unimod,'CONFIG',root/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'sources.json'),patch.object(unimod,'steam_roots',return_value=[]):
    unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
    app=unimod.App();app.geometry('1510x940+0+0');app.update();app.show_page('Installed Mods');app.update()
    # clear transient tooltip and use a demo header-only background
    ImageGrab.grab(bbox=(0,0,1510,940)).save('/mnt/data/UniMod-0.32-UI-preview.png')
    app.destroy()
print('PREVIEW_OK')
