"""UniMod 0.55: bounded Modrinth inspection and consent-gated import.

Do not turn an inspection result into game writes. A complete modpack importer
must independently revalidate manifest paths, downloads and user approval.
"""
import json
import re
import stat
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import provider_staging as staging

MAX_INDEX=2*1024*1024
MAX_ARCHIVE=512*1024*1024
MAX_ENTRIES=2000
MAX_TOTAL_UNCOMPRESSED=256*1024*1024
MAX_FILES=400
MAX_DOWNLOAD_TOTAL=2*1024*1024*1024
HEX40=re.compile(r'[A-Fa-f0-9]{40}\Z')
HEX128=re.compile(r'[A-Fa-f0-9]{128}\Z')

class PackError(ValueError):pass


def safe_relative(value):
    if not isinstance(value,str) or not 1<=len(value)<=512 or '\\' in value or ':' in value or '\x00' in value:
        raise PackError('Modpack contains an unsafe path.')
    if value.startswith('/') or value.endswith('/') or any(ord(c)<32 for c in value):
        raise PackError('Modpack contains an unsafe path.')
    parts=value.split('/')
    if any(part in ('','.', '..') for part in parts):
        raise PackError('Modpack contains a traversing or ambiguous path.')
    return value


def _url_safe(raw):
    if not isinstance(raw,str) or not 1<=len(raw)<=4096:return False
    try:u=urlsplit(raw)
    except ValueError:return False
    try:
        return (u.scheme=='https' and u.username is None and u.password is None and
                u.hostname=='cdn.modrinth.com' and u.port in (None,443) and
                u.path.startswith('/data/') and not u.fragment)
    except ValueError:return False


