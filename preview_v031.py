import json,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import ImageGrab
import unimod
with tempfile.TemporaryDirectory() as td:
    base=Path(td);game=base/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    entries=[
    ('Automate','Automate','pathoschild.automate'),
    ('BetterCrafting','Better Crafting','leclair.bettercrafting'),
    ('CP','Content Patcher','pathoschild.contentpatcher'),
    ('SVE Code','Stardew Valley Expanded','flashshifter.sve.code'),
    ('SVE Content Pack','Stardew Valley Expanded','flashshifter.sve.cp'),
    ('SVE FTM','Stardew Valley Expanded Farm Type Manager','flashshifter.sve.ftm'),
    ('RSV Core','Ridgeside Village [SMAPI component]','rsv.core'),
    ('RSV CP','Ridgeside Village [Content Patcher component]','rsv.cp'),
    ('RSV FTM','Ridgeside Village [Farm Type Manager component]','rsv.ftm'),
    ('RSV Companions','Ridgeside Village [Custom Companions component]','rsv.companions'),
    ('SpaceCore','SpaceCore','spacechase0.spacecore'),
    ('UI Info Suite 2','UI Info Suite 2','uiinfosuite2.mod'),
    ('TimeSpeed','TimeSpeed','timespeed.mod')]
    for folder,name,uid in entries:
        d=mods/folder;d.mkdir();(d/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':uid,'Version':'1.2.0'}))
    with patch.object(unimod,'CONFIG',base/'games.json'),patch.object(unimod,'SOURCE_OVERRIDES',base/'overrides.json'),patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App();app.geometry('1460x920+0+0');app.show_page('Installed Mods')
        app.update();app.after(350,app.quit);app.mainloop();app.update()
        ImageGrab.grab(bbox=(0,0,1460,920)).save('/mnt/data/UniMod-0.31-Grouped-Mods-preview.png')
        app.destroy()
print('PREVIEW_SAVED')
