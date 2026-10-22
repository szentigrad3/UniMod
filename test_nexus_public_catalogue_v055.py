"""Nexus metadata stays read-only, game-scoped, and authorization-free."""
import json
import unittest
import provider_catalogues as p

class NexusDiscovery(unittest.TestCase):
    def test_game_scoped_results_and_headers(self):
        seen=[]
        def provider(url,headers,body):
            request=json.loads(body)
            seen.append((url,headers,request))
            return {'data':{'mods':{'nodes':[
                {'modId':162,'name':'Keeper Co-op','summary':'multiplayer','version':'1.1','downloads':154,
                 'uploader':{'name':'Creator'},'game':{'domainName':'graveyardkeeper'}},
                {'modId':200,'name':'Wrong game', 'game':{'domainName':'graveyardkeeper2'}},
                {'modId':'../123','name':'Invalid ID','game':{'domainName':'graveyardkeeper'}},
                {'modId':888,'name':'Missing game'},
            ]}}}
        found=p.search('Nexus Mods','Keeper Co-op',community='graveyardkeeper',fetch=provider)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['url'],'https://www.nexusmods.com/graveyardkeeper/mods/162')
        self.assertEqual(found[0]['author'],'Creator')
        self.assertEqual(seen[0][0],p.NEXUS_GRAPHQL_ENDPOINT)
        self.assertEqual(seen[0][1]['Application-Name'],'UniMod')
        self.assertNotIn('Authorization',seen[0][1]);self.assertNotIn('api_key',str(seen))
        self.assertEqual(seen[0][2]['variables']['filter']['gameDomainName'][0]['value'],'graveyardkeeper')
        self.assertEqual(seen[0][2]['variables']['filter']['nameStemmed'][0]['value'],'Keeper Co-op')

    def test_graveyard_keeper_2_separate(self):
        r=p.search_nexus('Keeper','graveyardkeeper2',fetch=lambda _u,_h,_b:
                         {'data':{'mods':{'nodes':[{'modId':8,'name':'GK 2','game':{'domainName':'graveyardkeeper2'}},
                         {'modId':9,'name':'GK 1','game':{'domainName':'graveyardkeeper'}}]}}})
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['url'],'https://www.nexusmods.com/graveyardkeeper2/mods/8')

    def test_invalid_scope(self):
        for domain in ('../graveyardkeeper','graveyardkeeper/mods','', 'Graveyard Keeper', 'graveyardkeeper\n'):
            with self.subTest(domain=domain),self.assertRaises(p.ProviderError):
                p.search_nexus('Keeper',domain,fetch=lambda *_:{})

    def test_query_errors_not_silently_no_results(self):
        with self.assertRaisesRegex(p.ProviderError,'rejected'):
            p.search_nexus('Keeper','graveyardkeeper',fetch=lambda *_:{'errors':[{'message':'Authentication failed'}]})

    def test_unexpected_results_fail_closed(self):
        for data in ({'data':{}}, {'data':{'mods':{'nodes':'bad'}}}, {'data':{'mods':None}}):
            with self.subTest(data=data),self.assertRaises(p.ProviderError):
                p.search_nexus('Keeper','graveyardkeeper',fetch=lambda *_:data)

    def test_no_auto_assignment(self):
        x=p.search_nexus('keeper','graveyardkeeper',fetch=lambda *_:
             {'data':{'mods':{'nodes':[{'modId':15,'name':'Keeper','game':{'domainName':'graveyardkeeper'}}]}}})
        self.assertNotIn('installed',x[0]);self.assertNotIn('matched',x[0])

if __name__=='__main__': unittest.main()
