"""AIO source links: exact-ID protection and manual approval for component groups."""
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import unimod

class AioLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.game={'name':'Stardew Valley','kind':'smapi','root':str(self.base/'Stardew Valley')}
        self.mods=[]
        p=patch.object(unimod,'SOURCE_OVERRIDES',self.base/'source-overrides.json')
        p.start();self.addCleanup(p.stop)
    def add(self,name,uid,keys=None):
        obj={'name':name,'uid':uid,'version':'1.0','path':str(self.base/(name+' '+uid)),
             'update_keys':keys or [], 'enabled':True}
        self.mods.append(obj);return obj
    def test_source_catalogue_18_valid_user_pages(self):
        catalogue=unimod.load_stardew_aio_links()
        self.assertEqual(len(catalogue),18)
        self.assertEqual(catalogue['better crafting']['mod_id'],'11115')
        self.assertEqual(catalogue['time speed']['mod_id'],'169') if 'time speed' in catalogue else self.assertEqual(catalogue['timespeed']['mod_id'],'169')
        self.assertEqual(catalogue['east scarp remastered']['mod_id'],'5787')
    def test_better_crafting_missing_id_is_exact_match(self):
        m=self.add('Better Crafting','mod.BetterCrafting')
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[0]['status'],'Ready — exact name')
        self.assertEqual(unimod.apply_aio_nexus_links(self.game,p,[0]),1)
        self.assertEqual(unimod.nexus_reference(self.game,m)['mod_id'],'11115')
    def test_existing_correct_id_unchanged(self):
        self.add('Better Crafting','mod.BetterCrafting',['Nexus:11115'])
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[0]['status'],'Already linked')
        with self.assertRaises(ValueError):unimod.apply_aio_nexus_links(self.game,p,[0])
    def test_existing_other_id_rejected(self):
        m=self.add('Better Crafting','mod.BetterCrafting',['Nexus:99999'])
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[0]['status'],'Different Nexus ID — skip')
        with self.assertRaises(ValueError):unimod.apply_aio_nexus_links(self.game,p,[0])
        self.assertEqual(unimod.nexus_reference(self.game,m)['mod_id'],'99999')
    def test_related_components_need_review(self):
        self.add('East Scarp: C#','mod.eastscarp')
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[0]['status'],'Review related component')
        self.assertEqual(p[0]['candidate']['mod_id'],'5787')
    def test_not_fuzzy_name_guess(self):
        self.add('East Scarp New NPC Unrelated','mod.es.npc')
        # Prefixes deliberately exposed for human review, never autoselect.
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[0]['status'],'Review related component')
        self.assertFalse(p[0]['status'].startswith('Ready'))
        self.add('Integrated Minecarts','mod.mines')
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[-1]['status'],'No supplied link')
    def test_duplicate_uid_prevents_mass_assignment(self):
        self.add('Better Crafting','mod.same')
        self.add('Better Crafting','mod.same')
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertTrue(all(x['status']=='Duplicate SMAPI ID — skip' for x in p))
    def test_atomic_source_assignment_and_refresh_validation(self):
        a=self.add('Better Crafting','mod.craft')
        b=self.add('TimeSpeed','mod.time')
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual([x['status'] for x in p],['Ready — exact name']*2)
        # One stale assignment should make the entire batch fail.
        unimod.save_source_assignment(self.game,b,'https://www.nexusmods.com/stardewvalley/mods/100')
        with self.assertRaises(ValueError):unimod.apply_aio_nexus_links(self.game,p,[0,1])
        self.assertIsNone(unimod.nexus_reference(self.game,a))
        self.assertEqual(unimod.nexus_reference(self.game,b)['mod_id'],'100')
    def test_reject_other_game_and_malicious_links(self):
        self.add('Better Crafting','mod.craft')
        with self.assertRaises(ValueError):unimod.aio_nexus_preview({'name':'Graveyard Keeper 2','kind':'bepinex','root':str(self.base)},self.mods)
        payload={'links':[{'name':'Bad','url':'https://evil.example/stardewvalley/mods/123'}]}
        bad=self.base/'bad.json';bad.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):unimod.load_stardew_aio_links(bad)
    def test_game_files_untouched(self):
        mod=self.add('UI Info Suite 2','mod.ui')
        folder=Path(mod['path']);folder.mkdir(parents=True)
        manifest=folder/'manifest.json';manifest.write_text('{"Name":"UI Info Suite 2","UniqueID":"mod.ui"}')
        p=unimod.aio_nexus_preview(self.game,self.mods)
        self.assertEqual(p[0]['status'],'Ready — exact name')
        unimod.apply_aio_nexus_links(self.game,p,[0])
        self.assertEqual(manifest.read_text(),'{"Name":"UI Info Suite 2","UniqueID":"mod.ui"}')

if __name__=='__main__':unittest.main()
