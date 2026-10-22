import unittest, smapi_catalogue

MOD={'uid':'Example.Foo','version':'1.2.0','update_keys':[]}

class NewResolverTests(unittest.TestCase):
    def test_suggested_official_page_exact_id(self):
        def response(url,payload):
            self.assertEqual(payload['apiVersion'],'4.5.2')
            return [{'id':'Example.Foo','metadata':{'id':[]},
                     'suggestedUpdate':{'url':'https://www.nexusmods.com/stardewvalley/mods/1245'}}]
        self.assertEqual(smapi_catalogue.resolve_smapi_ids([MOD],fetch=response)['example.foo']['nexus_id'],'1245')

    def test_cross_host_not_accepted(self):
        def response(url,payload):
            return [{'id':'Example.Foo','metadata':{},'suggestedUpdate':
                     {'url':'https://www.nexusmods.com.evil.example/stardewvalley/mods/1245'}}]
        self.assertEqual(smapi_catalogue.resolve_smapi_ids([MOD],fetch=response),{})

    def test_conflicting_metadata_rejected(self):
        def response(url,payload):
            return [{'id':'Example.Foo','metadata':{'nexusID':1245},'suggestedUpdate':
                     {'url':'https://www.nexusmods.com/stardewvalley/mods/5467'}}]
        self.assertEqual(smapi_catalogue.resolve_smapi_ids([MOD],fetch=response),{})

    def test_empty_catalogue_diagnostics(self):
        out=smapi_catalogue.resolve_smapi_ids([MOD],fetch=lambda *_: [],diagnostics=True)
        self.assertEqual(out['matches'],{})
        self.assertEqual(out['requested'],1)
        self.assertEqual(out['returned'],0)

    def test_no_nexus_has_diagnostic(self):
        out=smapi_catalogue.resolve_smapi_ids([MOD],fetch=lambda *_: [{'id':'Example.Foo','metadata':{'id':['Example.Foo']}}],diagnostics=True)
        self.assertEqual(out['no_nexus'],1)
        self.assertEqual(out['matches'],{})

if __name__=='__main__':unittest.main()
