import tempfile, unittest
from pathlib import Path
import unimod

class SnapshotTests(unittest.TestCase):
    def test_added_removed_updated_toggle_and_identity(self):
        old=[dict(name='A',uid='a',version='1.0',enabled=True,relative='A'),
             dict(name='B',uid='b',version='1',enabled=True,relative='pack/B'),
             dict(name='C',uid='c',version='2',enabled=True,relative='C'),
             dict(name='D',uid='d',version='1',enabled=True,relative='D'),
             dict(name='F',uid='f',version='1',enabled=True,relative='F')]
        new=[dict(name='A',uid='a',version='1.1',enabled=True,relative='A'),
             dict(name='C',uid='c',version='2',enabled=False,relative='C'),
             dict(name='D',uid='newid',version='1',enabled=True,relative='D'),
             dict(name='E',uid='e',version='1',enabled=True,relative='E'),
             dict(name='F',uid='f',version='1',enabled=True,relative='F')]
        changes=unimod.compare_snapshot({'mods':unimod.snapshot_records(old)},new)
        self.assertEqual({x['change'] for x in changes}, {'Added','Missing','Version changed','Disabled','Identity changed'})
        self.assertEqual(len(changes),5)
    def test_saved_baseline_survives_reload(self):
        with tempfile.TemporaryDirectory() as root:
            old=unimod.SNAPSHOTS
            try:
                unimod.SNAPSHOTS=Path(root)
                game={'root':root,'name':'test','kind':'smapi'}
                mods=[dict(name='A',uid='x',version='1.0',enabled=True,relative='A')]
                unimod.save_snapshot(game,mods)
                saved=unimod.load_snapshot(game)
                self.assertEqual([],unimod.compare_snapshot(saved,mods))
                self.assertEqual('Version changed',unimod.compare_snapshot(saved,[dict(mods[0],version='2.0')])[0]['change'])
            finally:unimod.SNAPSHOTS=old
if __name__=='__main__':unittest.main()
