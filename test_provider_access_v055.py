import unittest
import provider_access
class AccessTests(unittest.TestCase):
    def test_nexus_requires_registered_app(self):
        x=provider_access.access_info('Nexus Mods')
        self.assertIn('registration',x['status'])
        self.assertIn('help.nexusmods.com',x['url'])
    def test_curseforge_requires_approval(self):
        x=provider_access.access_info('CurseForge',key_present=True)
        self.assertIn('approved API key',x['status'])
        self.assertNotIn('download enabled',x['status'].lower())
        self.assertIn('session',x['key'].lower())
    def test_modio_key(self):
        self.assertIn('API key',provider_access.access_info('mod.io')['status'])
    def test_modrinth_ungated(self):
        self.assertIn('no account key',provider_access.access_info('Modrinth')['status'])
    def test_unknown_provider_needs_no_fake_key(self):
        self.assertIsNone(provider_access.access_info('GitHub')['url'])
if __name__=='__main__':unittest.main()
