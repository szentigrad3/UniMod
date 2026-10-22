"""UniMod 0.54: reviewed Modrinth JAR deployment to recognised Prism/MultiMC instances.

No loader installation, modpack extraction, guessing of dependencies, or other
Minecraft launcher writes are performed. All paths are checked before writes.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import provider_staging

LOADER_COMPONENTS={
    'net.fabricmc.fabric-loader':'fabric',
    'org.quiltmc.quilt-loader':'quilt',
    'net.minecraftforge':'forge',
    'net.neoforged':'neoforge',
}
MAX_METADATA=256*1024
MAX_RECEIPTS=1000
NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.+() -]{0,180}\.jar$',re.I)
VERSION=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.+\-]{0,64}$')

class MinecraftError(ValueError):pass

def _json(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_METADATA:raise MinecraftError('Missing or unsafe Prism instance metadata.')
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError,OSError):raise MinecraftError('Invalid Prism instance metadata.') from None
    if not isinstance(data,dict):raise MinecraftError('Invalid Prism instance metadata.')
    return data

def discover_instances(home=None):
    """Identify installed Prism/MultiMC instances in known Linux locations only.

    Return only valid loader-equipped profiles; never recurse outside these roots.
    """
    home=Path(home or Path.home()).expanduser().absolute()
    roots=[home/'.local/share/PrismLauncher/instances',
           home/'.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances',
           home/'.local/share/multimc/instances',
           home/'MultiMC/instances',
           home/'PrismLauncher/instances']
    found={}
    for root in roots:
        if not root.is_dir() or root.is_symlink():continue
        try:candidates=list(root.iterdir())[:100]
        except OSError:continue
        for folder in candidates:
            if not folder.is_dir() or folder.is_symlink():continue
            try:entry=inspect_instance(folder)
            except (MinecraftError,OSError,ValueError):continue
            found[entry['root']]=entry
    return sorted(found.values(),key=lambda x:x['root'].casefold())

def inspect_instance(folder):
    root=Path(folder).expanduser().absolute()
    if not root.is_dir() or root.is_symlink():raise MinecraftError('Choose a Prism/MultiMC instance folder, not a symlink.')
    data=_json(root/'mmc-pack.json')
    components=data.get('components')
    if not isinstance(components,list) or len(components)>100:raise MinecraftError('Unsupported launcher component metadata.')
    mc=[]; loaders=[]; loader_versions=[]
    for entry in components:
        if not isinstance(entry,dict):continue
        uid=entry.get('uid');version=entry.get('version')
        if uid=='net.minecraft':mc.append(version)
        if uid in LOADER_COMPONENTS:
            loaders.append(LOADER_COMPONENTS[uid]);loader_versions.append(version)
    if len(mc)!=1 or not isinstance(mc[0],str) or not VERSION.fullmatch(mc[0]):
        raise MinecraftError('Cannot verify the installed Minecraft version.')
    if len(loaders)!=1 or len(loader_versions)!=1 or not isinstance(loader_versions[0],str) or not VERSION.fullmatch(loader_versions[0]):
        raise MinecraftError('Cannot verify one supported mod loader and its version (Fabric/Quilt/Forge/NeoForge).')
    candidates=[root/'.minecraft',root/'minecraft']
    dirs=[p for p in candidates if p.is_dir() and not p.is_symlink()]
    if len(dirs)!=1:raise MinecraftError('Cannot uniquely identify the instance Minecraft game directory.')
    minecraft=dirs[0]
    mods=minecraft/'mods'
    if mods.is_symlink() or (mods.exists() and not mods.is_dir()):raise MinecraftError('Mods folder is a symlink or not a directory.')
    return {'root':str(root),'minecraft':str(minecraft),'mods':str(mods),'version':mc[0],'loader':loaders[0],'loader_version':loader_versions[0]}

def installed_receipts(path):
    path=Path(path)
    try:
        if path.stat().st_size>2*1024*1024:return []
        rows=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(rows,list):return [r for r in rows[-MAX_RECEIPTS:] if isinstance(r,dict)]
    except (OSError,ValueError,UnicodeError):pass
    return []

def _write_receipts(path,rows):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.minecraft-receipts-',delete=False) as f:
            tmp=Path(f.name);json.dump(rows[-MAX_RECEIPTS:],f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        tmp.replace(path)
    finally:
        if tmp:tmp.unlink(missing_ok=True)

def _candidate_name(receipt):
    name=str(receipt.get('filename') or '')
    if not NAME.fullmatch(name) or name in ('.','..') or '/' in name or '\\' in name:
        raise MinecraftError('Only a single safely named Modrinth JAR can be installed.')
    return name

def preflight(receipt,instance,receipts_path):
    """Read-only and fail closed for missing dependencies and profiles."""
    if not isinstance(receipt,dict) or receipt.get('provider')!='Modrinth':raise MinecraftError('Select a verified Modrinth download.')
    name=_candidate_name(receipt)
    info=inspect_instance(instance)
    # Previous builds could bind a Modrinth download to the selected unrelated game.
    bound=str(receipt.get('game_root') or '')
    if bound and bound not in (info['root'],info['minecraft']):
        raise MinecraftError('Download is bound to another game. Stage it again without another selected game.')
    # inspect_receipt prohibits .jar by design; perform its tamper checks directly.
    path=Path(str(receipt.get('archive') or ''))
    if not path.is_file() or path.is_symlink() or path.name!=name:
        raise MinecraftError('Downloaded JAR is missing, renamed or symlinked.')
    if path.stat().st_size!=receipt.get('bytes') or provider_staging.file_sha256(path)!=receipt.get('sha256'):
        raise MinecraftError('Downloaded JAR has changed since staging.')
    if not zipfile.is_zipfile(path):raise MinecraftError('Downloaded JAR is not a valid archive.')
    versions=receipt.get('game_versions');loaders=receipt.get('loaders')
    if not isinstance(versions,list) or info['version'] not in versions:
        raise MinecraftError('Modrinth does not list support for Minecraft '+info['version']+'.')
    if not isinstance(loaders,list) or info['loader'] not in loaders:
        raise MinecraftError('Modrinth does not list support for '+info['loader']+'.')
    identity=receipt.get('identity')
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,70}',identity):
        raise MinecraftError('Missing exact Modrinth project identity.')
    saved=installed_receipts(receipts_path)
    root=info['root']
    own=[r for r in saved if r.get('profile')==root and r.get('project_id')==identity]
    if len(own)>1:raise MinecraftError('Multiple prior installs share the same Modrinth project ID.')
    for entry in receipt.get('dependencies') or []:
        if not isinstance(entry,dict):raise MinecraftError('Unrecognised dependency metadata.')
        dtype=entry.get('type')
        if dtype in ('incompatible','unknown'):
            raise MinecraftError('Incompatible or unrecognised dependency: '+str(entry.get('id',''))[:90])
        if dtype!='required':continue
        pid=str(entry.get('project_id') or (entry.get('id') if not entry.get('version_id') else '') or '')
        vid=str(entry.get('version_id') or '')
        matched=[]
        for r in saved:
            if r.get('profile')!=root:continue
            if pid and r.get('project_id')!=pid:continue
            if vid and r.get('version_id')!=vid:continue
            target=Path(str(r.get('installed_path') or ''))
            if target.parent!=Path(info['mods']) or target.is_symlink() or not target.is_file():continue
            if provider_staging.file_sha256(target)==r.get('installed_hash'):matched.append(r)
        if not matched:
            raise MinecraftError('Required dependency not verified in this instance: '+(pid or vid or 'unknown')[:100]+'. Stage/install it first.')
    mods=Path(info['mods'])
    destination=mods/name
    if destination.is_symlink():raise MinecraftError('Destination is a symlink.')
    previous=own[0] if own else None
    prevpath=Path(previous['installed_path']) if previous else None
    if previous:
        if prevpath.parent!=mods or not prevpath.is_file() or prevpath.is_symlink() or provider_staging.file_sha256(prevpath)!=previous.get('installed_hash'):
            raise MinecraftError('Previous managed version was changed; manual review required.')
    if destination.exists() and destination!=prevpath:
        raise MinecraftError('An unmanaged file already has this filename; refusing to overwrite.')
    # refuse changes to an identical already-installed build
    if previous and previous.get('installed_hash')==receipt['sha256']:
        raise MinecraftError('This exact Modrinth JAR is already installed.')
    return {'status':'Update existing' if previous else 'Install new','instance':info,
            'archive':str(path),'destination':str(destination),'previous':previous,
            'project_id':identity,'filename':name,'detail':f"{name}: {info['loader']} / Minecraft {info['version']}"}

def install_reviewed(receipt,instance,receipts_path,recovery_base):
    """Recheck immediately before writes, stage atomically, and restore on error."""
    plan=preflight(receipt,instance,receipts_path)
    info=plan['instance'];mods=Path(info['mods']);src=Path(plan['archive']);dst=Path(plan['destination'])
    prev=plan['previous'];old=Path(prev['installed_path']) if prev else None
    if mods.is_symlink() or mods.parent.is_symlink():raise MinecraftError('Unsafe instance Mods path.')
    created=False;temporary=None;backup=None;dest_created=False
    rows=installed_receipts(receipts_path)
    try:
        if not mods.exists():mods.mkdir(mode=0o755)
        created=True
        # immutable staged archive -> temporary copy -> exclusive destination
        with tempfile.NamedTemporaryFile(dir=mods,prefix='.unimod-',suffix='.part',delete=False) as f:
            temporary=Path(f.name)
            with src.open('rb') as stream:shutil.copyfileobj(stream,f,1024*1024)
            f.flush();os.fsync(f.fileno())
        if provider_staging.file_sha256(temporary)!=receipt['sha256']:
            raise MinecraftError('JAR changed during copy.')
        if old:
            recovery=Path(recovery_base)/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            recovery.mkdir(parents=True,exist_ok=True)
            backup=recovery/old.name
            old.rename(backup)
        # Exclusive link prevents clobbering if another process created the destination.
        os.link(temporary,dst);dest_created=True
        rec={'provider':'Modrinth','project_id':receipt['identity'],'version':str(receipt.get('version') or '')[:80],
             'version_id':str(receipt.get('version_id') or '')[:90],
             'profile':info['root'],'installed_path':str(dst),'installed_hash':receipt['sha256'],
             'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        rows=[r for r in rows if not (r.get('profile')==info['root'] and r.get('project_id')==receipt['identity'])]
        rows.append(rec)
        _write_receipts(receipts_path,rows)
        return {'action':'updated' if old else 'installed','path':str(dst),'backup':str(backup or ''),'profile':info['root']}
    except Exception:
        if dest_created:dst.unlink(missing_ok=True)
        if backup and backup.exists():backup.rename(old)
        raise
    finally:
        if temporary:temporary.unlink(missing_ok=True)
