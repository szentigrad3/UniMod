"""Offline exact-modfile, signed URL, journal, and installer checks."""
import hashlib
import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import modio_files as m
import provider_downloads as d
import provider_staging as s
import unimod

KEY='local-only-mock-key'
USER='456'
GAME='123'
MOD='77'
FILE='88'
URL=f'https://u-{USER}.modapi.io/v1/games/{GAME}/mods/{MOD}/files/{FILE}/download/abc123XYZtoken'
bio=io.BytesIO()
with zipfile.ZipFile(bio,'w') as z:
    z.writestr('Example/manifest.json',json.dumps({'UniqueID':'Test.Modio','Name':'Modio Example','Version':'1.2.0'}))
ZIP=bio.getvalue()

def datum(**opts):
    result={'id':int(FILE),'mod_id':int(MOD),'game_id':int(GAME),'filename':'Example.zip',
        'version':'1.2.0','filesize':len(ZIP),'filehash':{'md5':hashlib.md5(ZIP).hexdigest()},
        'download':{'binary_url':URL,'date_expires':int(time.time())+600},
        'virus_status':1,'virus_positive':0}
    result.update(opts)
    return result

class Response(io.BytesIO):
    def __init__(self,url,body):super().__init__(body);self.url=url;self.headers={}
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def geturl(self):return self.url

class Opener:
    def __init__(self,url,body):self.url=url;self.body=body
    def open(self,req,timeout=30):return Response(self.url,self.body)

