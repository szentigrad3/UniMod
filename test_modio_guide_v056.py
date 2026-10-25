"""Readiness/credential privacy checks for the UniMod mod.io tester guide."""
import hashlib
import unittest
from modio_guide import snapshot, safe_report, next_step

GAME={'kind':'smapi','name':'Stardew Valley','root':'/private/home/realgame'}
KEY='my-test-API-secret-never-share'
DIGEST=hashlib.sha256(KEY.encode()).digest()
VERIFIED=('123','456',DIGEST,'Stardew Valley')
SELECTED={'provider':'mod.io','identity':'123/77','title':'Example'}


class GuideTests(unittest.TestCase):
    def state(self, **changes):
        args=dict(game=GAME,provider='mod.io',game_id='123',user_id='456',
                  api_key=KEY,verified=VERIFIED,selected=SELECTED)
        args.update(changes)
        return snapshot(**args)

    def test_verified_game_and_selected_mod(self):
        state=self.state()
        self.assertTrue(all(state[key] for key in
                            ('game_selected','connection_entered','game_verified','mod_selected')))
        self.assertEqual(state['download_test'],'Not tested')

    def test_no_supported_game_has_clear_next_step(self):
        state=self.state(game={'kind':'unknown','name':'Game','root':'/tmp/example'})
        self.assertFalse(state['game_selected'])
        self.assertIn('Choose an installed',next_step(state))

    def test_missing_key_or_provider_requires_setup(self):
        self.assertFalse(self.state(api_key='short')['connection_entered'])
        self.assertFalse(self.state(provider='GitHub')['connection_entered'])
        self.assertIn('private key',next_step(self.state(api_key='short')))

    def test_wrong_game_or_wrong_user_key_is_not_verified(self):
        self.assertFalse(self.state(verified=('123','456',DIGEST,'Wrong'))['game_verified'])
        self.assertFalse(self.state(verified=('123','999',DIGEST,'Stardew Valley'))['game_verified'])
        self.assertFalse(self.state(api_key=KEY+'new')['game_verified'])

    def test_wrong_mod_scope_is_not_selected(self):
        self.assertFalse(self.state(selected=dict(SELECTED,identity='124/77'))['mod_selected'])
        self.assertFalse(self.state(selected=dict(SELECTED,identity='123/../77'))['mod_selected'])
        self.assertFalse(self.state(selected=dict(SELECTED,provider='GitHub'))['mod_selected'])

    def test_only_same_session_reports_passed(self):
        current=self.state()
        records={kind:{'result':'Passed','context':current['_context']}
                 for kind in ('metadata','download')}
        ok=self.state(test_results=records)
        self.assertEqual(ok['metadata_test'],'Passed')
        self.assertEqual(ok['download_test'],'Passed')
        self.assertIn('Checks passed',next_step(ok))
        changed=self.state(api_key=KEY+'new',test_results=records)
        self.assertEqual(changed['metadata_test'],'Not tested')
        other_mod=self.state(selected=dict(SELECTED,identity='123/88'),test_results=records)
        self.assertEqual(other_mod['download_test'],'Not tested')

    def test_safe_report_contains_no_credentials_or_paths(self):
        report=safe_report(self.state())
        for secret in (KEY,'123/77','456',GAME['root'],'signed','my-test-API'):
            self.assertNotIn(secret,report)
        self.assertIn('Metadata check: Not tested',report)
        self.assertIn('Real installation/rollback: Not tested',report)

    def test_untrusted_results_are_not_interpolated(self):
        state=self.state()
        state['metadata_test']='secret:'+KEY
        state['download_test']='https://url.example/download'
        report=safe_report(state)
        self.assertNotIn(KEY,report)
        self.assertNotIn('https://',report)
        self.assertIn('Not tested',report)


if __name__=='__main__':
    unittest.main()