def inspect_pack(receipt, instance=None):
    """Read-only archive verification, manifest parsing and path safety audit."""
    if not isinstance(receipt,dict) or receipt.get('provider')!='Modrinth':
        raise PackError('Choose a verified Modrinth download.')
    raw=receipt.get('archive')
    if not isinstance(raw,str) or not raw.lower().endswith('.mrpack'):
        raise PackError('Choose a staged .mrpack file.')
    path=Path(raw)
    if path.is_symlink() or not path.is_file() or path.name!=receipt.get('filename'):
        raise PackError('Modpack file is missing or was renamed.')
    if path.stat().st_size!=receipt.get('bytes') or path.stat().st_size>MAX_ARCHIVE or staging.file_sha256(path)!=receipt.get('sha256'):
        raise PackError('Modpack file changed or exceeds the size limit.')
    seen=set();override_count=0
    try:
        with zipfile.ZipFile(path) as pack:
            members=pack.infolist()
            if len(members)>MAX_ENTRIES:raise PackError('Modpack archive contains too many entries.')
            total=0
            for entry in members:
                name=entry.filename.rstrip('/') if entry.is_dir() else entry.filename
                safe_relative(name)
                norm=name.casefold()
                if norm in seen:raise PackError('Archive has duplicate or case-colliding paths.')
                seen.add(norm)
                mode=(entry.external_attr>>16) & 0xffff
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                    raise PackError('Modpack ZIP contains symlinks or unsupported special files.')
                if not entry.is_dir():
                    total+=entry.file_size
                    if entry.file_size>MAX_TOTAL_UNCOMPRESSED or total>MAX_TOTAL_UNCOMPRESSED:
                        raise PackError('Modpack archive has too much expanded data.')
                    if entry.file_size>0 and (entry.compress_size==0 or entry.file_size>1000*entry.compress_size):
                        raise PackError('Modpack has an excessively compressed member.')
                if name.startswith(('overrides/','client-overrides/')) and not entry.is_dir():override_count+=1
            if 'modrinth.index.json' not in pack.namelist():raise PackError('Missing modrinth.index.json.')
            index=pack.getinfo('modrinth.index.json')
            if index.file_size>MAX_INDEX:raise PackError('Modpack index exceeds safe size.')
            payload=pack.read(index)
    except (OSError,zipfile.BadZipFile,RuntimeError) as exc:
        raise PackError('Invalid Modrinth pack archive.') from exc
    try:data=json.loads(payload.decode('utf-8'))
    except (ValueError,UnicodeError):raise PackError('Invalid modrinth.index.json.') from None
    if not isinstance(data,dict) or data.get('formatVersion')!=1 or data.get('game')!='minecraft':
        raise PackError('Not a supported Modrinth Minecraft modpack format.')
    files=data.get('files'); dependencies=data.get('dependencies')
    if not isinstance(files,list) or len(files)>MAX_FILES or not isinstance(dependencies,dict):
        raise PackError('Invalid modpack file/dependency listing.')
    if not isinstance(dependencies.get('minecraft'),str):
        raise PackError('Modpack does not declare its Minecraft version.')
    pack_loader={key:value for key,value in dependencies.items() if key in ('fabric-loader','quilt-loader','forge','neoforge')}
    if len(pack_loader)!=1 or not all(isinstance(v,str) and v for v in pack_loader.values()):
        raise PackError('Modpack must declare exactly one supported loader.')
    paths=set();size=0;unsupported=0;optional=0
    for f in files:
        if not isinstance(f,dict):raise PackError('Invalid modpack file entry.')
        name=safe_relative(f.get('path'))
        norm=name.casefold()
        if norm in paths:raise PackError('Modpack has duplicate destination paths.')
        paths.add(norm)
        hs=f.get('hashes') or {};url=f.get('downloads')
        if not isinstance(hs,dict) or not HEX40.fullmatch(str(hs.get('sha1') or '')) or not HEX128.fullmatch(str(hs.get('sha512') or '')):
            raise PackError('Modpack file has missing or invalid SHA-1/SHA-512 hashes.')
        count=f.get('fileSize')
        if type(count)!=int or not 0<count<=MAX_ARCHIVE:raise PackError('Modpack has an invalid file size.')
        size+=count
        if size>MAX_DOWNLOAD_TOTAL:raise PackError('Modpack download total exceeds safety limit.')
        if not isinstance(url,list) or not url or not any(_url_safe(x) for x in url):unsupported+=1
        env=f.get('env') or {}
        if not isinstance(env,dict) or env.get('client') not in (None,'required','optional','unsupported'):
            raise PackError('Modpack has invalid client environment metadata.')
        if env.get('client')=='optional':optional+=1
    return {'name':str(data.get('name') or 'Unnamed pack')[:120],
            'version_id':str(data.get('versionId') or '')[:120],
            'minecraft':dependencies['minecraft'],'loader':pack_loader,
            'file_count':len(files),'override_count':override_count,
            'optional_count':optional,'bytes':size,'unsupported_urls':unsupported,
            'safe_to_preview':True,'install_supported':False}

# v0.55 Test 5: bounded, reviewed import into an existing verified launcher instance.
# The old inspect_pack() remains a read-only operation.
import datetime
import hashlib
import os
import shutil
import tempfile
import urllib.error
import urllib.request

import minecraft_profiles

_LOADER_NAMES={'fabric-loader':'fabric','quilt-loader':'quilt','forge':'forge','neoforge':'neoforge'}
# Refuse launcher metadata, saves, native programs and arbitrary paths in packs.
_SAFE_DIRS={'mods','config','defaultconfigs','resourcepacks','shaderpacks','kubejs','scripts','patchouli_books'}
_SAFE_TOP={'options.txt','optionsof.txt','optionsshaders.txt'}
_MAX_OVERRIDE_FILE=32*1024*1024


def _game_path(name):
    safe_relative(name)
    parts=name.split('/')
    if parts[0].casefold() not in _SAFE_DIRS and name.casefold() not in _SAFE_TOP:
        raise PackError('Pack destination is outside the allowed Minecraft content/config folders: '+name[:120])
    if any(x.startswith('.') for x in parts) or name.casefold().endswith(('.exe','.dll','.so','.sh','.bat','.cmd','.desktop','.py')):
        raise PackError('Refusing hidden or executable game content: '+name[:120])
    return name


