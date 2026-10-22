import unittest, tempfile, json
from pathlib import Path
from unittest.mock import patch
import unimod

class AutoSourcesTests(unittest.TestCase):
    def test_bepinex_metadata_url(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'Author-Mod'; p.mkdir()
            (p/'cool.dll').write_bytes(b'mock')
            (p/'manifest.json').write_text(json.dumps({'name':'Cool Mod','version_number':'1.2.3','website_url':'https://thunderstore.io/c/valheim/p/Author/CoolMod/'}))
            mods=unimod.discover_bepinex(Path(root),True)
            self.assertEqual(len(mods),1)
            self.assertEqual(unimod.metadata_source(mods[0])['site'],'Thunderstore')
            game={'root':root,'kind':'bepinex'}
            with patch.object(unimod,'SOURCE_OVERRIDES',Path(root)/'overrides.json'):
                rows=unimod.source_report(game,mods)
            self.assertEqual(rows[0]['match_type'],'Metadata')
            self.assertEqual(rows[0]['source'],'Thunderstore')
    def test_unsupported_metadata_rejected(self):
        self.assertIsNone(unimod.metadata_source({'website_url':'https://evil.example/path','update_keys':[]}))
    def test_smapi_nexus_url(self):
        mod={'uid':'author.mod','update_keys':['Nexus:12345']}
        self.assertEqual(unimod.metadata_source(mod)['url'],'https://www.nexusmods.com/stardewvalley/mods/12345')
    def test_manual_overrides_preferred(self):
        with tempfile.TemporaryDirectory() as root:
            game={'root':root,'kind':'smapi'}
            mod={'name':'Test','uid':'a.test','path':str(Path(root)/'Mods/Test'),'version':'1','enabled':True,'update_keys':['Nexus:100']}
            with patch.object(unimod,'SOURCE_OVERRIDES',Path(root)/'overrides.json'):
                unimod.save_source_assignment(game,mod,'https://github.com/a/b')
                result=unimod.source_report(game,[mod])[0]
            self.assertEqual(result['source'],'GitHub')
            self.assertEqual(result['match_type'],'Assigned')
if __name__=='__main__':unittest.main()
