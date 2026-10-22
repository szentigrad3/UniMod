import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import unimod

class InstallArchiveSafety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game={'root':str(self.root/'game'),'kind':'smapi','name':'Stardew Valley'}
        self.mods=self.root/'game'/'Mods';self.mods.mkdir(parents=True)
    def zip(self,names):
        f=self.root/'download.zip'
        with zipfile.ZipFile(f,'w') as z:
            for directory,uid in names:
                z.writestr(f'{directory}/manifest.json',json.dumps({'Name':directory,'UniqueID':uid,'Version':'1.0.0'}))
        return f
    def test_refuses_existing_id_even_if_other_folder(self):
        existing=self.mods/'A'
        existing.mkdir()
        (existing/'manifest.json').write_text(json.dumps({'UniqueID':'Author.Mod','Version':'1.0.0'}))
        with self.assertRaisesRegex(ValueError,'Already installed'):
            unimod.install_zip(self.game,self.zip([('B','author.mod')]))
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()),['A'])
    def test_refuses_duplicate_ids_inside_archive(self):
        with self.assertRaisesRegex(ValueError,'Duplicate SMAPI'):
            unimod.install_zip(self.game,self.zip([('A','author.mod'),('B','AUTHOR.MOD')]))
        self.assertEqual(list(self.mods.iterdir()),[])
    def test_installs_independent_mods(self):
        names=unimod.install_zip(self.game,self.zip([('A','one.mod'),('B','two.mod')]))
        self.assertEqual(names,['A','B'])
        self.assertEqual(len(unimod.items(self.game)),2)
    def test_manifest_at_zip_root_uses_archive_name(self):
        archive=self.root/'Single-Mod-1.2.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('manifest.json',json.dumps({'Name':'Single','UniqueID':'single.mod','Version':'1.2.0'}))
        names=unimod.install_zip(self.game,archive)
        self.assertEqual(names,['Single-Mod-1.2'])
        self.assertTrue((self.mods/'Single-Mod-1.2'/'manifest.json').is_file())

    def test_name_collision_gets_different_directory(self):
        (self.mods/'Same').mkdir()
        names=unimod.install_zip(self.game,self.zip([('Same','one.mod')]))
        self.assertEqual(names,['Same-2'])

if __name__=='__main__':unittest.main()
