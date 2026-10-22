"""Source-lookup tests that require no internet or game-file modifications."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import smapi_lookup_cache as cache
import smapi_catalogue
import unimod

class SourceLookupBackoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'negative.json'
        self.mod={'uid':'Mod.Author.Example','version':'1.0','update_keys':['GitHub:author/mod'], 'path':'PRIVATE_INSTALL_LOCATION'}
        self.other={'uid':'Mod.Author.Second','version':'2.0','update_keys':[]}
        self.ident=lambda mod:mod['uid'].casefold()

    def test_empty_catalogue_is_cached_but_never_a_false_source(self):
        diagnostics=smapi_catalogue.resolve_smapi_ids([self.mod],fetch=lambda *_: [],diagnostics=True)
        self.assertEqual(diagnostics['matches'],{})
        cache.record([self.mod],diagnostics,self.path,self.ident,now=1000)
        candidates, skipped=cache.pending([self.mod],self.path,self.ident,now=1001)
        self.assertEqual((candidates,skipped),([],1))
        self.assertNotIn('PRIVATE_INSTALL_LOCATION',self.path.read_text())
        self.assertNotIn(self.mod['uid'].casefold(),self.path.read_text())
        self.assertNotIn('GitHub:author/mod',self.path.read_text())
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1001,force=True),([self.mod],0))

    def test_cache_expiry_and_manifest_changes(self):
        cache.record([self.mod],{'matches':{},'error_ids':[]},self.path,self.ident,now=1000)
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1001)[1],1)
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1000+cache.TTL_SECONDS)[1],0)
        changed=dict(self.mod,version='1.1')
        self.assertEqual(cache.pending([changed],self.path,self.ident,now=1001)[1],0)
        changed=dict(self.mod,update_keys=['Nexus:453'])
        self.assertEqual(cache.pending([changed],self.path,self.ident,now=1001)[1],0)

    def test_per_id_catalogue_errors_are_not_negative(self):
        result=smapi_catalogue.resolve_smapi_ids([self.mod,self.other],
            fetch=lambda *_: [{'id':self.mod['uid'],'errors':['Unavailable'],'metadata':{}},
                             {'id':self.other['uid'],'metadata':{}}],diagnostics=True)
        self.assertIn(self.mod['uid'].casefold(),result['error_ids'])
        cache.record([self.mod,self.other],result,self.path,self.ident,now=1000)
        todo,skipped=cache.pending([self.mod,self.other],self.path,self.ident,now=1001)
        self.assertEqual(todo,[self.mod]);self.assertEqual(skipped,1)

    def test_conflicting_page_id_is_not_cached_as_absent(self):
        diagnostic=smapi_catalogue.resolve_smapi_ids([self.mod],fetch=lambda *_:[{
            'id':self.mod['uid'], 'metadata':{'nexusID':1234,
              'main':{'url':'https://www.nexusmods.com/stardewvalley/mods/4321'}}
        }],diagnostics=True)
        self.assertEqual(diagnostic['matches'],{})
        self.assertIn(self.mod['uid'].casefold(),diagnostic['error_ids'])
        cache.record([self.mod],diagnostic,self.path,self.ident,now=1000)
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1001)[1],0)

    def test_positive_matches_clear_previous_negative(self):
        cache.record([self.mod],{'matches':{},'error_ids':[]},self.path,self.ident,now=1000)
        cache.record([self.mod],{'matches':{self.mod['uid'].casefold():{'nexus_id':'1234'}},'error_ids':[]},
            self.path,self.ident,now=1001)
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1002)[1],0)

    def test_malformed_cache_fails_open_and_does_not_block_lookup(self):
        self.path.write_text('{garbled')
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1000),([self.mod],0))
        self.path.write_text(json.dumps({'schema':1,'entries':{'MOD.AUTHOR.EXAMPLE':{'timestamp':float('nan'),'fingerprint':'a'*64}}}))
        self.assertEqual(cache.pending([self.mod],self.path,self.ident,now=1000),([self.mod],0))

    def test_gui_source_action_uses_backoff_only_for_automatic_checks(self):
        # No live request; verify the callback routes through the proper mode.
        self.assertIn('force=not continue_check',
                      Path(unimod.__file__).read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
