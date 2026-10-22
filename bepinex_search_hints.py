"""Offline search hints for Graveyard Keeper BepInEx DLLs without original ZIPs.

Hints are search terms, not authenticated Nexus provenance. The module never
executes a DLL, reads other games, contacts a provider, assigns sources or
modifies an installed game. Untrusted manifests must remain untrusted.
"""
import json
import re
from pathlib import Path
from bepinex_nexus_evidence import SUPPORTED_GAMES, MAX_DLLS, _safe_installed_path, file_digest

MAX_MANIFEST_BYTES=64*1024
BLOCKED_TERMS={'mod','mods','plugin','plugins','bepinex','core','assembly','library','managed','dll',
               'graveyard keeper','graveyard keeper 2','version','default','patch','loader'}

def readable_title(value):
    if not isinstance(value,str) or len(value)>200 or any(ord(c)<32 for c in value):
        return ''
    value=value.removesuffix('.dll')
    value=re.sub(r'(?<=[a-z0-9])(?=[A-Z])',' ',value)
    value=re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])',' ',value)
    value=re.sub(r'[_.\-]+',' ',value)
    value=re.sub(r'\s+',' ',value).strip()
    # Do not build searches from paths, markup, URLs or meaningless tokens.
    if (not 3<=len(value)<=100 or len(value.split())>12 or '/' in value or '\\' in value
            or '://' in value or value.casefold() in BLOCKED_TERMS
            or not any(c.isalpha() for c in value)):
        return ''
    return value

def safe_manifest_name(path, plugins):
    """Return a local package name, if a bounded non-symlink manifest exists."""
    try:
        plugins=Path(plugins).resolve(strict=True)
        folder=Path(path).parent
        while folder==plugins or folder.is_relative_to(plugins):
            if folder.is_symlink():return ''
            for name in ('manifest.json','thunderstore.toml'):
                source=folder/name
                if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_MANIFEST_BYTES:
                    continue
                data=source.read_text(encoding='utf-8-sig')
                if name.endswith('.json'):
                    obj=json.loads(data)
                else:
                    try:
                        import tomllib  # Python 3.11+
                    except ModuleNotFoundError:
                        import tomli as tomllib  # Python 3.10
                    obj=tomllib.loads(data)
                    if isinstance(obj,dict):obj=obj.get('package',obj)
                if isinstance(obj,dict):
                    val=readable_title(obj.get('name'))
                    if val:return val
            if folder==plugins:break
            folder=folder.parent
    except (OSError,ValueError,RuntimeError,UnicodeError,TypeError,json.JSONDecodeError):
        return ''
    return ''

def preview_search_hints(game, mods, *, known_source=None, identity=None):
    if game.get('kind')!='bepinex' or game.get('name') not in SUPPORTED_GAMES:
        raise ValueError('Select Graveyard Keeper or Graveyard Keeper 2 BepInEx mods.')
    root=Path(game['root']).resolve(strict=True)
    plugins=root/'BepInEx'/'plugins'
    if not plugins.is_dir() or plugins.is_symlink():
        raise ValueError('BepInEx plugins folder not found.')
    mods=list(mods)
    if len(mods)>MAX_DLLS:raise ValueError('Too many installed DLLs for one scan.')
    rows=[];seen={};digests={}
    for mod in mods:
        path=_safe_installed_path(game,mod)
        # Only files in the current game's BepInEx plugins folder are in scope.
        if path and not path.resolve(strict=True).is_relative_to(plugins.resolve(strict=True)):
            path=None
        fingerprint=file_digest(path) if path else None
        sid=identity(game,mod) if identity else str(mod.get('path') or '')
        seen[sid]=seen.get(sid,0)+1
        if fingerprint:digests[fingerprint]=digests.get(fingerprint,0)+1
        hint=safe_manifest_name(path,plugins) if fingerprint else ''
        if not hint:hint=readable_title(mod.get('name') or '')
        if not hint and path:hint=readable_title(path.stem)
        rows.append({'mod':mod,'name':str(mod.get('name') or '')[:180],
                     'identity':sid,'fingerprint':fingerprint,'game_domain':SUPPORTED_GAMES[game['name']],
                     'query':hint,'basis':('Local package manifest / name hint' if hint else 'No safe search name'),
                     'status':'Search ready' if hint else 'No useful name'})
    for row in rows:
        if known_source and known_source(game,row['mod']):row['status']='Already linked'
        elif not row['fingerprint']:row['status']='Not readable'
        elif seen[row['identity']]>1 or digests[row['fingerprint']]>1:row['status']='Ambiguous DLL'
    return rows

def validate_search_hint(game, row, *, identity=None, known_source=None):
    if game.get('kind')!='bepinex' or SUPPORTED_GAMES.get(game.get('name')) != row.get('game_domain'):
        raise ValueError('Game selection changed. Scan again.')
    if row.get('status')!='Search ready' or not readable_title(row.get('query')):
        raise ValueError('Select an unlinked DLL with a usable search hint.')
    mod=row.get('mod') or {}
    if identity and identity(game,mod)!=row.get('identity'):
        raise ValueError('Mod selection changed. Scan again.')
    if known_source and known_source(game,mod):
        raise ValueError('Source has already been assigned. Scan again.')
    plugins=Path(game['root']).resolve(strict=True)/'BepInEx'/'plugins'
    path=_safe_installed_path(game,mod)
    if (not path or not path.resolve(strict=True).is_relative_to(plugins.resolve(strict=True))
            or file_digest(path)!=row.get('fingerprint')):
        raise ValueError('Installed DLL changed or is no longer safe to inspect. Rescan.')
    return row['query']
