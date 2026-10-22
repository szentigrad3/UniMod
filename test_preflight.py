import tempfile, unittest, zipfile
from pathlib import Path
import unimod

class PreflightTests(unittest.TestCase):
    def test_transitive_dependency_and_missing(self):
        a={"full_name":"Maker-A","version":"1.0.0","dependencies":["Maker-B-2.0.0"]}
        b={"full_name":"Maker-B","version":"2.0.0","dependencies":["Maker-C-1.0.0"]}
        result=unimod.dependency_plan(a,[a,b])
        self.assertEqual([x["status"] for x in result],["missing from catalogue","available"])
    def test_detects_existing_smapi_id(self):
        with tempfile.TemporaryDirectory() as td:
            game={"root":td,"kind":"smapi","name":"fixture"}
            dest=unimod.mod_root(game)/"Original"
            dest.mkdir(parents=True)
            (dest/"manifest.json").write_text('{"Name":"Old","UniqueID":"author.mod","Version":"1.0"}')
            archive=Path(td)/"new.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("New/manifest.json",'{"Name":"New","UniqueID":"Author.Mod","Version":"2.0"}')
            self.assertTrue(unimod.preflight_smapi_conflicts(game,archive))
    def test_accepts_distinct_id(self):
        with tempfile.TemporaryDirectory() as td:
            game={"root":td,"kind":"smapi","name":"fixture"}
            archive=Path(td)/"new.zip"
            with zipfile.ZipFile(archive,"w") as z:z.writestr("New/manifest.json",'{"UniqueID":"new.unique"}')
            self.assertEqual(unimod.preflight_smapi_conflicts(game,archive),[])

if __name__=="__main__":unittest.main()
