import tempfile, json, unittest
from pathlib import Path
import unimod

class LocalDependenciesTests(unittest.TestCase):
    def test_detect_package_metadata_and_versions(self):
        with tempfile.TemporaryDirectory() as td:
            game={'root':td,'kind':'bepinex'}
            folder=unimod.mod_root(game)/'Nested'/'TestMod';folder.mkdir(parents=True)
            (folder/'manifest.json').write_text(json.dumps({'name':'TestMod','owner':'Creator','version_number':'1.2.3'}))
            local=unimod.installed_thunderstore_packages(game)
            self.assertIn('creator-testmod',local)
            pkg={'dependencies':['Creator-TestMod-1.2.3','Creator-Other-2.0.0']}
            statuses=[x['status'] for x in unimod.dependency_plan(pkg,[],local_packages=local)]
            self.assertEqual(statuses,['installed locally','missing from catalogue'])
    def test_version_mismatch_and_smapi_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            game={'root':td,'kind':'smapi'};folder=unimod.mod_root(game)/'Pack';folder.mkdir(parents=True)
            (folder/'manifest.json').write_text(json.dumps({'Name':'Test','UniqueID':'Mod.Author','Version':'1.2.3','name':'Test','owner':'Creator','version':'1.2.3'}))
            self.assertEqual(unimod.installed_thunderstore_packages(game),{})
        local={'creator-testmod':{'version':'1.2.3'}}
        plan=unimod.dependency_plan({'dependencies':['Creator-TestMod-2.0.0']},[],local_packages=local)
        self.assertEqual(plan[0]['status'],'local version differs')
    def test_disabled_not_counted(self):
        with tempfile.TemporaryDirectory() as td:
            game={'root':td,'kind':'bepinex'};folder=unimod.disabled_root(game)/'Old';folder.mkdir(parents=True)
            (folder/'manifest.json').write_text(json.dumps({'name':'Old','owner':'Maker','version':'1.0.0'}))
            self.assertEqual(unimod.installed_thunderstore_packages(game),{})

if __name__=='__main__':unittest.main()
