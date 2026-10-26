"""mod.io (user API-key) reviewed modfile downloads.

Metadata requests use the user's session key; signed CDN URLs are never stored
in receipts, logs, or installation records. Game writes occur elsewhere, only
after a separate identity-based installer preflight and confirmation.
"""
import hashlib
import re
import time
from urllib.parse import urlencode, urlsplit

import provider_catalogues as catalogue
import provider_downloads


class ModioError(ValueError):
    pass


def _identity(value):
    if not isinstance(value,str) or not re.fullmatch(r'[1-9]\d{0,11}/[1-9]\d{0,11}',value):
        raise ModioError('Select an exact mod.io game and mod.')
    return value.split('/')


def _base(user_id, api_key):
    if not isinstance(api_key,str) or len(api_key.strip())<8:
        raise ModioError('Enter your mod.io session key.')
    # The documented legacy public API host supports key-only GET routes when
    # available. Newer account-scoped keys may require their unique API path.
    return (f'https://u-{catalogue.numeric(user_id)}.modapi.io/v1'
            if user_id is not None else 'https://api.mod.io/v1')


def _parse_modfile(data, game, mod):
    if not isinstance(data,dict) or str(data.get('mod_id'))!=mod:
        return None
    if data.get('game_id') is not None and str(data['game_id'])!=game:
        return None
    fid=str(data.get('id') or '')
    if not re.fullmatch(r'[1-9]\d{0,11}',fid):return None
    # Only reviewed ZIP packages can be sent to UniMod's game-specific installer.
    try: filename=provider_downloads._filename(data.get('filename'))
    except provider_downloads.DownloadError:return None
    if not filename.lower().endswith('.zip'):return None
    try:size=int(data.get('filesize'))
    except (ValueError,TypeError,OverflowError):return None
    if not 0<size<=provider_downloads.MAX_FILE:return None
    expected=(data.get('filehash') or {}).get('md5') if isinstance(data.get('filehash'),dict) else None
    if not isinstance(expected,str) or not re.fullmatch(r'[a-fA-F0-9]{32}',expected):
        return None  # no source hash, no download
    if data.get('virus_positive') not in (None,0):return None
    if data.get('virus_status') not in (None,1):return None
    download=data.get('download') or {}
    if not isinstance(download,dict):return None
    url=download.get('binary_url') or ''
    if not provider_downloads._safe_url(url,'mod.io'):return None
    # API downloads must identify the same exact game, mod, and file.
    parsed=urlsplit(url)
    prefix=f'/v1/games/{game}/mods/{mod}/files/{fid}/download/'
    if not parsed.path.startswith(prefix) or len(parsed.path)<=len(prefix):return None
    expires=download.get('date_expires')
    try:expires=int(expires) if expires is not None else 0
    except (TypeError,ValueError):return None
    if expires and expires<=int(time.time())+15:return None
    platforms=data.get('platforms') or []
    if not isinstance(platforms,list):return None
    if platforms and not any(isinstance(p,dict) and str(p.get('platform','')).upper() in ('ALL','LINUX','WINDOWS') and p.get('status')==1 for p in platforms):
        return None
    return {'provider':'mod.io','identity':f'{game}/{mod}','version_id':fid,'version':str(data.get('version') or '')[:80],
            'date_added':_date_added(data.get('date_added')),
            'filename':filename,'size':size,'hashes':{'md5':expected.lower()},'url':url,
            'expires':expires,'game_versions':[],'loaders':[],'dependencies':[],
            'compatibility':'Package compatibility must be reviewed; metadata does not prove installability'}


def _date_added(value):
    # The timestamp is API evidence, not a semantic-version comparison.
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if 0 < number <= 4102444800 else 0


def get_modfile_date(identity, file_id, *, user_id, api_key, fetch=None):
    """Read the exact installed modfile's date, even if its signed URL expired.

    This is metadata-only. Never trust a date from a different mod or game.
    Returns zero if the API did not supply a valid publication date.
    """
    game, mod = _identity(identity)
    fid = catalogue.numeric(file_id)
    base = _base(user_id, api_key)
    address = f'{base}/games/{game}/mods/{mod}/files/{fid}?' + urlencode({'api_key': api_key.strip()})
    result = catalogue.fetch_json(address, fetch=fetch)
    if (not isinstance(result, dict) or str(result.get('id')) != fid
            or str(result.get('mod_id')) != mod
            or (result.get('game_id') is not None and str(result['game_id']) != game)):
        raise ModioError('The installed mod.io file no longer has verifiable game/mod identity.')
    return _date_added(result.get('date_added'))