def _verify_tree(root,relative):
    """Reject symlinked parents and targets on the exact approved game path."""
    current=Path(root)
    if current.is_symlink() or not current.is_dir():raise PackError('Minecraft instance path changed or is a symlink.')
    for piece in relative.split('/')[:-1]:
        current=current/piece
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise PackError('Unsafe destination directory in instance: '+relative[:120])
    final=current/relative.split('/')[-1]
    if final.is_symlink() or (final.exists() and not final.is_file()):
        raise PackError('Unsafe destination file in instance: '+relative[:120])
    return final


def _sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as src:
        for block in iter(lambda:src.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def plan_import(receipt,instance,selected_optional=()):
    """Read-only, re-verified preflight. Optional client files require explicit selection."""
    if not isinstance(selected_optional,(list,tuple,set,frozenset)) or len(selected_optional)>MAX_FILES:
        raise PackError('Invalid optional modpack selection.')
    if any(not isinstance(x,str) for x in selected_optional):
        raise PackError('Optional modpack file selection must contain paths.')
    requested=set(selected_optional)
    if len(requested)!=len(selected_optional):
        raise PackError('Duplicate optional modpack selection.')
    audit=inspect_pack(receipt)
    try:info=minecraft_profiles.inspect_instance(instance)
    except minecraft_profiles.MinecraftError as exc:raise PackError('Unsafe or incompatible Prism/MultiMC profile: '+str(exc)) from exc
    loader_name,loader_version=next(iter(audit['loader'].items()))
    if (info['version']!=audit['minecraft'] or info['loader']!=_LOADER_NAMES[loader_name]
        or info['loader_version']!=loader_version):
        raise PackError('Selected Prism/MultiMC profile has a different Minecraft or loader version; create a compatible profile first.')
    raw=Path(receipt['archive'])
    with zipfile.ZipFile(raw) as z:
        data=json.loads(z.read('modrinth.index.json').decode('utf-8'))
        overrides={}
        for member in z.infolist():
            if member.is_dir():continue
            name=member.filename
            for prefix in ('overrides/','client-overrides/'):
                if name.startswith(prefix):
                    rel=_game_path(name[len(prefix):])
                    if member.file_size>_MAX_OVERRIDE_FILE:raise PackError('Oversized modpack override: '+rel[:120])
                    # Client layer deliberately replaces common layer.
                    old=overrides.get(rel.casefold())
                    if old and old['path']!=rel:raise PackError('Case-colliding overrides: '+rel[:120])
                    if not old or prefix=='client-overrides/':
                        overrides[rel.casefold()]={'path':rel,'member':name,'size':member.file_size,'source':'override'}
        listed={};ignored=0;optional_candidates=[];unavailable_optional=0;accepted=set()
        for item in data['files']:
            env=item.get('env') or {}
            mode=env.get('client')
            if mode=='unsupported':
                ignored+=1;continue  # Never install server-only files.
            optional=mode=='optional'
            if optional:
                # Unsafe optional content may not be installed; don't offer it in the UI.
                try:rel=_game_path(item['path'])
                except PackError:
                    if item['path'] in requested:raise
                    ignored+=1;unavailable_optional+=1;continue
            else:rel=_game_path(item['path'])
            key=rel.casefold()
            if key in listed or (not optional and key in overrides):
                raise PackError('Overlapping modpack destinations: '+rel[:120])
            allowed=next((url for url in item['downloads'] if _url_safe(url)),None)
            if optional:
                can_install=bool(allowed) and key not in overrides
                optional_candidates.append({'path':rel,'size':item['fileSize'],
                                            'available':can_install})
                if rel not in requested:
                    ignored+=1;continue
                if not can_install:
                    raise PackError('Selected optional file lacks supported CDN or conflicts with an override: '+rel[:120])
                accepted.add(rel)
            elif not allowed:
                raise PackError('Required modpack file has no supported Modrinth CDN URL: '+rel[:120])
            if key in overrides:raise PackError('Overlapping modpack destinations: '+rel[:120])
            listed[key]={'path':rel,'source':'download','url':allowed,
                         'sha1':item['hashes']['sha1'].lower(),'sha512':item['hashes']['sha512'].lower(),
                         'size':item['fileSize']}
        if accepted!=requested:
            raise PackError('Selected optional file is not offered by the current modpack: '+
                            ', '.join(sorted(requested-accepted))[:120])
        writes=list(listed.values())+list(overrides.values())
        if not writes and not optional_candidates:
            raise PackError('The pack contains no supported client content to install.')
        if len(writes)>MAX_FILES+MAX_ENTRIES:raise PackError('Too many files to install.')
        for row in writes:
            target=_verify_tree(info['minecraft'],row['path'])
            if target.exists() and target.stat().st_size>MAX_ARCHIVE:
                raise PackError('Existing destination exceeds safe backup limit: '+row['path'][:120])
            row['existing_hash']=_sha256(target) if target.exists() else None
            row['destination']=str(target)
        return {'profile':info,'archive':str(raw),'receipt':dict(receipt),
                'pack_name':audit['name'],'version_id':audit['version_id'],
                'writes':writes,'optional_skipped':ignored,
                'optional_candidates':optional_candidates,'unavailable_optional':unavailable_optional,
                'selected_optional':sorted(accepted),
                'download_count':len(listed),'download_bytes':sum(r['size'] for r in listed.values()),
                'overwrite_count':sum(1 for r in writes if r['existing_hash']),
                'backup_bytes':sum(Path(r['destination']).stat().st_size for r in writes if r['existing_hash'])}


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):self.count=0
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.count+=1
        if self.count>3 or not _url_safe(newurl):
            raise PackError('Modpack download redirected to an unapproved host or too many times.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def _download(row,output):
    redirect=_SafeRedirect()
    opener=urllib.request.build_opener(redirect)
    request=urllib.request.Request(row['url'],headers={'User-Agent':'UniMod/0.55 (reviewed Modrinth pack import)','Accept-Encoding':'identity'})
    with opener.open(request,timeout=25) as response,Path(output).open('wb') as out:
        if not _url_safe(response.geturl()):raise PackError('Unexpected final Modrinth download host.')
        length=response.headers.get('Content-Length')
        if length and int(length)!=row['size']:raise PackError('Unexpected Modrinth file size.')
        sha1=hashlib.sha1();sha512=hashlib.sha512();total=0
        while True:
            chunk=response.read(min(1024*1024,row['size']-total+1))
            if not chunk:break
            total+=len(chunk)
            if total>row['size']:raise PackError('Downloaded file exceeds declared size.')
            out.write(chunk);sha1.update(chunk);sha512.update(chunk)
        if total!=row['size'] or sha1.hexdigest()!=row['sha1'] or sha512.hexdigest()!=row['sha512']:
            raise PackError('Modpack download failed SHA-1/SHA-512/size verification.')
    return output


def install_import(plan,recovery_base,receipts_path,downloader=None,commit_hook=None):
    """Perform explicit-approval plan. Fetch & verify everything BEFORE game changes.

    downloader is a test seam; production uses strict HTTPS Modrinth CDN only.
    All destination content is backed up and transactional rollback covers failures.
    """
    old=plan['receipt']
    fresh=plan_import(old,plan['profile']['root'],selected_optional=plan.get('selected_optional',()))
    approved_fields=('path','source','existing_hash','sha1','sha512','size','url','member')
    if (fresh['selected_optional']!=plan.get('selected_optional',[])
        or [{k:x.get(k) for k in approved_fields} for x in fresh['writes']]
        !=[{k:x.get(k) for k in approved_fields} for x in plan['writes']]
        or fresh['profile']!=plan['profile']):
        raise PackError('Modpack or Minecraft files changed since approval. Review the import again.')
    if not fresh['writes']:
        raise PackError('No client files were selected for installation.')
    recovery_base=Path(recovery_base)
    receipts_path=Path(receipts_path)
    root=Path(fresh['profile']['minecraft'])
    if recovery_base.is_symlink() or (recovery_base.exists() and not recovery_base.is_dir()):
        raise PackError('Unsafe modpack recovery path.')
    target_root=root.resolve()
    backup_root=recovery_base.resolve()
    if target_root in backup_root.parents or backup_root==target_root:
        raise PackError('Recovery folder must be outside the Minecraft directory.')
    files=fresh['writes']
    with tempfile.TemporaryDirectory(prefix='unimod-mrpack-') as scratch:
        staged={}
        with zipfile.ZipFile(fresh['archive']) as archive:
            for i,row in enumerate(files):
                target=Path(scratch)/('entry-'+str(i))
                if row['source']=='download':
                    if downloader:
                        downloader(row,target)
                        if (target.stat().st_size!=row['size'] or
                            hashlib.sha1(target.read_bytes()).hexdigest()!=row['sha1'] or
                            hashlib.sha512(target.read_bytes()).hexdigest()!=row['sha512']):
                            raise PackError('Downloaded mod failed cryptographic verification.')
                    else:_download(row,target)
                else:
                    with archive.open(row['member']) as src,target.open('wb') as dst:
                        copied=0
                        while chunk:=src.read(1024*1024):
                            copied+=len(chunk)
                            if copied>_MAX_OVERRIDE_FILE:raise PackError('Override exceeded safe size.')
                            dst.write(chunk)
                    if copied!=row['size']:raise PackError('Override content changed since review.')
                staged[row['path']]=target
        # Revalidate the filesystem after all downloads and before any writes.
        for row in files:
            target=_verify_tree(root,row['path'])
            before=_sha256(target) if target.exists() else None
            if before!=row['existing_hash']:raise PackError('Minecraft files changed during download; no game files were modified.')
        recovery=recovery_base/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
        recovery.mkdir(parents=True,exist_ok=False)
        modified=[];temps=[];created_dirs=[]
        try:
            for row in files:
                target=_verify_tree(root,row['path'])
                if row['existing_hash']:
                    backup=recovery/row['path']
                    backup.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(target,backup)
                    if _sha256(backup)!=row['existing_hash']:raise PackError('Backup verification failed.')
            for row in files:
                dest=Path(row['destination'])
                parent=dest.parent
                missing=[];cur=parent
                while not cur.exists() and cur!=root:
                    missing.append(cur);cur=cur.parent
                for directory in reversed(missing):
                    directory.mkdir();created_dirs.append(directory)
                _verify_tree(root,row['path'])
                with tempfile.NamedTemporaryFile(dir=parent,prefix='.unimod-pack-',delete=False) as handle:
                    temp=Path(handle.name);temps.append(temp)
                    with staged[row['path']].open('rb') as source:
                        shutil.copyfileobj(source,handle,1024*1024)
                    handle.flush();os.fsync(handle.fileno())
                if _sha256(temp)!=_sha256(staged[row['path']]):raise PackError('Staged file changed during import.')
                os.replace(temp,dest);modified.append(row)
                if commit_hook:commit_hook(len(modified),row)
            saved=minecraft_profiles.installed_receipts(receipts_path)
            saved.append({'provider':'Modrinth-modpack','profile':fresh['profile']['root'],
                          'name':fresh['pack_name'],'version_id':fresh['version_id'],
                          'files':[x['path'] for x in files],
                          'selected_optional':fresh['selected_optional'],
                          'backup':str(recovery),
                          'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
            minecraft_profiles._write_receipts(receipts_path,saved)
            return {'installed':len(files),'backup':str(recovery),
                    'profile':fresh['profile']['root'],'skipped_optional':fresh['optional_skipped'],
                    'selected_optional':fresh['selected_optional']}
        except Exception:
            for row in reversed(modified):
                dest=Path(row['destination'])
                backup=recovery/row['path']
                if backup.is_file():shutil.copy2(backup,dest)
                else:dest.unlink(missing_ok=True)
            raise
        finally:
            for temp in temps:temp.unlink(missing_ok=True)
            for directory in reversed(created_dirs):
                try:directory.rmdir()
                except OSError:pass
