import unittest, tempfile, json, zipfile
from pathlib import Path
from source_provenance import read_mo2_sidecar
from unimod import discover_nexus_download_evidence, simple_source_preview

class MO2SourceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.game={'name':'Stardew Valley','kind':'smapi','nexus_domain':'stardewvalley','root':str(self.root)}
        self.mod={'name':'Example Component','uid':'Sample.Creator.Mod','version':'1.0','path':str(self.root/'installed'),'update_keys':[],'enabled':True}
        self.zip=self.root/'Example-1.0.zip'
        with zipfile.ZipFile(self.zip,'w') as z:
            z.writestr('Example/manifest.json',json.dumps({'Name':'Example','UniqueID':self.mod['uid'],'Version':'1.0'}))
    def sidecar(self, content):
        (self.root/(self.zip.name+'.meta')).write_text(content,encoding='utf-8')
    def test_exact_sidecar_proposes_page(self):
        self.sidecar('[General]\ngameName=Stardew Valley\nmodID=3753\nfileID=91234\n')
        records=discover_nexus_download_evidence(self.game,[self.mod],self.root)
        self.assertEqual({x['mod_id'] for x in records[self.mod['uid'].lower()]},{'3753'})
        p=simple_source_preview(self.game,[self.mod],self.root)
        self.assertEqual(p[0]['status'],'Review candidate')
        self.assertIn('3753',p[0]['candidate']['url'])
    def test_wrong_game_rejected(self):
        self.sidecar('[General]\ngameName=Skyrim\nmodID=3753\nfileID=9\n')
        self.assertFalse(discover_nexus_download_evidence(self.game,[self.mod],self.root))
    def test_file_id_required(self):
        self.sidecar('[General]\ngameName=Stardew Valley\nmodID=3753\n')
        self.assertIsNone(read_mo2_sidecar(self.zip))
    def test_symlink_meta_rejected(self):
        true=self.root/'elsewhere'
        true.write_text('[General]\ngameName=Stardew Valley\nmodID=3753\nfileID=9\n')
        (self.root/(self.zip.name+'.meta')).symlink_to(true)
        self.assertIsNone(read_mo2_sidecar(self.zip))
    def test_conflicting_manifest_id_is_not_silent(self):
        with zipfile.ZipFile(self.zip,'w') as z:
            z.writestr('manifest.json',json.dumps({'UniqueID':self.mod['uid'],'UpdateKeys':['Nexus:1234']}))
        self.sidecar('[General]\ngameName=Stardew Valley\nmodID=3753\nfileID=9\n')
        r=simple_source_preview(self.game,[self.mod],self.root)
        self.assertEqual(r[0]['status'],'Conflicting archive hints')
    def test_multiple_components_map_to_one_archive_page(self):
        extra=dict(self.mod,name='Second Component',uid='Sample.Creator.Other',path=str(self.root/'other'))
        with zipfile.ZipFile(self.zip,'w') as z:
            for m in (self.mod,extra):
                z.writestr(m['uid']+'/manifest.json',json.dumps({'UniqueID':m['uid']}))
        self.sidecar('[General]\ngameName=StardewValley\nmodID=3753\nfileID=9\n')
        r=discover_nexus_download_evidence(self.game,[self.mod,extra],self.root)
        self.assertEqual(set(r),{self.mod['uid'].lower(),extra['uid'].lower()})
        self.assertTrue(all(x['mod_id']=='3753' for entries in r.values() for x in entries))
    def test_no_arbitrary_filename_without_manifest(self):
        other=dict(self.mod,uid='Not.The.Mod')
        self.sidecar('[General]\ngameName=Stardew Valley\nmodID=3753\nfileID=9\n')
        self.assertFalse(discover_nexus_download_evidence(self.game,[other],self.root))
    def test_file_name_hint_cannot_hide_sidecar_evidence(self):
        hints={'sample.creator.mod':[
            {'mod_id':'3753','url':'https://www.nexusmods.com/stardewvalley/mods/3753',
             'evidence':'MO2 archive metadata (file #9)','filename':'one.zip'},
            {'mod_id':'3753','url':'https://www.nexusmods.com/stardewvalley/mods/3753',
             'evidence':'ZIP filename hint — verify on Nexus','filename':'one.zip'}]}
        row=simple_source_preview(self.game,[self.mod],scan=hints)[0]
        self.assertEqual(row['status'],'Review candidate')
        self.assertIn('MO2',row['evidence'])
    def test_garbage_meta_fails_closed(self):
        self.sidecar('[General]\nmodID=3753\nfileID=9\ngameName=Stardew Valley\ngameName=Other\n')
        self.assertIsNone(read_mo2_sidecar(self.zip))