def list_modfiles(identity, *, user_id, api_key, fetch=None):
    game,mod=_identity(identity)
    base=_base(user_id,api_key)
    # mod.io defaults to ascending ID (oldest first). Never silently miss the
    # latest releases for a project with more than 100 modfiles.
    address=f'{base}/games/{game}/mods/{mod}/files?'+urlencode({'api_key':api_key.strip(),'_limit':100,'_sort':'-date_added'})
    result=catalogue.fetch_json(address,fetch=fetch)
    if not isinstance(result,dict) or not isinstance(result.get('data'),list):
        raise ModioError('mod.io returned an invalid modfile list.')
    rows=[]
    for item in result['data'][:100]:
        row=_parse_modfile(item,game,mod)
        if row:rows.append(row)
    rows.sort(key=lambda x:(x['date_added'],int(x['version_id'])),reverse=True)
    return rows


def list_probe_candidates(identity, *, user_id, api_key, fetch=None, limit=3):
    """Read-only candidates for the isolated temporary AIO test.

    Collection records can have absent/expired short-lived download URLs.
    Keep their exact ID, MD5, size and version, then require an independent
    exact-file GET via refresh_selected() before any transfer. These preview
    records are never valid installation receipts or download URLs.
    """
    game,mod=_identity(identity)
    if type(limit) is not int or not 1<=limit<=3:
        raise ModioError('Invalid temporary probe limit.')
    base=_base(user_id,api_key)
    url=f'{base}/games/{game}/mods/{mod}/files?'+urlencode({
        'api_key':api_key.strip(),'_limit':100,'_sort':'-date_added'})
    response=catalogue.fetch_json(url,fetch=fetch)
    if not isinstance(response,dict) or not isinstance(response.get('data'),list):
        raise ModioError('mod.io returned an invalid modfile list.')
    candidates=[]
    rejected=0
    records=response['data'][:100]
    for item in records:
        if not isinstance(item,dict) or str(item.get('mod_id'))!=mod or (
                item.get('game_id') is not None and str(item['game_id'])!=game):
            rejected+=1
            continue
        fid=str(item.get('id') or '')
        if not re.fullmatch(r'[1-9]\\d{0,11}',fid):
            rejected+=1
            continue
        try:
            filename=provider_downloads._filename(item.get('filename'))
            size=int(item.get('filesize'))
        except (provider_downloads.DownloadError,ValueError,TypeError,OverflowError):
            rejected+=1
            continue
        md5=(item.get('filehash') or {}).get('md5') if isinstance(item.get('filehash'),dict) else None
        if (not filename.lower().endswith('.zip') or
                not 0<size<=provider_downloads.MAX_FILE or
                not isinstance(md5,str) or not re.fullmatch(r'[a-fA-F0-9]{32}',md5) or
                item.get('virus_positive') not in (None,0) or
                item.get('virus_status') not in (None,1)):
            rejected+=1
            continue
        # Keep only stable, expected properties. No URL from this collection
        # is ever used until its exact file metadata has been refetched.
        candidates.append({
            'provider':'mod.io','identity':f'{game}/{mod}',
            'version_id':fid,'filename':filename,'size':size,
            'hashes':{'md5':md5.lower()},
            'version':str(item.get('version') or '')[:80],
        })
    candidates.sort(key=lambda x:(x['size'],-int(x['version_id'])))
    return candidates[:limit],len(records),rejected


def refresh_selected(record, *, user_id, api_key, fetch=None):
    """Obtain a fresh signed URL from exact-ID file endpoint before download."""
    if not isinstance(record,dict) or record.get('provider')!='mod.io':
        raise ModioError('Select a mod.io file.')
    game,mod=_identity(record.get('identity'))
    fid=catalogue.numeric(record.get('version_id'))
    base=_base(user_id,api_key)
    address=f'{base}/games/{game}/mods/{mod}/files/{fid}?'+urlencode({'api_key':api_key.strip()})
    result=catalogue.fetch_json(address,fetch=fetch)
    row=_parse_modfile(result,game,mod)
    if row is None or row['version_id']!=fid:
        raise ModioError('Selected mod.io file is no longer available for this game.')
    # Avoid races where the file was replaced with different bytes after review.
    for field in ('filename','size','hashes','version'):
        if record.get(field)!=row[field]:
            raise ModioError('The mod.io release changed since review. Refresh the file list.')
    return row


def download_selected(record, directory, *, user_id, api_key, fetch=None, opener=None,
                      max_size=provider_downloads.MAX_FILE):
    new=refresh_selected(record,user_id=user_id,api_key=api_key,fetch=fetch)
    return provider_downloads.download_file(new,directory,opener=opener,max_size=max_size)
