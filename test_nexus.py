import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import unimod


class NexusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.game = {'name': 'Stardew Valley', 'root':self.tmp.name, 'kind':'smapi'}
        self.mod = {'name':'My Mod', 'uid':'author.mod', 'path':str(Path(self.tmp.name)/'Mods'/'My Mod'),
                    'version':'1.2.0', 'enabled':True, 'update_keys':['Nexus:123']}
        self.override = patch.object(unimod,'SOURCE_OVERRIDES',Path(self.tmp.name)/'overrides.json')
        self.override.start()
        self.addCleanup(self.override.stop)

    def test_parse_exact_valid_mod_page(self):
        expected={'game_domain':'stardewvalley','mod_id':'123',
                  'url':'https://www.nexusmods.com/stardewvalley/mods/123'}
        self.assertEqual(unimod.parse_nexus_link('https://www.nexusmods.com/stardewvalley/mods/123?tab=files'),expected)
        self.assertEqual(unimod.nexus_reference(self.game,self.mod),expected)

    def test_reject_wrong_or_ambiguous_links(self):
        for url in ('http://www.nexusmods.com/stardewvalley/mods/123',
                    'https://www.nexusmods.com.evil.invalid/stardewvalley/mods/123',
                    'https://www.nexusmods.com@evil.invalid/stardewvalley/mods/123',
                    'https://www.nexusmods.com/stardewvalley/mods/not-an-id',
                    'https://www.nexusmods.com/stardewvalley',
                    'https://www.nexusmods.com/stardewvalley/mods/123/extra',
                    'https://www.nexusmods.com:444/stardewvalley/mods/123',
                    'https://www.nexusmods.com/stardewvalley/mods/0'):
            with self.subTest(url=url):self.assertIsNone(unimod.parse_nexus_link(url))

    def test_manual_source_has_priority_and_not_fuzzy(self):
        unimod.save_source_assignment(self.game,self.mod,'https://github.com/author/project')
        self.assertIsNone(unimod.nexus_reference(self.game,self.mod))
        unimod.save_source_assignment(self.game,self.mod,'https://www.nexusmods.com/stardewvalley/mods/999')
        self.assertEqual(unimod.nexus_reference(self.game,self.mod)['mod_id'],'999')
        noid={**self.mod,'path':'/other','uid':'other','update_keys':[],'website_url':''}
        self.assertIsNone(unimod.nexus_reference(self.game,noid))

    def test_conflicting_metadata_is_marked_without_request(self):
        mod={**self.mod,'website_url':'https://www.nexusmods.com/stardewvalley/mods/222'}
        self.assertIn('error',unimod.nexus_reference(self.game,mod))
        called=[]
        results=unimod.check_nexus_updates(self.game,[mod],'fake-key',fetch=lambda *args:called.append(args))
        self.assertFalse(called)
        self.assertEqual(results[mod['path']]['status'],'Identity conflict')

    def test_api_headers_and_version_check(self):
        seen=[]
        def fetch(url,headers):
            seen.append((url,headers))
            return {'name':'My Mod','version':'1.3.0'}
        result=unimod.check_nexus_updates(self.game,[self.mod], 'sensitive-session-key',fetch=fetch)
        self.assertEqual(result[self.mod['path']]['status'],'Update available')
        self.assertEqual(result[self.mod['path']]['version'],'1.3.0')
        self.assertEqual(seen[0][0],'https://api.nexusmods.com/v1/games/stardewvalley/mods/123.json')
        self.assertEqual(seen[0][1]['apikey'],'sensitive-session-key')
        self.assertEqual(seen[0][1]['Application-Name'],'UniMod')
        self.assertEqual(seen[0][1]['Application-Version'],'0.54.0')
        self.assertNotIn('sensitive-session-key',repr(result))

    def test_deduplicate_requests_for_same_remote_mod(self):
        other={**self.mod,'path':'/second-copy','name':'Another name','version':'1.3.0'}
        urls=[]
        result=unimod.check_nexus_updates(self.game,[self.mod,other],'session-key',fetch=lambda u,h: (urls.append(u) or {'name':'My Mod','version':'1.3.0'}))
        self.assertEqual(len(urls),1)
        self.assertEqual(result[other['path']]['status'],'Current')
        self.assertEqual(len(result),2)

    def test_small_batches_and_stop_on_auth_failure(self):
        second={**self.mod,'path':'/2','update_keys':['Nexus:321']}
        fetched=[]
        def fetch(url,headers):
            fetched.append(url)
            raise ValueError('Authentication failed (HTTP 401). Check your personal API key.')
        result=unimod.check_nexus_updates(self.game,[self.mod,second],'wrong-key',fetch=fetch)
        self.assertEqual(len(fetched),1)
        self.assertEqual(len(result),1)
        self.assertEqual(result[self.mod['path']]['status'],'Check failed')
        with self.assertRaises(ValueError):unimod.check_nexus_updates(self.game,[self.mod],'',fetch=fetch)
        with self.assertRaises(ValueError):unimod.check_nexus_updates(self.game,[self.mod],'key',fetch=fetch,max_unique=100)

    def test_unknown_version_remains_unknown(self):
        result=unimod.check_nexus_updates(self.game,[{**self.mod,'version':'v1.2.0-beta'}],'key',
            fetch=lambda u,h:{'name':'My Mod','version':'1.3.0'})
        self.assertEqual(result[self.mod['path']]['status'],'Unknown')

    def test_other_game_requires_explicit_source(self):
        custom={'name':'Unrecognised game','root':self.tmp.name,'kind':'bepinex'}
        self.assertIsNone(unimod.nexus_reference(custom,self.mod))
        custom['nexus_domain']='examplegame'
        self.assertEqual(unimod.nexus_reference(custom,self.mod)['game_domain'],'examplegame')

if __name__=='__main__': unittest.main()
