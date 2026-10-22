"""No-archive Nexus hint fallback: search assistance, never source proof."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bepinex_search_hints as hints
import unimod

class HintsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.gk=self.root/'Graveyard Keeper';self.plugins=self.gk/'BepInEx/plugins';self.plugins.mkdir(parents=True)
        self.dll=self.plugins/'LongerDays.dll';self.dll.write_bytes(os.urandom(1000))
        self.game={'name':'Graveyard Keeper','kind':'bepinex','root':str(self.gk)}
        self.mod=unimod.discover_bepinex(self.plugins,True)[0]
        self.patch=patch.object(unimod,'SOURCE_OVERRIDES',self.root/'links.json');self.patch.start();self.addCleanup(self.patch.stop)

    def preview(self,mods=None):
        return hints.preview_search_hints(self.game,[self.mod] if mods is None else mods,
            known_source=lambda g,m:bool(unimod.reconcile_source(g,m).get('url')),
            identity=unimod.source_identity)

    def test_no_archive_needed_pascal_case(self):
        row=self.preview()[0]
        self.assertEqual(row['query'],'Longer Days')
        self.assertEqual(row['status'],'Search ready')
        self.assertEqual(row['game_domain'],'graveyardkeeper')
        self.assertFalse(unimod.SOURCE_OVERRIDES.exists())
        self.assertEqual(hints.validate_search_hint(self.game,row,identity=unimod.source_identity),'Longer Days')

    def test_gk2_game_scope(self):
        self.game['name']='Graveyard Keeper 2'
        row=self.preview()[0]
        self.assertEqual(row['game_domain'],'graveyardkeeper2')
        other=dict(self.game,name='Graveyard Keeper')
        with self.assertRaisesRegex(ValueError,'Game selection changed'):
            hints.validate_search_hint(other,row)

    def test_manifest_hint_preferred(self):
        (self.plugins/'manifest.json').write_text('{"name":"Longer Day Cycles","website_url":"https://attacker.example"}')
        self.assertEqual(self.preview()[0]['query'],'Longer Day Cycles')
        self.assertFalse(unimod.SOURCE_OVERRIDES.exists())

    def test_nested_toml_hint(self):
        pkg=self.plugins/'A';pkg.mkdir()
        dll=pkg/'unrelated.dll';dll.write_bytes(os.urandom(1000))
        (pkg/'thunderstore.toml').write_text('[package]\nname = "Expanded Crafting"\n')
        row=next(r for r in self.preview(unimod.discover_bepinex(self.plugins,True)) if r['mod']['path']==str(dll))
        self.assertEqual(row['query'],'Expanded Crafting')

    def test_nested_toml_hint_python_310_fallback(self):
        """Python 3.10 uses the tomli backport when tomllib is unavailable."""
        import sys
        from types import SimpleNamespace
        pkg=self.plugins/'Python310';pkg.mkdir()
        dll=pkg/'fallback.dll';dll.write_bytes(os.urandom(1000))
        (pkg/'thunderstore.toml').write_text('[package]\nname = "Backport Test"\n')
        fake_tomli=SimpleNamespace(loads=lambda content: {'package': {'name': 'Backport Test'}})
        with patch.dict(sys.modules, {'tomllib': None, 'tomli': fake_tomli}):
            row=next(r for r in self.preview(unimod.discover_bepinex(self.plugins, True))
                     if r['mod']['path']==str(dll))
        self.assertEqual(row['query'], 'Backport Test')

    def test_ignore_symlinked_manifest(self):
        external=self.root/'spoof.json';external.write_text('{"name":"Spoofed Nexus Identity"}')
        (self.plugins/'manifest.json').symlink_to(external)
        self.assertEqual(self.preview()[0]['query'],'Longer Days')

    def test_no_tracking_filenames_or_names_with_markup(self):
        self.assertEqual(hints.readable_title('https://fake.example/a'), '')
        self.assertEqual(hints.readable_title('Assembly'), '')
        self.assertEqual(hints.readable_title('LongerDays.dll'), 'Longer Days')
        self.assertEqual(hints.readable_title('abc\\def'), '')
        self.assertEqual(hints.readable_title('X'*210), '')

    def test_oversized_manifest_ignored(self):
        (self.plugins/'manifest.json').write_bytes(b'Z'*70000)
        self.assertEqual(self.preview()[0]['query'],'Longer Days')

    def test_already_linked_not_suggested(self):
        unimod.save_source_assignment(self.game,self.mod,'https://www.nexusmods.com/graveyardkeeper/mods/10')
        row=self.preview()[0]
        self.assertEqual(row['status'],'Already linked')
        with self.assertRaises(ValueError):hints.validate_search_hint(self.game,row)

    def test_changed_dll_blocks_search(self):
        row=self.preview()[0]
        self.dll.write_bytes(os.urandom(1500))
        with self.assertRaisesRegex(ValueError,'changed'):
            hints.validate_search_hint(self.game,row)

    def test_missing_symlinked_dll_not_used(self):
        row=self.preview()[0]
        dest=self.root/'outside.dll';dest.write_bytes(b'outside')
        self.dll.unlink();self.dll.symlink_to(dest)
        self.assertEqual(self.preview()[0]['status'],'Not readable')
        with self.assertRaises(ValueError):hints.validate_search_hint(self.game,row)

    def test_outside_plugins_refused_even_inside_game(self):
        extra=self.gk/'managed'/'Other.dll';extra.parent.mkdir();extra.write_bytes(b'mod')
        mod=dict(self.mod,path=str(extra))
        self.assertEqual(self.preview([mod])[0]['status'],'Not readable')

    def test_duplicate_hash_ambiguous(self):
        (self.plugins/'Duplicate.dll').write_bytes(self.dll.read_bytes())
        self.assertEqual([r['status'] for r in self.preview(unimod.discover_bepinex(self.plugins,True))],['Ambiguous DLL','Ambiguous DLL'])

    def test_game_not_supported(self):
        self.game['name']='Stardew Valley'
        with self.assertRaises(ValueError):self.preview()

    def test_plugin_folder_symlink_blocks(self):
        self.plugins.rename(self.gk/'original_plugins')
        self.plugins.symlink_to(self.gk/'original_plugins',target_is_directory=True)
        with self.assertRaises(ValueError):self.preview()

if __name__=='__main__':unittest.main()
