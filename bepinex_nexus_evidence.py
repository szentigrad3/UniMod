"""Offline Nexus download-archive evidence for installed Graveyard Keeper BepInEx DLLs.

All downloaded files and .meta sidecars are untrusted. SHA-256 equality only
establishes that bytes in the archive match the installed DLL; it does not
prove who published those bytes or authenticate the .meta file. Never writes
game files, accepts paths from ZIPs as extraction destinations, or contacts Nexus.
"""
import hashlib
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from source_provenance import read_mo2_sidecar

SUPPORTED_GAMES = {'Graveyard Keeper': 'graveyardkeeper', 'Graveyard Keeper 2': 'graveyardkeeper2'}
MAX_ARCHIVES = 120
MAX_ZIP_BYTES = 500 * 1024 * 1024
MAX_FILES_IN_ARCHIVE = 2500
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_DLLS = 1200
MAX_DLLS_PER_ARCHIVE = 300
MAX_HASHED_BYTES_PER_ARCHIVE = 256 * 1024 * 1024
MAX_HASHED_INSTALLED_BYTES = 1024 * 1024 * 1024
BLOCK = 1024 * 1024


def file_digest(path):
    """Read a regular local DLL, bounding size and refusing symlink hops."""
    path = Path(path)
    if path.suffix.casefold() != '.dll' or path.is_symlink() or not path.is_file():
        return None
    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_MEMBER_BYTES:
            return None
        h = hashlib.sha256()
        with path.open('rb') as f:
            while (chunk := f.read(BLOCK)):
                h.update(chunk)
        if path.stat().st_size != size:
            return None
        return (h.hexdigest(), size)
    except (OSError, ValueError):
        return None


def _safe_zip_member(info):
    name=info.filename
    if (not isinstance(name,str) or len(name)>500 or '\\' in name or '\x00' in name
            or not name.lower().endswith('.dll') or name.startswith('/') or ':' in name):
        return False
    parts = PurePosixPath(name).parts
    if not parts or any(x in ('', '.', '..') for x in parts):
        return False
    mode=(info.external_attr >> 16) & 0xFFFF
    if stat.S_IFMT(mode) == stat.S_IFLNK:
        return False
    if info.is_dir() or not 0 < info.file_size <= MAX_MEMBER_BYTES:
        return False
    # Ratio guard as well as expanded-size cap; rejects zero-byte compressed DLLs.
    if info.compress_size == 0 or info.file_size > 250 * info.compress_size:
        return False
    return True


def _archive_digests(archive):
    try:
        with zipfile.ZipFile(archive,'r') as z:
            members=z.infolist()
            if len(members)>MAX_FILES_IN_ARCHIVE:return set()
            found=set();hashed=0;count=0
            for info in members:
                if not _safe_zip_member(info):continue
                count+=1
                if count>MAX_DLLS_PER_ARCHIVE or hashed+info.file_size>MAX_HASHED_BYTES_PER_ARCHIVE:
                    return set()
                hashed+=info.file_size
                h=hashlib.sha256();total=0
                try:
                    with z.open(info,'r') as src:
                        while (chunk:=src.read(BLOCK)):
                            total+=len(chunk)
                            if total>MAX_MEMBER_BYTES:break
                            h.update(chunk)
                    if total==info.file_size:found.add((h.hexdigest(), total))
                except (RuntimeError,OSError,EOFError,zipfile.BadZipFile,ValueError):
                    continue
            return found
    except (OSError,ValueError,RuntimeError,zipfile.BadZipFile,EOFError):
        return set()


def _safe_installed_path(game,mod):
    try:
        root=Path(game['root']).resolve(strict=True)
        path=Path(mod['path'])
        if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
            return None
        # Don't follow directory symlinks to outside or within a game.
        cur=path.parent
        while cur != root and cur.is_relative_to(root):
            if cur.is_symlink():return None
            cur=cur.parent
        return path
    except (OSError,ValueError,RuntimeError,KeyError):
        return None


def preview_archive_evidence(game, mods, folder, *, known_source=None, identity=None):
    """Return review rows with exact local-file matches and explicit conflicts.

    Caller supplies callbacks for known-source detection and per-game identity.
    No online search, no writes, no automatic source approval.
    """
    if game.get('kind') != 'bepinex' or game.get('name') not in SUPPORTED_GAMES:
        raise ValueError('Offline Nexus archive matching supports Graveyard Keeper BepInEx games only.')
    domain=SUPPORTED_GAMES[game['name']]
    folder=Path(folder).expanduser()
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Select a real local download folder (not a symlink).')
    mods=list(mods)
    if len(mods)>MAX_DLLS:raise ValueError('Too many installed DLLs for one scan.')
    entries=[];index={};identities={};total_installed=0
    for mod in mods:
        path=_safe_installed_path(game,mod)
        fingerprint=file_digest(path) if path else None
        sid=identity(game,mod) if identity else str(mod.get('path') or '')
        identities[sid]=identities.get(sid,0)+1
        if fingerprint:
            total_installed += fingerprint[1]
            if total_installed > MAX_HASHED_INSTALLED_BYTES:
                raise ValueError("Installed DLL scan exceeds safety size limit.")
            index.setdefault(fingerprint,[]).append(sid)
        entries.append({'mod':mod,'name':str(mod.get('name') or '')[:180],
                        'identity':sid,'fingerprint':fingerprint,
                        'status':'Source needed','candidate':None,
                        'evidence':'No matching ZIP with same-game Nexus metadata.'})
    found={};archives_seen=0
    try:
        archives=sorted((p for p in folder.iterdir() if p.suffix.casefold()=='.zip' and p.is_file() and not p.is_symlink()),
                        key=lambda p:p.name.casefold())[:MAX_ARCHIVES]
    except OSError:archives=[]
    for archive in archives:
        try:
            if archive.stat().st_size > MAX_ZIP_BYTES or archive.stat().st_size < 50:continue
        except OSError:continue
        sidecar=read_mo2_sidecar(archive,domain)
        if not sidecar:continue
        archives_seen+=1
        matched=_archive_digests(archive).intersection(index)
        for digest in matched:
            for sid in index[digest]:
                found.setdefault(sid,{}).setdefault(sidecar['mod_id'],set()).add(
                    f"{archive.name} (Nexus file {sidecar['file_id']})")
    for row in entries:
        ident=row['identity'];d=row['fingerprint']; candidates=found.get(ident,{})
        if known_source and known_source(game,row['mod']):
            row.update(status='Already linked', evidence='Existing source retained; no overrides')
        elif identities[ident]>1 or (d and len(index.get(d,[]))>1):
            row.update(status='Ambiguous installed DLL', evidence='Duplicate installed identity or identical DLL bytes')
        elif d is None:
            row.update(status='Not readable', evidence='Invalid, symlinked, missing or oversized local DLL')
        elif len(candidates)>1:
            row.update(status='Conflicting Nexus IDs', evidence='Downloaded archives for this exact DLL disagree on the Nexus mod ID')
        elif len(candidates)==1:
            mod_id, sources=next(iter(candidates.items()))
            row.update(status='Review candidate',
                candidate={'url':f'https://www.nexusmods.com/{domain}/mods/{mod_id}',
                           'game_domain':domain,'mod_id':mod_id},
                evidence='Exact DLL SHA-256 match; untrusted sidecar: '+', '.join(sorted(sources)[:2]))
    return {'rows':entries,'archives_with_metadata':archives_seen,
            'reviewable':sum(r['status']=='Review candidate' for r in entries)}
