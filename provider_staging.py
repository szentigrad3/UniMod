"""UniMod 0.55 test12: audited staging journal and review-only install preflight.

A provider search result is never evidence that a local mod belongs to a source.
Journal receipts bind a *verified downloaded byte sequence* to its provider
metadata and a single selected game. Secrets and signed download links are not
persisted. Game writes live in unimod.py after an explicit GUI confirmation.
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import tempfile
import zipfile
from pathlib import Path

import provider_downloads

MAX_RECORDS = 300
MAX_JSON = 2 * 1024 * 1024
TRUSTED_TS_HOSTS = {'thunderstore.io', 'www.thunderstore.io', 'gcdn.thunderstore.io', 'cdn.thunderstore.io'}

class StageError(ValueError):
    pass


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def _read(path):
    try:
        path=Path(path)
        if path.stat().st_size > MAX_JSON: return []
        result=json.loads(path.read_text(encoding='utf-8'))
        return result[:MAX_RECORDS] if isinstance(result,list) else []
    except (ValueError,OSError,TypeError): return []


def read_staged(path):
    return [r for r in _read(path) if isinstance(r,dict) and r.get('provider') in ('GitHub','Modrinth','Thunderstore','mod.io')]


def _atomic_save(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.unimod-stage-',suffix='.tmp',encoding='utf-8',delete=False) as out:
        temp=Path(out.name)
        try:
            json.dump(rows[-MAX_RECORDS:],out,indent=2)
            out.write('\n')
            out.flush();os.fsync(out.fileno())
        except Exception:
            temp.unlink(missing_ok=True)
            raise
    try: temp.replace(path)
    finally:temp.unlink(missing_ok=True)


def _ts_url(url):
    if not isinstance(url,str) or len(url)>4096:return False
    try:p=urllib.parse.urlsplit(url)
    except ValueError:return False
    return (p.scheme=='https' and p.hostname in TRUSTED_TS_HOSTS and p.port in (None,443)
            and not p.username and not p.password and not p.fragment
            and bool(p.path) and not p.path.startswith('//'))


class _ThunderstoreRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,hdrs,newurl):
        if not _ts_url(newurl): raise StageError('Thunderstore redirected outside approved download hosts.')
        return super().redirect_request(req,fp,code,msg,hdrs,newurl)


def _thunderstore_zip(pkg,directory,*,opener=None):
    """Download only a reviewed Thunderstore ZIP; unknown remote size has a hard cap."""
    url=pkg.get('download_url','')
    if not _ts_url(url): raise StageError('Untrusted Thunderstore download URL.')
    identity=str(pkg.get('full_name') or '')
    if pkg.get('version') and not identity.endswith('-'+str(pkg['version'])):
        identity+='-'+str(pkg['version'])
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}-[A-Za-z0-9_-]{1,80}-[0-9A-Za-z_.-]{1,80}',identity):
        raise StageError('Unrecognised Thunderstore package identity.')
    destination=Path(directory).expanduser().resolve()
    if not destination.is_dir():raise StageError('Download folder does not exist.')
    name=provider_downloads._filename(identity+'.zip')
    output=destination/name
    if output.exists():raise FileExistsError('A ZIP with this name already exists.')
    temp=None
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'UniMod/0.55-test12 (Linux mod manager)'})
        opener=opener or urllib.request.build_opener(_ThunderstoreRedirect())
        with opener.open(req,timeout=30) as response:
            if not _ts_url(response.geturl()):raise StageError('Untrusted Thunderstore response URL.')
            with tempfile.NamedTemporaryFile(dir=destination,prefix='.unimod-',suffix='.part',delete=False) as out:
                temp=Path(out.name);total=0
                while True:
                    data=response.read(262144)
                    if not data:break
                    total+=len(data)
                    if total>provider_downloads.MAX_FILE:raise StageError('Thunderstore ZIP exceeds size limit.')
                    out.write(data)
        if not zipfile.is_zipfile(temp):raise StageError('Thunderstore returned an invalid ZIP.')
        os.link(temp,output)
        return output
    except OSError:
        raise StageError('Thunderstore download failed.') from None
    finally:
        if temp:temp.unlink(missing_ok=True)


def _limited_dependencies(dependencies):
    result=[]
    for entry in (dependencies if isinstance(dependencies,list) else [])[:60]:
        if isinstance(entry,str):result.append({'id':entry[:160],'type':'required'})
        elif isinstance(entry,dict):
            kind=str(entry.get('dependency_type') or '').lower()
            if kind not in ('required','optional','incompatible','embedded'):kind='unknown'
            dep=str(entry.get('project_id') or entry.get('version_id') or entry.get('file_name') or '')
            if dep:result.append({'id':dep[:160],'project_id':str(entry.get('project_id') or '')[:160], 'version_id':str(entry.get('version_id') or '')[:100], 'type':kind})
    return result


def stage_download(record,directory,receipt_path,*,game_root='',downloader=None,opener=None):
    """Stage, fingerprint, then persist a provider download receipt.

    The selected game binding prevents another game's install view from
    mistaking the same ZIP for a reviewed candidate. A failed receipt write
    leaves the ZIP untouched; users may inspect it manually.
    """
    if not isinstance(record,dict):raise StageError('Select a provider file first.')
    provider=record.get('provider')
    if provider not in ('GitHub','Modrinth','Thunderstore','mod.io'):raise StageError('Unsupported file provider.')
    game_path=str(Path(game_root).resolve()) if game_root else ''
    if provider=='Thunderstore':
        path=_thunderstore_zip(record,directory,opener=opener)
        identity=str(record.get('full_name') or '')
    else:
        downloader=downloader or provider_downloads.download_file
        path=downloader(record,directory)
        identity=str(record.get('identity') or '')
    file=Path(path).resolve(strict=True)
    receipt={'provider':provider,'identity':identity[:200], 'filename':file.name,
             'archive':str(file),'sha256':file_sha256(file),'bytes':file.stat().st_size,
             'version':str(record.get('version') or '')[:80], 'version_id':str(record.get('version_id') or '')[:90],
             'game_root':game_path,'dependencies':_limited_dependencies(record.get('dependencies',[])),
             'game_versions':[str(x)[:50] for x in record.get('game_versions',[])[:60]],
             'loaders':[str(x)[:50] for x in record.get('loaders',[])[:30]]}
    # Never persist download URL, authentication credentials, or response headers.
    rows=read_staged(receipt_path)
    rows=[r for r in rows if r.get('archive')!=receipt['archive']]
    rows.append(receipt)
    _atomic_save(receipt_path,rows)
    return file


def inspect_receipt(receipt,*,game_root='',allow_unbound=False):
    """Validate archive immutability and explicit game binding, without writing."""
    if not isinstance(receipt,dict):raise StageError('Invalid staging record.')
    raw=receipt.get('archive','')
    if not isinstance(raw,str) or not raw or len(raw)>4096:raise StageError('Invalid archive path.')
    p=Path(raw)
    if p.is_symlink() or not p.is_file():raise StageError('Archive is missing or symlinked.')
    if not p.name.lower().endswith('.zip'):
        raise StageError('Only ZIP packages can be installed by UniMod. JARs and modpacks are download-only.')
    if receipt.get('game_root'):
        if not game_root or str(Path(game_root).resolve())!=receipt['game_root']:
            raise StageError('This download was staged for a different game.')
    elif not allow_unbound:raise StageError('This download was not associated with a game; review manually.')
    if p.stat().st_size!=receipt.get('bytes') or file_sha256(p)!=receipt.get('sha256'):
        raise StageError('ZIP changed since download. Do not install; download again.')
    if p.stat().st_size>provider_downloads.MAX_FILE:raise StageError('ZIP exceeds size limit.')
    if not zipfile.is_zipfile(p):raise StageError('ZIP structure is invalid.')
    return p


def dependency_summary(record):
    deps=record.get('dependencies',[]) if isinstance(record,dict) else []
    required=[d['id'] for d in deps if isinstance(d,dict) and d.get('type')=='required']
    incompatible=[d['id'] for d in deps if isinstance(d,dict) and d.get('type')=='incompatible']
    unknown=[d['id'] for d in deps if isinstance(d,dict) and d.get('type')=='unknown']
    return required,incompatible,unknown
