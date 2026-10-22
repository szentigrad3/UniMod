import tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import unimod

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name);self.game={'name':'Fixture','kind':'smapi','root':str(self.base/'Game')}
        self.mods=unimod.mod_root(self.game);self.mods.mkdir(parents=True)
        self.patches=[patch.object(unimod,'APP',self.base/'config'),patch.object(unimod,'INSTALL_RECEIPTS',self.base/'receipts.json')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.dep=self.pkg('Core','1.0.0',[])
        self.target=self.pkg('Addon','2.0.0',['Maker-Core-1.0.0'])
    def pkg(self,name,ver,deps):
        return {'full_name':'Maker-'+name,'owner':'Maker','name':name,'version':ver,'dependencies':deps,'url':'https://thunderstore.io/', 'download_url':'https://thunderstore.io/package/download/Maker/'+name+'/'+ver+'/'}
    def fetch(self,url,path):
        name=url.split('/')[-3]
        with zipfile.ZipFile(path,'w') as z:z.writestr(name+'/manifest.json','{"Name":"'+name+'","UniqueID":"Maker.'+name+'","Version":"1.0"}')
    def test_success(self):
        receipts=unimod.thunderstore_install_transaction(self.game,self.target,[self.dep],self.fetch)
        self.assertEqual(len(receipts),2)
        self.assertTrue((self.mods/'Core'/'manifest.json').exists())
        self.assertTrue((self.mods/'Addon'/'manifest.json').exists())
    def test_missing_version_prevents_changes(self):
        bad=self.pkg('Core','2.0.0',[])
        with self.assertRaises(ValueError):unimod.thunderstore_install_transaction(self.game,self.target,[bad],self.fetch)
        self.assertEqual(list(self.mods.iterdir()),[])
    def test_duplicate_across_downloads(self):
        def fetch_duplicate(url,path):
            name=url.split('/')[-3]
            with zipfile.ZipFile(path,'w') as z:z.writestr(name+'/manifest.json','{"Name":"'+name+'","UniqueID":"Same.Id"}')
        with self.assertRaises(ValueError):unimod.thunderstore_install_transaction(self.game,self.target,[self.dep],fetch_duplicate)
        self.assertEqual(list(self.mods.iterdir()),[])
    def test_rollback_on_second_install_error(self):
        original=unimod.install_zip
        n=[0]
        def break_second(game,archive):
            n[0]+=1
            if n[0]==2:raise RuntimeError('injected failure')
            return original(game,archive)
        with patch.object(unimod,'install_zip',side_effect=break_second):
            with self.assertRaises(RuntimeError):unimod.thunderstore_install_transaction(self.game,self.target,[self.dep],self.fetch)
        self.assertEqual(list(self.mods.iterdir()),[])
        self.assertEqual(unimod.read_receipts(),[])
        self.assertTrue(list((self.base/'config'/'recovery').rglob('manifest.json')))
if __name__=='__main__':unittest.main()
