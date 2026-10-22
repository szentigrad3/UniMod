"""Nexus-linked/unlinked GUI and owner-declared origin control."""
import tempfile, json
from pathlib import Path
from unittest.mock import patch
import unimod
with tempfile.TemporaryDirectory() as tmp:
    home=Path(tmp)
    root=home/'Stardew Valley';mods=root/'Mods';mods.mkdir(parents=True)
    for i in range(6):
        d=mods/f'Folder{i:02}';d.mkdir()
        (d/'manifest.json').write_text(json.dumps({'Name':f'Mod {i}', 'UniqueID':f'example.mod{i}',
                     'Version':'1.0.0','UpdateKeys':[f'Nexus:{100+i}'] if i<2 else []}))
    with patch.object(unimod,'CONFIG',home/'games.json'),patch.object(unimod,'COLLECTION_SOURCES',home/'origins.json'),patch.object(unimod,'SOURCE_OVERRIDES',home/'source-overrides.json'), patch.object(unimod,'steam_roots',return_value=[]):
        unimod.cfg_save({'games':[{'name':'Stardew Valley','kind':'smapi','root':str(root)}]})
        app=unimod.App();app.update()
        app.show_page('Nexus Updates');app.update()
        assert len(app.nexus_display_rows)==6
        assert len(app.nexus_eligible())==2
        statuses=[app.nexus_tree.item(item,'values')[3] for item in app.nexus_tree.get_children()]
        assert statuses.count('No exact Nexus ID')==4,statuses
        app.nexus_all_origin.set(True);app.nexus_collection_toggle();app.update()
        statuses=[app.nexus_tree.item(item,'values')[3] for item in app.nexus_tree.get_children()]
        assert statuses.count('Link required')==4,statuses
        assert unimod.nexus_collection_origin(app.current())
        # Assigning the exact page identity is independent of the provenance flag.
        new=app.nexus_display_rows[2]
        unimod.save_source_assignment(app.current(),new,'https://www.nexusmods.com/stardewvalley/mods/1029')
        app.nexus_refresh();app.update()
        assert len(app.nexus_eligible())==3
        assert len(app.nexus_tree.get_children())==6
        app.destroy()
print('UNIMOD_V033_NEXUS_GUI_OK')
