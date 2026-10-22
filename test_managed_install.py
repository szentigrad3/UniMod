import tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import unimod

class ManagedInstallTests(unittest.TestCase):
    def test_install_and_recover_does_not_delete(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); game={'root':str(root/'Game'),'name':'Fixture','kind':'smapi'}
            mods=unimod.mod_root(game);mods.mkdir(parents=True)
            (mods/'Existing').mkdir()
            (mods/'Existing'/'manifest.json').write_text('{"Name":"Existing"}')
            pkg={'name':'Example','full_name':'Maker-Example','version':'1.2.0', 'owner':'Maker',
                 'url':'https://thunderstore.io/c/test/p/Maker/Example/',
                 'download_url':'https://thunderstore.io/package/download/Maker/Example/1.2.0/',
                 'dependencies':['Maker-Core-1.0.0']}
            def fetch(_url,path):
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('Example/manifest.json','{"Name":"Example","UniqueID":"Maker.Example","Version":"1.2.0"}')
            with patch.object(unimod,'INSTALL_RECEIPTS',root/'receipts.json'),patch.object(unimod,'APP',root/'config'):
                receipt=unimod.thunderstore_install(game,pkg,fetch)
                self.assertTrue((mods/'Example'/'manifest.json').exists())
                self.assertTrue((mods/'Existing'/'manifest.json').exists())
                recovered=unimod.undo_thunderstore_install(receipt,game)
                self.assertEqual(len(recovered),1)
                self.assertTrue(Path(recovered[0]).exists())
                self.assertTrue((mods/'Existing'/'manifest.json').exists())
                self.assertFalse((mods/'Example').exists())
    def test_untrusted_download_host_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            game={'root':td,'kind':'smapi'}
            with self.assertRaises(ValueError):
                unimod.thunderstore_install(game,{'download_url':'https://evil.example/file.zip'})

if __name__=='__main__':unittest.main()
