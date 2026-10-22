"""Offline provider journal and reviewed installation checks for v0.52."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import provider_staging as ps
import unimod


def makezip(path,manifest=None,dll=False):
    with zipfile.ZipFile(path,'w') as z:
        if manifest is not None:z.writestr('MyMod/manifest.json',json.dumps(manifest))
        if dll:z.writestr('MyMod/loader.dll',b'MZtest')
    return path


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.game={'kind':'smapi','root':str(self.base/'Stardew'),'name':'Test Stardew'}
        (self.base/'Stardew'/'Mods').mkdir(parents=True)
        self.receipts=self.base/'receipts.json'
        self.manifest={'UniqueID':'Example.Test','Name':'Test','Version':'2.0.0'}
        self.zip=makezip(self.base/'test.zip',self.manifest)
        self.record={'provider':'GitHub','identity':'creator/project','filename':'test.zip','version':'2.0.0',
                     'size':self.zip.stat().st_size,'url':'https://github.com/creator/project/releases/download/v2/test.zip',
                     'dependencies':[],'loaders':[],'game_versions':[]}

    def receipt(self,path=None,**extras):
        p=path or self.zip
        return {'archive':str(p),'sha256':ps.file_sha256(p),'bytes':p.stat().st_size,
                'provider':'GitHub','identity':'creator/project','game_root':str(Path(self.game['root']).resolve()),
                'dependencies':[],**extras}

    def test_download_journal_without_secrets(self):
        out=self.base/'download';out.mkdir()
        def mock_dl(record,directory):
            dest=Path(directory)/'test.zip'
            dest.write_bytes(self.zip.read_bytes())
            return dest
        record=dict(self.record,token='secret',api_key='password')
        result=ps.stage_download(record,out,self.receipts,game_root=self.game['root'],downloader=mock_dl)
        self.assertEqual(result.name,'test.zip')
        self.assertEqual(ps.read_staged(self.receipts)[0]['sha256'],ps.file_sha256(result))
        data=self.receipts.read_text()
        for private in ('secret','password','https://github.com/'):self.assertNotIn(private,data)

    def test_missing_and_wrong_game(self):
        r=self.receipt()
        with self.assertRaisesRegex(ps.StageError,'different game'):
            ps.inspect_receipt(r,game_root=self.base/'Elsewhere')
        self.zip.unlink()
        with self.assertRaisesRegex(ps.StageError,'missing'):
            ps.inspect_receipt(r,game_root=self.game['root'])

    def test_mutated_archive_is_rejected(self):
        r=self.receipt()
        self.zip.write_bytes(self.zip.read_bytes()+b'junk')
        with self.assertRaisesRegex(ps.StageError,'changed'):
            ps.inspect_receipt(r,game_root=self.game['root'])
        result=unimod.provider_install_preflight(self.game,r)
        self.assertEqual(result['status'],'Blocked')

    def test_minecraft_jar_is_download_only(self):
        jar=self.base/'plugin.jar'
        makezip(jar,self.manifest)
        with self.assertRaisesRegex(ps.StageError,'download-only'):
            ps.inspect_receipt(self.receipt(jar),game_root=self.game['root'])

    def test_new_smapi_install_is_reviewed(self):
        r=self.receipt()
        pre=unimod.provider_install_preflight(self.game,r)
        self.assertEqual(pre['status'],'Install new')
        with patch.object(unimod,'INSTALL_RECEIPTS',self.base/'installed.json'):
            result=unimod.provider_install_reviewed(self.game,r)
            self.assertEqual(result['action'],'installed')
            self.assertTrue((self.base/'Stardew'/'Mods'/'MyMod'/'manifest.json').is_file())
            self.assertEqual(len(unimod.read_receipts()),1)
            again=unimod.provider_install_preflight(self.game,r)
            self.assertEqual(again['status'],'Blocked')

    def test_required_missing_dependency_blocks(self):
        makezip(self.zip,dict(self.manifest,Dependencies=[{'UniqueID':'Missing.Framework','IsRequired':True}]))
        self.assertEqual(unimod.provider_install_preflight(self.game,self.receipt())['status'],'Blocked')

    def test_optional_missing_dependency_can_proceed(self):
        makezip(self.zip,dict(self.manifest,Dependencies=[{'UniqueID':'Other.Optional','IsRequired':False}]))
        self.assertEqual(unimod.provider_install_preflight(self.game,self.receipt())['status'],'Install new')

    def test_multi_component_new_allowed(self):
        with zipfile.ZipFile(self.zip,'w') as z:
            z.writestr('Parent/manifest.json',json.dumps(self.manifest))
            z.writestr('Component/manifest.json',json.dumps({'UniqueID':'Example.Child','Name':'Child','Version':'2.0.0',
                       'ContentPackFor':{'UniqueID':'Example.Test'}}))
        self.assertEqual(unimod.provider_install_preflight(self.game,self.receipt())['status'],'Install new')

    def test_duplicate_components_blocked(self):
        with zipfile.ZipFile(self.zip,'w') as z:
            z.writestr('A/manifest.json',json.dumps(self.manifest))
            z.writestr('B/manifest.json',json.dumps(self.manifest))
        self.assertEqual(unimod.provider_install_preflight(self.game,self.receipt())['status'],'Blocked')

    def test_modrinth_zip_is_download_only(self):
        r=self.receipt(provider='Modrinth')
        self.assertEqual(unimod.provider_install_preflight(self.game,r)['status'],'Unsupported game')

    def test_required_unresolved_modrinth_blocked(self):
        r=self.receipt(provider='Modrinth',dependencies=[{'id':'moda','type':'required'}])
        self.assertEqual(unimod.provider_install_preflight(self.game,r)['status'],'Unsupported game')

    def test_untrusted_thunderstore_source(self):
        with self.assertRaisesRegex(ps.StageError,'Untrusted'):
            ps._thunderstore_zip({'download_url':'https://evil.invalid/mod.zip','full_name':'Owner-Mod','version':'1.0.0'},self.base)
        self.assertFalse(ps._ts_url('https://thunderstore.io.evil.net/download/123'))

    def test_thunderstore_package_version_filename(self):
        class Opener:
            def open(self,req,timeout):
                class Response(io.BytesIO):
                    def __enter__(self):return self
                    def __exit__(self,*_):self.close()
                    def geturl(self):return 'https://thunderstore.io/package/download/Owner/Mod/1.0.0/'
                return Response(self_data)
        self_data=self.zip.read_bytes()
        pkg={'download_url':'https://thunderstore.io/package/download/Owner/Mod/1.0.0/',
             'full_name':'Owner-Mod','version':'1.0.0','provider':'Thunderstore','dependencies':[]}
        result=ps.stage_download(pkg,self.base,self.receipts,game_root=self.game['root'],opener=Opener())
        self.assertEqual(result.name,'Owner-Mod-1.0.0.zip')
        self.assertEqual(ps.read_staged(self.receipts)[0]['identity'],'Owner-Mod')

    def test_bepinex_package_requires_manifest_and_plugin(self):
        game={'kind':'bepinex','root':str(self.base/'BepGame')}
        (self.base/'BepGame').mkdir()
        makezip(self.zip,{'name':'TestPackage','version_number':'1.0.0','author':'Owner'},dll=True)
        rec=self.receipt(game_root=str(Path(game['root']).resolve()))
        self.assertEqual(unimod.provider_install_preflight(game,rec)['status'],'Install new')

    def test_incompatible_dep_blocks(self):
        r=self.receipt(dependencies=[{'id':'conflict','type':'incompatible'}])
        self.assertEqual(unimod.provider_install_preflight(self.game,r)['status'],'Blocked')

if __name__=='__main__':unittest.main()
