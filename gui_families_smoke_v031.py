"""Validate groups, per-component selection, buttons and filtered view in Tk."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import unimod
with tempfile.TemporaryDirectory() as td:
    root=Path(td);game=root/'Stardew Valley';mods=game/'Mods';mods.mkdir(parents=True)
    entries=[('SVE CP','Stardew Valley Expanded','example.svecp'),
             ('SVE Code','Stardew Valley Expanded','example.svecode'),
             ('SVE FTM','Stardew Valley Expanded Farm Type Manager','example.sveftm'),
             ('RSV CP','Ridgeside Village [Content Patcher component]','example.rsvcp'),
             ('RSV SMAPI','Ridgeside Village [SMAPI component]','example.rsvcode'),
             ('Automate','Automate','pathoschild.automate')]
    for folder,name,uid in entries:
        d=mods/folder;d.mkdir()
        (d/'manifest.json').write_text(json.dumps({'Name':name,'UniqueID':uid,'Version':'1.0.0'}))
    with patch.object(unimod,'CONFIG',root/'config.json'),patch.object(unimod,'SOURCE_OVERRIDES',root/'overrides.json'),patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','root':str(game),'kind':'smapi'}]})
        app=unimod.App();app.update()
        app.show_page('Installed Mods');app.update()
        roots=app.tree.get_children('')
        assert len(roots)==3,(roots,len(roots))
        groups=list(app.family_rows)
        assert len(groups)==2,app.family_rows
        assert len(app.tree.get_children(groups[0])) in (2,3)
        assert sum(len(app.tree.get_children(g)) for g in groups)==5
        app.tree.selection_set(groups[0]);app.describe_selected()
        assert 'components' in app.detail_state.get()
        assert all(b.instate(['disabled']) for b in app.mod_action_buttons)
        child=app.tree.get_children(groups[0])[0]
        app.tree.selection_set(child);app.describe_selected()
        assert app.picked() is not None
        assert app.detail_uid.get()!='—'
        assert all(not b.instate(['disabled']) for b in app.mod_action_buttons)
        # Search surfaces children without hiding their family.
        app.query.set('Farm Type Manager');app.update()
        assert len(app.tree.get_children(''))==1
        g=app.tree.get_children('')[0]
        assert 'Stardew Valley Expanded' in app.tree.item(g,'text')
        assert len(app.tree.get_children(g))==1
        app.query.set('');app.update()
        app.group_components.set(False);app.fill_mods();app.update()
        assert len(app.tree.get_children(''))==6
        assert not app.family_rows
        app.destroy()
print('UNIMOD_V031_FAMILY_GUI_OK')
