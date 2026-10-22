import hashlib
import io
import zipfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import provider_downloads as pd

_z=io.BytesIO()
with zipfile.ZipFile(_z, 'w') as z: z.writestr('manifest.json','{}')
ZIP=_z.getvalue()

class Response(io.BytesIO):
    def __init__(self,url,body,headers=None):
        super().__init__(body);self.url=url;self.headers=headers or {}
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

class Opener:
    def __init__(self,final,body=ZIP,headers=None):self.final=final;self.body=body;self.headers=headers or {}
    def open(self,req,timeout=30):return Response(self.final,self.body,self.headers)

class FileProviderTests(unittest.TestCase):
    def test_github_versions_and_assets(self):
        url='https://github.com/Maker/Archive/releases/download/v1.5/Archive.zip'
        rows=pd.github_files('Maker/Archive',fetch=lambda u,h:[
          {'draft':True,'tag_name':'v2','assets':[{'name':'dont.zip','size':40,'browser_download_url':url}]},
          {'tag_name':'v1.5','assets':[{'name':'Archive.zip','size':len(ZIP),'browser_download_url':url,'digest':'sha256:'+hashlib.sha256(ZIP).hexdigest()},
                                        {'name':'setup.exe','size':3,'browser_download_url':url.replace('Archive.zip','setup.exe')},
                                        {'name':'Bad.zip','size':30,'browser_download_url':'https://example.invalid/a.zip'},
                                        {'name':'other.zip','size':30,'browser_download_url':url.replace('/Maker/Archive/','/Bad/Archive/')}]}])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['version'],'v1.5')
        self.assertEqual(rows[0]['hashes']['sha256'],hashlib.sha256(ZIP).hexdigest())
        self.assertEqual(rows[0]['compatibility'],'Not verified')
    def test_github_does_not_accept_unsafe_repository(self):
        for repo in ('../bad','a/..','a/b/repo','https://github.com/a/b'):
            with self.subTest(repo=repo),self.assertRaises(pd.DownloadError):pd.github_files(repo,fetch=lambda *_:[])
    def test_modrinth_versions_and_filters(self):
        seen=[]
        url='https://cdn.modrinth.com/data/AA12BB34/versions/VVV/MyMod.jar'
        version={'version_number':'2.0','game_versions':['1.21.1'],'loaders':['fabric'],'dependencies':[{'dependency_type':'required','project_id':'xyz'}],
                 'files':[{'filename':'MyMod.jar','size':len(ZIP),'url':url,'hashes':{'sha1':hashlib.sha1(ZIP).hexdigest()}}]}
        rows=pd.modrinth_files('AA12BB34',loader='fabric',game_version='1.21.1',fetch=lambda u,h:(seen.append(u) or [version]))
        self.assertIn('%5B%22fabric%22%5D',seen[0]);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['game_versions'],['1.21.1']);self.assertEqual(len(rows[0]['dependencies']),1)
        self.assertEqual(pd.modrinth_files('AA12BB34',loader='forge',fetch=lambda *_:[version]),[])
    def test_modrinth_reject_non_cdn(self):
        entries=[{'version_number':'1','game_versions':[],'loaders':[], 'files':[{'filename':'evil.jar','size':99,'url':'https://phishing.example/evil.jar'}]}]
        self.assertEqual(pd.modrinth_files('AA12BB34',fetch=lambda *_:entries),[])
    def test_only_supported_providers(self):
        with self.assertRaises(pd.DownloadError):pd.list_files('CurseForge','123')
    def test_verified_download(self):
        url='https://cdn.modrinth.com/data/AA12BB34/versions/VVV/MyMod.jar'
        rec={'provider':'Modrinth','identity':'AA12BB34','url':url,'filename':'MyMod.jar','size':len(ZIP),'hashes':{'sha512':hashlib.sha512(ZIP).hexdigest()}}
        with tempfile.TemporaryDirectory() as tmp:
            p=pd.download_file(rec,tmp,opener=Opener(url))
            self.assertEqual(p.read_bytes(),ZIP)
            with self.assertRaises(FileExistsError):pd.download_file(rec,tmp,opener=Opener(url))
    def test_partial_download_is_removed(self):
        url='https://cdn.modrinth.com/data/A/versions/V/MyMod.zip'
        rec={'provider':'Modrinth','identity':'A','url':url,'filename':'MyMod.zip','size':len(ZIP),'hashes':{}}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(pd.DownloadError):pd.download_file(rec,tmp,opener=Opener(url,b'<html>error</html>'))
            self.assertFalse(list(Path(tmp).iterdir()))
    def test_bad_hash_is_removed(self):
        url='https://cdn.modrinth.com/data/A/versions/V/MyMod.zip'
        rec={'provider':'Modrinth','identity':'A','url':url,'filename':'MyMod.zip','size':len(ZIP),'hashes':{'sha1':'0'*40}}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(pd.DownloadError):pd.download_file(rec,tmp,opener=Opener(url))
            self.assertFalse(list(Path(tmp).iterdir()))
    def test_redirect_restriction(self):
        h=pd._Redirects('GitHub')
        with self.assertRaises(pd.DownloadError):h.redirect_request(None,None,302,'',{},'https://evil.invalid/archive.zip')
        self.assertTrue(pd._safe_url('https://release-assets.githubusercontent.com/obj/abcdef','GitHub'))
    def test_reject_path_and_creds(self):
        for name in ('../../evil.zip','evil.exe','.hidden.zip','a\\b.zip','x\n.jar'):
            with self.subTest(name=name),self.assertRaises(pd.DownloadError):pd._filename(name)
        self.assertFalse(pd._safe_url('https://username:pass@cdn.modrinth.com/data/x/file.jar','Modrinth'))
    def test_file_size_limit(self):
        url='https://cdn.modrinth.com/data/A/versions/V/MyMod.zip'
        rec={'provider':'Modrinth','identity':'A','url':url,'filename':'MyMod.zip','size':pd.MAX_FILE+1,'hashes':{}}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(pd.DownloadError):
            pd.download_file(rec,tmp,opener=Opener(url))

if __name__=='__main__':unittest.main()
