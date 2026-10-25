"""Read-only user-facing game audit aggregation and privacy checks."""
import unittest
import game_health

SMAPI={'kind':'smapi','name':'Private Stardew','root':'/home/user/private/SteamGame'}
BEPINEX={'kind':'bepinex','name':'Another Game','root':'/private/BepInEx'}

class GameHealthTests(unittest.TestCase):
    def test_healthy_smapi_summary(self):
        report=game_health.summarize(SMAPI,
            {'folders':12,'enabled_folders':10,'unmanaged':0},[],[])
        self.assertEqual(report['status'],'No issues found in supported checks')
        self.assertEqual(report['packages'],12)
        self.assertEqual(report['enabled'],10)
        self.assertEqual(report['dependencies'],0)

    def test_duplicate_and_required_dependency_warnings(self):
        issues=[{'type':'Duplicate enabled ID','detail':'/private/mod'},
                {'type':'Missing required dependency','detail':'/private/dependency'}]
        dependencies=[{'required':True,'mod_enabled':True,'status':'Missing'},
                      {'required':False,'mod_enabled':True,'status':'Missing'},
                      {'required':True,'mod_enabled':False,'status':'Missing'},
                      {'required':True,'mod_enabled':True,'status':'Below minimum'}]
        report=game_health.summarize(SMAPI,
            {'folders':7,'enabled_folders':7,'unmanaged':1},issues,dependencies)
        self.assertEqual(report['duplicates'],1)
        self.assertEqual(report['dependencies'],2)
        self.assertEqual(report['unmanaged'],1)
        self.assertEqual(report['status'],'Needs review')
        self.assertNotIn('/private',game_health.safe_report(report))

    def test_bepinex_does_not_pretend_to_inspect_smapi_dependencies(self):
        report=game_health.summarize(BEPINEX,
            {'folders':4,'enabled_folders':4,'unmanaged':0},[],[
                {'required':True,'mod_enabled':True,'status':'Missing'}])
        self.assertEqual(report['kind'],'bepinex')
        self.assertTrue(report['limited'])
        self.assertEqual(report['dependencies'],0)

    def test_only_whitelisted_data_in_report(self):
        report=game_health.summarize(SMAPI,{'folders':3,'enabled_folders':2,
            'unmanaged':1},[{'type':'Secret '+SMAPI['root']}],[])
        text=game_health.safe_report(report)
        for secret in (SMAPI['root'],SMAPI['name'],'https://secret.example','Secret'):
            self.assertNotIn(secret,text)
        self.assertIn('Privacy: local paths',text)

    def test_invalid_or_untrusted_report_values_are_not_interpolated(self):
        report={'kind':'token=PRIVATE','status':'https://unsafe.example',
                'packages':'SECRET','dependencies':True,'duplicates':-1,
                'enabled':0,'unmanaged':999999999999999999}
        text=game_health.safe_report(report)
        self.assertNotIn('PRIVATE',text)
        self.assertNotIn('SECRET',text)
        self.assertNotIn('https://',text)
        self.assertIn('Not verified',text)

    def test_invalid_input_rejected(self):
        for game,health,issues,deps in [
            (None,{},[],[]), (SMAPI,None,[],[]),
            (SMAPI,{},'no',[]), (SMAPI,{},[],None)]:
            with self.subTest(case=(game,health)),self.assertRaises(ValueError):
                game_health.summarize(game,health,issues,deps)

if __name__=='__main__':
    unittest.main()
