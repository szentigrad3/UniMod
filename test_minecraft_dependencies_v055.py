"""All provider metadata and downloads are mocked; no real Minecraft profile touched."""
import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import minecraft_dependencies as dep
import minecraft_profiles as mc


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.instance=self.root/'profiles'/'A';game=self.instance/'.minecraft';self.mods=game/'mods'
        self.mods.mkdir(parents=True)
        (self.instance/'mmc-pack.json').write_text(json.dumps({'components':[
            {'uid':'net.minecraft','version':'1.21.1'},
            {'uid':'net.fabricmc.fabric-loader','version':'0.16.9'}]}))
        self.journal=self.root/'installed.json';self.stage=self.root/'staged.json';self.recovery=self.root/'backups'
        self.parent=self.root/'Parent.jar';self._jar(self.parent)
        self.parent_receipt=self._receipt(self.parent,'PARENT12','parentver',[])
        self.rows={};self.byver={};self.filedata={}

    def _jar(self,path,content=b'ok'):
        with zipfile.ZipFile(path,'w') as z:z.writestr('fabric.mod.json',content)

    def _receipt(self,path,pid,version,deps):
        return {'provider':'Modrinth','identity':pid,'version_id':version,'version':'1.0',
                'archive':str(path),'filename':path.name,'bytes':path.stat().st_size,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'game_versions':['1.21.1'],'loaders':['fabric'],
                'dependencies':deps,'game_root':''}

    def _required(self,pid,version=''):
        return {'type':'required','id':pid,'project_id':pid,'version_id':version}

    def _add(self,pid,version=None,dependencies=None,content=None,version_files=None):
        version=version or 'V'+pid
        src=self.root/(pid+'.jar');self._jar(src,content or pid.encode())
        url='https://cdn.modrinth.com/data/'+pid+'/versions/'+version+'/'+pid+'.jar'
        download={'filename':src.name,'url':url,'size':src.stat().st_size,
                  'hashes':{'sha1':hashlib.sha1(src.read_bytes()).hexdigest(),
                            'sha512':hashlib.sha512(src.read_bytes()).hexdigest()},'primary':True}
        row={'id':version,'project_id':pid,'version_number':'1.0','game_versions':['1.21.1'],
             'loaders':['fabric'],'dependencies':[{'project_id':r.get('project_id'),'version_id':r.get('version_id'),
                                                   'dependency_type':r['type']} for r in (dependencies or [])],
             'files':version_files if version_files is not None else [download]}
        self.rows[pid]=[row];self.byver[version]=row;self.filedata[url]=src
        return row

    def _fetch(self,url,headers):
        if '/v2/version/' in url:return self.byver[url.rsplit('/',1)[-1]]
        pid=url.split('/v2/project/')[1].split('/')[0]
        return self.rows[pid]

    def _download(self,record,directory):
        src=self.filedata[record['url']]
        dest=Path(directory)/record['filename'];shutil.copyfile(src,dest)
        return dest

    def _plan(self):
        return dep.plan_dependencies(self.parent_receipt,self.instance,self.journal,fetch=self._fetch)

    def test_no_dependencies_offline(self):
        plan=dep.plan_dependencies(self.parent_receipt,self.instance,self.journal,
                                   fetch=lambda *_:self.fail('unexpected provider request'))
        self.assertEqual(plan['downloads'],0)

    def test_pinned_dependency_resolution(self):
        self._add('LIB12345','VLIB123')
        self.parent_receipt['dependencies']=[self._required('LIB12345','VLIB123')]
        plan=self._plan()
        self.assertEqual(plan['dependencies'][0]['version_id'],'VLIB123')
        self.assertEqual(plan['downloads'],1)
        self.assertFalse(self.mods.joinpath('LIB12345.jar').exists())

    def test_multi_step_dependency_order(self):
        self._add('CORE1234')
        self._add('UTIL1234',dependencies=[self._required('CORE1234')])
        self.parent_receipt['dependencies']=[self._required('UTIL1234')]
        plan=self._plan()
        self.assertEqual([d['identity'] for d in plan['dependencies']],['CORE1234','UTIL1234'])

    def test_install_after_explicit_plan(self):
        self._add('CORE1234')
        self._add('UTIL1234',dependencies=[self._required('CORE1234')])
        self.parent_receipt['dependencies']=[self._required('UTIL1234')]
        plan=self._plan()
        result=dep.install_plan(plan,self.root/'downloads',self.stage,self.journal,self.recovery,downloader=self._download)
        self.assertEqual(result['dependency_count'],2)
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()),['CORE1234.jar','Parent.jar','UTIL1234.jar'])
        self.assertEqual(len(mc.installed_receipts(self.journal)),3)

    def test_existing_verified_dependency_skipped(self):
        self._add('CORE1234')
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        p=self._plan();dep.install_plan(p,self.root/'downloads',self.stage,self.journal,self.recovery,downloader=self._download)
        # Reinstall parent different version; existing CORE not downloaded again.
        self._jar(self.parent,b'updated')
        self.parent_receipt=self._receipt(self.parent,'PARENT12','new-parent',self.parent_receipt['dependencies'])
        p=self._plan()
        self.assertEqual(p['downloads'],0)
        dep.install_plan(p,self.root/'downloads',self.stage,self.journal,self.recovery,downloader=self._download)
        self.assertEqual(len(mc.installed_receipts(self.journal)),2)

    def test_same_project_by_version_alias_is_deduplicated(self):
        self._add('CORE1234','VERSION1')
        self.parent_receipt['dependencies']=[self._required('CORE1234'),
              {'type':'required','version_id':'VERSION1','project_id':'','id':'VERSION1'}]
        p=self._plan()
        self.assertEqual([r['identity'] for r in p['dependencies']],['CORE1234'])

    def test_self_dependency_by_version_alias_rejected(self):
        self._add('CORE1234','VERSION1',dependencies=[{'type':'required','version_id':'VERSION1','project_id':'','id':'VERSION1'}])
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        with self.assertRaisesRegex(dep.ResolutionError,'Circular'):
            self._plan()

    def test_bad_provider_bytes_never_installed(self):
        self._add('CORE1234')
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        def bad(record,folder):
            p=Path(folder)/record['filename'];p.write_bytes(b'bad');return p
        with self.assertRaisesRegex(dep.ResolutionError,'Downloaded dependency hash'):
            dep.install_plan(self._plan(),self.root/'downloads',self.stage,self.journal,self.recovery,downloader=bad)
        self.assertFalse(list(self.mods.iterdir()))
        self.assertFalse(self.journal.exists())

    def test_cycle_rejected(self):
        self._add('CORE1234',dependencies=[self._required('UTIL1234')])
        self._add('UTIL1234',dependencies=[self._required('CORE1234')])
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        with self.assertRaisesRegex(dep.ResolutionError,'Circular'):
            self._plan()

    def test_conflicting_pinned_versions_rejected(self):
        self._add('COMMON12','VC1');self._add('COMMON12','VC2')
        self._add('CORE1234',dependencies=[self._required('COMMON12','VC1')])
        self._add('UTIL1234',dependencies=[self._required('COMMON12','VC2')])
        self.parent_receipt['dependencies']=[self._required('CORE1234'),self._required('UTIL1234')]
        with self.assertRaisesRegex(dep.ResolutionError,'Conflicting'):
            self._plan()

    def test_pinned_mismatched_project_rejected(self):
        self._add('CORE1234','KNOWN123')
        self.parent_receipt['dependencies']=[self._required('WRONG123','KNOWN123')]
        with self.assertRaisesRegex(dep.ResolutionError,'different Modrinth project'):
            self._plan()

    def test_pinned_incompatible_loader_rejected(self):
        self._add('CORE1234','KNOWN123')
        self.byver['KNOWN123']['loaders']=['forge']
        self.parent_receipt['dependencies']=[self._required('CORE1234','KNOWN123')]
        with self.assertRaisesRegex(dep.ResolutionError,'loader'):
            self._plan()

    def test_missing_provider_sha512_rejected(self):
        row=self._add('CORE1234')
        row['files'][0]['hashes']={'sha1':'0'*40}
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        with self.assertRaisesRegex(dep.ResolutionError,'No verifiable'):
            self._plan()

    def test_untrusted_host_rejected(self):
        row=self._add('CORE1234')
        row['files'][0]['url']='https://evil.example/CORE1234.jar'
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        with self.assertRaisesRegex(dep.ResolutionError,'No verifiable'):
            self._plan()

    def test_ambiguous_files_rejected(self):
        row=self._add('CORE1234')
        row['files'].append(dict(row['files'][0],filename='second.jar',primary=True))
        self.parent_receipt['dependencies']=[self._required('CORE1234','VCORE1234')]
        with self.assertRaisesRegex(dep.ResolutionError,'equally ranked'):
            self._plan()

    def test_unknown_dependency_blocked(self):
        self.parent_receipt['dependencies']=[{'type':'unknown','id':'X'}]
        with self.assertRaisesRegex(dep.ResolutionError,'unknown dependency'):
            self._plan()

    def test_download_failure_does_not_modify_instance(self):
        self._add('CORE1234')
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        def broken(*_):raise RuntimeError('network failed')
        with self.assertRaisesRegex(RuntimeError,'network failed'):
            dep.install_plan(self._plan(),self.root/'downloads',self.stage,self.journal,self.recovery,downloader=broken)
        self.assertFalse(list(self.mods.iterdir()));self.assertFalse(self.journal.exists())

    def test_failed_parent_install_rolls_back_installed_dependency(self):
        self._add('CORE1234')
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        original=mc.install_reviewed
        def fail_parent(receipt,*args,**kwargs):
            if receipt['identity']=='PARENT12':raise OSError('simulated install error')
            return original(receipt,*args,**kwargs)
        with patch.object(mc,'install_reviewed',side_effect=fail_parent):
            with self.assertRaisesRegex(OSError,'simulated'):
                dep.install_plan(self._plan(),self.root/'downloads',self.stage,self.journal,self.recovery,downloader=self._download)
        self.assertEqual(list(self.mods.iterdir()),[])
        self.assertFalse(self.journal.exists())

    def test_changed_cached_download_rejected(self):
        self._add('CORE1234')
        self.parent_receipt['dependencies']=[self._required('CORE1234')]
        plan=self._plan()
        # Stage but fail before install, then alter cache.
        with patch.object(mc,'install_reviewed',side_effect=OSError('interrupted')):
            with self.assertRaisesRegex(OSError,'interrupted'):
                dep.install_plan(plan,self.root/'downloads',self.stage,self.journal,self.recovery,downloader=self._download)
        cached=self.root/'downloads'/'CORE1234'/'VCORE1234'/'CORE1234.jar'
        cached.write_bytes(b'tampered')
        with self.assertRaisesRegex(dep.ResolutionError,'Cached dependency changed'):
            dep.install_plan(plan,self.root/'downloads',self.stage,self.journal,self.recovery,downloader=self._download)
        self.assertFalse(list(self.mods.iterdir()))

if __name__=='__main__':unittest.main()
