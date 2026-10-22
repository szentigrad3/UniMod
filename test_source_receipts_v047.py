"""Offline provenance tests; no Nexus API access or live game writes."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import source_receipts
from unimod import discover_nexus_download_evidence, simple_source_preview

class DownloadReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.archive=self.root/'my-archive.zip'
        self.db=self.root/'private.json'
        self.mod={'uid':'author.samplecomponent','name':'Sample component','path':str(self.root/'installed'),
                  'version':'1.0', 'enabled':True, 'update_keys':[]}
        self.game={'name':'Stardew Valley','root':str(self.root),'kind':'smapi','nexus_domain':'stardewvalley'}
        self.write_zip({'manifest.json':{'UniqueID':self.mod['uid'],'Version':'2.0'}})
    def write_zip(self, manifests):
        with zipfile.ZipFile(self.archive,'w') as z:
            for file, manifest in manifests.items():z.writestr(file, json.dumps(manifest))
    def record(self,ids=None,mid='3753',domain='stardewvalley'):
        return source_receipts.record_receipt(self.archive,domain,mid,'123',
             [{'uid':ident} for ident in (ids if ids is not None else [self.mod['uid']])],self.db)
    def test_persists_only_nonsensitive_identifiers(self):
        receipt=self.record()
        self.assertEqual(len(source_receipts.load_receipts(self.db)),1)
        self.assertEqual(receipt['file_id'],'123')
        stored=self.db.read_text()
        self.assertNotIn(str(self.root),stored)
        self.assertNotIn('nxm://',stored)
        self.assertNotIn('api_key',stored)
        self.assertEqual(self.db.stat().st_mode&0o777,0o600)
    def test_archive_can_be_renamed_and_still_matches(self):
        self.record()
        moved=self.root/'moved-something.zip'
        self.archive.rename(moved)
        self.assertEqual(source_receipts.find_receipt(moved,'stardewvalley',self.db)[0]['mod_id'],'3753')
        self.assertFalse(source_receipts.find_receipt(moved,'skyrim',self.db))
    def test_archive_changes_do_not_match_old_receipt(self):
        self.record()
        self.write_zip({'manifest.json':{'UniqueID':'Different.Mod'}})
        self.assertFalse(source_receipts.find_receipt(self.archive,'stardewvalley',self.db))
    def test_multi_component_archive_one_source(self):
        self.record(ids=[self.mod['uid'],'other.second'])
        self.assertEqual(len(source_receipts.uid_candidates('stardewvalley',
             [self.mod['uid'],'other.second'],self.db)),2)
    def test_receipt_survives_deleted_archive_but_requires_review(self):
        self.record()
        self.archive.unlink()
        with patch('unimod.NEXUS_RECEIPTS',self.db):
            scanned=discover_nexus_download_evidence(self.game,[self.mod],self.root)
            preview=simple_source_preview(self.game,[self.mod],scan=scanned)
        self.assertEqual(preview[0]['status'],'Review candidate')
        self.assertIn('download receipt',preview[0]['evidence'])
    def test_wrong_uid_is_never_matched(self):
        self.record(ids=['not.the.installed.mod'])
        self.assertFalse(source_receipts.uid_candidates('stardewvalley',[self.mod['uid']],self.db))
    def test_conflicting_source_id_requires_review(self):
        self.record(mid='3753')
        self.write_zip({'manifest.json':{'UniqueID':self.mod['uid'], 'UpdateKeys':['Nexus:7286']}})
        with patch('unimod.NEXUS_RECEIPTS',self.db):
            scanned=discover_nexus_download_evidence(self.game,[self.mod],self.root)
            preview=simple_source_preview(self.game,[self.mod],scan=scanned)
        self.assertEqual(preview[0]['status'],'Conflicting archive hints')
    def test_no_receipt_for_unidentified_archive(self):
        result=source_receipts.record_receipt(self.archive,'stardewvalley','3753','123',[],self.db)
        self.assertIsNone(result)
        self.assertFalse(self.db.exists())
    def test_refuse_symlinked_database(self):
        other=self.root/'unexpected.txt';other.write_text('preserve')
        self.db.symlink_to(other)
        with self.assertRaises(ValueError):self.record()
        self.assertEqual(other.read_text(),'preserve')
    def test_refuse_symlinked_archive(self):
        moved=self.root/'normal.zip';self.archive.rename(moved)
        self.archive.symlink_to(moved)
        with self.assertRaises(ValueError):self.record()
    def test_corrupt_and_oversized_receipt_db_ignored(self):
        self.db.write_text('invalid json')
        self.assertEqual(source_receipts.load_receipts(self.db),[])
        self.db.write_bytes(b'x'*(source_receipts.MAX_DB_BYTES+1))
        self.assertEqual(source_receipts.load_receipts(self.db),[])
    def test_receipt_priority_over_weak_filename_hint(self):
        r={'mod_id':'3753','url':'https://www.nexusmods.com/stardewvalley/mods/3753',
          'evidence':'UniMod approved Nexus download receipt (file #123)', 'filename':'download history'}
        hint=dict(r,evidence='ZIP filename hint — verify on Nexus')
        preview=simple_source_preview(self.game,[self.mod],scan={self.mod['uid']:[hint,r]})
        self.assertIn('approved Nexus',preview[0]['evidence'])
    def test_duplicate_same_download_replaces_receipt(self):
        self.record();self.record()
        self.assertEqual(len(source_receipts.load_receipts(self.db)),1)

if __name__=='__main__':unittest.main()
