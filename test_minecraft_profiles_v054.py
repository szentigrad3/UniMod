"""Offline tests for exact Prism/MultiMC Minecraft profile installs."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import minecraft_profiles as mc
import provider_downloads
import provider_staging

class MinecraftProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.profile=self.base/'instances'/'Test';self.profile.mkdir(parents=True)
        self.game=self.profile/'.minecraft';self.mods=self.game/'mods';self.mods.mkdir(parents=True)
        self.pack=self.profile/'mmc-pack.json'
        self.set_pack()
        self.archive=self.base/'example.jar'
        self.makejar(self.archive)
        self.journal=self.base/'install-receipts.json'
        self.recovery=self.base/'backups'
        self.receipt=self.make_receipt()

    def set_pack(self,game='1.21.1',loader='net.fabricmc.fabric-loader',components=None):
        parts=components if components is not None else [{'uid':'net.minecraft','version':game},{'uid':loader,'version':'0.16.9'}]
        self.pack.write_text(json.dumps({'formatVersion':1,'components':parts}))

    def makejar(self,path,content=b'entry'):
        with zipfile.ZipFile(path,'w') as z:z.writestr('fabric.mod.json',content)

    def make_receipt(self,**options):
        base={'provider':'Modrinth','identity':'AAABBB123','filename':self.archive.name,
            'archive':str(self.archive),'bytes':self.archive.stat().st_size,
            'sha256':hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            'version':'2.0','version_id':'version123','game_versions':['1.21.1'],
            'loaders':['fabric'],'dependencies':[],'game_root':''}
        base.update(options);return base

    def test_prism_profile_recognition(self):
        out=mc.inspect_instance(self.profile)
        self.assertEqual((out['version'],out['loader']),('1.21.1','fabric'))
        self.assertEqual(out['mods'],str(self.mods))

    def test_loader_variants(self):
        for uid,loader in mc.LOADER_COMPONENTS.items():
            self.set_pack(loader=uid)
            self.assertEqual(mc.inspect_instance(self.profile)['loader'],loader)

    def test_no_loader_or_multiple_loaders_rejected(self):
        self.set_pack(components=[{'uid':'net.minecraft','version':'1.21.1'}])
        with self.assertRaises(mc.MinecraftError):mc.inspect_instance(self.profile)
        self.set_pack(components=[{'uid':'net.minecraft','version':'1.21.1'},
          {'uid':'net.fabricmc.fabric-loader','version':'0.16'},
          {'uid':'net.minecraftforge','version':'47.0'}])
        with self.assertRaises(mc.MinecraftError):mc.inspect_instance(self.profile)

    def test_symlink_instance_rejected(self):
        link=self.base/'instance-alias';link.symlink_to(self.profile, target_is_directory=True)
        with self.assertRaisesRegex(mc.MinecraftError,'symlink'):mc.inspect_instance(link)

    def test_wrong_version_loader_block(self):
        with self.assertRaisesRegex(mc.MinecraftError,'does not list support for Minecraft'):
            mc.preflight(self.make_receipt(game_versions=['1.20']),self.profile,self.journal)
        with self.assertRaisesRegex(mc.MinecraftError,'does not list support for fabric'):
            mc.preflight(self.make_receipt(loaders=['forge']),self.profile,self.journal)

    def test_missing_dependency_blocks_but_optional_allows(self):
        dep={'id':'OtherProject','project_id':'OtherProject','type':'required'}
        with self.assertRaisesRegex(mc.MinecraftError,'Required dependency'):
            mc.preflight(self.make_receipt(dependencies=[dep]),self.profile,self.journal)
        plan=mc.preflight(self.make_receipt(dependencies=[dict(dep,type='optional')]),self.profile,self.journal)
        self.assertEqual(plan['status'],'Install new')

    def test_incompatible_blocks(self):
        with self.assertRaisesRegex(mc.MinecraftError,'Incompatible'):
            mc.preflight(self.make_receipt(dependencies=[{'id':'Conflict','type':'incompatible'}]),self.profile,self.journal)

    def test_binding_another_game_blocks(self):
        with self.assertRaisesRegex(mc.MinecraftError,'bound to another game'):
            mc.preflight(self.make_receipt(game_root=str(self.base/'Stardew')),self.profile,self.journal)

    def test_content_tamper_blocks(self):
        r=self.make_receipt();self.makejar(self.archive,b'new data')
        with self.assertRaisesRegex(mc.MinecraftError,'changed'):
            mc.preflight(r,self.profile,self.journal)

    def test_jar_only_and_name_safety(self):
        with self.assertRaisesRegex(mc.MinecraftError,'safely named'):
            mc.preflight(self.make_receipt(filename='../../evil.jar'),self.profile,self.journal)
        with self.assertRaisesRegex(mc.MinecraftError,'safely named'):
            mc.preflight(self.make_receipt(filename='pack.mrpack'),self.profile,self.journal)

    def test_install_writes_mod_and_receipt(self):
        result=mc.install_reviewed(self.receipt,self.profile,self.journal,self.recovery)
        self.assertEqual(result['action'],'installed')
        self.assertEqual((self.mods/'example.jar').read_bytes(),self.archive.read_bytes())
        installed=mc.installed_receipts(self.journal)
        self.assertEqual(installed[0]['project_id'],'AAABBB123')
        self.assertEqual(installed[0]['version_id'],'version123')
        with self.assertRaisesRegex(mc.MinecraftError,'already installed'):
            mc.preflight(self.receipt,self.profile,self.journal)

    def test_update_creates_recovery_backup(self):
        mc.install_reviewed(self.receipt,self.profile,self.journal,self.recovery)
        initial=self.archive.read_bytes()
        self.makejar(self.archive,b'new file version')
        updated=self.make_receipt(version='2.1',version_id='version124')
        result=mc.install_reviewed(updated,self.profile,self.journal,self.recovery)
        self.assertEqual(result['action'],'updated')
        self.assertEqual(Path(result['backup']).read_bytes(),initial)
        self.assertEqual((self.mods/'example.jar').read_bytes(),self.archive.read_bytes())
        self.assertEqual(len(mc.installed_receipts(self.journal)),1)

    def test_update_does_not_replace_external_changes(self):
        mc.install_reviewed(self.receipt,self.profile,self.journal,self.recovery)
        self.makejar(self.mods/'example.jar',b'edited')
        self.makejar(self.archive,b'new')
        with self.assertRaisesRegex(mc.MinecraftError,'changed'):
            mc.preflight(self.make_receipt(),self.profile,self.journal)

    def test_unmanaged_collision_blocks(self):
        self.makejar(self.mods/'example.jar',b'user-file')
        with self.assertRaisesRegex(mc.MinecraftError,'unmanaged'):
            mc.preflight(self.receipt,self.profile,self.journal)
        self.assertFalse(self.journal.exists())

    def test_receipt_save_failure_rolls_back(self):
        old=self.archive.read_bytes()
        mc.install_reviewed(self.receipt,self.profile,self.journal,self.recovery)
        self.makejar(self.archive,b'next version')
        r=self.make_receipt(version='3')
        with patch.object(mc,'_write_receipts',side_effect=OSError('test failure')):
            with self.assertRaises(OSError):mc.install_reviewed(r,self.profile,self.journal,self.recovery)
        self.assertEqual((self.mods/'example.jar').read_bytes(),old)
        self.assertEqual(mc.installed_receipts(self.journal)[0]['version'],'2.0')

    def test_required_dependency_confirmed_by_receipt_and_hash(self):
        dependency=self.base/'dep.jar';self.makejar(dependency,b'dep version')
        dep_name=dependency.name
        dep_receipt=self.make_receipt(identity='OtherProject',filename=dep_name,archive=str(dependency),
                                     bytes=dependency.stat().st_size,
                                     sha256=hashlib.sha256(dependency.read_bytes()).hexdigest(),
                                     version_id='dep-version')
        mc.install_reviewed(dep_receipt,self.profile,self.journal,self.recovery)
        requirement={'id':'OtherProject','project_id':'OtherProject','version_id':'dep-version','type':'required'}
        self.assertEqual(mc.preflight(self.make_receipt(dependencies=[requirement]),self.profile,self.journal)['status'],'Install new')
        with self.assertRaisesRegex(mc.MinecraftError,'Required dependency'):
            mc.preflight(self.make_receipt(dependencies=[dict(requirement,version_id='wrong')]),self.profile,self.journal)

    def test_provider_version_and_dependency_ids_survive_staging(self):
        row={'id':'version123','version_number':'2.0','game_versions':['1.21.1'],'loaders':['fabric'],
             'files':[{'filename':'example.jar','url':'https://cdn.modrinth.com/data/AAABBB123/versions/version123/example.jar',
                       'size':self.archive.stat().st_size,'hashes':{'sha256':self.receipt['sha256']}}],
             'dependencies':[{'project_id':'OtherProject','version_id':'specific123','dependency_type':'required'}]}
        options=provider_downloads.modrinth_files('AAABBB123',fetch=lambda _url,_headers:[row])
        self.assertEqual(options[0]['version_id'],'version123')
        self.assertEqual(options[0]['dependencies'][0]['version_id'],'specific123')
        target=self.base/'download';target.mkdir()
        staged=provider_staging.stage_download(options[0],target,self.base/'staged.json',
            downloader=lambda _record,_dest:self.archive)
        receipt=provider_staging.read_staged(self.base/'staged.json')[0]
        self.assertEqual(receipt['version_id'],'version123')
        self.assertEqual(receipt['dependencies'][0]['project_id'],'OtherProject')
        self.assertEqual(receipt['dependencies'][0]['version_id'],'specific123')

    def test_auto_discovery_of_known_prism_paths(self):
        found=self.base/'.local/share/PrismLauncher/instances/Demo'
        found.parent.mkdir(parents=True)
        self.profile.rename(found)
        self.profile=found
        self.game=self.profile/'.minecraft';self.mods=self.game/'mods';self.pack=self.profile/'mmc-pack.json'
        result=mc.discover_instances(self.base)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['root'],str(self.profile))

    def test_profile_mods_symlink_rejected(self):
        self.mods.rmdir();out=self.base/'external';out.mkdir();self.mods.symlink_to(out, target_is_directory=True)
        with self.assertRaises(mc.MinecraftError):mc.inspect_instance(self.profile)

if __name__=='__main__':unittest.main()
