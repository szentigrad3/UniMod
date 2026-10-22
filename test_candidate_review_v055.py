import unittest
import candidate_review as r

BASE='https://www.nexusmods.com/graveyardkeeper/mods/'
def entry(name,mid,domain='graveyardkeeper'):
    return {'provider':'Nexus Mods','title':name,'author':'Unverified',
            'url':f'https://www.nexusmods.com/{domain}/mods/{mid}','identity':f'{domain}/{mid}',
            'version':'','description':''}

class ReviewTests(unittest.TestCase):
    def test_dll_pascal_case(self):
        self.assertEqual(r.terms('LongerDays.dll'),frozenset({'longer','days'}))
        self.assertEqual(r.review_hint('Longer Days',entry('Longer Days',1),'graveyardkeeper')['band'],4)
    def test_stable_sort_and_no_auto_link(self):
        items=[entry('Unrelated game assistant',1),entry('Longer Days improved',2),entry('Longer Days',3),entry('Longer Days',4)]
        before=[dict(x) for x in items]
        out=r.order_for_review('Longer Days',items,game_domain='graveyardkeeper')
        self.assertEqual([x['identity'] for x in out],['graveyardkeeper/3','graveyardkeeper/4','graveyardkeeper/2','graveyardkeeper/1'])
        self.assertTrue(all('unverified' in x['review_hint'].lower() or 'inspect' in x['review_hint'].lower() for x in out))
        self.assertEqual(items,before)
        self.assertFalse(any(x.get('approved') for x in out))
    def test_cross_game_link_no_match_even_same_name(self):
        bad=entry('Longer Days',3,'graveyardkeeper2')
        self.assertEqual(r.review_hint('Longer Days',bad,'graveyardkeeper')['band'],0)
        self.assertIn('Different Nexus game',r.review_hint('Longer Days',bad,'graveyardkeeper')['hint'])
    def test_forged_hosts_and_path_queries_rejected(self):
        for url in (BASE+'3?key=xx','https://www.nexusmods.com.evil/graveyardkeeper/mods/3',
                    BASE+'3/../../graveyardkeeper2/mods/4','http://www.nexusmods.com/graveyardkeeper/mods/3'):
            row=entry('Longer Days',3);row['url']=url
            self.assertEqual(r.review_hint('Longer Days',row,'graveyardkeeper')['band'],0)
    def test_unicode_and_noise(self):
        self.assertEqual(r.terms('ＢｅｔｔｅｒCrafting MOD'),frozenset({'better','crafting'}))
        self.assertEqual(r.terms('Graveyard Keeper 2 BepInEx'),frozenset())
    def test_empty_and_non_nexus(self):
        self.assertEqual(r.review_hint('a',entry('mod',1))['band'],1)
        self.assertEqual(r.review_hint('More Items',{'provider':'GitHub','title':'More Items','url':'https://github.com/a/b'},'graveyardkeeper')['band'],4)

if __name__=='__main__':unittest.main()
