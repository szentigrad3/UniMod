"""Offline .mrpack import tests: exact loader, checksums, rollback, paths."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path
import minecraft_mrpack as mr


class PackInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.instance=self.root/'instances'/'Example';self.instance.mkdir(parents=True)
        self.game=self.instance/'.minecraft';self.game.mkdir()
        (self.instance/'mmc-pack.json').write_text(json.dumps({'components':[
            {'uid':'net.minecraft','version':'1.21.1'},
            {'uid':'net.fabricmc.fabric-loader','version':'0.16.9'}]}))
        self.blob=b'jar-bytes-for-offline-modrinth-test'
        self.url='https://cdn.modrinth.com/data/PROJECT/version/VERSION/example.jar'
        self.row={'path':'mods/Example.jar','fileSize':len(self.blob),
                  'hashes':{'sha1':hashlib.sha1(self.blob).hexdigest(),'sha512':hashlib.sha512(self.blob).hexdigest()},
                  'downloads':[self.url]}
        self.index={'formatVersion':1,'game':'minecraft','name':'Test pack','versionId':'1.0',
                    'dependencies':{'minecraft':'1.21.1','fabric-loader':'0.16.9'},
                    'files':[self.row]}
        self.pack=self.root/'pack.mrpack'
        self.recovery=self.root/'backups'
        self.journal=self.root/'pack-receipts.json'

    def receipt(self,overrides=None,index=None):
        with zipfile.ZipFile(self.pack,'w') as z:
            z.writestr('modrinth.index.json',json.dumps(index or self.index))
            for k,v in (overrides or {}).items():z.writestr(k,v)
        return {'provider':'Modrinth','filename':self.pack.name,'archive':str(self.pack),
                'bytes':self.pack.stat().st_size,'sha256':hashlib.sha256(self.pack.read_bytes()).hexdigest()}

    def good_downloader(self,row,target):target.write_bytes(self.blob)

    def test_review_does_not_write_and_download_after_review(self):
        r=self.receipt(overrides={'overrides/config/settings.json':'{}'})
        plan=mr.plan_import(r,self.instance)
        self.assertEqual(plan['download_count'],1)
        self.assertEqual(plan['overwrite_count'],0)
        self.assertFalse((self.game/'mods').exists())
        result=mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader)
        self.assertEqual(result['installed'],2)
        self.assertEqual((self.game/'mods/Example.jar').read_bytes(),self.blob)
        self.assertEqual((self.game/'config/settings.json').read_text(),'{}')
        self.assertTrue(self.journal.is_file())

    def test_exact_loader_version_required(self):
        r=self.receipt()
        components=json.loads((self.instance/'mmc-pack.json').read_text())
        components['components'][1]['version']='0.16.8'
        (self.instance/'mmc-pack.json').write_text(json.dumps(components))
        with self.assertRaisesRegex(mr.PackError,'different Minecraft or loader version'):
            mr.plan_import(r,self.instance)

    def test_unsupported_host_fails_preflight(self):
        self.index['files'][0]['downloads']=['https://github.com/repo/example.jar']
        with self.assertRaisesRegex(mr.PackError,'no supported'):
            mr.plan_import(self.receipt(),self.instance)

    def test_skip_optional_and_server_only(self):
        rows=[]
        for mode in ('optional','unsupported'):
            row=dict(self.row);row['path']='mods/'+mode+'.jar';row['env']={'client':mode};rows.append(row)
        self.index['files'].extend(rows)
        plan=mr.plan_import(self.receipt(),self.instance)
        self.assertEqual(plan['optional_skipped'],2)
        self.assertEqual(plan['download_count'],1)

    def test_symlink_folder_is_blocked_before_writes(self):
        (self.game/'mods').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(mr.PackError,'Unsafe or incompatible'):
            mr.plan_import(self.receipt(),self.instance)

    def test_unsafe_override_blocks(self):
        with self.assertRaisesRegex(mr.PackError,'outside the allowed'):
            mr.plan_import(self.receipt(overrides={'overrides/saves/world/level.dat':b'new'}),self.instance)

    def test_overwrite_creates_backup(self):
        (self.game/'mods').mkdir()
        (self.game/'mods/Example.jar').write_bytes(b'older-user-version')
        plan=mr.plan_import(self.receipt(),self.instance)
        self.assertEqual(plan['overwrite_count'],1)
        result=mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader)
        self.assertEqual((Path(result['backup'])/'mods/Example.jar').read_bytes(),b'older-user-version')
        self.assertEqual((self.game/'mods/Example.jar').read_bytes(),self.blob)

    def test_modified_existing_target_blocks_after_review(self):
        (self.game/'mods').mkdir()
        file=self.game/'mods/Example.jar';file.write_bytes(b'original')
        plan=mr.plan_import(self.receipt(),self.instance)
        file.write_bytes(b'other-process-edit')
        with self.assertRaisesRegex(mr.PackError,'changed'):
            mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader)
        self.assertEqual(file.read_bytes(),b'other-process-edit')

    def test_hash_mismatch_does_not_touch_files(self):
        (self.game/'mods').mkdir()
        file=self.game/'mods/Example.jar';file.write_bytes(b'original')
        plan=mr.plan_import(self.receipt(),self.instance)
        with self.assertRaisesRegex(mr.PackError,'cryptographic'):
            mr.install_import(plan,self.recovery,self.journal,downloader=lambda row,target:target.write_bytes(b'bad'))
        self.assertEqual(file.read_bytes(),b'original')
        self.assertFalse(self.journal.exists())

    def test_commit_failure_restores_everything(self):
        (self.game/'mods').mkdir()
        file=self.game/'mods/Example.jar';file.write_bytes(b'original')
        plan=mr.plan_import(self.receipt(overrides={'overrides/config/custom.json':b'{"ok":true}'}),self.instance)
        def fail_second(n,row):
            if n==2:raise RuntimeError('Injected disk/write failure')
        with self.assertRaisesRegex(RuntimeError,'Injected'):
            mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader,commit_hook=fail_second)
        self.assertEqual(file.read_bytes(),b'original')
        self.assertFalse((self.game/'config/custom.json').exists())
        self.assertFalse(self.journal.exists())

    def test_receipt_write_failure_restores_previous_file(self):
        (self.game/'mods').mkdir()
        file=self.game/'mods/Example.jar';file.write_bytes(b'old-version')
        plan=mr.plan_import(self.receipt(),self.instance)
        with patch.object(mr.minecraft_profiles,'_write_receipts',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):
                mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader)
        self.assertEqual(file.read_bytes(),b'old-version')
        self.assertFalse(self.journal.exists())

    def test_client_override_wins(self):
        files={'overrides/config/a.toml':'old','client-overrides/config/a.toml':'new'}
        plan=mr.plan_import(self.receipt(overrides=files),self.instance)
        result=mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader)
        self.assertEqual(result['installed'],2)
        self.assertEqual((self.game/'config/a.toml').read_text(),'new')

    def test_symlink_inserted_after_review_fails(self):
        plan=mr.plan_import(self.receipt(),self.instance)
        (self.game/'mods').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(mr.PackError):mr.install_import(plan,self.recovery,self.journal,downloader=self.good_downloader)
        self.assertFalse((self.root/'Example.jar').exists())

if __name__=='__main__':unittest.main()
