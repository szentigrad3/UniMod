import unittest
from unimod import thunderstore_catalogue

class CatalogueTests(unittest.TestCase):
    def test_valid_catalogue(self):
        def fetch(url):
            self.assertEqual(url,'https://thunderstore.io/c/valheim/api/v1/package/')
            return [{'owner':'Example','name':'BetterGame','total_downloads':42,
                     'versions':[{'version_number':'1.2.0','description':'Quality of life', 'dependencies':['Example-Core-1.0.0']}],
                     'package_url':'https://thunderstore.io/c/valheim/p/Example/BetterGame/'}]
        r=thunderstore_catalogue('valheim',fetch)
        self.assertEqual(r[0]['version'],'1.2.0')
        self.assertEqual(r[0]['dependencies'],['Example-Core-1.0.0'])
    def test_invalid_slug(self):
        for slug in ('../x','test/a','https://example.org',''):
            with self.assertRaises(ValueError):thunderstore_catalogue(slug,lambda _:[])
    def test_unexpected_data(self):
        with self.assertRaises(ValueError):thunderstore_catalogue('valheim',lambda _: {})
if __name__=='__main__': unittest.main()
