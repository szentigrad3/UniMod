"""Regression tests for the user-facing unified update summary and security gates."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unimod


class UnifiedUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.game={'name':'Stardew Valley','root':self.tmp.name,'kind':'smapi'}
        self.manual=patch.object(unimod,'SOURCE_OVERRIDES',Path(self.tmp.name)/'overrides.json')
        self.manual.start();self.addCleanup(self.manual.stop)
        self.a={'name':'Stardew Valley Expanded','path':self.tmp.name+'/Mods/SVE1', 'version':'1.2.0',
                'update_keys':['Nexus:3753'],'uid':'example.sve', 'enabled':True}
        self.b={'name':'Stardew Valley Expanded CP','path':self.tmp.name+'/Mods/SVE2', 'version':'1.2.0',
                'update_keys':['Nexus:3753'],'uid':'example.svecp', 'enabled':True}

    def test_not_checked_does_not_claim_no_updates(self):
        records=unimod.unified_update_rows(self.game,[self.a])
        self.assertEqual(records[0]['status'],'Not checked')
        self.assertEqual(records[0]['source'],'Nexus')

    def test_identical_nexus_page_groups_components(self):
        rows=unimod.unified_update_rows(self.game,[self.a,self.b],{
            self.a['path']:{'status':'Update available','version':'1.3.0'},
            self.b['path']:{'status':'Current','version':'1.2.0'}})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['components'],2)
        self.assertEqual(rows[0]['status'],'Update available')
        self.assertEqual(rows[0]['remote_version'],'1.3.0')
        self.assertEqual(set(rows[0]['paths']),{self.a['path'],self.b['path']})

    def test_known_source_without_response_not_current(self):
        rows=unimod.unified_update_rows(self.game,[self.a,self.b])
        self.assertEqual(rows[0]['status'],'Not checked')
        self.assertEqual(rows[0]['components'],2)

    def test_unlinked_mod_is_included_and_not_guessed(self):
        unknown={**self.a,'name':'Unlinked','uid':'unlinked','path':self.tmp.name+'/Mods/unlinked','update_keys':[]}
        rows=unimod.unified_update_rows(self.game,[unknown])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'Source needed')
        self.assertFalse(rows[0]['url'])

    def test_failed_check_does_not_claim_version(self):
        rows=unimod.unified_update_rows(self.game,[self.a],{self.a['path']:{'status':'Check failed','error':'HTTP 429'}})
        self.assertEqual(rows[0]['status'],'Check failed')
        self.assertFalse(rows[0]['remote_version'])

    def test_source_conflict_not_a_confirmed_update(self):
        conflict={**self.a,'website_url':'https://www.nexusmods.com/stardewvalley/mods/222'}
        rows=unimod.unified_update_rows(self.game,[conflict])
        self.assertEqual(rows[0]['status'],'ID conflict')
        self.assertEqual(rows[0]['source'],'Unknown')

    def test_github_and_nexus_reports_merge_conservatively(self):
        m={**self.a,'update_keys':['Nexus:3753','GitHub:someorg/realrepo']}
        rows=unimod.unified_update_rows(self.game,[m],{m['path']:{'status':'Check failed'}},
            {m['path']:{'status':'Update available','version':'1.3.0'}})
        self.assertEqual(rows[0]['status'],'Update available')
        self.assertEqual(rows[0]['remote_version'],'1.3.0')

    def test_unindexed_folder_retained_without_forced_identity(self):
        extra={'name':'Unknown folder', 'path':self.tmp.name+'/Mods/Folder', 'version':'', 'update_keys':[]}
        rows=unimod.unified_update_rows(self.game,[self.a],extra_folders=[extra])
        self.assertEqual(len(rows),2)
        self.assertEqual(next(r for r in rows if r['name']=='Unknown folder')['status'],'Source needed')


if __name__=='__main__':unittest.main()