class ModioDownloadTests(unittest.TestCase):
    def test_listing_uses_user_path_and_key(self):
        called=[]
        rec=m.list_modfiles(f'{GAME}/{MOD}',user_id=USER,api_key=KEY,
            fetch=lambda u,h:(called.append((u,h)) or {'data':[datum()]}))
        self.assertEqual(rec[0]['identity'],f'{GAME}/{MOD}')
        self.assertEqual(rec[0]['version_id'],FILE)
        self.assertIn(f'u-{USER}.modapi.io/v1/games/{GAME}/mods/{MOD}/files?',called[0][0])
        self.assertEqual(rec[0]['hashes']['md5'],hashlib.md5(ZIP).hexdigest())
        self.assertNotIn(KEY,str(rec))
    def test_reject_wrong_game_mod_file_and_malformed_urls(self):
        bad=[{'game_id':999},{'mod_id':12},{'filehash':{}},{'virus_positive':1},
             {'filename':'../bad.zip'},{'filename':'bad.exe'},
             {'download':{'binary_url':'https://evil.invalid/payload.zip'}},
             {'download':{'binary_url':URL+'?api_key='+KEY}},
             {'download':{'binary_url':URL.replace('/mods/77/','/mods/13/')}},
             {'download':{'binary_url':URL,'date_expires':time.time()-1}}]
        for change in bad:
            with self.subTest(change=change):
                self.assertEqual(m.list_modfiles(f'{GAME}/{MOD}',user_id=USER,api_key=KEY,fetch=lambda *_:{'data':[datum(**change)]}),[])
    def test_platform_filtering(self):
        linux={'platform':'LINUX','status':1};denied={'platform':'LINUX','status':2}
        self.assertEqual(len(m.list_modfiles('123/77',user_id=USER,api_key=KEY,fetch=lambda *_:{'data':[datum(platforms=[linux])]})),1)
        self.assertEqual(m.list_modfiles('123/77',user_id=USER,api_key=KEY,fetch=lambda *_:{'data':[datum(platforms=[denied])]}),[])
    def test_expired_refresh_and_changed_bytes_blocked(self):
        selected=m._parse_modfile(datum(),'123','77')
        fresh=m.refresh_selected(selected,user_id=USER,api_key=KEY,fetch=lambda *_:datum())
        self.assertEqual(fresh['url'],URL)
        for change in [{'version':'5.0'},{'filehash':{'md5':'0'*32}},{'filename':'Other.zip'},{'filesize':len(ZIP)+1}]:
            with self.subTest(change=change),self.assertRaises(m.ModioError):
                m.refresh_selected(selected,user_id=USER,api_key=KEY,fetch=lambda *_:datum(**change))
    def test_hash_and_redirect_enforced(self):
        selected=m._parse_modfile(datum(),'123','77')
        with tempfile.TemporaryDirectory() as temp:
            p=m.download_selected(selected,temp,user_id=USER,api_key=KEY,fetch=lambda *_:datum(),opener=Opener(URL,ZIP))
            self.assertEqual(p.read_bytes(),ZIP)
            p.unlink()
            with self.assertRaises(d.DownloadError):
                m.download_selected(selected,temp,user_id=USER,api_key=KEY,fetch=lambda *_:datum(),opener=Opener(URL,b'not a zip'))
            self.assertEqual(list(Path(temp).iterdir()),[])
            with self.assertRaises(d.DownloadError):
                m.download_selected(selected,temp,user_id=USER,api_key=KEY,fetch=lambda *_:datum(),opener=Opener('https://private.example/file.zip',ZIP))
            self.assertEqual(list(Path(temp).iterdir()),[])
    def test_stage_receipt_and_managed_install(self):
        selected=m._parse_modfile(datum(),'123','77')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'Downloads').mkdir();(root/'Stardew'/'Mods').mkdir(parents=True)
            journal=root/'stage.json';game={'kind':'smapi','name':'Stardew Valley','root':str(root/'Stardew')}
            stage=s.stage_download(selected,root/'Downloads',journal,game_root=game['root'],
                downloader=lambda rec,folder:m.download_selected(rec,folder,user_id=USER,api_key=KEY,
                    fetch=lambda *_:datum(),opener=Opener(URL,ZIP)))
            receipt=s.read_staged(journal)[0]
            self.assertEqual(receipt['identity'],f'{GAME}/{MOD}')
            self.assertEqual(receipt['version_id'],FILE)
            self.assertNotIn(KEY,journal.read_text())
            self.assertNotIn(URL,journal.read_text())
            self.assertEqual(unimod.provider_install_preflight(game,receipt)['status'],'Install new')
            with patch.object(unimod,'INSTALL_RECEIPTS',root/'install.json'):
                first=unimod.provider_install_reviewed(game,receipt)
                self.assertEqual(first['action'],'installed')
                self.assertTrue((root/'Stardew'/'Mods'/'Example'/'manifest.json').exists())
    def test_managed_existing_mod_update_with_backup(self):
        selected=m._parse_modfile(datum(),'123','77')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'Downloads').mkdir()
            local=root/'Stardew'/'Mods'/'Example';local.mkdir(parents=True)
            (local/'manifest.json').write_text(json.dumps({'UniqueID':'Test.Modio','Name':'Modio Example','Version':'0.8.0'}))
            (local/'old.txt').write_text('preserve in recovery')
            game={'kind':'smapi','name':'Stardew Valley','root':str(root/'Stardew')}
            receipt_file=root/'stage.json'
            s.stage_download(selected,root/'Downloads',receipt_file,game_root=game['root'],
                downloader=lambda rec,folder:m.download_selected(rec,folder,user_id=USER,api_key=KEY,
                    fetch=lambda *_:datum(),opener=Opener(URL,ZIP)))
            rec=s.read_staged(receipt_file)[0]
            self.assertEqual(unimod.provider_install_preflight(game,rec)['status'],'Update existing')
            with patch.object(unimod,'INSTALL_RECEIPTS',root/'install.json'),patch.object(unimod,'APP',root/'config'):
                result=unimod.provider_install_reviewed(game,rec)
            self.assertEqual(result['action'],'updated')
            self.assertEqual(json.loads((local/'manifest.json').read_text())['Version'],'1.2.0')
            self.assertTrue(result['backup'])
            self.assertTrue(Path(result['backup']).exists())
            self.assertEqual((Path(result['backup'])/'old.txt').read_text(),'preserve in recovery')

    def test_invalid_identity_and_key(self):
        for ident in ['123/../7','12/a','123/7/6','https://mod.io/mod']:
            with self.assertRaises(m.ModioError):m.list_modfiles(ident,user_id=USER,api_key=KEY)
        with self.assertRaises(m.ModioError):m.list_modfiles('123/77',user_id=USER,api_key='')

if __name__=='__main__':unittest.main()
