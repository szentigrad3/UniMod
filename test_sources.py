import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import unimod

class TestSources(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.override=Path(self.tmp.name)/'overrides.json'
        self.patcher=patch.object(unimod,'SOURCE_OVERRIDES',self.override)
        self.patcher.start()
        self.game={'root':self.tmp.name,'kind':'smapi','name':'Stardew Valley'}
        self.mod={'name':'Test Mod','version':'1.0','uid':'Example.Mod','enabled':True,'update_keys':[], 'relative':'Pack/Mod','path':str(Path(self.tmp.name)/'Mods/Pack/Mod')}
    def tearDown(self):
        self.patcher.stop();self.tmp.cleanup()
    def test_assignment_persists_after_rename(self):
        unimod.save_source_assignment(self.game,self.mod,'https://www.nexusmods.com/stardewvalley/mods/123')
        moved={**self.mod,'relative':'DifferentFolder/Mod'}
        self.assertEqual(unimod.assigned_source(self.game,moved)['site'],'Nexus Mods')
        self.assertEqual(unimod.source_report(self.game,[moved])[0]['match_type'],'Assigned')
    def test_bad_urls_refused(self):
        for bad in ['http://github.com/user/repo','https://evilgithub.com/test', 'file:///etc/passwd','https://github.com@evil.example/repo','https://foo.invalid/mod']:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):unimod.save_source_assignment(self.game,self.mod,bad)
    def test_clear(self):
        unimod.save_source_assignment(self.game,self.mod,'https://github.com/owner/repo')
        unimod.clear_source_assignment(self.game,self.mod)
        self.assertIsNone(unimod.assigned_source(self.game,self.mod))
    def test_csv(self):
        out=Path(self.tmp.name)/'sources.csv'
        self.assertEqual(unimod.export_source_csv(out,self.game,[self.mod]),1)
        self.assertIn('Unmatched',out.read_text(encoding='utf-8-sig'))

if __name__=='__main__':unittest.main()
