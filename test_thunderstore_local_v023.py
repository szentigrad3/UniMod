import json
import tempfile
import unittest
from pathlib import Path
import unimod

COMMUNITY='valheim'

def package(folder, owner, name, version='1.0.0', url=None):
    folder.mkdir(parents=True)
    (folder/'plugin.dll').write_bytes(b'mock binary')
    if url is None:url=f'https://thunderstore.io/c/valheim/p/{owner}/{name}/'
    (folder/'manifest.json').write_text(json.dumps({'name':name,'author':owner,
                              'version_number':version,'website_url':url}))

def catalogue(owner='Acme',name='RealMod',version='2.0.0',url=None):
    return [{'owner':owner,'name':name,'version':version,
             'url':url if url is not None else f'https://thunderstore.io/c/valheim/p/{owner}/{name}/'}]

class ThunderstoreLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.game={'root':self.tmp.name,'kind':'bepinex','name':'Sample BepInEx'}
        self.root=unimod.mod_root(self.game)

    def test_verified_update_is_read_only(self):
        p=self.root/'Acme-Mod'
        package(p,'Acme','RealMod','1.0.0')
        before=(p/'manifest.json').read_bytes()
        rows=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'Update available')
        self.assertEqual(rows[0]['confidence'],'Verified metadata')
        self.assertEqual(rows[0]['url'],catalogue()[0]['url'])
        self.assertEqual((p/'manifest.json').read_bytes(),before)

    def test_current_and_newer(self):
        p=self.root/'Package'
        package(p,'Acme','RealMod','2.0.0')
        self.assertEqual(unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)[0]['status'],'Current')
        package2=p/'manifest.json'
        data=json.loads(package2.read_text());data['version_number']='3.0.0';package2.write_text(json.dumps(data))
        self.assertEqual(unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)[0]['status'],'Local newer')

    def test_wrong_community_is_not_verified(self):
        package(self.root/'P','Acme','RealMod','1.0.0','https://thunderstore.io/c/lethal-company/p/Acme/RealMod/')
        row=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)[0]
        self.assertEqual(row['status'],'Different community')

    def test_forged_website_is_not_verified(self):
        package(self.root/'P','Acme','RealMod','1.0.0','https://thunderstore.io.evil.example/c/valheim/p/Acme/RealMod/')
        row=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)[0]
        self.assertEqual(row['status'],'Community unverified')
        for bad in ('https://thunderstore.io@evil.example/c/valheim/p/Acme/RealMod/',
                    'http://thunderstore.io/c/valheim/p/Acme/RealMod/',
                    'https://thunderstore.io/c/valheim/p/Acme/RealMod/extra',
                    'https://thunderstore.io:abc/c/valheim/p/Acme/RealMod/'):
            self.assertIsNone(unimod._thunderstore_page_identity(bad))

    def test_external_website_is_unverified(self):
        package(self.root/'P','Acme','RealMod','1.0.0','https://github.com/Acme/RealMod')
        row=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)[0]
        self.assertEqual(row['status'],'Community unverified')

    def test_conflicting_metadata_id(self):
        package(self.root/'P','Acme','RealMod','1.0.0','https://thunderstore.io/c/valheim/p/Other/RealMod/')
        row=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)[0]
        self.assertEqual(row['status'],'Conflicting source ID')

    def test_duplicate_packages_flagged(self):
        package(self.root/'P','Acme','RealMod')
        package(self.root/'Different','Acme','RealMod')
        rows=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['status']=='Multiple local copies' for r in rows))
        self.assertTrue(all(r['copies']==2 for r in rows))

    def test_disabled_package_included(self):
        package(unimod.disabled_root(self.game)/'P','Acme','RealMod')
        rows=unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY)
        self.assertFalse(rows[0]['enabled'])
        self.assertEqual(rows[0]['status'],'Update available')

    def test_missing_catalogue_and_unverified_catalogue_url(self):
        package(self.root/'P','Acme','RealMod')
        self.assertEqual(unimod.thunderstore_installed_report(self.game,[],COMMUNITY)[0]['status'],'Not in catalogue')
        fake=catalogue(url='https://thunderstore.io/c/lethal-company/p/Acme/RealMod/')
        row=unimod.thunderstore_installed_report(self.game,fake,COMMUNITY)[0]
        self.assertEqual(row['status'],'Catalogue URL unverified')
        self.assertEqual(row['url'],'')

    def test_ambiguous_catalogue_and_smapi_not_guessed(self):
        package(self.root/'P','Acme','RealMod')
        rows=unimod.thunderstore_installed_report(self.game,catalogue()*2,COMMUNITY)
        self.assertEqual(rows[0]['status'],'Not in catalogue')
        self.assertEqual(unimod.thunderstore_installed_report({'root':self.tmp.name,'kind':'smapi'},catalogue(),COMMUNITY),[])

    def test_symlink_package_skipped(self):
        actual=Path(self.tmp.name)/'external'
        package(actual,'Acme','RealMod')
        self.root.mkdir(parents=True)
        (self.root/'linked').symlink_to(actual, target_is_directory=True)
        self.assertEqual(unimod.thunderstore_installed_report(self.game,catalogue(),COMMUNITY),[])

    def test_invalid_community_rejected(self):
        with self.assertRaises(ValueError):unimod.thunderstore_installed_report(self.game,catalogue(),'../valheim')

if __name__=='__main__':unittest.main()
