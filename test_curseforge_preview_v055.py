import unittest
from unittest.mock import patch
import provider_catalogues as p

class CurseForgePreviewTests(unittest.TestCase):
    def test_game_verification_uses_official_id(self):
        calls=[]
        result=p.curseforge_game(432,'approved-key',fetch=lambda url,headers:(calls.append((url,headers)) or {'data':{'id':432,'name':'Minecraft','slug':'minecraft'}}))
        self.assertEqual(result['id'],'432')
        self.assertEqual(result['name'],'Minecraft')
        self.assertEqual(calls[0][0],'https://api.curseforge.com/v1/games/432')
        self.assertEqual(calls[0][1]['x-api-key'],'approved-key')
        self.assertNotIn('approved-key',repr(result))
    def test_wrong_game_id_rejected(self):
        with self.assertRaises(p.ProviderError):
            p.curseforge_game(432,'approved-key',fetch=lambda *_:{'data':{'id':123,'name':'Other'}})
    def test_secret_errors_not_exposed(self):
        with self.assertRaises(p.ProviderError) as ex:
            p.curseforge_game(432,'',fetch=lambda *_:{})
        self.assertNotIn('432',str(ex.exception))
    def test_file_records_strict_game_scope(self):
        entries=[
            {'id':1,'modId':22,'gameId':432,'fileName':'Good.jar','fileLength':1000,'gameVersions':['1.20.1'],'releaseType':1,'downloadUrl':'https://malicious.invalid/a'},
            {'id':2,'modId':22,'gameId':999,'fileName':'WrongGame.jar','fileLength':2},
            {'id':3,'modId':23,'gameId':432,'fileName':'WrongMod.jar','fileLength':2},
            {'id':4,'modId':22,'gameId':432,'fileName':'Bad/Name.jar','fileLength':2},
            {'id':5,'modId':22,'gameId':432,'fileName':'Unavailable.jar','fileLength':2,'isAvailable':False},
        ]
        seen=[]
        result=p.curseforge_files('432/22','approved-key',fetch=lambda url,h:(seen.append((url,h)) or {'data':entries}))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['filename'],'Good.jar')
        self.assertEqual(result[0]['versions'],['1.20.1'])
        self.assertNotIn('downloadUrl',result[0]);self.assertNotIn('malicious.invalid',repr(result))
        self.assertEqual(seen[0][0],'https://api.curseforge.com/v1/mods/22/files?index=0&pageSize=50')
        self.assertNotIn('approved-key',repr(result))
    def test_wrong_identity_rejected_no_request(self):
        for bad in ('432/../../secret','432/0','432/-3','aaa/22','1/2/3'):
            with self.subTest(bad=bad),self.assertRaises(p.ProviderError):
                p.curseforge_files(bad,'approved-key',fetch=lambda *_:self.fail('Unexpected request'))
    def test_cross_game_search_result_rejected(self):
        data={'data':[{'id':5,'gameId':123,'name':'Wrong','links':{'websiteUrl':'https://www.curseforge.com/minecraft/mc-mods/wrong'}},
                      {'id':6,'gameId':432,'name':'Right','links':{'websiteUrl':'https://www.curseforge.com/minecraft/mc-mods/right'}}]}
        results=p.search_curseforge('test',432,'approved-key',fetch=lambda *_:data)
        self.assertEqual([r['identity'] for r in results],['432/6'])
    def test_non_list_response(self):
        with self.assertRaises(p.ProviderError):
            p.curseforge_files('432/22','approved-key',fetch=lambda *_:{'data':'not a list'})

if __name__=='__main__':unittest.main()
