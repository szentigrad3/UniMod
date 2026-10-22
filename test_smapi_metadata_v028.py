"""The installed mod folders are real, including those not indexed by the old parser."""
import tempfile, unittest, json
from pathlib import Path
import unimod

class SmapiFlexibleManifests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.mods=Path(self.temp.name)/'Stardew Valley'/'Mods'; self.mods.mkdir(parents=True)
        self.game={'name':'Stardew Valley','root':str(self.mods.parent),'kind':'smapi'}
    def make(self,name,data,filename='manifest.json'):
        p=self.mods/name;p.mkdir(parents=True)
        if data is not None:(p/filename).write_text(data,encoding='utf8')
        return p
    def test_comments_trailing_comma(self):
        self.make('SpaceCore','''// JSON with comments accepted by SMAPI\n{ "Name": "SpaceCore", "UniqueID": "spacechase0.SpaceCore", "Version": "1.28.0", }''')
        mods=unimod.items(self.game)
        self.assertEqual(len(mods),1);self.assertEqual(mods[0]['uid'],'spacechase0.SpaceCore')
    def test_unquoted_keys_single_quotes(self):
        self.make('StarMod',"{ Name: 'Fancy Mod', UniqueID: 'test.Fancy', Version: '2.0', }")
        self.assertEqual(unimod.items(self.game)[0]['name'],'Fancy Mod')
    def test_case_insensitive_filename_and_keys(self):
        self.make('NamedMod','{ "uniqueId": "test.case", "NAME": "Caseworks" }','MANIFEST.JSON')
        self.assertEqual(unimod.items(self.game)[0]['name'],'Caseworks')
    def test_bom(self):
        p=self.make('BOM',None);(p/'manifest.json').write_bytes(b'\xef\xbb\xbf'+json.dumps({'UniqueID':'test.bom'}).encode())
        self.assertEqual(unimod.items(self.game)[0]['uid'],'test.bom')
    def test_still_show_unindexed_mod_folder_without_discrediting(self):
        self.make('ManualMod',None)
        self.assertEqual(len(unimod.items(self.game)),0)
        groups=unimod.mod_packages(self.game)
        self.assertEqual(len(groups),1)
        self.assertIn('Installed mod folder',groups[0]['kind'])
        self.assertTrue(groups[0]['is_folder_only'])
        self.assertEqual(unimod.existing_mod_health(self.game)['folders'],1)
    def test_manifest_parse_error_does_not_hide_folder(self):
        self.make('NeedsIndex','{THIS IS BROKEN')
        groups=unimod.mod_packages(self.game)
        self.assertEqual(len(groups),1);self.assertIn('manifest unreadable',groups[0]['kind'])
    def test_url_comment_not_stripped(self):
        self.make('DownloadMod','{ "Name":"Url", "UniqueID":"test.url", "UpdateKeys":["Nexus:100"], "Description":"https://example.com/mod", }')
        self.assertEqual(unimod.items(self.game)[0]['uid'],'test.url')
    def test_all_real_folders_are_visible(self):
        for i in range(29):
            data=('{"UniqueID":"test.mod%d",}'%i) if i<11 else None
            self.make(f'Mod{i:02d}',data)
        groups=unimod.mod_packages(self.game)
        self.assertEqual(len(groups),29)
        self.assertEqual(len(unimod.items(self.game)),11)
        self.assertEqual(unimod.existing_mod_health(self.game)['folders'],29)
    def test_unreadable_metadata_not_allowed_as_installer_match(self):
        self.make('SpaceCore','{invalid}')
        self.assertFalse(unimod.items(self.game))

if __name__=='__main__':unittest.main()
