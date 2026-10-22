"""Tests exercise malicious paths, ZIP bombs and invalid Modrinth manifests."""
import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

import minecraft_mrpack as mr

class ModpackInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'sample.mrpack'
        self.manifest={'formatVersion':1,'game':'minecraft','versionId':'pack-1','name':'Pack',
                       'dependencies':{'minecraft':'1.21.1','fabric-loader':'0.16.9'},
                       'files':[{'path':'mods/Example.jar',
                                 'hashes':{'sha1':'a'*40,'sha512':'b'*128},
                                 'fileSize':100,'env':{'client':'required','server':'unsupported'},
                                 'downloads':['https://cdn.modrinth.com/data/PROJ1234/versions/VER1234/Example.jar']}]}

    def build(self, manifest=None, entries=None):
        data=self.manifest if manifest is None else manifest
        with zipfile.ZipFile(self.path,'w') as z:
            z.writestr('modrinth.index.json',json.dumps(data))
            for name,value in (entries or {}).items():z.writestr(name,value)
        return {'provider':'Modrinth','identity':'PACK1234','filename':self.path.name,'archive':str(self.path),
                'bytes':self.path.stat().st_size,'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}

    def test_safe_manifest_reports_downloads_without_installing(self):
        summary=mr.inspect_pack(self.build(entries={'overrides/config/option.json':'{}'}))
        self.assertEqual(summary['file_count'],1)
        self.assertEqual(summary['override_count'],1)
        self.assertEqual(summary['unsupported_urls'],0)
        self.assertFalse(summary['install_supported'])

    def test_archive_modified_after_stage_rejected(self):
        receipt=self.build();self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(mr.PackError,'changed'):
            mr.inspect_pack(receipt)

    def test_manifest_traversal_rejected(self):
        for path in ('../escape.jar','/mods/out.jar','mods/../bad.jar','C:/mods/bad.jar',
                     'mods\\bad.jar','mods//bad.jar','mods/bad\x00.jar'):
            with self.subTest(path=path):
                data=json.loads(json.dumps(self.manifest));data['files'][0]['path']=path
                with self.assertRaises(mr.PackError):mr.inspect_pack(self.build(data))

    def test_zip_traversal_rejected(self):
        for filename in ('../outside','overrides/../outside','client-overrides//a'):
            with self.subTest(filename=filename):
                with self.assertRaises(mr.PackError):mr.inspect_pack(self.build(entries={filename:'bad'}))

    def test_duplicate_destinations_rejected(self):
        data=json.loads(json.dumps(self.manifest))
        item=dict(data['files'][0]);item['path']='mods/example.jar';data['files'].append(item)
        with self.assertRaisesRegex(mr.PackError,'duplicate'):
            mr.inspect_pack(self.build(data))

    def test_symlink_entry_rejected(self):
        with zipfile.ZipFile(self.path,'w') as z:
            z.writestr('modrinth.index.json',json.dumps(self.manifest))
            item=zipfile.ZipInfo('overrides/link');item.create_system=3
            item.external_attr=(stat.S_IFLNK|0o777)<<16
            z.writestr(item,'../../etc/passwd')
        receipt={'provider':'Modrinth','archive':str(self.path),'filename':self.path.name,
                 'bytes':self.path.stat().st_size,'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}
        with self.assertRaisesRegex(mr.PackError,'symlinks'):
            mr.inspect_pack(receipt)

    def test_nonmodrinth_cdn_urls_preview_unsupported(self):
        data=json.loads(json.dumps(self.manifest))
        data['files'][0]['downloads']=['https://evil.example/mod.jar']
        self.assertEqual(mr.inspect_pack(self.build(data))['unsupported_urls'],1)

    def test_malformed_hash_and_loader_rejected(self):
        data=json.loads(json.dumps(self.manifest))
        data['files'][0]['hashes']['sha512']='not-a-hash'
        with self.assertRaisesRegex(mr.PackError,'hashes'):
            mr.inspect_pack(self.build(data))
        data=json.loads(json.dumps(self.manifest))
        data['dependencies']['forge']='48.0'
        with self.assertRaisesRegex(mr.PackError,'one supported loader'):
            mr.inspect_pack(self.build(data))

    def test_optional_environment(self):
        data=json.loads(json.dumps(self.manifest))
        data['files'][0]['env']={'client':'optional'}
        self.assertEqual(mr.inspect_pack(self.build(data))['optional_count'],1)

    def test_duplicate_archive_case_rejected(self):
        with self.assertRaisesRegex(mr.PackError,'case-colliding'):
            mr.inspect_pack(self.build(entries={'overrides/A':'hello','overrides/a':'world'}))

if __name__=='__main__':unittest.main()
