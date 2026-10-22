"""Reviewed GitHub and Modrinth release-file acquisition, UniMod v0.55 test12.

Search results are leads only. No automatic installed-mod linking or deployment.
API access is read-only, file selection is explicit, downloads are staged in
an existing inbox, and every downloadable artifact is verified before exposure.
"""
import hashlib
import os
import re
import tempfile
import zipfile
import urllib.parse
import urllib.request
from pathlib import Path

import provider_catalogues as catalog

MAX_FILE = 512 * 1024 * 1024
EXTS = ('.zip', '.jar', '.mrpack', '.7z', '.rar')
GITHUB_REPO = re.compile(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z')
MODRINTH_PROJECT = re.compile(r'[a-zA-Z0-9]{3,50}\Z')
HASH = {'md5':32, 'sha1':40, 'sha256':64, 'sha512':128}

class DownloadError(ValueError):
    pass


def _filename(name):
    if not isinstance(name,str) or not 1 <= len(name) <= 170 or name != Path(name).name:
        raise DownloadError('Invalid file name.')
    if name[0] in '. ' or name.endswith((' ','.')) or re.search(r'[\\/:\x00-\x1f]',name):
        raise DownloadError('Unsafe file name.')
    if not name.lower().endswith(EXTS):
        raise DownloadError('Only archive/mod package files (ZIP, JAR, MRPACK, 7z, RAR) are supported.')
    return name


def _safe_url(url, provider):
    if not isinstance(url,str) or not 1 <= len(url) <= 4096: return False
    try: p=urllib.parse.urlsplit(url)
    except ValueError: return False
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.fragment: return False
    host=(p.hostname or '').lower()
    if provider=='Modrinth':
        return host in ('cdn.modrinth.com','cdn-raw.modrinth.com') and p.path.startswith('/data/')
    if provider=='GitHub':
        return ((host=='github.com' and bool(re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/.+',p.path)))
                or host in ('release-assets.githubusercontent.com','objects.githubusercontent.com'))
    if provider=='mod.io':
        if host=='api.mod.io' or re.fullmatch(r'u-[1-9]\d{0,11}\.modapi\.io',host):
            return bool(re.fullmatch(r'/v1/games/[1-9]\d*/mods/[1-9]\d*/files/[1-9]\d*/download/[A-Za-z0-9_-]{8,200}',p.path)) and not p.query
        # CDNs may redirect to known mod.io hosts, but credentials are never added.
        return host in ('cdn.mod.io','static.mod.io') and bool(p.path)
    return False


def _hashes(raw):
    if not isinstance(raw,dict): return {}
    result={}
    for method,n in HASH.items():
        value=raw.get(method)
        if isinstance(value,str) and re.fullmatch('[a-fA-F0-9]{'+str(n)+'}',value):
            result[method]=value.lower()
    return result


def _row(provider,identity,version,filename,url,size,hashes,game_versions,loaders,dependencies=None,version_id=''):
    if not _safe_url(url,provider):return None
    if provider=='Modrinth' and not urllib.parse.urlsplit(url).path.startswith('/data/'+identity+'/'):
        return None
    try:
        filename=_filename(filename)
        size=int(size)
    except (ValueError,TypeError,OverflowError,DownloadError):return None
    if not 0<size<=MAX_FILE:return None
    return {'provider':provider,'identity':identity,'version':str(version)[:80], 'version_id':str(version_id)[:90],
            'filename':filename,'url':url,'size':size,'hashes':_hashes(hashes),
            'game_versions':list(game_versions)[:100], 'loaders':list(loaders)[:40],
            'dependencies':list(dependencies or [])[:50],
            'compatibility':'Not verified' if provider=='GitHub' else 'Metadata available'}


def github_files(identity, *, fetch=None):
    """List non-draft, non-prerelease release assets; never assume a repository fits a game."""
    if not isinstance(identity,str) or not GITHUB_REPO.fullmatch(identity) or '..' in identity.split('/'):
        raise DownloadError('Invalid GitHub repository identity.')
    url=f'https://api.github.com/repos/{identity}/releases?per_page=12'
    data=catalog.fetch_json(url,fetch=fetch)
    if not isinstance(data,list):raise DownloadError('Unexpected GitHub release listing.')
    results=[]
    for release in data[:12]:
        if not isinstance(release,dict) or release.get('draft') or release.get('prerelease'):continue
        tag=release.get('tag_name') or ''
        if not isinstance(tag,str) or not tag:continue
        for asset in (release.get('assets') or [])[:60]:
            if not isinstance(asset,dict) or asset.get('state','uploaded')!='uploaded':continue
            rawurl=asset.get('browser_download_url') or ''
            row=_row('GitHub',identity,tag,asset.get('name'),rawurl,asset.get('size'),
                     {'sha256':str(asset.get('digest') or '').removeprefix('sha256:')},[],[])
            if row:
                # Never accept an asset URL pointing to a different repository.
                parts=urllib.parse.urlsplit(rawurl).path.split('/')
                if len(parts)<7 or '/'.join(parts[1:3]).lower()!=identity.lower():continue
                results.append(row)
        if len(results)>=80:break
    return results[:80]


def modrinth_files(identity, *, game_version='', loader='', fetch=None):
    """List versions with exact game-version and loader filtering via Modrinth API."""
    if not isinstance(identity,str) or not MODRINTH_PROJECT.fullmatch(identity):
        raise DownloadError('Invalid Modrinth project identity.')
    query={'include_changelog':'false'}
    if game_version:
        if not re.fullmatch(r'[a-zA-Z0-9_.+-]{1,45}',game_version):raise DownloadError('Invalid game version filter.')
        query['game_versions']='["'+game_version+'"]'
    if loader:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',loader):raise DownloadError('Invalid loader filter.')
        query['loaders']='["'+loader+'"]'
    url='https://api.modrinth.com/v2/project/'+identity+'/version?'+urllib.parse.urlencode(query)
    data=catalog.fetch_json(url,fetch=fetch)
    if not isinstance(data,list):raise DownloadError('Unexpected Modrinth versions listing.')
    rows=[]
    for version in data[:50]:
        if not isinstance(version,dict):continue
        gv=version.get('game_versions') or []; ls=version.get('loaders') or []
        if not isinstance(gv,list) or not isinstance(ls,list):continue
        if game_version and game_version not in gv:continue
        if loader and loader not in ls:continue
        for f in (version.get('files') or [])[:25]:
            if not isinstance(f,dict):continue
            row=_row('Modrinth',identity,version.get('version_number') or version.get('name') or '',
                     f.get('filename'),f.get('url'),f.get('size'),f.get('hashes'),gv,ls,version.get('dependencies'),version_id=version.get('id') or '')
            if row:
                row['primary']=bool(f.get('primary'))
                row['file_type']=str(f.get('file_type') or '')[:40]
                rows.append(row)
        if len(rows)>=100:break
    return rows[:100]


def list_files(provider,identity,*,game_version='',loader='',fetch=None):
    if provider=='GitHub':return github_files(identity,fetch=fetch)
    if provider=='Modrinth':return modrinth_files(identity,game_version=game_version,loader=loader,fetch=fetch)
    raise DownloadError('This provider does not yet support in-app file selection.')


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self,provider):self.provider=provider
    def redirect_request(self,req,fp,code,msg,hdrs,newurl):
        if not _safe_url(newurl,self.provider):
            raise DownloadError('Download redirected outside approved provider hosts.')
        return super().redirect_request(req,fp,code,msg,hdrs,newurl)


def _signature(filename,head):
    if filename.lower().endswith(('.zip','.jar','.mrpack')):
        return head.startswith((b'PK\x03\x04',b'PK\x05\x06'))
    if filename.lower().endswith('.7z'):return head.startswith(b'7z\xbc\xaf\x27\x1c')
    if filename.lower().endswith('.rar'):return head.startswith((b'Rar!\x1a\x07\x00',b'Rar!\x1a\x07\x01'))
    return False


def download_file(record, directory, *, opener=None, max_size=MAX_FILE, progress=None):
    """Only stage a selected file. Validate size/hash/signature, never overwrite, no installation.

    opener is injectable for offline integration tests and should support open(Request, timeout).
    """
    if not isinstance(record,dict):raise DownloadError('Select a file from the provider listing.')
    provider=record.get('provider');url=record.get('url');name=_filename(record.get('filename'))
    if not _safe_url(url,provider):raise DownloadError('File URL is not from an approved provider host.')
    identity=record.get('identity')
    if provider=='Modrinth' and (not isinstance(identity,str) or not MODRINTH_PROJECT.fullmatch(identity) or
                                  not urllib.parse.urlsplit(url).path.startswith('/data/'+identity+'/')):
        raise DownloadError('Modrinth file does not belong to the selected project.')
    if provider=='mod.io' and (not isinstance(identity,str) or not re.fullmatch(r'[1-9]\d{0,11}/[1-9]\d{0,11}',identity) or
                              not re.fullmatch(r'[1-9]\d{0,11}',str(record.get('version_id'))) or
                              not urllib.parse.urlsplit(url).path.startswith('/v1/games/'+identity.split('/')[0]+'/mods/'+identity.split('/')[1]+'/files/'+str(record['version_id'])+'/download/')):
        raise DownloadError('mod.io download does not match the selected game and modfile.')
    if provider=='GitHub' and (not isinstance(identity,str) or not GITHUB_REPO.fullmatch(identity) or
                               not urllib.parse.urlsplit(url).path.lower().startswith('/'+identity.lower()+'/releases/download/')):
        raise DownloadError('GitHub file does not belong to the selected repository.')
    try:size=int(record.get('size'))
    except (ValueError,TypeError):raise DownloadError('Missing file size.') from None
    if not 0<size<=min(max_size,MAX_FILE):raise DownloadError('File exceeds the download limit.')
    directory=Path(directory).expanduser().resolve()
    if not directory.is_dir():raise DownloadError('Choose an existing Downloads folder.')
    dest=directory/name
    if dest.exists():raise FileExistsError('A file with this name already exists; no overwrite was made.')
    hashes=_hashes(record.get('hashes') or {})
    if provider=='mod.io' and not hashes.get('md5'):
        raise DownloadError('mod.io file has no expected MD5 checksum.')
    check={key:hashlib.new(key) for key in hashes}
    tmp=None
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'UniMod/0.55-test12 (Linux mod manager)'})
        opener=opener or urllib.request.build_opener(_Redirects(provider))
        with opener.open(request,timeout=30) as response:
            if not _safe_url(response.geturl(),provider):raise DownloadError('Unexpected download response host.')
            announced=response.headers.get('Content-Length') if hasattr(response,'headers') else None
            if announced and announced.isdigit() and int(announced)>max_size:
                raise DownloadError('Download exceeds size limit.')
            with tempfile.NamedTemporaryFile(dir=directory,prefix='.unimod-',suffix='.part',delete=False) as f:
                tmp=Path(f.name);total=0;head=b''
                while True:
                    piece=response.read(262144)
                    if not piece:break
                    total+=len(piece)
                    if total>min(max_size,MAX_FILE):raise DownloadError('Download exceeds size limit.')
                    if len(head)<8:head+=piece[:8-len(head)]
                    for h in check.values():h.update(piece)
                    f.write(piece)
                    if progress:progress(total,size)
        if total!=size:raise DownloadError('Download size did not match provider metadata.')
        if not _signature(name,head):raise DownloadError('File is not a valid expected archive type.')
        if name.lower().endswith(('.zip','.jar','.mrpack')) and not zipfile.is_zipfile(tmp):
            raise DownloadError('Downloaded ZIP/JAR archive is incomplete or invalid.')
        for method,digest in hashes.items():
            if check[method].hexdigest()!=digest:raise DownloadError('Provider checksum mismatch.')
        # An exclusive hard link prevents clobbering files created during transfer.
        os.link(tmp,dest)
        return dest
    except OSError as exc:
        raise DownloadError('Download failed. Check your connection or destination folder.') from None
    finally:
        if tmp is not None:
            try:tmp.unlink(missing_ok=True)
            except OSError:pass
