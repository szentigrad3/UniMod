"""v0.35 local-first source discovery and conservative, optional bulk save."""
import json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import unimod

class LocalSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.download=self.base/'Downloads';self.download.mkdir()
        self.root=self.base/'Stardew Valley';(self.root/'Mods').mkdir(parents=True)
        self.game={'name':'Stardew Valley','kind':'smapi','root':str(self.root)}
        self.mods=[]
        self.sourcepatch=patch.object(unimod,'SOURCE_OVERRIDES',self.base/'sources.json')
        self.sourcepatch.start();self.addCleanup(self.sourcepatch.stop)
        self.originpatch=patch.object(unimod,'COLLECTION_SOURCES',self.base/'origin.json')
        self.originpatch.start();self.addCleanup(self.originpatch.stop)

    def add_mod(self,name,uid,keys=None):
        folder=self.root/'Mods'/name.replace(' ','_');folder.mkdir()
        data={'UniqueID':uid,'Name':name,'Version':'1.0','UpdateKeys':keys or []}
        (folder/'manifest.json').write_text(json.dumps(data))
        mod={'uid':uid,'name':name,'version':'1.0','path':str(folder),'relative':folder.name,'enabled':True,'update_keys':keys or []}
        self.mods.append(mod);return mod

    def archive(self,name,entries):
        file=self.download/name
        with zipfile.ZipFile(file,'w') as z:
            for folder,data in entries:
                z.writestr(folder+'/manifest.json',json.dumps(data))
        return file

    def test_no_downloads_or_key_required(self):
        self.add_mod('Missing','demo.missing')
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual(rows[0]['status'],'Needs source')
        self.assertIsNone(rows[0]['candidate'])

    def test_exact_metadata_is_identified_without_network(self):
        self.add_mod('Known','demo.known',['Nexus:234'])
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual(rows[0]['status'],'Already identified')
        self.assertEqual(rows[0]['candidate']['mod_id'],'234')

    def test_download_zip_single_uid_review_and_save(self):
        mod=self.add_mod('Better Crafting','demo.crafting')
        self.archive('Better Crafting-11115-2-18-0-123456.zip', [('Craft',{'UniqueID':mod['uid'],'Name':'Better Crafting'})])
        hits=unimod.discover_nexus_download_evidence(self.game,self.mods,self.download)
        rows=unimod.simple_source_preview(self.game,self.mods,scan=hits)
        self.assertEqual(rows[0]['status'],'Review candidate')
        self.assertEqual(rows[0]['candidate']['mod_id'],'11115')
        self.assertIn('verify',rows[0]['evidence'])
        self.assertEqual(unimod.apply_simple_source_matches(self.game,rows,[0]),1)
        self.assertEqual(unimod.nexus_reference(self.game,mod)['mod_id'],'11115')
        self.assertEqual(json.loads((self.root/'Mods'/'Better_Crafting'/'manifest.json').read_text())['UniqueID'],'demo.crafting')

    def test_multiple_components_from_one_zip(self):
        self.add_mod('A','demo.a');self.add_mod('B','demo.b')
        self.archive('Example-5555-1-2-0-12345.zip', [('A',{'UniqueID':'demo.a'}),('B',{'UniqueID':'demo.b'})])
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual([r['status'] for r in rows],['Review candidate','Review candidate'])
        self.assertEqual({r['candidate']['mod_id'] for r in rows},{'5555'})

    def test_archive_rename_does_not_autoguess(self):
        self.add_mod('A','demo.a')
        self.archive('modbundle.zip',[('A',{'UniqueID':'demo.a'})])
        self.assertEqual(unimod.simple_source_preview(self.game,self.mods,self.download)[0]['status'],'Needs source')

    def test_zip_manifest_nexus_key_is_candidate_even_with_generic_name(self):
        self.add_mod('A','demo.a')
        self.archive('modbundle.zip',[('A',{'uniqueid':'demo.a','updatekeys':['Nexus:90210']})])
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual(rows[0]['candidate']['mod_id'],'90210')
        self.assertEqual(rows[0]['status'],'Review candidate')

    def test_conflicting_candidates_stay_unassigned(self):
        self.add_mod('A','demo.a')
        for num in (1234,5678):self.archive(f'Mod-{num}-1-2-3-555.zip',[('A',{'UniqueID':'demo.a'})])
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual(rows[0]['status'],'Conflicting archive hints')
        with self.assertRaises(ValueError):unimod.apply_simple_source_matches(self.game,rows,[0])

    def test_existing_source_not_overwritten(self):
        self.add_mod('A','demo.a',['Nexus:1234'])
        self.archive('Mod-5678-1-2-3-555.zip',[('A',{'UniqueID':'demo.a'})])
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual(rows[0]['status'],'Already identified')
        with self.assertRaises(ValueError):unimod.apply_simple_source_matches(self.game,rows,[0])
        self.assertFalse(unimod.SOURCE_OVERRIDES.exists())

    def test_unsafe_zip_ignored_and_no_symlinks(self):
        self.add_mod('A','demo.a')
        file=self.download/'Evil-3333-1-2-3-555.zip'
        with zipfile.ZipFile(file,'w') as z:z.writestr('../A/manifest.json',json.dumps({'UniqueID':'demo.a'}))
        (self.download/'Link-1234-1-2-3-555.zip').symlink_to(file)
        self.assertEqual(unimod.simple_source_preview(self.game,self.mods,self.download)[0]['status'],'Needs source')

    def test_duplicate_uid_blocks_candidate(self):
        self.add_mod('A','same.uid');self.add_mod('B','same.uid')
        self.archive('Mod-5555-1-2-3-666.zip',[('A',{'UniqueID':'same.uid'})])
        rows=unimod.simple_source_preview(self.game,self.mods,self.download)
        self.assertEqual({r['status'] for r in rows},{'Duplicate installed ID'})

if __name__=='__main__':unittest.main()
