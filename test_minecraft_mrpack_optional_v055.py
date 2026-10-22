"""Offline Test 6 regression cases for consent-gated .mrpack optional files."""
import json
import unittest
from pathlib import Path
from test_minecraft_mrpack_install_v055 import PackInstallTests
import minecraft_mrpack as mr
BaseSetup=PackInstallTests.setUp
BaseReceipt=PackInstallTests.receipt
del PackInstallTests


class OptionalPackTests(unittest.TestCase):
    def setUp(self):
        BaseSetup(self)
        self.optional_blob=b'optional-jar-bytes'
        row=dict(self.row)
        row['path']='mods/Optional.jar'
        row['fileSize']=len(self.optional_blob)
        import hashlib
        row['hashes']={'sha1':hashlib.sha1(self.optional_blob).hexdigest(),
                       'sha512':hashlib.sha512(self.optional_blob).hexdigest()}
        row['env']={'client':'optional','server':'required'}
        self.index['files'].append(row)
    receipt=BaseReceipt
    def downloader(self,row,target):
        target.write_bytes(self.optional_blob if row['path']=='mods/Optional.jar' else self.blob)

    def test_defaults_to_off_and_lists_opt_in(self):
        plan=mr.plan_import(self.receipt(),self.instance)
        self.assertEqual(plan['selected_optional'],[])
        self.assertEqual(len(plan['optional_candidates']),1)
        self.assertEqual(plan['optional_skipped'],1)
        self.assertEqual(plan['download_count'],1)
        result=mr.install_import(plan,self.recovery,self.journal,downloader=self.downloader)
        self.assertEqual(result['installed'],1)
        self.assertFalse((self.game/'mods/Optional.jar').exists())

    def test_explicit_option_installs_and_is_recorded(self):
        plan=mr.plan_import(self.receipt(),self.instance,['mods/Optional.jar'])
        self.assertEqual(plan['selected_optional'],['mods/Optional.jar'])
        self.assertEqual(plan['download_count'],2)
        self.assertEqual(plan['optional_skipped'],0)
        result=mr.install_import(plan,self.recovery,self.journal,downloader=self.downloader)
        self.assertEqual(result['installed'],2)
        self.assertEqual((self.game/'mods/Optional.jar').read_bytes(),self.optional_blob)
        records=json.loads(self.journal.read_text())
        self.assertEqual(records[0]['selected_optional'],['mods/Optional.jar'])

    def test_missing_or_nonoptional_choice_rejected(self):
        receipt=self.receipt()
        for choice in (['mods/Missing.jar'],['mods/Example.jar'],['mods/Optional.jar','mods/Optional.jar'],['../bad.jar']):
            with self.subTest(choice=choice):
                with self.assertRaises(mr.PackError):mr.plan_import(receipt,self.instance,choice)
        self.assertFalse((self.game/'mods').exists())

    def test_optional_unsupported_source_is_not_available(self):
        self.index['files'][-1]['downloads']=['https://example.org/file.jar']
        receipt=self.receipt()
        plan=mr.plan_import(receipt,self.instance)
        self.assertFalse(plan['optional_candidates'][0]['available'])
        with self.assertRaisesRegex(mr.PackError,'lacks supported CDN'):
            mr.plan_import(receipt,self.instance,['mods/Optional.jar'])

    def test_optional_server_unsupported_not_presented(self):
        self.index['files'][-1]['env']={'client':'unsupported'}
        receipt=self.receipt()
        plan=mr.plan_import(receipt,self.instance)
        self.assertEqual(plan['optional_candidates'],[])
        with self.assertRaisesRegex(mr.PackError,'not offered'):
            mr.plan_import(receipt,self.instance,['mods/Optional.jar'])

    def test_selected_option_failure_rolls_back(self):
        (self.game/'mods').mkdir()
        prev=self.game/'mods/Optional.jar';prev.write_bytes(b'original-optional')
        plan=mr.plan_import(self.receipt(),self.instance,['mods/Optional.jar'])
        def fail_second(n,row):
            if n==2:raise RuntimeError('write interrupted')
        with self.assertRaisesRegex(RuntimeError,'write interrupted'):
            mr.install_import(plan,self.recovery,self.journal,downloader=self.downloader,commit_hook=fail_second)
        self.assertEqual(prev.read_bytes(),b'original-optional')
        self.assertFalse((self.game/'mods/Example.jar').exists())
        self.assertFalse(self.journal.exists())

    def test_revalidated_optional_selection_cannot_be_changed_after_approval(self):
        plan=mr.plan_import(self.receipt(),self.instance,['mods/Optional.jar'])
        plan['selected_optional']=[]
        with self.assertRaisesRegex(mr.PackError,'changed since approval'):
            mr.install_import(plan,self.recovery,self.journal,downloader=self.downloader)
        self.assertFalse((self.game/'mods').exists())

    def test_optional_destination_conflicts_with_override(self):
        receipt=self.receipt(overrides={'overrides/mods/Optional.jar':b'override'})
        plan=mr.plan_import(receipt,self.instance)
        self.assertFalse(plan['optional_candidates'][0]['available'])
        with self.assertRaises(mr.PackError):
            mr.plan_import(receipt,self.instance,['mods/Optional.jar'])

if __name__=='__main__':unittest.main()

class OptionalOnlyPackTests(unittest.TestCase):
    def test_optional_only_pack_can_be_reviewed_but_not_installed_without_selection(self):
        fixture=OptionalPackTests('test_explicit_option_installs_and_is_recorded')
        fixture.setUp()
        try:
            fixture.index['files']=[fixture.index['files'][-1]]
            receipt=fixture.receipt()
            preview=mr.plan_import(receipt,fixture.instance)
            self.assertEqual(preview['download_count'],0)
            self.assertEqual(len(preview['optional_candidates']),1)
            with self.assertRaisesRegex(mr.PackError,'No client files'):
                mr.install_import(preview,fixture.recovery,fixture.journal,downloader=fixture.downloader)
            chosen=mr.plan_import(receipt,fixture.instance,['mods/Optional.jar'])
            self.assertEqual(chosen['download_count'],1)
        finally:fixture.doCleanups()
