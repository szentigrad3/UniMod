import unittest
from unimod import mod_family_groups

class FamilyGroupingTests(unittest.TestCase):
    def setUp(self):
        names=[
            ('Stardew Valley Expanded','mod.sve.cp'),
            ('Stardew Valley Expanded','mod.sve.code'),
            ('Stardew Valley Expanded Farm Type Manager','mod.sve.ftm'),
            ('Ridgeside Village [SMAPI component]','mod.rsv.code'),
            ('Ridgeside Village [Content Patcher component]','mod.rsv.cp'),
            ('Unrelated Mod','author.unrelated'),
            ('Unrelated Mod Extra','author.unrelatedextra'),
        ]
        self.mods=[{'name':name,'uid':uid,'path':f'/f{i}','enabled':True} for i,(name,uid) in enumerate(names)]
    def test_related_components_get_one_parent_not_merged(self):
        groups=mod_family_groups(self.mods)
        grouped={g['name']:g for g in groups}
        self.assertEqual(len(groups),4)
        self.assertEqual([m['uid'] for m in grouped['Stardew Valley Expanded']['members']],
                         ['mod.sve.cp','mod.sve.code','mod.sve.ftm'])
        self.assertEqual(len(grouped['Ridgeside Village']['indices']),2)
        self.assertFalse(grouped['Unrelated Mod']['grouped'])
        self.assertFalse(grouped['Unrelated Mod Extra']['grouped'])
    def test_duplicate_id_flagged_not_silenced(self):
        mods=[{**m} for m in self.mods[:2]]
        mods[1]['uid']=mods[0]['uid']
        groups=mod_family_groups(mods)
        self.assertEqual(len(groups),1)
        self.assertTrue(groups[0]['duplicate_ids'])
        self.assertEqual(len(groups[0]['members']),2)
    def test_similar_names_do_not_get_grouped_without_component_markers(self):
        mods=[{'name':'Magic','uid':'a','path':'/1'},
              {'name':'Magic on Steroids','uid':'b','path':'/2'}]
        self.assertEqual(len(mod_family_groups(mods)),2)
    def test_never_modifies_inputs(self):
        before=[dict(m) for m in self.mods]
        mod_family_groups(self.mods)
        self.assertEqual(self.mods,before)

if __name__=='__main__':unittest.main()
