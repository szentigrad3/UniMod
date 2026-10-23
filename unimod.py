#!/usr/bin/env python3
"""UniMod 0.55 test12 - reviewed mod.io downloads and ZIP updates."""
import json, os, re, shutil, subprocess, tempfile, threading, urllib.request, urllib.error, webbrowser, zipfile, datetime, time, csv, hashlib, sys, queue, sqlite3
from pathlib import Path
from source_provenance import read_mo2_sidecar
from archive_discovery import find_archives
import archive_discovery
import source_receipts
from contextlib import closing
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import nexus_integration as nexus_integr
import nexus_oauth as nexus_oauth
from nexus_queue import NexusDownloadQueue
import nxm_handler
import instance_bridge
import smapi_catalogue
import smapi_lookup_cache
import provider_catalogues
import provider_downloads
import modio_files
import modio_managed
import modio_diagnostics
import provider_staging
import minecraft_profiles
import minecraft_dependencies
import minecraft_mrpack
import bepinex_nexus_evidence
import bepinex_search_hints
import candidate_review
import provider_access

APP = Path.home()/'.config'/'unimod'; CONFIG = APP/'games.json'; INVENTORY = APP/'inventory.json'
NEXUS_RECEIPTS = APP/'nexus-download-receipts.json'
APP.mkdir(parents=True, exist_ok=True)
GAME_HINTS={'Stardew Valley':'Stardew Valley','Graveyard Keeper 2':'Graveyard Keeper 2','Graveyard Keeper':'Graveyard Keeper'}
UI_SETTINGS = APP/'ui.json'
STEAM_LIBRARY_CONFIG = APP/'steam-libraries.json'
STORE_LINKS={'Nexus Mods':'https://www.nexusmods.com/','Thunderstore':'https://thunderstore.io/','CurseForge':'https://www.curseforge.com/','Modrinth':'https://modrinth.com/mods','ModDB':'https://www.moddb.com/mods','GitHub':'https://github.com/','Steam Workshop':'https://steamcommunity.com/workshop/','mod.io':'https://mod.io/'}

def cfg_load():
    try: return json.loads(CONFIG.read_text())
    except (OSError, ValueError): return {'games':[]}
def cfg_save(data):
    tmp=CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2)); tmp.replace(CONFIG)
def unique(dst):
    if not dst.exists(): return dst
    for i in range(2,10000):
        candidate=dst.with_name(f'{dst.name}-{i}')
        if not candidate.exists(): return candidate
    raise RuntimeError('Too many duplicate names')
def normalize_steam_library(path):
    """Canonical steamapps path, accepting a library root or steamapps folder.

    Reject directories without a common folder. Manual paths are never created.
    Resolved symlinks can represent intentionally linked Steam libraries.
    """
    try:
        base=Path(path).expanduser().resolve(strict=True)
        for apps in (base, base/'steamapps'):
            if apps.name=='steamapps' and apps.is_dir() and (apps/'common').is_dir():
                return apps
    except (OSError, RuntimeError, ValueError, TypeError):
        pass
    return None


def load_custom_steam_libraries():
    """Read optional library locations without trusting saved paths as game IDs."""
    try:
        data=json.loads(STEAM_LIBRARY_CONFIG.read_text(encoding='utf-8'))
        if not isinstance(data,list):return []
        return [v for v in data[:200] if isinstance(v,str) and v.strip() and len(v)<4096]
    except (OSError,ValueError):return []


def save_custom_steam_libraries(paths):
    """Store only verified local libraries and write atomically."""
    roots={}
    for raw in paths:
        if apps:=normalize_steam_library(raw):roots[str(apps)]=apps
    STEAM_LIBRARY_CONFIG.parent.mkdir(parents=True,exist_ok=True)
    tmp=STEAM_LIBRARY_CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps(sorted(roots),indent=2)+'\n',encoding='utf-8')
    tmp.replace(STEAM_LIBRARY_CONFIG)
    return sorted(roots)


def mounted_steam_libraries(mount_roots=None, max_visits=1200, max_depth=4):
    """Bounded shallow search: mounts like /mnt/games/Steam/steamapps.

    Does not inspect game contents, follow symlink directories, or traverse
    arbitrary user trees. Custom paths cover unusually deeply nested libraries.
    """
    from collections import deque
    mount_roots=[Path(p) for p in (mount_roots if mount_roots is not None else ('/mnt','/run/media','/media'))]
    results=set();seen=set();queue_dirs=deque((p,0) for p in mount_roots)
    visits=0
    skip={'steamapps','common','compatdata','shadercache','.Trash-1000','$RECYCLE.BIN','lost+found','.cache','.git','node_modules'}
    while queue_dirs and visits<max_visits:
        folder,depth=queue_dirs.popleft()
        try:
            if folder.is_symlink() or not folder.is_dir():continue
            canonical=str(folder.resolve())
            if canonical in seen:continue
            seen.add(canonical);visits+=1
            if apps:=normalize_steam_library(folder/'steamapps'):
                results.add(str(apps))
            if folder.name=='steamapps':
                if apps:=normalize_steam_library(folder):results.add(str(apps))
                continue
            if depth>=max_depth:continue
            # Bound directory listing as well as total scanned directories.
            with os.scandir(folder) as entries:
                subdirs=[]
                inspected=0
                for entry in entries:
                    inspected+=1
                    if inspected>1000 or len(subdirs)>=180:break
                    if entry.name not in skip and not entry.name.startswith('.') and entry.is_dir(follow_symlinks=False):
                        subdirs.append(Path(entry.path))
                queue_dirs.extend((p,depth+1) for p in subdirs)
        except (OSError,PermissionError,RuntimeError):continue
    return [Path(v) for v in sorted(results)]


def steam_library_inventory():
    """Return all found libraries, identifying user-defined paths for the GUI."""
    auto=set()
    home=Path.home()
    bases=[home/'.local/share/Steam',home/'.steam/steam',home/'.steam/root',
           home/'.var/app/com.valvesoftware.Steam/.local/share/Steam',
           home/'.var/app/com.valvesoftware.Steam/.steam/steam']
    for base in bases:
        if apps:=normalize_steam_library(base):auto.add(str(apps))
        file=base/'steamapps/libraryfolders.vdf'
        try:
            if not file.is_file() or file.stat().st_size>1024*1024:continue
            # Steam writes path entries in its VDF. Do not execute this text.
            for raw in re.findall(r'"path"\s+"([^"\n]+)"',file.read_text(errors='replace')):
                if apps:=normalize_steam_library(raw.replace('\\','/')):auto.add(str(apps))
        except (OSError,ValueError):pass
    auto.update(str(p) for p in mounted_steam_libraries())
    manual={str(p) for raw in load_custom_steam_libraries() if (p:=normalize_steam_library(raw))}
    return [{'path':p,'origin':'Custom + detected' if p in manual and p in auto else 'Custom' if p in manual else 'Detected'}
            for p in sorted(auto|manual)]


def steam_roots():
    return [Path(entry['path']) for entry in steam_library_inventory()]

def steam_appmanifest_games(steamapps):
    """Return local Steam games identified by their appmanifest; never trust paths outside common/."""
    common=steamapps/'common'
    if not common.is_dir():return []
    result=[]
    try:
        manifests=sorted(steamapps.glob('appmanifest_*.acf'))[:5000]
        for entry in manifests:
            if not entry.is_file() or entry.is_symlink() or not entry.stem.removeprefix('appmanifest_').isdigit() or entry.stat().st_size>256*1024:continue
            raw=entry.read_text(encoding='utf-8-sig',errors='replace')
            def field(key):
                m=re.search(r'"'+re.escape(key)+r'"\s+"((?:\\.|[^"\\])*)"',raw,re.I)
                return m.group(1).replace('\\"','"').replace('\\\\','\\') if m else ''
            directory=field('installdir')
            title=field('name') or directory
            # Do not follow traversal values, absolute paths or symlinked directories.
            if not directory or directory in ('.','..') or '/' in directory or '\\' in directory:continue
            installed=common/directory
            if installed.is_symlink() or not installed.is_dir():continue
            resolved=installed.resolve()
            if not resolved.is_relative_to(common.resolve()):continue
            kind=infer_mod_layout(installed,title)
            if kind:result.append({'name':title,'root':str(installed),'kind':kind, 'appid':entry.stem.removeprefix('appmanifest_'), 'steamapps':str(steamapps)})
    except (OSError,UnicodeError):pass
    return result

def infer_mod_layout(root,title=''):
    """Only auto-register a Steam installation when a recognisable mod layout exists."""
    root=Path(root)
    if (root/'BepInEx'/'plugins').is_dir():return 'bepinex'
    if (root/'MelonLoader').is_dir() and (root/'Mods').is_dir():return 'melonloader'
    if (root/'Mods').is_dir():
        if str(title).casefold()=='stardew valley':return 'smapi'
        # Probe modestly to avoid expensive recursive scans of arbitrary games.
        try:
            for folder in list((root/'Mods').iterdir())[:150]:
                if folder.is_dir() and not folder.is_symlink() and smapi_manifest(folder):return 'smapi'
        except OSError:pass
    return None

def _verified_launcher_game(title, installed_path, launcher, store='', reference=''):
    """Import only existing, non-symlink game installations with identifiable mod layouts.

    Source metadata is untrusted, even when read from a local launcher config.
    A launcher record alone never authorises modifications to game content.
    """
    if not isinstance(installed_path, str) or not installed_path.strip() or len(installed_path)>4096:
        return None
    try:
        folder=Path(installed_path).expanduser()
        # Relative paths are ambiguous and not safe automatic-import targets.
        if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():return None
        folder=folder.resolve(strict=True)
        if not folder.is_dir():return None
        title=str(title or folder.name).strip()[:200] or folder.name
        kind=infer_mod_layout(folder,title)
        if kind not in ('smapi','bepinex','melonloader'):return None
        return {'name':title,'root':str(folder),'kind':kind,'launcher':launcher,
                'store':store,'launcher_ref':str(reference)[:150]}
    except (OSError,RuntimeError,ValueError,TypeError):
        return None


def _read_launcher_json(path, max_bytes=8*1024*1024):
    """Read only a specific launcher install index; never scan caches or account tokens."""
    try:
        path=Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size>max_bytes:return None
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,UnicodeError,ValueError,TypeError):return None


def heroic_game_inventory(config_roots=None):
    """Recognise Heroic Epic, GOG, Amazon and standalone Legendary installed games.

    Both native and Flatpak config layouts are supported. Unknown formats are
    ignored; only actual directories with mod frameworks are imported.
    """
    home=Path.home()
    if config_roots is None:
        locations=[(home/'.config/heroic','Heroic'),
                   (home/'.var/app/com.heroicgameslauncher.hgl/config/heroic','Heroic'),
                   (home/'.config/legendary','Legendary'),
                   (home/'.var/app/com.heroicgameslauncher.hgl/config/legendary','Legendary')]
    else:
        locations=[(Path(base),str(label)) for base,label in config_roots]
    formats=[('legendaryConfig/legendary/installed.json','Epic'),
             ('gog_store/installed.json','GOG'),
             ('nile_config/nile/installed.json','Amazon'),
             ('nile_config/installed.json','Amazon')]
    result=[];seen=set()
    for config_root,launcher in locations:
        files=([('installed.json','Epic')] if launcher=='Legendary' else formats)
        for relative,store in files:
            data=_read_launcher_json(config_root/relative)
            if isinstance(data,dict):
                if isinstance(data.get('installed'),list):
                    rows=[(None,v) for v in data['installed'][:5000]]
                else:
                    rows=list(data.items())[:5000]
            elif isinstance(data,list):rows=[(None,v) for v in data[:5000]]
            else:continue
            for appid,record in rows:
                if not isinstance(record,dict) or record.get('is_dlc'):continue
                loc=record.get('install_path') or record.get('path')
                # Keep names informative but never use an ID as a filesystem location.
                name=record.get('title') or record.get('name') or record.get('game_title')
                game=_verified_launcher_game(name,loc,launcher,store,
                    record.get('app_name') or record.get('appName') or record.get('id') or appid or '')
                if not game:continue
                key=game['root']
                if key not in seen:result.append(game);seen.add(key)
    return result


def lutris_game_inventory(database_paths=None):
    """Read Lutris pga.db in SQLite immutable read-only mode (no YAML/parser dependencies).

    Rows whose installed flag is false or whose game directory lacks a mod
    framework are ignored. Never connects to the Lutris network or edits DB.
    """
    home=Path.home()
    if database_paths is None:
        database_paths=[home/'.local/share/lutris/pga.db',
                        home/'.var/app/net.lutris.Lutris/data/lutris/pga.db']
    result=[];seen=set()
    from urllib.parse import quote
    for db in database_paths:
        db=Path(db)
        try:
            if not db.is_file() or db.is_symlink() or db.stat().st_size>250*1024*1024:continue
            # immutable avoids sidecar writes to the user's launcher's DB; DB updates
            # during scanning may therefore not be visible until the next scan.
            uri='file:'+quote(str(db.resolve()),safe='/')+'?mode=ro&immutable=1'
            with closing(sqlite3.connect(uri,uri=True,timeout=1)) as conn:
                conn.row_factory=sqlite3.Row
                columns={r['name'] for r in conn.execute('PRAGMA table_info(games)')}
                if not {'name','directory','installed'}.issubset(columns):continue
                runner='runner' if 'runner' in columns else "'' AS runner"
                game_id='id' if 'id' in columns else "'' AS id"
                entries=conn.execute(f'SELECT name,directory,installed,{runner},{game_id} FROM games WHERE installed=1 LIMIT 5000').fetchall()
            for entry in entries:
                game=_verified_launcher_game(entry['name'],entry['directory'],'Lutris',
                                            str(entry['runner'] or ''),str(entry['id'] or ''))
                if game and game['root'] not in seen:result.append(game);seen.add(game['root'])
        except (sqlite3.Error,OSError,RuntimeError,ValueError,TypeError):continue
    return result


def launcher_game_inventory(heroic_roots=None,lutris_databases=None):
    """Read-only discovery independent of Steam, deduplicated by real game path."""
    found=[];seen=set()
    for game in heroic_game_inventory(heroic_roots)+lutris_game_inventory(lutris_databases):
        if game['root'] not in seen:found.append(game);seen.add(game['root'])
    return found

def detect_games():
    result=[];known=set()
    for root in steam_roots():
        # Manifests retain app ID and library; hints cover games before framework setup.
        for game in steam_appmanifest_games(root):
            key=str(Path(game['root']).resolve())
            if key not in known:result.append(game);known.add(key)
        for title,dirname in GAME_HINTS.items():
            p=root/'common'/dirname
            if p.is_dir() and not p.is_symlink():
                key=str(p.resolve())
                if key not in known:
                    result.append({'name':title,'root':str(p),'kind':'smapi' if title=='Stardew Valley' else 'bepinex', 'steamapps':str(root)})
                    known.add(key)
    # Steam metadata wins when two launchers point to the same install.
    for game in launcher_game_inventory():
        key=str(Path(game['root']).resolve())
        if key not in known:result.append(game);known.add(key)
    return result

def mod_root(game):
    root=Path(game['root']); kind=game['kind']
    return root/('Mods' if kind in ('smapi','generic','melonloader') else 'BepInEx/plugins')
def disabled_root(game):return mod_root(game).parent/'.unimod-disabled'
def _manifest_path(folder):
    """SMAPI metadata filenames are usually lowercase; accept other casing too."""
    direct=folder/'manifest.json'
    if direct.is_file() and not direct.is_symlink():return direct
    try:
        for p in folder.iterdir():
            if p.name.casefold()=='manifest.json' and p.is_file() and not p.is_symlink():return p
    except OSError:pass
    return None


def _smapi_json(path):
    """Read SMAPI/JSON.NET-friendly manifests without executing mod code.

    A manifest may contain comments/trailing commas (JSON5 syntax). Bundled
    json5 is used *only* after strict JSON fails. Maximum 1 MiB per manifest.
    """
    raw=path.read_bytes()
    if len(raw)>1024*1024:raise ValueError('manifest is larger than 1 MiB')
    source=raw.decode('utf-8-sig')
    try:return json.loads(source)
    except ValueError:
        import json5
        return json5.loads(source,allow_duplicate_keys=False)


def _manifest_field(raw, name, default=None):
    if not isinstance(raw,dict):return default
    return next((value for key,value in raw.items() if str(key).casefold()==name.casefold()),default)


def smapi_manifest(path):
    manifest=_manifest_path(Path(path))
    if manifest is None:return None
    try:
        raw=_smapi_json(manifest)
        if not isinstance(raw,dict):return None
        uid=_manifest_field(raw,'UniqueID','')
        if not isinstance(uid,str) or not uid.strip():return None
        keys=_manifest_field(raw,'UpdateKeys',[]) or []
        if not isinstance(keys,list):keys=[]
        pack=_manifest_field(raw,'ContentPackFor')
        dependencies=_manifest_field(raw,'Dependencies',[])
        return {'name':str(_manifest_field(raw,'Name') or Path(path).name),
                'author':str(_manifest_field(raw,'Author') or ''),
                'description':str(_manifest_field(raw,'Description') or ''),
                'version':str(_manifest_field(raw,'Version') or ''),
                'uid':uid.strip(), 'update_keys':[str(k) for k in keys if isinstance(k,str)],
                'content_pack_for':str(_manifest_field(pack,'UniqueID','') or '') if isinstance(pack,dict) else '',
                'dependencies':[{'uid':str(_manifest_field(d,'UniqueID','') or ''),
                                 'required':bool(_manifest_field(d,'IsRequired',True)),
                                 'minimum_version':str(_manifest_field(d,'MinimumVersion') or '')}
                                for d in dependencies if isinstance(d,dict) and _manifest_field(d,'UniqueID')]
                                if isinstance(dependencies,list) else []}
    except (OSError,ValueError,UnicodeError,TypeError,RecursionError):return None


def smapi_manifest_status(folder):
    """A missing/parsing-failed manifest is not evidence that a user's mod is illegitimate."""
    manifest=_manifest_path(folder)
    if manifest is None:return 'Installed mod folder (metadata not found)'
    try:
        data=_smapi_json(manifest)
        if isinstance(data,dict) and _manifest_field(data,'UniqueID'):
            return 'SMAPI manifest (index pending)'
        return 'Installed mod folder (ID unavailable)'
    except (OSError,ValueError,UnicodeError,TypeError,RecursionError):
        return 'Installed mod folder (manifest unreadable)'


def discover_smapi(base,enabled):
    found=[]
    if not base.is_dir():return found
    # Scan nested modpacks but never recurse through symlinked folders.
    for path,dirs,files in os.walk(base,followlinks=False):
        dirs[:]=[d for d in dirs if not d.startswith('.') and d!='__MACOSX' and not (Path(path)/d).is_symlink()]
        folder=Path(path)
        if any(name.casefold()=='manifest.json' for name in files):
            info=smapi_manifest(folder)
            if info:
                found.append({**info,'path':str(folder),'enabled':enabled,'root_dir':str(base),'relative':str(folder.relative_to(base))})
    return found

def discover_bepinex(base,enabled):
    """Find individual DLLs (including nested package layouts) without following symlinks."""
    found=[]
    if not base.is_dir():return found
    for root,dirs,files in os.walk(base,followlinks=False):
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(root)/d).is_symlink()]
        folder=Path(root)
        metadata={}
        for candidate in ('manifest.json','thunderstore.toml'):
            path=folder/candidate
            if not path.is_file():continue
            try:
                if candidate.endswith('.json'):
                    obj=json.loads(path.read_text(encoding='utf-8-sig'))
                    if isinstance(obj,dict):metadata=obj
                else:
                    try:
                        import tomllib
                    except ModuleNotFoundError:
                        import tomli as tomllib  # Python 3.10 (Ubuntu 22.04 AppImage builder)
                    obj=tomllib.loads(path.read_text(encoding='utf-8-sig'))
                    if isinstance(obj,dict):metadata=obj.get('package',obj)
            except (OSError,UnicodeError,ValueError):pass
            break
        # Inherit package metadata from the nearest enclosing plugin folder.
        # This matters for Thunderstore ZIPs containing subfolders of DLLs.
        if not metadata:
            for ancestor in folder.parents:
                if ancestor==base.parent or not ancestor.is_relative_to(base):break
                info=_read_package_manifest(ancestor/'manifest.json')
                if info:
                    metadata={'name':info['name'],'version_number':info['version'],
                              'website_url':info['website_url']}
                    break
        for filename in sorted(files):
            if not filename.lower().endswith('.dll'):continue
            dll=folder/filename
            if dll.is_symlink():continue
            rel=dll.relative_to(base)
            found.append({'name':str(metadata.get('name') or dll.stem),
                'version':str(metadata.get('version_number') or metadata.get('version') or ''),
                'uid':str(metadata.get('website_url') or ''),
                'path':str(dll),'enabled':enabled,'update_keys':[],
                'root_dir':str(base),'relative':str(rel),
                'website_url':str(metadata.get('website_url') or metadata.get('website') or '')})
    return found

def discover_melonloader(base, enabled):
    """Read-only discovery of loose or nested MelonLoader DLL mods; no binary rewriting."""
    found=[]
    if not base.is_dir():return found
    for root,dirs,files in os.walk(base,followlinks=False):
        here=Path(root)
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (here/d).is_symlink()]
        for file in files:
            plugin=here/file
            if plugin.is_symlink() or plugin.suffix.casefold()!='.dll':continue
            found.append({'name':plugin.stem,'version':'','uid':'','path':str(plugin),
                'enabled':enabled,'update_keys':[],'root_dir':str(base),
                'relative':str(plugin.relative_to(base)),'discovery':'Loose MelonLoader DLL'})
    return found

def smapi_folder_entries(game, mods=None):
    """Read-only, exhaustive top-level directory inventory for SMAPI.

    Recognition of a manifest is separate from existence of a directory.
    Do not follow links, claim an unknown folder is a loadable SMAPI mod,
    or hand unrecognised folders to mutation/update operations.
    """
    if game['kind'] != 'smapi':
        return []
    mods = items(game) if mods is None else mods
    result = []
    for enabled, base in ((True, mod_root(game)), (False, disabled_root(game))):
        if not base.is_dir():
            continue
        try:
            folders = sorted(base.iterdir(), key=lambda x: x.name.casefold())
        except OSError:
            continue
        for folder in folders:
            if folder.name.startswith('.') or folder.name == '__MACOSX':
                continue
            if not folder.is_dir() and not folder.is_symlink():
                continue
            direct = [m for m in mods if Path(m['path']) == folder]
            if direct:
                continue  # Already represented by the actual manifest, never twice.
            nested = [m for m in mods if Path(m['path']) != folder and Path(m['path']).is_relative_to(folder)]
            if folder.is_symlink():
                kind = 'Linked mod folder (read-only)'
            elif nested:
                kind = f'Modpack folder ({len(nested)} nested mod(s))'
            else:
                kind = smapi_manifest_status(folder)
            result.append({'name':folder.name, 'kind':kind, 'version':'',
                           'enabled':enabled, 'dll_count':0, 'path':str(folder),
                           'source':'', 'is_folder_only':True,'metadata_unindexed':True})
    return result

def mod_packages(game, mods=None):
    """Read-only, grouped inventory. Never infer ownership of DLLs from a file name."""
    mods=items(game) if mods is None else mods
    if game['kind'] not in ('bepinex','melonloader'):
        recognised=[{'name':m['name'],'kind':'SMAPI manifest' if game['kind']=='smapi' else 'Existing entry',
                 'version':m.get('version',''),'enabled':m['enabled'],'dll_count':0,
                 'path':m['path'],'source':source_of(m)} for m in mods]
        if game['kind']=='smapi':
            recognised.extend(smapi_folder_entries(game, mods))
        return sorted(recognised,key=lambda g:(g['name'].casefold(),g['path']))
    packages={}
    for mod in mods:
        base=Path(mod['root_dir'])
        path=Path(mod['path'])
        if not path.is_relative_to(base):continue
        # Find nearest metadata-owned package (if any); never cross the mods root.
        identity=None;info=None
        for folder in (path.parent,*path.parents):
            if folder==base:break
            if not folder.is_relative_to(base):break
            if game['kind']=='bepinex' and (folder/'manifest.json').is_file() and not (folder/'manifest.json').is_symlink():
                info=_read_package_manifest(folder/'manifest.json')
                if info:identity=folder;break
        if identity is None:
            rel=path.relative_to(base)
            identity=base/(rel.parts[0]) if len(rel.parts)>1 else path
            status='Unmanaged folder' if identity.is_dir() else 'Loose DLL'
            if game['kind']=='melonloader':status='MelonLoader '+status.lower()
        else:status='Metadata package'
        key=(str(identity),bool(mod['enabled']))
        if key not in packages:
            packages[key]={'name':info['name'] if info else (identity.name if identity.is_dir() else path.stem),
                           'kind':status,'version':info['version'] if info else mod.get('version',''),
                           'enabled':bool(mod['enabled']),'dll_count':0,'path':str(identity),
                           'source':info.get('website_url','') if info else ''}
        packages[key]['dll_count']+=1
    return sorted(packages.values(),key=lambda x:(x['name'].casefold(),x['path']))

def mod_family_groups(mods):
    """Group manifest rows for display only; never merge SMAPI identities or folders.

    Strong evidence: repeated exact Name, or a labelled component of that name.
    Parent labels are presentation-only, and a shared display name is not proof
    that two mods have the same author. Each child retains its own UniqueID/path.
    Unrelated names and singleton entries remain separate.
    """
    from collections import defaultdict
    explicit={str(m.get('name','')).strip().casefold():str(m.get('name','')).strip()
              for m in mods if not m.get('is_folder_only') and m.get('name')}
    patterns=(
        re.compile(r'^(.*?)\s*\[\s*(?:content patcher|smapi|custom companions|farm type manager|code|framework|[a-z0-9 ._-]+)\s+component\s*\]$', re.I),
        re.compile(r'^(.*?)\s*[-:]\s*(?:content patcher|smapi|custom companions|farm type manager|code|framework)\s+component$', re.I),
    )
    suffixes=('farm type manager','content patcher','custom companions','smapi','code','framework')
    names=[]
    for mod in mods:
        title=str(mod.get('name','')).strip()
        target=title
        for pattern in patterns:
            matched=pattern.fullmatch(title)
            if matched:
                target=matched.group(1).strip();break
        else:
            # Only group a suffix with an *existing exact parent name*.
            # Arbitrary shared prefixes do not prove a common project.
            for suffix in suffixes:
                end=' '+suffix
                if title.casefold().endswith(end):
                    prefix=title[:-len(end)].strip()
                    if prefix.casefold() in explicit:
                        target=explicit[prefix.casefold()]
                        break
        names.append(target)
    indexed=defaultdict(list)
    for i,key in enumerate(names):indexed[key.casefold()].append(i)
    result=[]
    for _,ids in indexed.items():
        first=ids[0]
        group={'name':names[first], 'indices':ids, 'members':[mods[i] for i in ids]}
        ids_u=[str(mods[i].get('uid','')).casefold() for i in ids if mods[i].get('uid')]
        group['duplicate_ids']=len(ids_u)!=len(set(ids_u))
        group['grouped']=len(ids)>1
        result.append(group)
    return sorted(result,key=lambda g:(g['name'].casefold(),str(g['members'][0].get('path',''))))


def existing_mod_health(game, mods=None):
    """Summary without filesystem mutations or network access."""
    mods=items(game) if mods is None else mods
    groups=mod_packages(game,mods)
    unmanaged=sum(g['kind'] != 'SMAPI manifest' if game['kind']=='smapi' else g['kind'] in
                  ('Loose DLL','Unmanaged folder','MelonLoader loose dll','MelonLoader unmanaged folder') for g in groups)
    return {'mods':len(mods),'enabled':sum(bool(m['enabled']) for m in mods),
            'folders':len(groups),'enabled_folders':sum(bool(g['enabled']) for g in groups),
            'packages':len(groups),'unmanaged':unmanaged,
            'sources':sum(bool(reconcile_source(game,m)['url']) for m in mods),
            'issues':len(audit_mods(mods,game['kind']))}

def items(game):
    result=[]
    for enabled,base in ((True,mod_root(game)),(False,disabled_root(game))):
        if not base.exists():continue
        if game['kind']=='smapi':result.extend(discover_smapi(base,enabled));continue
        if game['kind']=='bepinex':result.extend(discover_bepinex(base,enabled));continue
        if game['kind']=='melonloader':result.extend(discover_melonloader(base,enabled));continue
        for p in sorted(base.iterdir(),key=lambda x:x.name.casefold()):
            if p.name.startswith('.') or p.name=='__MACOSX' or p.is_symlink():continue
            result.append({'name':p.name,'version':'','uid':'','path':str(p),'enabled':enabled,'update_keys':[],
                           'root_dir':str(base),'relative':p.name})
    return sorted(result,key=lambda x:(x['name'].casefold(),x['path']))


def audit_mods(mods, kind):
    """Read-only diagnostics. Disabled mods are not counted as satisfying dependencies."""
    issues=[]
    if kind != 'smapi':
        return issues
    by_uid={}
    for m in mods:
        uid=m.get('uid','').casefold().strip()
        if uid:
            by_uid.setdefault(uid,[]).append(m)
    for uid,group in sorted(by_uid.items()):
        enabled=[m for m in group if m.get('enabled')]
        if len(enabled)>1:
            issues.append({'severity':'Warning','type':'Duplicate enabled ID','mod':group[0]['name'],
                           'detail':f'{uid} has {len(enabled)} enabled copies: '+', '.join(m['path'] for m in enabled)})
    for m in mods:
        if not m.get('enabled'):continue
        for d in m.get('dependencies',[]):
            if not d.get('required',True):continue
            dep=d.get('uid','').casefold().strip()
            if dep and not any(x.get('enabled') for x in by_uid.get(dep,[])):
                issues.append({'severity':'Warning','type':'Missing required dependency','mod':m['name'],
                               'detail':f"{d['uid']} not found enabled (may be a built-in/game-provided dependency)"})
        if m.get('content_pack_for'):
            dep=m['content_pack_for'].casefold().strip()
            if not any(x.get('enabled') for x in by_uid.get(dep,[])):
                issues.append({'severity':'Warning','type':'Missing content pack target','mod':m['name'],
                               'detail':f"ContentPackFor: {m['content_pack_for']} not found enabled"})
    return issues

def smapi_dependency_report(mods):
    """Read-only SMAPI dependency inspector, independent of installer/Steam metadata.

    Includes disabled providers and optional dependencies. Versions are only
    compared where both sides are numeric, otherwise results remain uncertain.
    A reported missing ID can be supplied by SMAPI/the game itself.
    """
    by_id={}
    for mod in mods:
        uid=str(mod.get('uid') or '').strip().casefold()
        if uid:by_id.setdefault(uid,[]).append(mod)
    rows=[]
    for mod in sorted(mods,key=lambda x:(str(x.get('name','')).casefold(),str(x.get('path','')))):
        requirements=[]
        for dep in mod.get('dependencies',[]):
            if not isinstance(dep,dict):continue
            dep_uid=str(dep.get('uid') or '').strip()
            if dep_uid:
                requirements.append((dep_uid,bool(dep.get('required',True)),'Dependency',str(dep.get('minimum_version') or '')))
        if mod.get('content_pack_for'):
            requirements.append((str(mod['content_pack_for']),True,'Content pack target',''))
        for dep_uid,required,kind,minimum in requirements:
            providers=by_id.get(dep_uid.casefold(),[])
            active=[x for x in providers if x.get('enabled')]
            if len(active)>1:status='Ambiguous providers'
            elif not active:
                status='Disabled provider' if providers else ('Missing' if required else 'Optional absent')
            elif minimum:
                comparison=compare_versions(str(active[0].get('version','')),minimum)
                status={'Update available':'Below minimum','Current':'Satisfied','Local newer':'Satisfied','Unknown':'Version unverified'}[comparison]
            else:status='Satisfied'
            rows.append({'mod':str(mod.get('name','')),'mod_id':str(mod.get('uid','')),
                         'mod_enabled':bool(mod.get('enabled')),
                         'dependency':dep_uid,'type':kind,'required':bool(required),
                         'minimum_version':minimum,
                         'installed_versions':', '.join(str(x.get('version') or '?') for x in active),
                         'providers':len(providers),'status':status,
                         'mod_path':str(mod.get('path',''))})
    return rows


def export_smapi_dependencies(path, rows):
    """CSV export with a fixed schema; never reads or modifies game content."""
    fields=('mod','mod_id','mod_enabled','dependency','type','required',
            'minimum_version','installed_versions','providers','status','mod_path')
    with Path(path).open('w',newline='',encoding='utf-8') as output:
        writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


SOURCE_OVERRIDES = APP/'source-overrides.json'
SMAPI_EXACT_CACHE = APP/'smapi-exact-source-cache.json'
SMAPI_NEGATIVE_CACHE = APP/'smapi-no-match-cache.json'

def load_smapi_exact_cache():
    try:
        data=json.loads(SMAPI_EXACT_CACHE.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def cached_smapi_reference(game,mod):
    if game.get('kind')!='smapi':return None
    uid=str(mod.get('uid') or '').strip()
    if not uid:return None
    value=load_smapi_exact_cache().get(source_identity(game,mod))
    if not isinstance(value,dict):return None
    number=str(value.get('nexus_id') or '')
    if not smapi_catalogue.VALID_NEXUS.fullmatch(number):return None
    return {'game_domain':'stardewvalley','mod_id':number,
            'url':f'https://www.nexusmods.com/stardewvalley/mods/{number}'}

def cache_exact_smapi_matches(game,mods,matches):
    """Persist only catalogue-confirmed exact UniqueIDs; keep explicit IDs untouched."""
    if game.get('kind')!='smapi':return {'added':0,'skipped':len(mods)}
    data=load_smapi_exact_cache();added=0;skipped=0
    for mod in mods:
        uid=str(mod.get('uid') or '').strip().casefold()
        found=matches.get(uid)
        if not found or not smapi_catalogue.VALID_NEXUS.fullmatch(str(found.get('nexus_id') or '')):
            skipped+=1;continue
        # Never replace a manually assigned page, manifest Nexus update key,
        # or conflict between those direct identifiers.
        existing=nexus_reference(game,mod,include_cache=False)
        if assigned_source(game,mod) or existing:
            skipped+=1;continue
        key=source_identity(game,mod)
        previous=data.get(key)
        if previous and previous.get('nexus_id')!=str(found['nexus_id']):
            skipped+=1;continue
        if not previous:
            data[key]={'nexus_id':str(found['nexus_id']),'method':'smapi-exact-uid'}
            added+=1
    if added:
        tmp=SMAPI_EXACT_CACHE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        tmp.replace(SMAPI_EXACT_CACHE)
    return {'added':added,'skipped':skipped}

COLLECTION_SOURCES = APP/'collection-sources.json'

def collection_source_key(game):
    return str(Path(game['root']).expanduser().resolve())

def nexus_collection_origin(game):
    """An origin declared by the owner; not an exact verified Nexus mod page."""
    if not game or game.get('kind') != 'smapi': return False
    try:
        data=json.loads(COLLECTION_SOURCES.read_text(encoding='utf-8'))
        return data.get(collection_source_key(game)) == 'Nexus Mods' if isinstance(data,dict) else False
    except (OSError, ValueError): return False

def set_nexus_collection_origin(game, enabled):
    if game.get('kind')!='smapi':raise ValueError('This setting applies to SMAPI collections')
    try: data=json.loads(COLLECTION_SOURCES.read_text(encoding='utf-8'))
    except (OSError,ValueError): data={}
    if not isinstance(data,dict): data={}
    identity=collection_source_key(game)
    if enabled: data[identity]='Nexus Mods'
    else: data.pop(identity,None)
    tmp=COLLECTION_SOURCES.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(COLLECTION_SOURCES)
KNOWN_SOURCE_HOSTS = {
    'nexusmods.com':'Nexus Mods', 'github.com':'GitHub',
    'thunderstore.io':'Thunderstore', 'curseforge.com':'CurseForge',
    'modrinth.com':'Modrinth', 'moddb.com':'ModDB',
    'steamcommunity.com':'Steam Workshop', 'mod.io':'mod.io',
    'moddrop.com':'ModDrop',
}

def validate_source_link(url):
    """Accept only real HTTPS landing URLs from a known mod platform."""
    from urllib.parse import urlsplit
    if not isinstance(url,str) or len(url)>2048:return None
    try:parsed=urlsplit(url.strip())
    except ValueError:return None
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):return None
    host=parsed.hostname.lower()
    for domain,name in KNOWN_SOURCE_HOSTS.items():
        if host==domain or host.endswith('.'+domain):
            return {'url':url.strip(),'site':name}
    return None

def source_identity(game,mod):
    """Uniquely identify a mod per game without relying only on names."""
    root=str(Path(game['root']).resolve())
    uid=str(mod.get('uid') or '').strip()
    if game.get('kind')=='smapi' and uid:return root+'|smapi|'+uid.casefold()
    return root+'|path|'+str(mod.get('relative') or '').casefold()

def load_source_overrides():
    try:
        data=json.loads(SOURCE_OVERRIDES.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def assigned_source(game,mod):
    raw=load_source_overrides().get(source_identity(game,mod))
    return validate_source_link(raw) if raw else None

def save_source_assignment(game,mod,url):
    parsed=validate_source_link(url)
    if not parsed:raise ValueError('Enter an HTTPS link from a supported mod website.')
    overrides=load_source_overrides()
    overrides[source_identity(game,mod)]=parsed['url']
    tmp=SOURCE_OVERRIDES.with_suffix('.tmp')
    tmp.write_text(json.dumps(overrides,indent=2,sort_keys=True),encoding='utf-8')
    tmp.replace(SOURCE_OVERRIDES)
    return parsed

def clear_source_assignment(game,mod):
    overrides=load_source_overrides()
    overrides.pop(source_identity(game,mod),None)
    tmp=SOURCE_OVERRIDES.with_suffix('.tmp')
    tmp.write_text(json.dumps(overrides,indent=2,sort_keys=True),encoding='utf-8')
    tmp.replace(SOURCE_OVERRIDES)

# v0.34: explicit owner-provided Nexus AIO import. No game files are modified.
AIO_NEXUS_LIST = Path(__file__).resolve().with_name('stardew-aio-nexus-links.json')
AIO_EXACT_ALIASES = {
    'farm type manager ftm': 'farm type manager',
    'mapping extensions and extra properties meep': 'mapping extensions and extra properties',
    'generic mod config menu gmcm': 'generic mod config menu',
    'ui info suite 2': 'ui info suite 2',
    'uiinfosuite2': 'ui info suite 2',
    'lumisteria tilesheets indoor': 'lumisteria tilesheets indoor',
    'lumisteria tilesheets outdoor': 'lumisteria tilesheets outdoor',
}

def aio_normalized_name(name):
    """Canonicalise typography and known parenthetical abbreviations, not arbitrary fuzzy names."""
    text=str(name or '').casefold().replace('–','-').replace('—','-')
    text=re.sub(r'[^\w]+',' ',text,flags=re.UNICODE).strip()
    return AIO_EXACT_ALIASES.get(text,text)

def load_stardew_aio_links(path=None):
    """Read a user-provided catalogue; reject malformed or non-Stardew URLs."""
    file=Path(path) if path else AIO_NEXUS_LIST
    raw=json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(raw,dict) or not isinstance(raw.get('links'),list) or len(raw['links'])>200:
        raise ValueError('Invalid AIO link catalogue')
    found={}; used=set()
    for entry in raw['links']:
        if not isinstance(entry,dict) or not isinstance(entry.get('name'),str):raise ValueError('Invalid AIO entry')
        name=entry['name'].strip()
        if not name or len(name)>200:raise ValueError('Invalid AIO mod name')
        ref=parse_nexus_link(entry.get('url'))
        if not ref or ref['game_domain']!='stardewvalley':raise ValueError('Only exact Stardew Valley Nexus pages are allowed')
        ident=aio_normalized_name(name)
        if ident in found or ref['mod_id'] in used:raise ValueError('Duplicate AIO name or Nexus page')
        found[ident]={**ref,'name':name,'aio_version':str(entry.get('version') or '')}
        used.add(ref['mod_id'])
    return found

def aio_mod_candidate(name,catalogue):
    """Exact name => proposal. Clearly related pack component => review only."""
    normalized=aio_normalized_name(name)
    exact=catalogue.get(normalized)
    if exact:return exact,'Exact AIO name'
    # Component prefix is a *review suggestion*, never an automatic match.
    for family in ('stardew valley expanded','ridgeside village'):
        if normalized.startswith(family+' ') and family in catalogue:
            return catalogue[family],'Related component — review'
    if (normalized.startswith('east scarp ') or normalized.startswith('forage settings east scarp')) and 'east scarp remastered' in catalogue:
        return catalogue['east scarp remastered'],'Related component — review'
    return None,'Not in supplied AIO list'

def aio_nexus_preview(game,mods,catalogue=None):
    """Preview user-provided exact page links without guessing unrelated mods.

    An existing explicit page/metadata identity always wins; mismatches require
    manual review instead of silently changing the source. Duplicate UniqueIDs
    cannot be mass-assigned safely.
    """
    if game.get('kind')!='smapi' or (game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name')))!='stardewvalley':
        raise ValueError('The supplied AIO catalogue is only for Stardew Valley SMAPI')
    catalogue=load_stardew_aio_links() if catalogue is None else catalogue
    counts={}
    for mod in mods:
        key=source_identity(game,mod)
        counts[key]=counts.get(key,0)+1
    preview=[]
    for mod in mods:
        candidate,evidence=aio_mod_candidate(mod.get('name',''),catalogue)
        existing=nexus_reference(game,mod)
        assigned=assigned_source(game,mod)
        if candidate is None:status='No supplied link'
        elif assigned and assigned['site']!='Nexus Mods':status='Conflicting source — skip'
        elif existing and 'error' in existing:status='Conflicting metadata — skip'
        elif existing and existing['game_domain']==candidate['game_domain'] and existing['mod_id']==candidate['mod_id']:status='Already linked'
        elif existing:status='Different Nexus ID — skip'
        elif counts[source_identity(game,mod)]>1:status='Duplicate SMAPI ID — skip'
        elif evidence.startswith('Related'):status='Review related component'
        else:status='Ready — exact name'
        preview.append({'mod':mod,'uid':str(mod.get('uid','')),'candidate':candidate,'evidence':evidence,'status':status})
    return preview

def apply_aio_nexus_links(game,preview,indices):
    """Persist only explicitly selected, unchanged proposals in one atomic config write.

    This never writes to game folders or contacts Nexus. Even a stale preview
    is revalidated against current overrides before writing anything.
    """
    selected=set(indices)
    if not all(isinstance(i,int) and 0<=i<len(preview) for i in selected):
        raise ValueError('Invalid selection')
    approved={}; identities=set()
    for i in sorted(selected):
        row=preview[i]
        if row['status'] not in ('Ready — exact name','Review related component'):
            raise ValueError(f'Cannot apply {row["status"]}')
        mod=row['mod'];candidate=row['candidate']
        if not candidate:raise ValueError('Link missing')
        ref=parse_nexus_link(candidate['url'])
        if not ref or ref['game_domain']!='stardewvalley':raise ValueError('Invalid Nexus page')
        present=nexus_reference(game,mod)
        if present is not None:raise ValueError('Mod source changed; refresh the preview')
        if assigned_source(game,mod):raise ValueError('An existing assignment must not be overwritten')
        identity=source_identity(game,mod)
        if identity in identities:raise ValueError('Duplicate SMAPI ID in selected group')
        identities.add(identity);approved[identity]=ref['url']
    saved=load_source_overrides()
    for identity in approved:
        if identity in saved:raise ValueError('Source assignment changed; refresh the preview')
    saved.update(approved)
    if approved:
        SOURCE_OVERRIDES.parent.mkdir(parents=True,exist_ok=True)
        tmp=SOURCE_OVERRIDES.with_suffix('.tmp')
        tmp.write_text(json.dumps(saved,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        tmp.replace(SOURCE_OVERRIDES)
    return len(approved)

def metadata_source(mod):
    """Return a source link only from explicit local metadata and supported domains.

    Never search by a guessed name or interpret an arbitrary website as a mod page.
    """
    website=mod.get('website_url')
    if website:
        result=validate_source_link(website)
        if result:return result
    url=source_url(mod)
    return validate_source_link(url) if url else None

def auto_source_matches(game,mods):
    """Non-destructively inspect package metadata; return matches without saving overrides."""
    matches=[]
    for mod in mods:
        if assigned_source(game,mod):continue
        found=metadata_source(mod)
        if found:matches.append({'name':mod['name'],'path':mod['path'],**found})
    return matches

def source_report(game,mods):
    records=[]
    for mod in mods:
        if game.get('kind')=='smapi' and str(mod.get('uid') or '').casefold() in smapi_catalogue.BUNDLED_SMAPI_IDS:
            records.append({'name':mod['name'],'version':mod.get('version',''),
                'unique_id':mod.get('uid',''),'enabled':bool(mod.get('enabled')),
                'source':'SMAPI','source_url':'','match_type':'Bundled with SMAPI',
                'path':mod['path']})
            continue
        override=assigned_source(game,mod)
        auto=metadata_source(mod)
        smapi=cached_smapi_reference(game,mod) if not (override or auto) else None
        records.append({'name':mod['name'],'version':mod.get('version',''),
            'unique_id':mod.get('uid',''),'enabled':bool(mod.get('enabled')),
            'source':override['site'] if override else (auto['site'] if auto else ('Nexus Mods' if smapi or nexus_collection_origin(game) else source_of(mod))),
            'source_url':override['url'] if override else (auto['url'] if auto else (smapi['url'] if smapi else '')),
            'match_type':'Assigned' if override else ('Metadata' if auto else ('SMAPI catalogue exact ID' if smapi else ('Owner-declared origin; link needed' if nexus_collection_origin(game) else 'Unmatched'))),
            'path':mod['path']})
    return records

def export_source_csv(path,game,mods):
    records=source_report(game,mods)
    columns=['name','version','unique_id','enabled','source','source_url','match_type','path']
    with open(path,'w',newline='',encoding='utf-8-sig') as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader();writer.writerows(records)
    return len(records)

def source_of(mod):
    keys=mod.get('update_keys',[])
    sources=[]
    for key in keys:
        prefix=key.split(':',1)[0].lower()
        name={'nexus':'Nexus Mods','github':'GitHub','moddrop':'ModDrop',
              'curseforge':'CurseForge','modrinth':'Modrinth'}.get(prefix)
        if name and name not in sources:sources.append(name)
    return ', '.join(sources) or 'Unknown'

def reconcile_source(game, mod):
    """Use only explicit local identifiers; never infer a download from a name.

    This is a source *hint*; no local metadata proves the publisher or archive
    is authentic. Links are for a person to review in their browser.
    """
    base={'name':str(mod.get('name','')), 'version':str(mod.get('version','')),
          'uid':str(mod.get('uid','')), 'enabled':bool(mod.get('enabled')),
          'path':str(mod.get('path','')), 'source':'Unknown',
          'status':'Unmatched', 'url':'', 'alternatives':[]}
    if game.get('kind')=='smapi' and str(mod.get('uid') or '').casefold() in smapi_catalogue.BUNDLED_SMAPI_IDS:
        return {**base,'source':'SMAPI','status':'Bundled with SMAPI — no Nexus page required'}
    override=assigned_source(game,mod)
    if override:
        return {**base,'source':override['site'],'status':'Assigned by user',
                'url':override['url']}
    # Real metadata website, after strict HTTPS/domain vetting. For modloaders
    # this may identify the package, not every DLL inside it.
    explicit=validate_source_link(mod.get('website_url',''))
    if explicit:
        return {**base,'source':explicit['site'],'status':'Metadata link',
                'url':explicit['url']}
    # For SMAPI UpdateKeys, link only when an identifier is syntactically exact
    # and the game-specific Nexus domain is known. Do not assume Stardew Valley.
    links=[]
    reference=nexus_reference(game,mod) if game.get('kind')=='smapi' else None
    if reference and 'error' in reference:
        return {**base,'status':'Conflicting Nexus keys', 'source':'Nexus Mods'}
    if reference and validate_source_link(reference.get('url','')):
        links.append(('Nexus Mods',reference['url']))
    repo=github_repo(mod)
    if repo:
        url='https://github.com/'+repo+'/releases'
        if validate_source_link(url):links.append(('GitHub',url))
    for key in mod.get('update_keys',[]):
        prefix,sep,value=str(key).partition(':')
        if sep and prefix.casefold()=='modrinth' and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value.strip()):
            links.append(('Modrinth','https://modrinth.com/mod/'+value.strip()))
    # Distinct valid source links are choices, not conflicting mod identities.
    links=list(dict.fromkeys(links))
    if links:
        primary=links[0]
        return {**base,'source':primary[0],
                'status':('SMAPI catalogue exact ID' if cached_smapi_reference(game,mod) and not github_repo(mod) and not any(str(k).casefold().startswith('nexus:') for k in mod.get('update_keys',[])) else 'Update key link') if len(links)==1 else 'Multiple source links',
                'url':primary[1], 'alternatives':[u for _,u in links[1:]]}
    if nexus_collection_origin(game):
        return {**base,'source':'Nexus Mods','status':'Nexus origin — page ID needed'}
    source=source_of(mod)
    if source!='Unknown':
        return {**base,'source':source,'status':'Key only — review needed'}
    return base


def source_reconciliation(game, mods):
    """Read-only source inventory, stable when rescanning the same local mods."""
    return [reconcile_source(game,mod) for mod in mods]


def export_source_reconciliation(path, game, mods):
    rows=source_reconciliation(game,mods)
    fields=('name','version','uid','enabled','source','status','url','path','alternatives')
    with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row,'alternatives':' | '.join(row['alternatives'])})
    return len(rows)

# v0.35 — local-first source discovery. No API key, network or game-file changes.
# Download filenames alone are untrusted evidence: any proposed IDs require review.
def nexus_download_filename_candidate(filename, game_domain):
    """Extract a *tentative* Nexus ID from the standard Nexus archive filename.

    The filename is NOT proof that the ZIP came from Nexus. This function must
    never be used for silent assignment or installing an archive.
    """
    stem=Path(str(filename)).stem
    if not isinstance(game_domain,str) or not NEXUS_DOMAIN_RE.fullmatch(game_domain):return None
    # Typical Nexus name: ModName-11115-2-18-0-17234567.zip. This is only
    # a hint, and the package's own UniqueID must match an installed mod.
    hits=re.findall(r'(?<!\d)-([1-9][0-9]{0,11})-(?:[0-9]+-){2,}[0-9]+(?:-|$)',stem)
    if len(set(hits))!=1:return None
    return {'mod_id':hits[0], 'game_domain':game_domain,
            'url':f'https://www.nexusmods.com/{game_domain}/mods/{hits[0]}'}


def _archive_manifest_identities(archive):
    """Read at most 1 MiB per manifest; validate ZIP paths before trusting IDs."""
    archive=Path(archive)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size>512*1024*1024:
        raise ValueError('Invalid or oversized ZIP')
    found=[]
    with zipfile.ZipFile(archive) as z:
        members=z.infolist()
        if len(members)>10000 or sum(m.file_size for m in members)>2*1024**3:
            raise ValueError('Excessive ZIP entries or uncompressed size')
        for m in members:
            path=m.filename.replace('\\','/')
            parts=path.split('/')
            if (path.startswith('/') or re.match(r'^[A-Za-z]:',path)
                or '..' in parts or '\x00' in path or
                (m.external_attr>>16)&0o170000==0o120000):
                raise ValueError('Unsafe archive path or symlink')
            if m.is_dir() or Path(path).name.casefold()!='manifest.json':continue
            if m.file_size>1024*1024:raise ValueError('Oversized manifest')
            with z.open(m) as stream:payload=stream.read(1024*1024+1)
            if len(payload)>1024*1024:raise ValueError('Oversized manifest')
            source=payload.decode('utf-8-sig')
            try:raw=json.loads(source)
            except ValueError:
                import json5
                raw=json5.loads(source,allow_duplicate_keys=False)
            if not isinstance(raw,dict):continue
            uid=_manifest_field(raw,'UniqueID')
            if not isinstance(uid,str) or not uid.strip():continue
            keys=_manifest_field(raw,'UpdateKeys')
            keys=keys if isinstance(keys,list) else []
            found.append({'uid':uid.strip(), 'name':str(_manifest_field(raw,'Name') or ''),
                'update_keys':[k for k in keys if isinstance(k,str)]})
    return found


def discover_nexus_download_evidence(game,mods,folder,max_archives=150,include_common=False,home=None,app_dir=None):
    """Read downloaded ZIP SMAPI IDs and optional MO2 sidecar provenance.

    A sidecar alone never identifies an installed mod. Archive identities are
    matched by exact UniqueID, and all candidates remain review-only.
    """
    if game.get('kind')!='smapi':return {}
    domain=game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name'))
    if not domain or not NEXUS_DOMAIN_RE.fullmatch(str(domain)):return {}
    by_uid={}
    for mod in mods:
        uid=str(mod.get('uid','')).casefold()
        if uid:by_uid.setdefault(uid,[]).append(mod)
    # Include named download locations only when the user explicitly chooses
    # automatic scanning; never crawl the game Mods tree or the full home dir.
    archives=find_archives(folder,include_common=include_common,home=home,
                           app_dir=app_dir,max_archives=min(180,max_archives))
    evidence={}
    for file in archives:
        try:identities=_archive_manifest_identities(file)
        except (OSError,ValueError,UnicodeError,zipfile.BadZipFile,RuntimeError,EOFError):continue
        candidate_from_name=nexus_download_filename_candidate(file.name,str(domain))
        # MO2 writes file.zip.meta next to file.zip with exact Nexus IDs.
        # It remains untrusted metadata and must never trigger an automatic install.
        sidecar=read_mo2_sidecar(file,str(domain))
        downloaded_receipts=source_receipts.find_receipt(file,str(domain),NEXUS_RECEIPTS)
        for entry in identities:
            uid=entry['uid'].casefold()
            if len(by_uid.get(uid,[]))!=1:continue
            ids=set()
            for key in entry['update_keys']:
                prefix,sep,value=key.partition(':')
                if sep and prefix.casefold()=='nexus' and NEXUS_ID_RE.fullmatch(value.strip()):
                    ids.add(value.strip())
            # A manifest with multiple Nexus IDs is ambiguous, not a verified match.
            if len(ids)>1:continue
            sources=[]
            if ids:sources.append((next(iter(ids)),'Archive SMAPI update key'))
            if sidecar:sources.append((sidecar['mod_id'], 'MO2 archive metadata (file #'+sidecar['file_id']+')'))
            for receipt in downloaded_receipts:
                if uid in {i.casefold() for i in receipt['smapi_ids']}:
                    sources.append((receipt['mod_id'], 'UniMod approved Nexus download receipt (file #'+receipt['file_id']+')'))
            if candidate_from_name:sources.append((candidate_from_name['mod_id'],'ZIP filename hint — verify on Nexus'))
            # Keep competing IDs so the preview marks their conflict rather than
            # overriding the original installed source with a misleading sidecar.
            for mod_id,origin in sources:
                record={'uid':entry['uid'], 'mod_id':mod_id,
                        'url':f'https://www.nexusmods.com/{domain}/mods/{mod_id}',
                        'evidence':origin,'filename':file.name}
                evidence.setdefault(uid,[]).append(record)
    # A completed UniMod download can still identify its matching SMAPI IDs
    # after the ZIP is moved. Such matches always require explicit review.
    old=source_receipts.uid_candidates(str(domain),by_uid,NEXUS_RECEIPTS)
    for uid,rows in old.items():
        if len(by_uid.get(uid,[]))==1:
            evidence.setdefault(uid,[]).extend(rows)
    return evidence

def simple_source_preview(game,mods,folder=None,scan=None,include_common=False,home=None,app_dir=None):
    """One screen: known links, reviewable ZIP hints, and exceptions only."""
    download_evidence=scan if scan is not None else discover_nexus_download_evidence(
        game,mods,folder if folder is not None else Path.home()/'Downloads',
        include_common=include_common,home=home,app_dir=app_dir)
    counts={}
    for m in mods:
        uid=str(m.get('uid','')).casefold()
        if uid:counts[uid]=counts.get(uid,0)+1
    preview=[]
    for m in mods:
        ref=nexus_reference(game,m) if game.get('kind')=='smapi' else None
        uid=str(m.get('uid','')).casefold()
        candidates=download_evidence.get(uid,[])
        # Prefer exact embedded metadata over an easily renamed filename when
        # several hints agree on the same Nexus page. Conflicting page IDs are
        # still shown for review, never silently reconciled.
        def evidence_rank(entry):
            evidence=str(entry.get('evidence') or '')
            if evidence.startswith('Archive SMAPI update key'):return 0
            if evidence.startswith('UniMod approved Nexus download receipt'):return 1
            if evidence.startswith('MO2 archive metadata'):return 2
            return 3
        distinct={}
        for candidate in candidates:
            ident=candidate.get('mod_id')
            if ident not in distinct or evidence_rank(candidate)<evidence_rank(distinct[ident]):
                distinct[ident]=candidate
        row={'mod':m, 'name':m.get('name',''), 'candidate':None,
             'status':'Needs source', 'evidence':'No exact local source ID'}
        if ref and 'error' in ref:
            row.update(status='Conflicting source',evidence=ref['error'])
        elif ref:
            row.update(status='Already identified',candidate=ref,evidence='Local metadata or assignment')
        elif counts.get(uid,0)>1:
            row.update(status='Duplicate installed ID',evidence='Review duplicate SMAPI UniqueID')
        elif len(distinct)>1:
            row.update(status='Conflicting archive hints',evidence='Different downloaded archives suggest different pages')
        elif len(distinct)==1:
            found=next(iter(distinct.values()))
            row.update(status='Review candidate',candidate=found,evidence=found['evidence']+' · '+found['filename'])
        preview.append(row)
    return preview


def apply_simple_source_matches(game,preview,indices):
    """Commit approved source hints in one config write, never touch game files."""
    indices=set(indices)
    if not all(isinstance(i,int) and 0<=i<len(preview) for i in indices):
        raise ValueError('Invalid source selection')
    planned={}
    for i in sorted(indices):
        row=preview[i]
        if row['status']!='Review candidate':raise ValueError('Only reviewable sources can be saved')
        mod=row['mod'];candidate=row['candidate'] or {}
        ref=parse_nexus_link(candidate.get('url'))
        expected=game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name'))
        if not ref or ref['game_domain']!=expected:raise ValueError('Invalid Nexus candidate')
        if nexus_reference(game,mod) or assigned_source(game,mod):
            raise ValueError('Source changed since preview; rescan')
        identity=source_identity(game,mod)
        if identity in planned:raise ValueError('Duplicate selected installed mod identity')
        planned[identity]=ref['url']
    overrides=load_source_overrides()
    if any(key in overrides for key in planned):raise ValueError('Source assignment changed; rescan')
    if planned:
        SOURCE_OVERRIDES.parent.mkdir(parents=True,exist_ok=True)
        overrides.update(planned)
        temp=SOURCE_OVERRIDES.with_suffix('.tmp')
        temp.write_text(json.dumps(overrides,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        temp.replace(SOURCE_OVERRIDES)
    return len(planned)

# v0.26 global inventory is read-only; game files are never adopted or modified.
def global_mod_library(games, scan=None, max_games=250):
    """Read registered mod layouts, reporting exact sources without name guessing.

    One SMAPI manifest is a row; for BepInEx and MelonLoader DLLs are grouped by
    their local package directory. Duplicate registered roots are scanned once.
    Broken/missing game folders are reported separately, not silently dropped.
    """
    scan=scan or items
    if not isinstance(games, (list, tuple)):
        raise ValueError('Game list must be a sequence')
    records=[]; problems=[]; checked=set(); registered=0
    for game in games[:max_games]:
        if not isinstance(game,dict):continue
        path=game.get('root'); kind=game.get('kind')
        if not isinstance(path,str) or not Path(path).is_absolute() or kind not in ('smapi','bepinex','melonloader','generic'):
            problems.append({'game':str(game.get('name','Unknown')),'reason':'Invalid game registration'});continue
        base=Path(path).expanduser()
        # Reject symlink game directories in the consolidated inventory; registered
        # paths may have been manually edited or imported from a launcher.
        if base.is_symlink() or not base.is_dir():
            problems.append({'game':str(game.get('name','Unknown')),'reason':'Game folder missing or symlinked'});continue
        root=str(base.resolve())
        if root in checked:continue
        checked.add(root);registered+=1
        try:
            mods=scan(game)
            groups=mod_packages(game, mods)
            for i,group in enumerate(groups):
                url='';site='Unknown';state='Unmatched'
                if kind=='smapi':
                    # Match by exact manifest path, not list index: the folder
                    # inventory has additional read-only entries and is sorted.
                    manifest=next((m for m in mods if m['path']==group['path']),None)
                    if manifest is not None:
                        match=reconcile_source(game,manifest)
                        url=match['url'];site=match['source'];state=match['status']
                    else:
                        state='Needs review'
                else:
                    verified=validate_source_link(group.get('source',''))
                    if verified:
                        url=verified['url'];site=verified['site'];state='Metadata link'
                    elif group['kind'] in ('Loose DLL','Unmanaged folder','MelonLoader loose dll','MelonLoader unmanaged folder'):
                        state='Unmanaged'
                records.append({'game':str(game.get('name') or base.name),'game_root':root,
                    'loader':kind.upper(),'mod':str(group['name']),
                    'version':str(group.get('version') or ''),
                    'enabled':bool(group.get('enabled')), 'package_type':str(group['kind']),
                    'dll_count':int(group.get('dll_count',0)), 'source':site,
                    'source_status':state,'source_url':url,'path':str(group['path'])})
        except (OSError, ValueError, RuntimeError) as exc:
            problems.append({'game':str(game.get('name','Unknown')),'reason':f'Scan failed: {type(exc).__name__}'})
    records.sort(key=lambda r:(r['game'].casefold(),r['mod'].casefold(),r['path']))
    return {'games_scanned':registered,'mods':records,'problems':problems,
            'enabled':sum(r['enabled'] and (r['loader']!='SMAPI' or r['package_type']=='SMAPI manifest') for r in records),
            'linked':sum(bool(r['source_url']) for r in records),
            'unmanaged':sum(r['source_status']=='Unmanaged' for r in records)}


def export_global_mod_library(path, report):
    """Export a local inventory only; neutralise spreadsheet formula cells."""
    fields=('game','loader','mod','version','enabled','package_type','dll_count',
            'source','source_status','source_url','path','game_root')
    def safe(value):
        text=str(value)
        if text.lstrip().startswith(('=','+','-','@')) or text[:1] in ('\t','\r','\n'):
            return "'"+text
        return text
    with Path(path).open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for item in report['mods']:
            writer.writerow({k:safe(item.get(k,'')) for k in fields})
    return len(report['mods'])

# GitHub update keys are checked through public releases; Nexus uses a separate exact-ID API check.
GITHUB_CACHE = APP/'github-release-cache.json'
def github_repo(mod):
    for key in mod.get('update_keys',[]):
        if key.lower().startswith('github:'):
            repo=key.split(':',1)[1].strip().strip('/')
            if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):return repo
    return None

def compare_versions(local,remote):
    # Conservative comparison: unknown is not evidence of an update.
    def parse(v):
        v=str(v).strip().lstrip('vV')
        if not re.fullmatch(r'\d+(?:\.\d+){0,5}',v):return None
        return tuple(int(x) for x in v.split('.'))
    a,b=parse(local),parse(remote)
    if a is None or b is None:return 'Unknown'
    size=max(len(a),len(b));a=a+(0,)*(size-len(a));b=b+(0,)*(size-len(b))
    return 'Update available' if a<b else 'Current' if a==b else 'Local newer'

def github_latest(repo, fetch=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid GitHub repository')
    url='https://api.github.com/repos/'+repo+'/releases/latest'
    req=urllib.request.Request(url,headers={'User-Agent':'UniMod/0.54','Accept':'application/vnd.github+json'})
    if fetch is None:
        with urllib.request.urlopen(req,timeout=12) as res:
            data=json.load(res)
    else:data=fetch(url)
    version=str(data.get('tag_name') or '').strip()
    if not version:raise ValueError('No published release tag')
    return {'repo':repo,'version':version,'url':str(data.get('html_url') or f'https://github.com/{repo}/releases')}

def check_github_updates(mods,fetch=None):
    repo_results={}; outcomes={}
    for mod in mods:
        repo=github_repo(mod)
        if not repo:continue
        if repo not in repo_results:
            try:repo_results[repo]=github_latest(repo,fetch=fetch)
            except Exception as exc:repo_results[repo]={'error':str(exc),'repo':repo}
        result=repo_results[repo]
        status='Check failed' if 'error' in result else compare_versions(mod.get('version',''),result['version'])
        outcomes[mod['path']]={'status':status,**result}
    return outcomes

# Read-only Nexus Mods v1 API (legacy public API). Never persists API keys.
# Personal API keys are for testing/personal use; public deployments need app registration.
NEXUS_ID_RE = re.compile(r"[1-9][0-9]{0,11}\Z")
NEXUS_DOMAIN_RE = re.compile(r"[a-z][a-z0-9-]{1,79}\Z")
NEXUS_GAME_DOMAINS = {'Stardew Valley': 'stardewvalley',
                      'Graveyard Keeper 2': 'graveyardkeeper2',
                      'Graveyard Keeper': 'graveyardkeeper'}

def parse_nexus_link(url):
    """Only exact game-scoped mod page links count as Nexus identities."""
    from urllib.parse import urlsplit
    if not isinstance(url, str) or len(url) > 2048: return None
    try: parsed = urlsplit(url.strip())
    except ValueError: return None
    if (parsed.scheme != 'https' or parsed.hostname not in ('nexusmods.com', 'www.nexusmods.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        return None
    match = re.fullmatch(r'/([a-z][a-z0-9-]{1,79})/mods/([1-9][0-9]{0,11})/?', parsed.path, flags=re.IGNORECASE)
    if not match: return None
    domain, mod_id = match.group(1).lower(), match.group(2)
    return {'game_domain': domain, 'mod_id': mod_id,
            'url': f'https://www.nexusmods.com/{domain}/mods/{mod_id}'}

def nexus_reference(game, mod, include_cache=True):
    """Resolve only explicit IDs; conflicting metadata is never silently guessed."""
    manual = assigned_source(game, mod)
    if manual:
        if manual['site'] != 'Nexus Mods': return None
        ref = parse_nexus_link(manual['url'])
        if not ref: return None
        return ref
    refs = []
    website = parse_nexus_link(mod.get('website_url', ''))
    if website: refs.append(website)
    name = game.get('name', '')
    domain = game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(name)
    if domain and NEXUS_DOMAIN_RE.fullmatch(str(domain)):
        for key in mod.get('update_keys', []):
            prefix, sep, value = str(key).partition(':')
            if sep and prefix.strip().casefold() == 'nexus' and NEXUS_ID_RE.fullmatch(value.strip()):
                refs.append({'game_domain': domain, 'mod_id': value.strip(),
                            'url': f'https://www.nexusmods.com/{domain}/mods/{value.strip()}'})
    if not refs:
        return cached_smapi_reference(game,mod) if include_cache else None
    if len({(r['game_domain'], r['mod_id']) for r in refs}) != 1:
        return {'error': 'Conflicting Nexus IDs in mod metadata'}
    return refs[0]

def nexus_api_json(url, api_key, fetch=None):
    """Small, read-only Nexus request. Never show a raw exception containing a secret."""
    import ssl, socket
    headers = {'User-Agent':'UniMod/0.54', 'Application-Name':'UniMod',
               'Application-Version':'0.54.0', 'Accept':'application/json',
               'apikey':api_key.strip()}
    if fetch is not None:
        # Test adapter; callers inject a test response, not a live request.
        return fetch(url, dict(headers))
    # Never forward an API key through cross-host redirects.
    from urllib.parse import urlsplit
    origin=urlsplit(url)
    if origin.scheme!='https' or origin.hostname!='api.nexusmods.com' or origin.username or origin.password or origin.port not in (None,443):
        raise ValueError('Only the official Nexus API host is permitted')
    class NexusOnlyRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            target=urlsplit(newurl)
            if target.scheme!='https' or target.hostname!='api.nexusmods.com':
                raise ValueError('Nexus API request redirected outside the API host')
            return super().redirect_request(req,fp,code,msg,hdrs,newurl)
    request=urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.build_opener(NexusOnlyRedirect()).open(request,timeout=12) as response:
            raw=response.read(512*1024+1)
            if len(raw)>512*1024:raise ValueError('Nexus response exceeded 512 KiB')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        code=exc.code
        if code==401: raise ValueError('Authentication failed (HTTP 401). Check your personal API key.') from None
        if code==403: raise ValueError('Access denied (HTTP 403). The API or key may not be authorised for this request.') from None
        if code==404: raise ValueError('Nexus API endpoint or mod not found (HTTP 404).') from None
        if code==429: raise ValueError('Rate limit reached (HTTP 429). Wait before trying again.') from None
        if code>=500: raise ValueError(f'Nexus server unavailable (HTTP {code}). Retry later.') from None
        raise ValueError(f'Nexus request rejected (HTTP {code}).') from None
    except (socket.timeout, TimeoutError):
        raise ValueError('Network timeout connecting to the Nexus API.') from None
    except (ssl.SSLError, ssl.SSLCertVerificationError):
        raise ValueError('TLS certificate verification failed. Check system CA certificates (ca-certificates on CachyOS).') from None
    except urllib.error.URLError as exc:
        reason=exc.reason
        if isinstance(reason, (ssl.SSLError,ssl.SSLCertVerificationError)):
            raise ValueError('TLS certificate verification failed. Check the AppImage/system CA certificate paths.') from None
        if isinstance(reason,(socket.timeout,TimeoutError)):
            raise ValueError('Network timeout connecting to the Nexus API.') from None
        if isinstance(reason,(socket.gaierror,ConnectionError,OSError)):
            raise ValueError('Network connection failed. Check DNS, internet access, proxy and firewall settings.') from None
        raise ValueError('Network connection to the Nexus API failed.') from None
    except json.JSONDecodeError:
        raise ValueError('Invalid JSON received from the Nexus API.') from None

def nexus_validate_key(api_key, fetch=None):
    if not isinstance(api_key,str) or not api_key.strip():
        raise ValueError('Enter a Nexus personal API key first.')
    data=nexus_api_json('https://api.nexusmods.com/v1/users/validate.json',api_key,fetch=fetch)
    if not isinstance(data,dict) or not any(k in data for k in ('user_id','name','email')):
        raise ValueError('Unexpected API validation response.')
    return True

def nexus_mod_info(game_domain, mod_id, api_key, fetch=None):
    """Fetch one exact Nexus mod; never persists or logs personal keys."""
    if not NEXUS_DOMAIN_RE.fullmatch(str(game_domain)) or not NEXUS_ID_RE.fullmatch(str(mod_id)):
        raise ValueError('Invalid Nexus game domain or mod ID')
    if not isinstance(api_key,str) or not api_key.strip():
        raise ValueError('Enter a Nexus personal API key to check versions')
    url=f'https://api.nexusmods.com/v1/games/{game_domain}/mods/{mod_id}.json'
    data=nexus_api_json(url,api_key,fetch=fetch)
    if not isinstance(data,dict) or not isinstance(data.get('name'),str) or not data.get('name'):
        raise ValueError('Unexpected Nexus mod response')
    return {'name':data['name'], 'version':str(data.get('version') or ''),
            'url':f'https://www.nexusmods.com/{game_domain}/mods/{mod_id}',
            'mod_id':str(mod_id),'game_domain':game_domain}

def check_nexus_updates(game, mods, api_key, fetch=None, max_unique=25):
    """Check a small user-initiated batch; reuse results for duplicate mod references."""
    if not 1 <= max_unique <= 25: raise ValueError('Nexus batch size must be 1–25')
    if not isinstance(api_key,str) or not api_key.strip(): raise ValueError('Nexus API key required')
    results = {}; cache = {}; seen = 0
    for mod in mods:
        ref = nexus_reference(game, mod)
        if ref is None: continue
        path = mod['path']
        if 'error' in ref:
            results[path] = {'status':'Identity conflict', 'error':ref['error']}
            continue
        key = (ref['game_domain'], ref['mod_id'])
        if key not in cache:
            if seen >= max_unique: break
            seen += 1
            try: cache[key] = nexus_mod_info(*key, api_key, fetch=fetch)
            except Exception as error:
                # Failed requests should not cause repeated requests for matching copies.
                cache[key] = {'error':str(error).replace(api_key,'[redacted]'), 'url':ref['url']}
        info = cache[key]
        status = ('Check failed' if 'error' in info
                  else compare_versions(mod.get('version',''), info['version']))
        results[path] = {'status': status, **info, 'local_version':mod.get('version',''),
                         'mod_name':mod.get('name','')}
        if 'error' in info and any(word in info['error'].lower() for word in ('rate limit','authentication','access denied','network','tls certificate','server unavailable')):
            break  # protect quota and avoid repeated invalid-auth requests
    return results

def unified_update_rows(game, mods, nexus_results=None, github_results=None, extra_folders=None):
    """A read-only, grouped view of checked and unchecked installed updates.

    Never equate a source link or missing API key with a completed version check.
    Repeated SMAPI components sharing an exact Nexus page appear as one result.
    Unknown/unindexed folders remain visible without fabricated identities.
    """
    nexus_results = nexus_results or {}
    github_results = github_results or {}
    extra_folders = extra_folders or []
    grouped = {}
    for mod in list(mods) + list(extra_folders):
        path = mod.get('path', '')
        if not path: continue
        ref = nexus_reference(game, mod) if game else None
        repo = github_repo(mod) if mod.get('update_keys') else None
        if ref and 'error' in ref:
            identity = 'conflict:' + path
        elif ref:
            identity = 'nexus:' + ref['game_domain'] + '/' + ref['mod_id']
        elif repo:
            identity = 'github:' + repo.casefold()
        else:
            identity = 'local:' + path
        n = nexus_results.get(path, {})
        h = github_results.get(path, {})
        checked = [r for r in (n, h) if r and r.get('status')]
        statuses = [r.get('status', '') for r in checked]
        if 'Update available' in statuses:
            status = 'Update available'
        elif statuses and all(x in ('Current', 'Local newer') for x in statuses):
            status = 'Up to date' if 'Current' in statuses else 'Local newer'
        elif 'Check failed' in statuses:
            status = 'Check failed'
        elif 'Unknown' in statuses:
            status = 'Version review'
        elif ref and 'error' in ref:
            status = 'ID conflict'
        elif game and game.get('kind')=='smapi' and str(mod.get('uid') or '').casefold() in smapi_catalogue.BUNDLED_SMAPI_IDS:
            status = 'Bundled component'
        elif not ref and not repo:
            status = 'Source needed'
        else:
            status = 'Not checked'
        # A page link is never proof a newer release exists.
        valid_ref = ref if ref and 'error' not in ref else None
        url = (valid_ref or {}).get('url') or (f'https://github.com/{repo}/releases' if repo else '')
        remote = next((r.get('version', '') for r in checked if r.get('status') == 'Update available'), '')
        if not remote: remote = next((r.get('version', '') for r in checked if r.get('version')), '')
        origin = 'Nexus' if valid_ref else 'GitHub' if repo else ('SMAPI' if status=='Bundled component' else 'Unknown')
        group = grouped.get(identity)
        if group is None:
            group = {'identity':identity, 'name':mod.get('name', Path(path).name),
                     'version':mod.get('version', '') or '—', 'remote_version':remote,
                     'status':status, 'source':origin, 'url':url, 'mod':mod,
                     'paths':[path], 'components':1, 'statuses':[status]}
            grouped[identity] = group
        else:
            group['paths'].append(path)
            group['components'] += 1
            group['statuses'].append(status)
            if status == 'Update available':
                group['status'] = status
                if remote: group['remote_version'] = remote
            elif group['status'] != 'Update available' and status in ('ID conflict', 'Check failed'):
                group['status'] = status
            elif group['status'] in ('Not checked', 'Source needed') and status == 'Up to date':
                group['status'] = status
    order = {'Update available':0, 'Check failed':1, 'ID conflict':2,
             'Version review':3, 'Not checked':4, 'Source needed':5,'Bundled component':8,
             'Local newer':6, 'Up to date':7}
    return sorted(grouped.values(),key=lambda r:(order.get(r['status'],8),r['name'].casefold()))


def match_update_downloads(rows, inbox_records):
    """Associate vetted local ZIP inspections with exact installed paths.

    Never infer association from family display name or archive filename. Grouped
    Nexus families may contain several independently installed SMAPI packages.
    Only one ready matching ZIP qualifies for direct Review & Install. Other
    ZIPs remain visible in the advanced inbox for individual inspection.
    """
    safe_status = {'Ready to update', 'Review version'}
    mapped = {}
    for match in inbox_records:
        target = str(match.get('target_path') or '')
        if not target or match.get('status') not in safe_status:
            continue
        mapped.setdefault(target, []).append(match)
    results = []
    for row in rows:
        candidates = []
        for path in row.get('paths', []):
            candidates.extend(mapped.get(str(path), []))
        # Paths must not identify several installed mods with ambiguous ownership.
        if len(candidates) == 1:
            matched = candidates[0]
            stage = 'Ready for review' if matched['status'] == 'Ready to update' else 'Version review'
            selected = matched
        elif len(candidates) > 1:
            stage = 'Multiple archives — review in Inbox'
            selected = None
        else:
            stage = 'No matching ZIP'
            selected = None
        results.append({**row, 'local_archive': selected,
                        'download_status': stage, 'matching_archives': len(candidates)})
    return results


def prepare_update_batch(game, rows, installed=None, limit=30):
    """Fully inspect a selected set of *newer* exact ZIP matches before writing.

    No fuzzy matches, uncertain versions, duplicates or nested target directories.
    The returned plan is immutable by convention; execution verifies every ZIP again.
    """
    if game.get('kind') not in ('smapi','bepinex'):
        raise ValueError('Batch updates require an SMAPI or BepInEx game')
    if not rows or len(rows)>limit:
        raise ValueError(f'Select between 1 and {limit} downloaded updates')
    installed = items(game) if installed is None else installed
    selected=[]; seen_paths=set(); seen_archives=set()
    for row in rows:
        match=row.get('local_archive')
        if row.get('download_status')!='Ready for review' or not match or match.get('status')!='Ready to update':
            raise ValueError(f"{row.get('name','Mod')}: no unambiguous newer ZIP; review individually")
        # Archives are re-opened and hashed immediately before being approved.
        current=(match_downloaded_smapi_archive(game,match['archive']) if game['kind']=='smapi'
                 else match_downloaded_bepinex_archive(game,match['archive']))
        check=('uid','version','target_path','sha256')
        if current.get('status')!='Ready to update' or any(str(current.get(k,''))!=str(match.get(k,'')) for k in check):
            raise ValueError(f"{row['name']}: archive or installed mod changed; rescan")
        target=Path(current['target_path']).resolve()
        archive=Path(current['archive']).resolve()
        if target in seen_paths or archive in seen_archives:
            raise ValueError('Two updates target the same folder or use one archive')
        if any(target.is_relative_to(other) or other.is_relative_to(target) for other in seen_paths):
            raise ValueError('Nested mod folders cannot be replaced together safely')
        if Path(current['target_path']).is_symlink():
            raise ValueError('Cannot batch-update a symlinked mod folder')
        seen_paths.add(target);seen_archives.add(archive)
        deps=update_dependency_preflight(game,current,installed)
        selected.append({'name':row['name'],'match':current,'dependency_issues':deps['new_issues'],
                         'dependency_note':deps['note'],'dependency_supported':deps['supported']})
    return {'game_root':str(Path(game['root']).resolve()),'game_kind':game['kind'],'updates':selected}


def execute_update_batch(game, plan, apply_fn=None, restore_fn=None):
    """Install preapproved updates sequentially; roll back successful ones on error.

    Best-effort file transaction: power failure or external file changes cannot be
    made atomic. Existing backup receipts survive successful installations.
    """
    if (str(Path(game['root']).resolve())!=plan.get('game_root') or
            game.get('kind')!=plan.get('game_kind')):
        raise ValueError('The selected game changed before installation')
    apply_fn=apply_fn or apply_downloaded_update
    restore_fn=restore_fn or restore_backup
    done=[]
    try:
        for entry in plan['updates']:
            match=entry['match']
            backup=Path(apply_fn(game,match))
            record={'game_root':str(Path(game['root']).resolve()), 'kind':game['kind'],
                    'mod_uid':match['uid'],'original_path':match['target_path'],
                    'backup_path':str(backup)}
            done.append((entry['name'],record))
    except Exception as exc:
        failures=[];restored=[]
        for name,record in reversed(done):
            try:
                restore_fn(game,record)
                restored.append(name)
            except Exception as rollback_exc:
                failures.append(f'{name}: {rollback_exc}')
        outcome=f'Batch failed: {exc}. Rolled back {len(restored)}/{len(done)} previous updates.'
        if failures:
            outcome+=' MANUAL RECOVERY REQUIRED: '+'; '.join(failures)
        raise RuntimeError(outcome) from exc
    return {'count':len(done),'backups':[record['backup_path'] for _,record in done],
            'names':[name for name,_ in done]}


def update_dependency_preflight(game, match, mods=None):
    """Advisory comparison of a SMAPI update's required dependency health.

    The archive must match a unique installed mod. Dependencies are read from
    the candidate manifest, never executed. Existing unrelated SMAPI warnings
    are deliberately not promoted into new blockers.
    """
    if game.get('kind') != 'smapi':
        return {'supported': False, 'new_issues': [], 'note': 'BepInEx dependency compatibility is not verified by this inspector.'}
    mods = items(game) if mods is None else mods
    candidates = [m for m in mods if m.get('path') == match.get('target_path')]
    if len(candidates) != 1:
        raise ValueError('Update destination is no longer uniquely identified; rescan')
    old = candidates[0]
    infos = inspect_smapi_archive(match['archive'])
    if len(infos) != 1 or infos[0]['uid'].casefold() != str(old.get('uid', '')).casefold():
        raise ValueError('ZIP no longer matches the installed SMAPI UniqueID')
    with zipfile.ZipFile(match['archive']) as z:
        member = infos[0]['member']
        if z.getinfo(member).file_size > 1024*1024:raise ValueError('Manifest too large')
        rawbytes = z.read(member)
    rawtext = rawbytes.decode('utf-8-sig')
    try: raw = json.loads(rawtext)
    except ValueError:
        import json5
        raw = json5.loads(rawtext, allow_duplicate_keys=False)
    if not isinstance(raw, dict):raise ValueError('Invalid candidate manifest')
    deps = _manifest_field(raw,'Dependencies',[])
    if not isinstance(deps,list):deps=[]
    dependencies=[{'uid':str(_manifest_field(d,'UniqueID','') or ''),
                   'required':bool(_manifest_field(d,'IsRequired',True)),
                   'minimum_version':str(_manifest_field(d,'MinimumVersion') or '')}
                  for d in deps if isinstance(d,dict) and _manifest_field(d,'UniqueID')]
    cp = _manifest_field(raw,'ContentPackFor')
    revised = {**old, 'version':str(_manifest_field(raw,'Version') or infos[0]['version']),
               'dependencies':dependencies,
               'content_pack_for':str(_manifest_field(cp,'UniqueID','') or '') if isinstance(cp,dict) else ''}
    before = smapi_dependency_report(mods)
    after = smapi_dependency_report([revised if m['path']==old['path'] else m for m in mods])
    bad = {'Missing','Disabled provider','Below minimum','Ambiguous providers','Version unverified'}
    def failures(records):
        return {(r['mod_path'],r['dependency'].casefold(),r['type']):r for r in records
                if r['required'] and r['mod_enabled'] and r['status'] in bad}
    previous = failures(before)
    new = [r for key,r in failures(after).items()
           if key not in previous or previous[key]['status'] != r['status']]
    return {'supported': True, 'new_issues': new,
            'note': 'Advisory SMAPI dependency review; some IDs are built into the game or SMAPI.'}


# Public Thunderstore catalogue: read-only, network operations are in a worker thread.
# v1 community URL documented at https://thunderstore.io/api/docs/
THUNDERSTORE_COMMUNITY_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
THUNDERSTORE_CACHE = APP/'thunderstore-cache'

def thunderstore_catalogue(community, fetch=None):
    community = str(community).strip().lower()
    if not THUNDERSTORE_COMMUNITY_RE.fullmatch(community):
        raise ValueError('Invalid Thunderstore community slug')
    url = f'https://thunderstore.io/c/{community}/api/v1/package/'
    if fetch is None:
        req = urllib.request.Request(url, headers={'User-Agent':'UniMod/0.54','Accept':'application/json'})
        with urllib.request.urlopen(req, timeout=25) as response:
            # Cap large JSON responses rather than trusting a network endpoint.
            data = response.read(35 * 1024 * 1024 + 1)
            if len(data) > 35 * 1024 * 1024:
                raise ValueError('Catalogue exceeded 35 MiB')
            packages = json.loads(data)
    else:
        packages = fetch(url)
    if not isinstance(packages, list):
        raise ValueError('Unexpected Thunderstore catalogue format')
    result = []
    for package in packages:
        if not isinstance(package, dict):continue
        versions = package.get('versions') or []
        latest = versions[0] if isinstance(versions,list) and versions and isinstance(versions[0],dict) else {}
        owner = package.get('owner') or ''
        name = package.get('name') or ''
        if not isinstance(owner,str) or not isinstance(name,str) or not owner or not name:continue
        package_url=package.get('package_url') or ''
        if not (isinstance(package_url,str) and package_url.startswith('https://thunderstore.io/')):
            package_url=f'https://thunderstore.io/c/{community}/p/{owner}/{name}/'
        result.append({'owner':owner,'name':name,'description':str(latest.get('description') or ''),
                       'version':str(latest.get('version_number') or ''),
                       'downloads':int(package.get('total_downloads') or 0),
                       'url':package_url,
                       'dependencies':list(latest.get('dependencies') or []),
                       'download_url':str(latest.get('download_url') or ''),
                       'full_name':str(package.get('full_name') or f'{owner}-{name}')})
    return result


# v0.11: use explicit on-disk Thunderstore package metadata to confirm dependencies.
def installed_thunderstore_packages(game):
    """Read-only package metadata scan; never infer identity from a loose DLL name."""
    base=mod_root(game)
    result={}
    if not base.is_dir():return result
    for root,dirs,files in os.walk(base,followlinks=False):
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(root)/d).is_symlink()]
        folder=Path(root)
        if 'manifest.json' not in files:continue
        try:
            metadata=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
        except (OSError,ValueError,UnicodeError):continue
        if not isinstance(metadata,dict):continue
        # SMAPI manifests have UniqueID and cannot be taken as Thunderstore identities.
        if 'UniqueID' in metadata:continue
        owner=metadata.get('owner') or metadata.get('author')
        name=metadata.get('name')
        version=metadata.get('version_number') or metadata.get('version')
        if not all(isinstance(v,str) and v.strip() for v in (owner,name,version)):continue
        package=f'{owner.strip()}-{name.strip()}'
        result[package.casefold()]={'package':package,'version':version.strip(),'path':str(folder)}
    return result

def version_satisfies(installed,required):
    """Thunderstore references an exact released version, not a minimum version."""
    return not required or str(installed)==str(required)

# v0.23: exact-identity Thunderstore installed-package reconciliation.
# The selected catalogue is NOT an authoritative game compatibility database.
# Only a matching, official Thunderstore community URL is strong evidence that
# an installed package belongs to the catalogue currently being compared.
from urllib.parse import urlsplit


def _thunderstore_page_identity(link):
    """Parse an official Thunderstore package URL; ignore query/fragment/credentials."""
    if not isinstance(link, str) or len(link) > 2048: return None
    try:
        parsed = urlsplit(link.strip())
        port = parsed.port
    except (ValueError,TypeError): return None
    if (parsed.scheme != 'https' or parsed.hostname not in ('thunderstore.io', 'www.thunderstore.io')
            or parsed.username or parsed.password or port not in (None,443)):
        return None
    match = re.fullmatch(r'/c/([a-z0-9][a-z0-9-]{0,79})/p/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/?', parsed.path)
    if not match:return None
    return {'community':match.group(1).casefold(), 'owner':match.group(2).casefold(),
            'name':match.group(3).casefold()}


def thunderstore_installed_report(game, catalogue, community):
    """Compare explicit local BepInEx manifests with one loaded community catalogue.

    Never fuzzy-match folder names, DLL names, or SMAPI UniqueIDs. No I/O writes.
    A catalogue entry with the same author/package is *not* enough to confirm
    game/community identity; a valid matching Thunderstore package URL is required.
    """
    if game.get('kind') != 'bepinex': return []
    if not THUNDERSTORE_COMMUNITY_RE.fullmatch(str(community).strip().lower()):
        raise ValueError('Invalid Thunderstore community')
    community=str(community).strip().casefold()
    by_key={}
    for raw in catalogue:
        if not isinstance(raw,dict): continue
        owner,name=raw.get('owner'),raw.get('name')
        if not isinstance(owner,str) or not isinstance(name,str):continue
        k=(owner.casefold(),name.casefold())
        if k in by_key: by_key[k] = None  # Ambiguous catalogues never get an identity match.
        else: by_key[k]=raw
    packages=discover_bepinex_packages(game)
    copies={}
    for entry in packages:
        k=(entry['owner'].casefold(),entry['name'].casefold())
        copies[k]=copies.get(k,0)+1
    rows=[]
    for entry in packages:
        key=(entry['owner'].casefold(), entry['name'].casefold())
        remote=by_key.get(key)
        identity=_thunderstore_page_identity(entry.get('website_url',''))
        if identity is None:
            confidence='Unverified community'
        elif (identity['owner'],identity['name']) != key:
            confidence='Conflicting source ID'
        elif identity['community']!=community:
            confidence='Different community'
        else:
            confidence='Verified metadata'
        latest=str(remote.get('version') or '') if isinstance(remote,dict) else ''
        url=str(remote.get('url') or '') if isinstance(remote,dict) else ''
        # Catalogue-provided URLs must themselves match this community and identity.
        remote_page=_thunderstore_page_identity(url)
        if remote_page != {'community':community,'owner':key[0],'name':key[1]}:
            url=''
        if copies[key]>1: status='Multiple local copies'
        elif confidence=='Conflicting source ID': status='Conflicting source ID'
        elif confidence=='Different community': status='Different community'
        elif confidence!='Verified metadata': status='Community unverified'
        elif not isinstance(remote,dict): status='Not in catalogue'
        elif not url: status='Catalogue URL unverified'
        else: status=compare_versions(entry['version'],latest)
        rows.append({'package':entry['owner']+'-'+entry['name'],
                     'installed':entry['version'], 'latest':latest,
                     'status':status,'confidence':confidence,'enabled':bool(entry['enabled']),
                     'copies':copies[key],'path':entry['folder'], 'url':url,
                     'dll_count':entry['dll_count']})
    return sorted(rows,key=lambda r:(r['package'].casefold(),r['path']))


# v0.10 pre-install planning: advisory dependency lookup and hard SMAPI ID collision checks.
def dependency_plan(package, catalogue, receipts=(), local_packages=None):
    """Resolve Thunderstore identifiers against the loaded catalogue; no downloads."""
    byname={str(p.get('full_name','')).casefold():p for p in catalogue}
    installed={str(r.get('package','')).casefold():str(r.get('version','')) for r in receipts}
    local_packages=local_packages or {}
    plan=[]; visiting=set(); visited=set()
    def visit(dep,depth=0):
        if depth>24: raise ValueError('Dependency nesting exceeds safety limit')
        # Thunderstore dependencies encode Owner-Name-Version. Split from right.
        bits=str(dep).rsplit('-',1)
        full=bits[0] if len(bits)==2 else str(dep)
        wanted=bits[1] if len(bits)==2 else ''
        key=full.casefold()
        if key in visited:return
        if key in visiting:raise ValueError('Cyclic dependency: '+full)
        visiting.add(key)
        found=byname.get(key)
        if found:
            for child in found.get('dependencies',[]): visit(child,depth+1)
        visiting.remove(key);visited.add(key)
        local=local_packages.get(key)
        if key in installed:
            status='tracked' if version_satisfies(installed[key],wanted) else 'installed version differs'
        elif local:
            status='installed locally' if version_satisfies(local['version'],wanted) else 'local version differs'
        else:
            status=('missing from catalogue' if not found else
                    'catalogue version differs' if wanted and wanted!=str(found.get('version','')) else 'available')
        plan.append({'dependency':str(dep),'package':full,'status':status,
                     'latest':str(found.get('version','')) if found else ''})
    for dep in package.get('dependencies',[]):visit(dep)
    return plan

def preflight_smapi_conflicts(game,archive):
    """Refuse duplicate UniqueIDs, including duplicates inside the ZIP."""
    if game.get('kind')!='smapi':return []
    existing={m.get('uid','').casefold():m['name'] for m in items(game) if m.get('uid')}
    with zipfile.ZipFile(archive) as z:
        names=[n for n in z.namelist() if n.lower().endswith('/manifest.json') or n.lower()=='manifest.json']
        if len(names)>1000:raise ValueError('Too many manifest files')
        seen=set();conflicts=[]
        for n in names:
            info=z.getinfo(n)
            if info.file_size>1024*1024:raise ValueError('Manifest exceeds 1 MiB')
            try:manifest=json.loads(z.read(n))
            except (ValueError,UnicodeError):continue
            if not isinstance(manifest,dict):continue
            uid=str(manifest.get('UniqueID','')).strip()
            if not uid:continue
            key=uid.casefold()
            if key in seen:conflicts.append(uid+' appears more than once in ZIP')
            if key in existing:conflicts.append(uid+' already installed as '+existing[key])
            seen.add(key)
    return conflicts

# Managed installs are additive: never overwrite pre-existing mods. The receipt
# records only newly created directories and supports undo for managed installs.
INSTALL_RECEIPTS = APP / 'install-receipts.json'

def read_receipts():
    try:
        value=json.loads(INSTALL_RECEIPTS.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def write_receipts(receipts):
    tmp=INSTALL_RECEIPTS.with_suffix('.tmp')
    tmp.write_text(json.dumps(receipts,indent=2));tmp.replace(INSTALL_RECEIPTS)

def thunderstore_install(game, package, fetch_archive=None):
    """Install a selected package (only), preserving existing mods and a receipt.

    Dependencies are disclosed by the GUI but never silently installed.
    """
    if not game or game.get('kind') not in ('smapi','bepinex'):
        raise ValueError('Select a SMAPI or BepInEx game before installing.')
    link=package.get('download_url','')
    from urllib.parse import urlsplit
    parsed=urlsplit(link)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Package is missing a valid HTTPS download URL.')
    # The Thunderstore API normally serves packages from thunderstore.io/CDN.
    # Reject arbitrary host URLs in catalogue records.
    host=parsed.hostname.lower()
    if host not in ('thunderstore.io','www.thunderstore.io','gcdn.thunderstore.io','cdn.thunderstore.io'):
        raise ValueError('Unexpected Thunderstore download host: '+host)
    with tempfile.TemporaryDirectory(prefix='unimod-ts-') as td:
        archive=Path(td)/'package.zip'
        if fetch_archive is None:download(link,archive)
        else:fetch_archive(link,archive)
        if not zipfile.is_zipfile(archive):raise ValueError('Package download is not a ZIP.')
        collisions=preflight_smapi_conflicts(game,archive)
        if collisions:raise ValueError('Duplicate SMAPI IDs blocked: '+ '; '.join(collisions))
        created=install_zip(game,archive)
    root=mod_root(game).resolve()
    paths=[str((root / name).resolve()) for name in created]
    receipt={'game':str(Path(game['root']).resolve()),'package':package.get('full_name') or package['name'],
             'version':package.get('version',''),'source':package.get('url',''),
             'dependencies':package.get('dependencies',[]),'paths':paths,
             'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    receipts=read_receipts();receipts.append(receipt);write_receipts(receipts)
    return receipt

def thunderstore_install_transaction(game, package, catalogue, fetch_archive=None):
    """Install exact catalogue dependency versions and target as an all-or-nothing batch.

    Strict mode: refuses ambiguous/missing versions and leaves existing directories untouched.
    Existing locally satisfied dependencies must be confirmed by explicit metadata.
    """
    if not game or game.get('kind') not in ('smapi','bepinex'):
        raise ValueError('Only SMAPI/BepInEx layouts are supported.')
    game_id=str(Path(game['root']).resolve())
    receipts=[r for r in read_receipts() if r.get('game')==game_id]
    local=installed_thunderstore_packages(game)
    plan=dependency_plan(package,catalogue,receipts,local)
    bad=[d for d in plan if d['status'] not in ('tracked','installed locally','available')]
    if bad:raise ValueError('Unresolved dependencies: '+', '.join(x['dependency']+' ('+x['status']+')' for x in bad))
    byname={str(x.get('full_name','')).casefold():x for x in catalogue}
    targets=[]
    for item in plan:
        if item['status']!='available':continue
        dep=byname[item['package'].casefold()]
        if item['dependency'].rsplit('-',1)[-1]!=str(dep.get('version','')):
            raise ValueError('Exact dependency release missing: '+item['dependency'])
        targets.append(dep)
    targets.append(package)
    # Download and validate every archive before modifying the game.
    with tempfile.TemporaryDirectory(prefix='unimod-batch-') as td:
        archives=[]; staged_uids=set()
        for i,pkg in enumerate(targets):
            link=pkg.get('download_url','')
            from urllib.parse import urlsplit
            u=urlsplit(link)
            if u.scheme!='https' or u.username or u.password or (u.hostname or '').lower() not in (
                'thunderstore.io','www.thunderstore.io','gcdn.thunderstore.io','cdn.thunderstore.io'):
                raise ValueError('Untrusted Thunderstore download URL for '+str(pkg.get('full_name')))
            archive=Path(td)/f'package-{i}.zip'
            if fetch_archive is None:download(link,archive)
            else:fetch_archive(link,archive)
            if not zipfile.is_zipfile(archive):raise ValueError('Invalid ZIP for '+str(pkg.get('full_name')))
            # safe_extract rejects traversal, symlinks and oversized ZIPs; validate before mutation.
            with zipfile.ZipFile(archive) as z:
                safe_extract(z,Path(td)/f'check-{i}')
            conflicts=preflight_smapi_conflicts(game,archive)
            if conflicts:raise ValueError('Duplicate SMAPI IDs: '+'; '.join(conflicts))
            if game['kind']=='smapi':
                for m in (Path(td)/f'check-{i}').rglob('manifest.json'):
                    try:uid=str(json.loads(m.read_text(encoding='utf-8-sig')).get('UniqueID','')).casefold()
                    except (ValueError,UnicodeError,OSError):continue
                    if uid and uid in staged_uids:raise ValueError('Duplicate SMAPI ID across packages: '+uid)
                    if uid:staged_uids.add(uid)
            archives.append((pkg,archive))
        created_paths=[];new_receipts=[]
        root=mod_root(game).resolve()
        try:
            for pkg,archive in archives:
                # Record any directories created even if an installation throws mid-copy.
                before={p.name for p in root.iterdir()} if root.exists() else set()
                try:
                    names=install_zip(game,archive)
                finally:
                    if root.exists():
                        created_paths.extend(root/p.name for p in root.iterdir() if p.name not in before)
                new_receipts.append({'game':game_id,'package':pkg.get('full_name') or pkg['name'],
                  'version':pkg.get('version',''),'source':pkg.get('url',''),
                  'dependencies':pkg.get('dependencies',[]),
                  'paths':[str(root/name) for name in names],
                  'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
            write_receipts(read_receipts()+new_receipts)
            return new_receipts
        except Exception:
            # Never overwrite existing folders; remove only newly created paths.
            # Move to recovery instead of destroying staged user files.
            recovery=APP/'recovery'/'failed-transactions'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            for path in reversed(created_paths):
                if path.exists() and path.parent==root:
                    recovery.mkdir(parents=True,exist_ok=True)
                    shutil.move(str(path),str(unique(recovery/path.name)))
            raise

def undo_thunderstore_install(receipt, game):
    """Move managed files into recovery storage. Never delete user data."""
    root=mod_root(game).resolve()
    if str(Path(game['root']).resolve())!=receipt.get('game'):
        raise ValueError('Receipt belongs to another game.')
    paths=[Path(x).resolve() for x in receipt.get('paths',[])]
    if not paths or any(p.parent!=root for p in paths):
        raise ValueError('Unsafe receipt path; aborting.')
    recovery=APP/'recovery'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    recovery.mkdir(parents=True,exist_ok=False)
    moved=[]
    for path in paths:
        if path.exists():
            target=recovery/path.name
            shutil.move(str(path),str(target));moved.append(str(target))
    receipts=read_receipts()
    if receipt in receipts:receipts.remove(receipt);write_receipts(receipts)
    return moved

def inventory_update(game,mods):
    try:data=json.loads(INVENTORY.read_text())
    except (OSError,ValueError):data={}
    key=str(Path(game['root']).resolve())
    history=data.get(key,{})
    for mod in mods:
        identity=mod['uid'] or mod['relative']
        old=history.get(identity,{})
        history[identity]={'name':mod['name'],'version':mod['version'], 'path':mod['path'],
                           'enabled':mod['enabled'],'update_keys':mod.get('update_keys',[]),
                           'first_seen':old.get('first_seen') or datetime.date.today().isoformat(),
                           'last_seen':datetime.date.today().isoformat()}
    data[key]=history
    tmp=INVENTORY.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(INVENTORY)
    return len(history)

# Explicit scan snapshots are stored separately from discovery history.
SNAPSHOTS = APP/'snapshots'
def snapshot_key(game):
    import hashlib
    return hashlib.sha256(str(Path(game['root']).resolve()).encode('utf-8')).hexdigest()[:24]

def snapshot_file(game):
    return SNAPSHOTS/(snapshot_key(game)+'.json')

def snapshot_records(mods):
    # Keep duplicates by matching their game-relative path, not by SMAPI UID alone.
    records={}
    for m in mods:
        key=('on/' if m['enabled'] else 'off/')+str(m['relative']).replace('\\','/')
        records[key]={'name':m['name'],'uid':m.get('uid',''),'version':m.get('version',''),
                      'enabled':bool(m['enabled']),'relative':m['relative']}
    return records

def load_snapshot(game):
    f=snapshot_file(game)
    if not f.is_file():return None
    try:
        data=json.loads(f.read_text(encoding='utf-8'))
        if data.get('game_root') != str(Path(game['root']).resolve()) or not isinstance(data.get('mods'),dict):return None
        return data
    except (OSError,ValueError,TypeError):return None

def save_snapshot(game,mods):
    SNAPSHOTS.mkdir(parents=True,exist_ok=True)
    data={'format':1,'game_root':str(Path(game['root']).resolve()),
          'created':datetime.datetime.now().astimezone().isoformat(),'mods':snapshot_records(mods)}
    dest=snapshot_file(game)
    with tempfile.NamedTemporaryFile('w',dir=SNAPSHOTS,encoding='utf-8',delete=False) as out:
        tmp=Path(out.name);json.dump(data,out,indent=2)
    tmp.replace(dest)
    return dest

def compare_snapshot(saved, current_mods):
    if not saved:return []
    previous=saved['mods'];current=snapshot_records(current_mods)
    result=[]
    # Compare by relative paths independent of enabled state so toggles are changes.
    def group(records):
        output={}
        for item in records.values():
            output[item['relative']]=item
        return output
    old=group(previous);now=group(current)
    for key in sorted(set(old)|set(now),key=str.casefold):
        a=old.get(key);b=now.get(key)
        if a is None:kind='Added'
        elif b is None:kind='Missing'
        elif a['enabled'] != b['enabled']:kind='Enabled' if b['enabled'] else 'Disabled'
        elif a['version'] != b['version']:kind='Version changed'
        elif a['uid'] != b['uid']:kind='Identity changed'
        else:continue
        result.append({'change':kind,'mod':(b or a)['name'],'before':a['version'] if a else '',
                       'after':b['version'] if b else '', 'relative':key})
    return result

def top_level_mod_path(game,mod):
    base=Path(mod['root_dir']);relative=Path(mod['relative'])
    return base/relative.parts[0]

def profile_inventory(game, mods=None):
    """Group discovered mods by their movable *top-level* payload (not individual DLLs).

    Repeated SMAPI manifests or nested BepInEx DLLs are always one profile unit.
    This function reads but never modifies the game installation.
    """
    mods = items(game) if mods is None else mods
    groups = {}
    for mod in mods:
        top = top_level_mod_path(game, mod)
        name = top.name
        if (not name or name in ('.', '..') or '/' in name or '\\' in name
                or name.startswith('.') or top.is_symlink()):
            raise ValueError(f'Unsafe mod payload in profile inventory: {top}')
        if not top.exists():
            raise ValueError(f'Profile payload vanished during scan: {top}')
        if name in groups and groups[name]['enabled'] != bool(mod['enabled']):
            raise ValueError(f'Both enabled and disabled copies exist for {name!r}; resolve this manually before switching profiles.')
        if name not in groups:
            groups[name] = {'name':name, 'enabled':bool(mod['enabled']),
                            'source':top, 'mod_count':0}
        groups[name]['mod_count'] += 1
    return groups


def profile_document(game, mods=None):
    """v0.18 profile files (game+mods) remain readable in v0.19."""
    entries = profile_inventory(game, mods)
    return {'schema':2, 'game':str(Path(game['root']).resolve()), 'kind':game['kind'],
            'mods':{name:entry['enabled'] for name,entry in sorted(entries.items())}}


def plan_profile_switch(game, profile, mods=None):
    """Preflight all profile moves, without making changes or silently skipping conflicts."""
    if not isinstance(profile,dict) or not isinstance(profile.get('mods'),dict):
        raise ValueError('Invalid profile: expected an object containing a mods mapping')
    if profile.get('game') != str(Path(game['root']).resolve()):
        raise ValueError('Profile belongs to a different game installation')
    if profile.get('kind') not in (None,game['kind']):
        raise ValueError('Profile belongs to a different mod framework')
    requested=profile['mods']
    for name, enabled in requested.items():
        if (not isinstance(name,str) or not name or name.startswith('.') or name in ('.','..')
                or '/' in name or '\\' in name or '\x00' in name or not isinstance(enabled,bool)):
            raise ValueError(f'Invalid profile entry: {name!r} (names must be simple folder/file names and states must be booleans)')
    enabled_root=mod_root(game)
    off_root=disabled_root(game)
    if enabled_root.is_symlink() or off_root.is_symlink():
        raise ValueError('Profile roots must not be symbolic links')
    inventory=profile_inventory(game,mods)
    moves=[]
    for name,entry in sorted(inventory.items()):
        desired=requested.get(name)
        if desired is None or desired==entry['enabled']:continue
        source=entry['source']
        destination=(enabled_root if desired else off_root)/name
        if destination.exists() or destination.is_symlink():
            raise ValueError(f'Profile conflict: target already exists: {destination}. No files have been moved.')
        moves.append({'name':name,'source':source,'destination':destination,
                      'from_enabled':entry['enabled'],'to_enabled':desired,
                      'mod_count':entry['mod_count']})
    return {'game':game, 'changes':moves,
            'missing':sorted(set(requested)-set(inventory)),
            'unchanged':sum(name in requested and requested[name]==entry['enabled'] for name,entry in inventory.items()),
            'unmanaged':sorted(set(inventory)-set(requested))}


def apply_profile_plan(plan, move=None):
    """Rename grouped payloads; roll all successful moves back on any failure.

    Renames stay inside the same game filesystem. A power failure cannot be made
    atomic across multiple renames, so this is best-effort process-level rollback.
    """
    move = move or (lambda src,dst:src.rename(dst))
    game=plan['game']
    enabled_root=mod_root(game);off_root=disabled_root(game)
    if enabled_root.is_symlink() or off_root.is_symlink():
        raise ValueError('Profile roots must not be symbolic links')
    moves=plan['changes']
    # Verify *every* destination and source before starting the first write.
    for operation in moves:
        src=Path(operation['source']);dst=Path(operation['destination'])
        expected_src=(enabled_root if operation['from_enabled'] else off_root)/operation['name']
        expected_dst=(enabled_root if operation['to_enabled'] else off_root)/operation['name']
        if src!=expected_src or dst!=expected_dst or src.is_symlink() or not src.exists() or dst.exists() or dst.is_symlink():
            raise ValueError(f'Profile files changed since preview: {operation["name"]}. Reopen the profile to preview it again.')
    completed=[]
    try:
        for operation in moves:
            src=Path(operation['source']);dst=Path(operation['destination'])
            dst.parent.mkdir(parents=True,exist_ok=True)
            move(src,dst)
            completed.append((dst,src))
    except Exception as original:
        rollback_errors=[]
        for now,previous in reversed(completed):
            try:move(now,previous)
            except Exception as exc:rollback_errors.append(f'{now.name}: {exc}')
        if rollback_errors:
            raise RuntimeError(f'Profile switch failed ({original}) and recovery was incomplete: {"; ".join(rollback_errors)}') from original
        raise RuntimeError(f'Profile switch failed ({original}); completed moves were rolled back.') from original
    return len(completed)


def safe_extract(z, dest):
    members=z.infolist()
    if len(members)>10000: raise ValueError('Archive contains too many files')
    total=sum(x.file_size for x in members)
    if total>2*1024**3: raise ValueError('Archive expands beyond the 2 GiB safety limit')
    root=dest.resolve()
    for m in members:
        if m.is_dir(): continue
        n=m.filename.replace('\\','/')
        if n.startswith('/') or re.match(r'^[a-zA-Z]:',n):raise ValueError('Absolute archive path blocked')
        target=(root/n).resolve()
        if not target.is_relative_to(root):raise ValueError('Archive traversal blocked')
        if (m.external_attr>>16)&0o170000 == 0o120000:raise ValueError('Archive symlinks blocked')
        target.parent.mkdir(parents=True,exist_ok=True)
        with z.open(m) as src, target.open('wb') as dst:shutil.copyfileobj(src,dst)

def install_zip(game, archive):
    base=mod_root(game);base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='unimod-') as td:
        stage=Path(td)
        with zipfile.ZipFile(archive) as z:safe_extract(z,stage)
        if game['kind']=='smapi':
            # Scan every packaged SMAPI identity, including nested content packs.
            # Do not use folder names as identities and do not create duplicate IDs.
            manifests=sorted((p for p in stage.rglob('manifest.json') if p.is_file()),key=lambda p:str(p).casefold())
            details=[(p.parent,smapi_manifest(p.parent)) for p in manifests]
            details=[(folder,info) for folder,info in details if info]
            if not details:raise ValueError('No SMAPI manifest.json found in this ZIP; no files installed.')
            imported={}
            for folder,info in details:
                uid=info['uid'].casefold()
                if uid in imported:
                    raise ValueError(f'Duplicate SMAPI UniqueID inside ZIP: {info["uid"]}')
                imported[uid]=folder
            current={m['uid'].casefold() for m in items(game) if m.get('uid')}
            conflicts=current.intersection(imported)
            if conflicts:
                raise ValueError('Already installed SMAPI UniqueID(s): '+', '.join(sorted(conflicts))+'. Use Download Inbox or Replace ZIP + backup to update.')
            mods=[folder for folder,_ in details]
            mods=[folder for folder in mods if not any(other in folder.parents for other in mods)]
            planned=[]
            reserved=set()
            for folder in mods:
                name=Path(archive).stem if folder==stage else folder.name
                candidate=base/name
                i=2
                while candidate.exists() or candidate.name in reserved:
                    candidate=base/(name+'-'+str(i));i+=1
                reserved.add(candidate.name)
                planned.append((folder,candidate))
            installed=[]
            try:
                for folder,dest in planned:
                    shutil.copytree(folder,dest)
                    installed.append(dest)
            except Exception:
                # Only remove directories created in this call, never prior mods.
                for target in reversed(installed):shutil.rmtree(target)
                raise
            return [target.name for target in installed]
        # BepInEx: preserve single-package metadata when present. Existing mods
        # can subsequently be matched for safe folder-level ZIP updates.
        if game['kind']=='bepinex':
            inspected=inspect_bepinex_archive(archive)
            if inspected['status']=='Identified':
                conflicts=[p for p in discover_bepinex_packages(game) if _package_matches(p,inspected)]
                if conflicts:raise ValueError('BepInEx package already installed. Use Update Inbox for safe replacement.')
                pkgroot=stage/Path(inspected['member']).parent
                group=unique(base/re.sub(r'[^A-Za-z0-9_.-]','_',inspected['name']))
                with tempfile.TemporaryDirectory(prefix='unimod-bep-layout-') as layout_temp:
                    pkgroot=_normalize_bepinex_stage(pkgroot,layout_temp)
                    shutil.copytree(pkgroot,group)
                return [group.name]
            if inspected['status'] in ('Multi-package ZIP','Ambiguous ZIP layout'):
                raise ValueError(inspected['note']+'; install these packages separately')
            # Metadata-free legacy ZIPs still import, but are not eligible for
            # automatic package updates without a clear source identity.
            dlls=[p for p in stage.rglob('*.dll') if 'BepInEx/core' not in p.as_posix() and 'BepInEx/patchers' not in p.as_posix()]
            if not dlls:raise ValueError('No plugin DLLs found in archive.')
            group=unique(base/archive.stem);group.mkdir()
            try:
                for dll in dlls:shutil.copy2(dll,unique(group/dll.name))
            except Exception:
                shutil.rmtree(group)
                raise
            return [group.name]
        if game['kind']=='melonloader':
            raise ValueError('MelonLoader installation is discovery-only in v0.18. Use the game-specific official installation method.')
        # Generic: install top-level folder(s) as mods.
        roots=[p for p in stage.iterdir() if p.name!='__MACOSX']
        if not roots:raise ValueError('Empty archive')
        installed=[]
        for p in roots:
            d=unique(base/p.name)
            if p.is_dir():shutil.copytree(p,d)
            else:shutil.copy2(p,d)
            installed.append(d.name)
        return installed

# Browser-assisted downloaded ZIP matching (no Nexus file APIs or filename guesses).
# This inspects ZIP metadata without extracting into the game or reading whole archives.
def inspect_smapi_archive(archive):
    """Return all SMAPI identities inside ZIP, rejecting unsafe/unreasonable entries.

    File names and archive metadata are untrusted. Nothing is written to disk.
    """
    archive=Path(archive)
    if not archive.is_file() or archive.stat().st_size > 512*1024*1024:
        raise ValueError('Archive missing or larger than 512 MiB')
    result=[]
    with zipfile.ZipFile(archive) as z:
        members=z.infolist()
        if len(members)>10000:raise ValueError('Archive contains too many files')
        if sum(m.file_size for m in members)>2*1024**3:raise ValueError('Archive expands beyond 2 GiB')
        for member in members:
            name=member.filename.replace('\\','/')
            parts=name.split('/')
            if (name.startswith('/') or re.match(r'^[A-Za-z]:', name) or
                    any(x=='..' for x in parts) or '\x00' in name or
                    (member.external_attr>>16)&0o170000 == 0o120000):
                raise ValueError('Unsafe ZIP member path or symlink')
            if member.is_dir() or Path(name).name.casefold()!='manifest.json':
                continue
            if member.file_size>1024*1024:raise ValueError('Manifest exceeds 1 MiB')
            with z.open(member) as raw:
                source=raw.read(1024*1024+1).decode('utf-8-sig')
            try:manifest=json.loads(source)
            except ValueError:
                import json5
                manifest=json5.loads(source,allow_duplicate_keys=False)
            uid=_manifest_field(manifest,'UniqueID')
            if not isinstance(uid,str) or not uid.strip():continue
            result.append({'uid':uid.strip(),
                           'name':str(_manifest_field(manifest,'Name') or Path(name).parent.name),
                           'version':str(_manifest_field(manifest,'Version') or ''),
                           'member':name})
    return result

def match_downloaded_smapi_archive(game, archive, installed=None):
    """Match using *exact* UniqueID; do not infer trust/provenance from filenames."""
    record={'archive':str(Path(archive)),'status':'Unknown','uid':'','name':'',
            'version':'','installed':'','local_version':'','target_path':'','note':'','sha256':''}
    if game.get('kind')!='smapi':
        record.update(status='Unsupported game',note='Downloaded ZIP matching currently supports SMAPI only')
        return record
    try:
        mod_infos=inspect_smapi_archive(archive)
        # Hash the archive after successful validation so a changed but identical
        # version/UniqueID does not silently replace the reviewed package.
        sha=hashlib.sha256()
        with Path(archive).open('rb') as stream:
            for block in iter(lambda:stream.read(4*1024*1024),b''):
                sha.update(block)
        record['sha256']=sha.hexdigest()
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile,
            RuntimeError, EOFError) as exc:
        record.update(status='Invalid / unsafe ZIP',note=str(exc)[:240]);return record
    if not mod_infos:
        record.update(status='Not SMAPI',note='No valid manifest.json with UniqueID');return record
    if len(mod_infos)!=1:
        record.update(status='Multi-mod ZIP', note=f'{len(mod_infos)} SMAPI manifests. Import as a modpack separately.');return record
    info=mod_infos[0];record.update(uid=info['uid'],name=info['name'],version=info['version'])
    mods=items(game) if installed is None else installed
    hits=[m for m in mods if m.get('uid','').casefold()==info['uid'].casefold()]
    if not hits:
        record.update(status='No installed match',note='UniqueID not present in selected game');return record
    if len(hits)!=1:
        record.update(status='Duplicate installed ID',note=f'{len(hits)} existing copies found. Resolve duplicates first.');return record
    local=hits[0]
    record.update(installed=local['name'],local_version=local.get('version',''),target_path=local['path'])
    comparison=compare_versions(local.get('version',''),info['version'])
    if comparison=='Current':status='Already current';note='Installed version equals archive version'
    elif comparison=='Local newer':status='Archive older';note='Archive version is below installed version'
    elif comparison=='Unknown':status='Review version';note='Version strings cannot be compared; inspect before replacing'
    else:status='Ready to update';note='UniqueID matches an existing mod (not a source authenticity check)'
    record.update(status=status,note=note)
    return record

def scan_download_inbox(game, folder, max_archives=200):
    """Read-only; scan top-level downloaded ZIPs, newest first."""
    if not 1<=max_archives<=2000:raise ValueError('Invalid archive limit')
    root=Path(folder).expanduser()
    if not root.is_dir():raise ValueError('Download directory does not exist')
    mods=items(game)
    paths=[]
    for entry in root.iterdir():
        try:
            if entry.is_file() and entry.suffix.casefold()=='.zip':
                paths.append((entry.stat().st_mtime,entry))
        except OSError:continue
    paths.sort(reverse=True,key=lambda pair:pair[0])
    return [match_downloaded_smapi_archive(game,p,installed=mods) for _,p in paths[:max_archives]]

def apply_downloaded_smapi_update(game, match, backup_base=None):
    """Recheck ZIP and installation at execution; preserve old mod in recovery."""
    if match.get('status') not in ('Ready to update','Review version'):
        raise ValueError('Only ready or manually reviewed updates can be applied')
    archive=Path(match['archive'])
    now=match_downloaded_smapi_archive(game,archive)
    if (now['status'] not in ('Ready to update','Review version') or
            now['uid'].casefold()!=match['uid'].casefold() or
            now['target_path']!=match['target_path'] or
            now['version']!=match['version'] or
            (match.get('sha256') and now.get('sha256')!=match['sha256'])):
        raise ValueError('Archive or installed mod changed since scan; rescan before updating')
    installed=[m for m in items(game) if m['path']==now['target_path']]
    if len(installed)!=1:raise ValueError('The installed mod is no longer uniquely identified')
    return replace_smapi_zip(game,installed[0],archive,backup_base=backup_base)

# Conservative BepInEx package matching. We NEVER identify updates by DLL filename alone.
# Requires a package manifest, a declared owner or exact HTTPS source, and DLLs in an
# exclusively owned package folder. Existing hand-installed loose DLLs remain untouched.
def _package_metadata(obj):
    if not isinstance(obj,dict):return None
    name=str(obj.get('name') or '').strip()
    version=str(obj.get('version_number') or obj.get('version') or '').strip()
    owner=str(obj.get('namespace') or obj.get('author') or '').strip()
    page=str(obj.get('website_url') or '').strip()
    if not name or not version:return None
    # Arbitrary or malicious URLs must not become trusted identification tokens.
    if page:
        from urllib.parse import urlsplit, urlunsplit
        parsed=urlsplit(page)
        if parsed.scheme.lower()!='https' or not parsed.hostname or parsed.username or parsed.password:
            page=''
        else:
            page=urlunsplit(('https',parsed.netloc.lower(),parsed.path.rstrip('/'),'',''))
    # Avoid an unscoped, common package name matching another author's mod.
    if not owner and not page:return None
    return {'name':name,'version':version,'owner':owner,'website_url':page,
            'identity':('owner:'+owner.casefold()+':'+name.casefold()) if owner else
                       ('site:'+page.casefold()+':'+name.casefold())}

def _package_matches(a,b):
    if a['name'].casefold()!=b['name'].casefold():return False
    if a['owner'] and b['owner'] and a['owner'].casefold()!=b['owner'].casefold():return False
    if a['website_url'] and b['website_url'] and a['website_url'].casefold()!=b['website_url'].casefold():return False
    return bool((a['owner'] and b['owner'] and a['owner'].casefold()==b['owner'].casefold()) or
                (a['website_url'] and b['website_url'] and a['website_url'].casefold()==b['website_url'].casefold()))

def _read_package_manifest(path):
    try:
        raw=path.read_bytes()
        if len(raw)>1024*1024: return None
        return _package_metadata(json.loads(raw.decode('utf-8-sig')))
    except (OSError,ValueError,UnicodeError):return None

def discover_bepinex_packages(game):
    '''Identify package-owned directories, including disabled ones, without following symlinks.'''
    found=[]
    for enabled,base in ((True,mod_root(game)),(False,disabled_root(game))):
        if not base.is_dir():continue
        for dirname,dirs,files in os.walk(base,followlinks=False):
            folder=Path(dirname)
            dirs[:]=[d for d in dirs if not (folder/d).is_symlink() and not d.startswith('.')]
            if 'manifest.json' not in files or (folder/'manifest.json').is_symlink():continue
            info=_read_package_manifest(folder/'manifest.json')
            if not info or folder==base:continue
            # A package must actually contain a plugin. No package is inferred from
            # a framework manifest, and a metadata file alone is never executable.
            dlls=[x for x in folder.rglob('*') if x.is_file() and x.suffix.casefold()=='.dll' and not x.is_symlink()]
            if not dlls:continue
            found.append({**info,'folder':str(folder),'enabled':enabled,'dll_count':len(dlls)})
    return found

def _check_update_zip(archive):
    '''Validate ZIP members without touching the game, including duplicate names.'''
    path=Path(archive)
    if not path.is_file() or path.stat().st_size>512*1024*1024:
        raise ValueError('ZIP missing or larger than 512 MiB')
    manifest_entries=[]; dll_entries=[]; seen=set()
    with zipfile.ZipFile(path) as z:
        entries=z.infolist()
        if len(entries)>10000 or sum(e.file_size for e in entries)>2*1024**3:
            raise ValueError('ZIP has too many entries or exceeds 2 GiB unpacked')
        for e in entries:
            n=e.filename.replace('\\','/')
            components=n.rstrip('/').split('/')
            if (n.startswith('/') or re.match(r'^[A-Za-z]:',n) or '\x00' in n or
                any(part in ('..','.','') for part in components) or
                (e.external_attr>>16)&0o170000==0o120000):
                raise ValueError('Unsafe ZIP member name or symlink')
            key='/'.join(components).casefold()
            if key in seen:raise ValueError('Duplicate ZIP member names')
            seen.add(key)
            # Updating a plugin must never alter BepInEx framework/core files.
            lc=[x.casefold() for x in components]
            if any(lc[i:i+2] in (['bepinex','core'],['bepinex','patchers'],['bepinex','config']) for i in range(len(lc)-1)):
                raise ValueError('ZIP bundles BepInEx framework/core/patcher/config files')
            if e.is_dir():continue
            if components[-1].casefold()=='manifest.json':
                if e.file_size>1024*1024:raise ValueError('Manifest larger than 1 MiB')
                with z.open(e) as f:
                    info=_package_metadata(json.loads(f.read(1024*1024+1).decode('utf-8-sig')))
                if info:manifest_entries.append({**info,'member':n})
            if components[-1].casefold().endswith('.dll'):dll_entries.append(n)
    return manifest_entries,dll_entries

def inspect_bepinex_archive(archive):
    '''Return package info for a single mod ZIP; no DLL-name-only matching.'''
    manifests,dlls=_check_update_zip(archive)
    if not manifests:return {'status':'No package metadata','note':'A manifest.json with name, version and owner or HTTPS website_url is required'}
    if len(manifests)!=1:return {'status':'Multi-package ZIP','note':f'{len(manifests)} package manifests found; update manually'}
    info=manifests[0]
    folder=Path(info['member']).parent
    if not dlls:return {'status':'No plugin DLL','note':'This package does not contain a plugin DLL'}
    if any(folder != Path(dll).parent and folder not in Path(dll).parents for dll in dlls):
        return {'status':'Ambiguous ZIP layout','note':'DLL files exist outside the metadata-owned package directory'}
    return {**info,'status':'Identified','note':f'{len(dlls)} packaged DLL file(s)'}

def match_downloaded_bepinex_archive(game,archive,installed=None):
    record={'archive':str(Path(archive)),'status':'Unknown','uid':'','name':'','version':'',
            'installed':'','local_version':'','target_path':'','note':'','sha256':''}
    if game.get('kind')!='bepinex':
        record.update(status='Unsupported game',note='BepInEx ZIP matching requires a BepInEx game');return record
    try:
        info=inspect_bepinex_archive(archive)
        if info['status']!='Identified':
            record.update(status=info['status'],note=info['note']);return record
        digest=hashlib.sha256()
        with Path(archive).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                digest.update(chunk)
        record['sha256']=digest.hexdigest()
    except (OSError,ValueError,UnicodeError,zipfile.BadZipFile,RuntimeError,EOFError) as exc:
        record.update(status='Invalid / unsafe ZIP',note=str(exc)[:240]);return record
    record.update(uid=info['identity'],name=info['name'],version=info['version'])
    installed=discover_bepinex_packages(game) if installed is None else installed
    hits=[m for m in installed if _package_matches(m,info)]
    if not hits:
        record.update(status='No installed match',note='No matching metadata-owned BepInEx package folder');return record
    if len(hits)>1:
        record.update(status='Duplicate installed ID',note=f'{len(hits)} matching package folders; resolve manually');return record
    local=hits[0]
    record.update(installed=local['name'],local_version=local['version'],target_path=local['folder'])
    cmp=compare_versions(local['version'],info['version'])
    status={'Current':'Already current','Local newer':'Archive older','Unknown':'Review version'}.get(cmp,'Ready to update')
    record.update(status=status,note=info['note']+'; identity is metadata only, NOT proof of authenticity')
    return record

def scan_update_inbox(game,folder,max_archives=200):
    '''Read-only cross-game ZIP inbox; legacy SMAPI scanner remains available.'''
    if game.get('kind')=='smapi':return scan_download_inbox(game,folder,max_archives)
    if game.get('kind')!='bepinex':raise ValueError('Update Inbox supports SMAPI and BepInEx only')
    if not 1<=max_archives<=2000:raise ValueError('Invalid ZIP limit')
    root=Path(folder).expanduser()
    if not root.is_dir():raise ValueError('Download directory does not exist')
    installed=discover_bepinex_packages(game)
    paths=[]
    for p in root.iterdir():
        try:
            if p.is_file() and p.suffix.casefold()=='.zip':paths.append((p.stat().st_mtime,p))
        except OSError:pass
    paths.sort(reverse=True,key=lambda x:x[0])
    return [match_downloaded_bepinex_archive(game,p,installed) for _,p in paths[:max_archives]]

def _normalize_bepinex_stage(candidate, temp_root):
    '''Convert common Thunderstore layout to a managed BepInEx package folder.'''
    nested_plugin_dir=candidate/'BepInEx'/'plugins'
    if not nested_plugin_dir.is_dir():return candidate
    dlls=[x for x in candidate.rglob('*') if x.is_file() and x.suffix.casefold()=='.dll']
    if any(not x.is_relative_to(nested_plugin_dir) for x in dlls):
        raise ValueError('Mixed BepInEx plugin layout; install manually')
    normalized=Path(temp_root)/'normalized'
    normalized.mkdir()
    for f in candidate.iterdir():
        if f.name=='BepInEx':continue
        dest=normalized/f.name
        if f.is_dir():shutil.copytree(f,dest)
        else:shutil.copy2(f,dest)
    for f in nested_plugin_dir.iterdir():
        dest=normalized/f.name
        if dest.exists():raise ValueError('Plugin collision while normalizing archive')
        if f.is_dir():shutil.copytree(f,dest)
        else:shutil.copy2(f,dest)
    return normalized

def replace_bepinex_zip(game,selected,archive,backup_base=None):
    '''Replace an owned plugin directory, backing up before writing; never overwrite a loose DLL.'''
    if game.get('kind')!='bepinex':raise ValueError('BepInEx game required')
    src=Path(selected['folder'])
    if src.is_symlink() or not src.is_dir():raise ValueError('Package directory is missing or symlinked')
    base=mod_root(game) if selected['enabled'] else disabled_root(game)
    realbase=base.resolve();realsrc=src.resolve()
    if not realsrc.is_relative_to(realbase) or realsrc==realbase:
        raise ValueError('Package directory is outside managed plugins')
    # Reject directories containing other metadata-owned mods, even if their DLLs
    # happen to share a parent with the selected package.
    if any(p.parent!=src for p in src.rglob('manifest.json') if _read_package_manifest(p)):
        raise ValueError('Package contains nested packages; manual update required')
    # Also verify direct callers; preview checks must not be bypassed.
    inspected=inspect_bepinex_archive(archive)
    if inspected['status']!='Identified' or not _package_matches(selected,inspected):
        raise ValueError('Ambiguous ZIP or package identity changed')
    with tempfile.TemporaryDirectory(prefix='unimod-bep-update-') as td:
        stage=Path(td)/'raw'
        stage.mkdir()
        with zipfile.ZipFile(archive) as z:safe_extract(z,stage)
        manifests=[p for p in stage.rglob('manifest.json') if _read_package_manifest(p)]
        if len(manifests)!=1:raise ValueError('ZIP does not contain exactly one identifiable package')
        incoming=_read_package_manifest(manifests[0])
        if not _package_matches(selected,incoming):raise ValueError('Package identity changed; refusing update')
        candidate=manifests[0].parent
        if not any(x.is_file() and x.suffix.casefold()=='.dll' for x in candidate.rglob('*')):
            raise ValueError('New package has no DLL files')
        candidate=_normalize_bepinex_stage(candidate,td)
        backup_root=Path(backup_base) if backup_base else APP/'backups'
        backup_root.mkdir(parents=True,exist_ok=True)
        backup=backup_root/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-bep-'+re.sub(r'[^A-Za-z0-9_.-]','_',src.name))
        if backup.exists():raise ValueError('Backup already exists')
        metadata={'game_root':str(Path(game['root']).resolve()),'kind':'bepinex',
                  'mod_uid':selected['identity'],'original_path':str(src),
                  'backup_path':str(backup),'saved_at':datetime.datetime.now().isoformat()}
        receipt=backup.with_name(backup.name+'.unimod.json')
        # Write the recovery receipt before touching live files. After a crash
        # immediately following the move, the GUI can still locate the backup.
        receipt.write_text(json.dumps(metadata,indent=2))
        try:
            shutil.move(str(src),str(backup))
            try:shutil.copytree(candidate,src)
            except Exception:
                if src.exists():shutil.rmtree(src)
                shutil.move(str(backup),str(src))
                raise
        except Exception:
            receipt.unlink(missing_ok=True)
            raise
        return backup

def apply_downloaded_bepinex_update(game,match,backup_base=None):
    if match.get('status') not in ('Ready to update','Review version'):
        raise ValueError('Update is not ready; no files changed')
    now=match_downloaded_bepinex_archive(game,match['archive'])
    if (now['status'] not in ('Ready to update','Review version') or
        any(now[key]!=match[key] for key in ('uid','version','target_path','sha256'))):
        raise ValueError('Archive or package changed since scan; rescan before updating')
    candidates=[x for x in discover_bepinex_packages(game) if x['folder']==now['target_path']]
    if len(candidates)!=1:raise ValueError('Package path is no longer uniquely identified')
    return replace_bepinex_zip(game,candidates[0],match['archive'],backup_base)

def apply_downloaded_update(game,match,backup_base=None):
    if game.get('kind')=='smapi':return apply_downloaded_smapi_update(game,match,backup_base)
    if game.get('kind')=='bepinex':return apply_downloaded_bepinex_update(game,match,backup_base)
    raise ValueError('Unsupported update layout')

# v0.52: one read-only preflight for provider-staged archives.  A provider
# receipt proves which verified bytes UniMod fetched, NOT game compatibility.
PROVIDER_STAGE_FILE = APP / 'provider-stage-receipts.json'

def provider_install_preflight(game, receipt):
    """Review a staged ZIP without touching the game. Fail closed for ambiguity."""
    if not game or game.get('kind') not in ('smapi','bepinex'):
        return {'status':'Unsupported game','detail':'Only SMAPI and BepInEx ZIP installation is supported.'}
    if receipt.get('provider')=='Modrinth':
        return {'status':'Unsupported game','detail':'Modrinth Minecraft archives require a Minecraft loader-specific installer. Download only.'}
    try:
        archive=provider_staging.inspect_receipt(receipt,game_root=game['root'])
    except (provider_staging.StageError,OSError,ValueError) as exc:
        return {'status':'Blocked','detail':str(exc)}
    dependencies=receipt.get('dependencies') or []
    if dependencies and not isinstance(dependencies,list):
        return {'status':'Blocked','detail':'Invalid recorded dependency data.'}
    needed,conflicts,unknown=provider_staging.dependency_summary(receipt)
    if conflicts:
        return {'status':'Blocked','detail':'Provider marks incompatible packages: '+', '.join(conflicts[:8])}
    if unknown:
        return {'status':'Blocked','detail':'Unrecognised provider dependencies: '+', '.join(unknown[:8])}
    if needed:
        # Provider-specific exact identities cannot be inferred from display names.
        # Modrinth Minecraft dependencies are not deployable by this installer.
        if receipt.get('provider')!='Thunderstore':
            return {'status':'Blocked','detail':'Required provider dependencies need a supported game-specific resolver: '+', '.join(needed[:8])}
        game_id=str(Path(game['root']).resolve())
        receipts=[r for r in read_receipts() if r.get('game')==game_id]
        installed=installed_thunderstore_packages(game)
        for dep in needed:
            full,sep,version=dep.rpartition('-')
            if not sep or not full or not version:
                return {'status':'Blocked','detail':'Invalid Thunderstore dependency: '+dep[:100]}
            saved=any(r.get('package','').casefold()==full.casefold() and str(r.get('version'))==version for r in receipts)
            local=installed.get(full.casefold())
            if not saved and not (local and str(local.get('version'))==version):
                return {'status':'Blocked','detail':'Required Thunderstore package is not confirmed installed: '+dep[:100]}
    try:
        if game['kind']=='smapi':
            with zipfile.ZipFile(archive) as z:
                mod_infos=inspect_smapi_archive(archive)
                if not mod_infos:
                    return {'status':'Unsupported archive','detail':'ZIP contains no SMAPI UniqueID manifests.'}
                keys=[x['uid'].casefold() for x in mod_infos]
                if len(keys)!=len(set(keys)):
                    return {'status':'Blocked','detail':'ZIP contains duplicate SMAPI UniqueIDs.'}
                current={m.get('uid','').casefold():m for m in items(game) if m.get('uid')}
                existing=[x for x in keys if x in current]
                if existing and len(mod_infos)!=1:
                    return {'status':'Blocked','detail':'Mixed multi-component update; use Update Inbox or separate packages.'}
                missing=[]
                for info in mod_infos:
                    raw=z.read(info['member'])
                    if len(raw)>1024*1024:raise ValueError('Manifest exceeds 1 MiB.')
                    try:manifest=json.loads(raw.decode('utf-8-sig'))
                    except ValueError:
                        import json5
                        manifest=json5.loads(raw.decode('utf-8-sig'),allow_duplicate_keys=False)
                    if not isinstance(manifest,dict):raise ValueError('Invalid SMAPI manifest.')
                    req=_manifest_field(manifest,'Dependencies',[])
                    if isinstance(req,list):
                        for dep in req:
                            if not isinstance(dep,dict) or not _manifest_field(dep,'IsRequired',True):continue
                            uid=str(_manifest_field(dep,'UniqueID','') or '').strip()
                            if uid and uid.casefold() not in current and uid.casefold() not in keys and uid.casefold() not in ('pathoschild.smapi','concernedape.stardewvalley'):
                                missing.append(uid)
                            elif uid.casefold() in current:
                                found=current[uid.casefold()]
                                minimum=str(_manifest_field(dep,'MinimumVersion','') or '').strip()
                                if not found.get('enabled'):
                                    missing.append(uid+' (disabled)')
                                elif minimum and compare_versions(str(found.get('version','')),minimum) not in ('Current','Local newer'):
                                    missing.append(uid+' (minimum version '+minimum+' not verified)')
                    content=_manifest_field(manifest,'ContentPackFor')
                    if isinstance(content,dict):
                        uid=str(_manifest_field(content,'UniqueID','') or '').strip()
                        if uid and uid.casefold() not in current and uid.casefold() not in keys:
                            missing.append(uid)
                if missing:return {'status':'Blocked','detail':'Required SMAPI mods not installed: '+', '.join(sorted(set(missing))[:12])}
                if existing:
                    match=match_downloaded_smapi_archive(game,archive)
                    if match['status'] not in ('Ready to update','Review version'):
                        return {'status':'Blocked','detail':match['status']+': '+match['note']}
                    return {'status':'Update existing','detail':f"{match['installed']} ({match['local_version']}) → {match['version']} (backup kept)", 'match':match}
                return {'status':'Install new','detail':f"{len(mod_infos)} new SMAPI component(s); no installed UniqueID conflicts."}
        inspected=inspect_bepinex_archive(archive)
        if inspected['status']!='Identified':
            return {'status':'Unsupported archive','detail':inspected['status']+': '+inspected['note']}
        existing=[m for m in discover_bepinex_packages(game) if _package_matches(m,inspected)]
        if len(existing)>1:return {'status':'Blocked','detail':'Multiple existing packages share this identity.'}
        if existing:
            match=match_downloaded_bepinex_archive(game,archive)
            if match['status'] not in ('Ready to update','Review version'):
                return {'status':'Blocked','detail':match['status']+': '+match['note']}
            return {'status':'Update existing','detail':f"{match['installed']} ({match['local_version']}) → {match['version']} (backup kept)", 'match':match}
        return {'status':'Install new','detail':'New metadata-owned BepInEx package (no existing identity conflict).'}
    except (OSError,UnicodeError,ValueError,TypeError,zipfile.BadZipFile,RuntimeError,EOFError) as exc:
        return {'status':'Blocked','detail':'Unsafe or invalid package: '+str(exc)[:180]}


def provider_install_reviewed(game,receipt,*,receipt_path=None):
    """Recheck bytes/dependencies on action; install only when explicitly approved in UI."""
    plan=provider_install_preflight(game,receipt)
    if plan['status'] not in ('Install new','Update existing'):
        raise ValueError(plan['detail'])
    archive=provider_staging.inspect_receipt(receipt,game_root=game['root'])
    if plan['status']=='Update existing':
        backup=apply_downloaded_update(game,plan['match'])
        # An update has committed at this point. A failed history write
        # must not cause a dangerous retry or hide a successful update.
        target=str(Path(plan['match']['target_path']).resolve())
        history_warning=False
        try:
            details=modio_managed.provenance(game,[target],receipt)
            if details:
                record={'game':str(Path(game['root']).resolve()),
                        'package':'mod.io:'+str(receipt['identity']),
                        'version':str(receipt.get('version') or '')[:80],
                        'source':'', 'dependencies':receipt.get('dependencies',[]),
                        'paths':[target], 'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        **details}
                history=read_receipts();history.append(record);write_receipts(history)
        except (OSError,ValueError,TypeError):
            history_warning=True
        return {'action':'updated','backup':str(backup),'paths':[],
                'history_warning':history_warning}
    base=mod_root(game).resolve();before={p.name for p in base.iterdir()} if base.exists() else set()
    try:
        names=install_zip(game,archive)
        paths=[str(base/name) for name in names]
        record={'game':str(Path(game['root']).resolve()),'package':receipt.get('provider','')+':'+receipt.get('identity',''),
                'version':receipt.get('version',''),'source':'', 'dependencies':receipt.get('dependencies',[]),
                'paths':paths,'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        record.update(modio_managed.provenance(game,paths,receipt))
        all_receipts=read_receipts();all_receipts.append(record);write_receipts(all_receipts)
        return {'action':'installed','backup':'','paths':paths}
    except Exception:
        # New managed directories go to recovery rather than being deleted; pre-existing
        # directories are never moved. This includes receipt-write failures.
        recovery=APP/'recovery'/'provider-installs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        if base.exists():
            for path in base.iterdir():
                if path.name not in before and not path.is_symlink():
                    recovery.mkdir(parents=True,exist_ok=True)
                    shutil.move(str(path),str(unique(recovery/path.name)))
        raise

def source_url(mod):
    """Return a verified-shaped public landing-page URL, never an invented download URL."""
    repo=github_repo(mod)
    if repo:return f'https://github.com/{repo}/releases'
    for key in mod.get('update_keys',[]):
        kind,sep,value=key.partition(':')
        if not sep:continue
        value=value.strip()
        if kind.lower()=='nexus' and re.fullmatch(r'\d+',value):
            return f'https://www.nexusmods.com/stardewvalley/mods/{value}'
        if kind.lower()=='modrinth' and re.fullmatch(r'[A-Za-z0-9_-]+',value):
            return f'https://modrinth.com/mod/{value}'
    uid=mod.get('uid','')
    if isinstance(uid,str) and uid.startswith('https://'):
        from urllib.parse import urlparse
        parsed=urlparse(uid)
        if parsed.hostname in ('thunderstore.io','www.nexusmods.com','github.com','modrinth.com','www.curseforge.com'):
            return uid
    return None

def replace_smapi_zip(game, selected, archive, backup_base=None):
    """Replace one selected SMAPI mod only if archive matches its UniqueID.

    A backup is retained outside the Mods folder. Restore original on an installation failure.
    """
    if game['kind']!='smapi':raise ValueError('Safe replacement currently supports SMAPI only')
    if not selected.get('uid'):raise ValueError('Selected mod has no UniqueID')
    if Path(selected['path']).is_symlink():raise ValueError('Refusing symlinked mod folder')
    base=Path(selected['root_dir']).resolve();src=Path(selected['path']).resolve()
    if not src.is_dir() or not src.is_relative_to(base) or src==base:
        raise ValueError('Invalid selected mod path')
    # Don't replace a grouped parent folder containing other mods.
    for p in src.rglob('manifest.json'):
        if p.parent!=src and smapi_manifest(p.parent):
            raise ValueError('Selected mod contains nested mods: update this collection manually')
    with tempfile.TemporaryDirectory(prefix='unimod-update-') as td:
        stage=Path(td)
        with zipfile.ZipFile(archive) as z:safe_extract(z,stage)
        matches=[]
        for manifest in stage.rglob('manifest.json'):
            info=smapi_manifest(manifest.parent)
            if info and info['uid'].casefold()==selected['uid'].casefold():matches.append(manifest.parent)
        if len(matches)!=1:raise ValueError(f'Expected exactly one mod matching {selected["uid"]}; found {len(matches)}')
        candidate=matches[0]
        if any(smapi_manifest(x.parent) for x in candidate.rglob('manifest.json') if x.parent!=candidate):
            raise ValueError('Archive contains nested mods; use normal import instead')
        backup_base=Path(backup_base) if backup_base else APP/'backups'
        backup_base.mkdir(parents=True,exist_ok=True)
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup=backup_base/(stamp+'-'+re.sub(r'[^A-Za-z0-9_.-]','_',src.name))
        if backup.exists():raise ValueError('Backup path already exists')
        shutil.move(str(src),str(backup))
        try:shutil.copytree(candidate,src)
        except Exception:
            if src.exists():shutil.rmtree(src)
            shutil.move(str(backup),str(src))
            raise
        meta={'game_root':str(Path(game['root']).resolve()),'mod_uid':selected['uid'], 'original_path':str(src),'backup_path':str(backup),'saved_at':datetime.datetime.now().isoformat()}
        try:backup.with_name(backup.name+'.unimod.json').write_text(json.dumps(meta,indent=2))
        except OSError: pass # backup itself is still retained
        return backup

def backups_for_game(game):
    result=[]
    root=str(Path(game['root']).resolve())
    for metadata in sorted((APP/'backups').glob('*.unimod.json'),reverse=True) if (APP/'backups').is_dir() else []:
        try:
            entry=json.loads(metadata.read_text())
            if entry.get('game_root')!=root:continue
            backup=Path(entry['backup_path'])
            if not backup.is_dir() or not backup.parent.resolve()==(APP/'backups').resolve():continue
            if entry.get('kind','smapi')!=game.get('kind'):continue
            if not backup.with_name(backup.name+'.unimod.json')==metadata:continue
            result.append(entry)
        except (OSError,ValueError,KeyError,TypeError):continue
    return result

def restore_backup(game,entry):
    if game['kind'] not in ('smapi','bepinex'):raise ValueError('Unsupported backup format')
    if entry.get('kind','smapi')!=game['kind']:raise ValueError('Backup type does not match selected game')
    if entry.get('game_root')!=str(Path(game['root']).resolve()):raise ValueError('Backup belongs to a different game')
    backup=Path(entry['backup_path']).resolve();original=Path(entry['original_path']).resolve()
    backup_root=(APP/'backups').resolve()
    allowed_roots=[mod_root(game).resolve(),disabled_root(game).resolve()]
    if backup.parent!=backup_root or not any(original.is_relative_to(r) and original!=r for r in allowed_roots):raise ValueError('Backup path check failed')
    if not backup.is_dir() or not (backup/'manifest.json').is_file():raise ValueError('Backup is missing or invalid')
    if game['kind']=='smapi':
        info=smapi_manifest(backup)
        if not info or info['uid'].casefold()!=str(entry.get('mod_uid','')).casefold():raise ValueError('Backup identity does not match')
    else:
        info=_read_package_manifest(backup/'manifest.json')
        if not info or info['identity']!=entry.get('mod_uid'):
            raise ValueError('BepInEx backup identity does not match')
    original.parent.mkdir(parents=True,exist_ok=True)
    # Preserve current version rather than destructively overwriting it.
    previous=None
    if original.exists():
        if original.is_symlink() or not original.is_dir():raise ValueError('Current mod path is not a safe folder')
        previous=unique(backup_root/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-pre-restore-'+original.name))
        shutil.move(str(original),str(previous))
    try:shutil.move(str(backup),str(original))
    except Exception:
        if previous and previous.exists():shutil.move(str(previous),str(original))
        raise
    metadata=backup_root/(backup.name+'.unimod.json')
    if metadata.exists():metadata.unlink()
    return previous

def download(url,target):
    if not url.startswith('https://'):raise ValueError('Only HTTPS direct download URLs are supported')
    req=urllib.request.Request(url,headers={'User-Agent':'UniMod/0.54'})
    with urllib.request.urlopen(req,timeout=45) as response:
        if response.status!=200:raise ValueError(f'HTTP {response.status}')
        content=0
        with open(target,'wb') as out:
            while True:
                part=response.read(1024*1024)
                if not part:break
                content+=len(part)
                if content>512*1024*1024:raise ValueError('Download exceeded 512 MiB')
                out.write(part)
    if not zipfile.is_zipfile(target):raise ValueError('Downloaded file is not a ZIP archive')



def steam_game_context(game, library_roots=None):
    """Resolve a selected install to an exact Steam appmanifest and available Proton prefix.

    This is informational only. An app ID is never guessed from a game title.
    """
    path=Path(game['root'])
    result={'appid':'', 'steamapps':'', 'proton_prefix':'', 'prefix_exists':False,
            'steam_detected':False, 'prefix_location':'', 'compatdata_found_elsewhere':False}
    root=path.resolve(strict=False)
    candidates=[]
    if path.parent.name=='common' and path.parent.parent.name=='steamapps':
        candidates.append(path.parent.parent)
    if game.get('steamapps'):
        candidates.append(Path(game['steamapps']))
    roots=steam_roots() if library_roots is None else library_roots
    candidates.extend(Path(p) for p in roots)
    seen=set()
    for apps in candidates:
        if str(apps) in seen:continue
        seen.add(str(apps))
        if not (apps/'common').is_dir():continue
        # Exact install-path comparison; no network or generated identifier.
        for entry in steam_appmanifest_games(apps):
            if Path(entry['root']).resolve(strict=False)==root:
                result['appid']=entry['appid']
                result['steamapps']=str(apps)
                result['steam_detected']=True
                break
        if result['steam_detected']:break
    # Vanilla games will not appear in steam_appmanifest_games. Read only bounded
    # appmanifests and match an exact, safe installation directory.
    if not result['steam_detected']:
        for apps in candidates:
            if not (apps/'common').is_dir():continue
            try: entries=sorted(apps.glob('appmanifest_*.acf'))[:5000]
            except OSError:continue
            for entry in entries:
                try:
                    if entry.is_symlink() or not entry.stem.removeprefix('appmanifest_').isdigit() or entry.stat().st_size>256*1024:continue
                    raw=entry.read_text(encoding='utf-8-sig',errors='replace')
                    match=re.search(r'"installdir"\s+"([^"\\]*)"',raw,re.I)
                    if not match or not match.group(1) or '/' in match.group(1) or '\\' in match.group(1) or match.group(1) in ('.','..'):continue
                    dest=apps/'common'/match.group(1)
                    if dest.is_symlink() or dest.resolve(strict=False)!=root:continue
                    result.update({'appid':entry.stem.removeprefix('appmanifest_'),'steamapps':str(apps),'steam_detected':True})
                    break
                except (OSError,UnicodeError):continue
            if result['steam_detected']:break
    if result['appid']:
        # The game's own library is preferred. Some configurations store
        # compatdata on another Steam library; report it rather than assuming.
        prefix_roots=[Path(result['steamapps'])]+[Path(x) for x in roots if str(x)!=result['steamapps']]
        for apps in prefix_roots:
            prefix=apps/'compatdata'/result['appid']/'pfx'
            if prefix.is_dir() and not prefix.is_symlink():
                result['proton_prefix']=str(prefix)
                result['prefix_exists']=True
                result['prefix_location']=str(apps)
                result['compatdata_found_elsewhere']=str(apps)!=result['steamapps']
                break
    return result


def game_diagnostics(game, library_roots=None):
    """Read-only diagnostics with advisory statuses, not authoritative game-health claims."""
    context=steam_game_context(game, library_roots)
    root=Path(game['root'])
    kind=game['kind']
    checks=[]
    def record(item,status,details):checks.append({'check':item,'status':status,'details':str(details)})
    record('Game installation','OK' if root.is_dir() else 'Missing',root)
    if not root.is_dir():
        return {'schema':1,'game':game.get('name',''),'kind':kind,'game_root':str(root),
                'steam':context,'checks':checks}
    record('Framework', 'Info',kind.upper())
    record('Detected launcher','Info', (game.get('launcher') or 'Steam / manual')+ (' · '+game.get('store') if game.get('store') else ''))
    moddir=mod_root(game)
    record('Mod directory','OK' if moddir.is_dir() else 'Missing',moddir)
    if moddir.is_dir():
        scanned=items(game)
        record('Existing mod entries','Info',f'{len(scanned)} discovered, {sum(bool(m["enabled"]) for m in scanned)} enabled')
        record('Grouped packages','Info',len(mod_packages(game,scanned)))
        if kind=='smapi':
            problems=audit_mods(scanned,kind)
            record('SMAPI installation audit','Warning' if problems else 'OK',f'{len(problems)} potential issue(s)')
    if kind=='smapi':
        executables=[root/'StardewModdingAPI',root/'StardewModdingAPI.exe']
        installed=[p for p in executables if p.is_file() and not p.is_symlink()]
        record('SMAPI loader','OK' if installed else 'Warning', installed[0] if installed else 'Could not identify a SMAPI executable at game root')
    elif kind=='bepinex':
        core=root/'BepInEx'/'core'
        dlls=[core/'BepInEx.dll',core/'BepInEx.Core.dll']
        record('BepInEx core','OK' if any(p.is_file() for p in dlls) else 'Warning',core)
        # Some games use a different injector. This is an advisory, not a failure.
        record('Windows proxy loader','OK' if (root/'winhttp.dll').is_file() else 'Info', 'winhttp.dll present' if (root/'winhttp.dll').is_file() else 'winhttp.dll not found; other loaders may be used')
        log=root/'BepInEx'/'LogOutput.log'
        record('BepInEx launch log','OK' if log.is_file() else 'Info',log if log.is_file() else 'No launch log found; not proof of failed injection')
    elif kind=='melonloader':
        record('MelonLoader management','Info','Discovery-only. UniMod does not deploy MelonLoader mods.')
    record('Steam app ID','OK' if context['appid'] else 'Info',context['appid'] or 'No matching Steam appmanifest found')
    if context['appid']:
        record('Proton prefix','OK' if context['prefix_exists'] else 'Info',context['proton_prefix'] if context['prefix_exists'] else 'Not found; game may be native or has not been launched through Proton')
        if context['compatdata_found_elsewhere']:
            record('Compatdata location','Info','Located in a different Steam library: '+context['prefix_location'])
    return {'schema':1,'game':game.get('name',''),'kind':kind,'game_root':str(root),
            'steam':context,'checks':checks}


def export_diagnostics(path,report):
    """Write a report on user request; no tokens, auth headers or game file data."""
    path=Path(path)
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return path

def apply_bepinex_archive_candidates(game,preview,indices):
    """Explicit-review, all-or-nothing source assignment; no game-file writes."""
    domain=bepinex_nexus_evidence.SUPPORTED_GAMES.get(game.get('name'))
    if game.get('kind')!='bepinex' or not domain:
        raise ValueError('Wrong game for Nexus archive matching.')
    indices=list(indices)
    if not indices or len(set(indices))!=len(indices) or any(type(i) is not int or i<0 or i>=len(preview) for i in indices):
        raise ValueError('Invalid candidate selection.')
    planned={}
    for i in indices:
        row=preview[i]
        if row.get('status')!='Review candidate':raise ValueError('Only reviewable candidates can be saved.')
        mod=row['mod']; candidate=row.get('candidate') or {}
        ref=parse_nexus_link(candidate.get('url'))
        if not ref or ref['game_domain']!=domain:raise ValueError('Nexus page belongs to the wrong game.')
        from bepinex_nexus_evidence import _safe_installed_path, file_digest
        local=_safe_installed_path(game,mod)
        if not local or file_digest(local)!=row.get('fingerprint'):
            raise ValueError('Installed DLL changed since the scan. Rescan before saving.')
        if reconcile_source(game,mod).get('url'):
            raise ValueError('Mod already has a source link. Rescan before saving.')
        ident=source_identity(game,mod)
        if ident!=row.get('identity') or ident in planned:
            raise ValueError('Ambiguous or changed installed mod identity.')
        planned[ident]=ref['url']
    override=load_source_overrides()
    if any(i in override for i in planned):
        raise ValueError('Source assignments changed since the scan.')
    if SOURCE_OVERRIDES.is_symlink():raise ValueError('Source assignment path is a symlink.')
    SOURCE_OVERRIDES.parent.mkdir(parents=True,exist_ok=True)
    tmp=SOURCE_OVERRIDES.with_suffix('.tmp')
    if tmp.is_symlink():raise ValueError('Source temporary file is a symlink.')
    override.update(planned)
    tmp.write_text(json.dumps(override,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(SOURCE_OVERRIDES)
    return len(planned)


class App(tk.Tk):
    def __init__(self, incoming_nxm=None, bridge=None):
        super().__init__()
        self.instance_bridge=bridge
        self.source_candidate_target=None
        self._queue_events=queue.Queue()
        self._provider_events=queue.Queue()
        self._stage_running=False
        self._nexus_batch_remaining=0
        self._nexus_cancel_event=None
        self.title('UniMod 0.55 test12 — Linux Mod Manager')
        self.geometry('1500x900'); self.minsize(1024,640)
        self.data=cfg_load(); self.selected=None; self.update_results={}; self.rows=[]; self.ts_results=[]; self.ts_filtered=[]; self.ts_loaded_community=None; self.ts_request_serial=0; self.nexus_results={}; self.nexus_running=False; self.nexus_oauth_tokens=None; self.nexus_checked=set(); self.inbox_results=[]; self.inbox_busy=False; self.family_rows={}; self.collapsed_families=set(); self.nexus_queue=NexusDownloadQueue(); self.unified_nexus={}; self.unified_github={}; self.unified_rows=[]; self.unified_running=False; self.unified_root=None; self._unified_events=queue.Queue(); self.unified_downloads=[]; self.unified_download_root=None; self.unified_download_busy=False; self.unified_install_busy=False
        style=ttk.Style(self)
        if 'clam' in style.theme_names(): style.theme_use('clam')
        style.configure('Title.TLabel',font=('Sans',21,'bold'))
        style.configure('Section.TLabel',font=('Sans',12,'bold'))
        style.configure('Accent.TButton',padding=(12,7))
        style.configure('Treeview',rowheight=27)
        style.configure('Treeview.Heading',font=('Sans',10,'bold'))
        self.configure(background='#151923')
        self.apply_theme('dark')
        self.bind('<Control-f>', lambda e:self.focus_filter())
        self.bind('<Control-r>', lambda e:self.refresh())
        self.bind('<F5>', lambda e:self.refresh())
        # Gale-inspired shell. Keep the same notebook/pages and backend
        # operations but put the mod list first, rather than a wide workspace tree.
        main=ttk.Frame(self,padding=0);main.pack(fill='both',expand=True)
        head=ttk.Frame(main,style='Header.TFrame',padding=(14,8));head.pack(fill='x')
        ttk.Label(head,text='◆',style='BrandIcon.TLabel').pack(side='left',padx=(0,7))
        ttk.Label(head,text='UniMod',style='Brand.TLabel').pack(side='left',padx=(0,18))
        ttk.Separator(head,orient='vertical').pack(side='left',fill='y',padx=(0,14))
        ttk.Label(head,text='GAME',style='TopMuted.TLabel').pack(side='left',padx=(0,7))
        self.game_combo_value=tk.StringVar()
        self.game_combo=ttk.Combobox(head,state='readonly',textvariable=self.game_combo_value,width=25,style='Top.TCombobox')
        self.game_combo.pack(side='left',padx=(0,14))
        self.game_combo.bind('<<ComboboxSelected>>',self.change_game_combo)
        self.game_list=tk.Listbox(main,exportselection=False) # legacy selection API, hidden
        self.profile_menu=ttk.Menubutton(head,text='Profile: Default  ▾',style='Top.TMenubutton')
        self.profile_menu.pack(side='left',padx=(0,10))
        pm=tk.Menu(self.profile_menu,tearoff=False)
        pm.add_command(label='Save current profile…',command=self.save_profile)
        pm.add_command(label='Load profile…',command=self.load_profile)
        pm.add_command(label='Restore backup…',command=self.restore_from_backup)
        self.profile_menu.configure(menu=pm)
        ttk.Button(head,text='+ Install ZIP',command=self.install_archive,style='Top.TButton').pack(side='left',padx=4)
        ttk.Button(head,text='↻ Rescan',command=self.refresh,style='Top.TButton').pack(side='left',padx=4)
        ttk.Button(head,text='Check updates',command=lambda:self.show_page('Updates Available'),style='Top.TButton').pack(side='left',padx=4)
        ttk.Button(head,text='Scan games',command=self.auto_detect,style='Top.TButton').pack(side='right',padx=4)
        ttk.Button(head,text='+ Add game',command=self.add_game,style='Top.TButton').pack(side='right',padx=4)
        self.tools_button=ttk.Menubutton(head,text='Tools  ▾',style='Top.TMenubutton')
        self.tools_button.pack(side='right',padx=10)
        body_shell=ttk.Frame(main);body_shell.pack(fill='both',expand=True)
        rail=ttk.Frame(body_shell,style='Rail.TFrame',padding=(6,12));rail.pack(side='left',fill='y')
        self.primary_workspaces=(
            ('Mods','Installed Mods'),('Updates','Updates Available'),('Library','All Games & Mods'),
            ('Discover','Mod Websites'),('Downloads','Update Inbox'),('Overview','Overview'),
        )
        # Buttons keep the icon navigation directly actionable. Tooltips give
        # accessible full page labels without a permanently wide sidebar.
        self.rail_buttons={}
        for glyph,title,page in [('▤','Mods','Installed Mods'),('↻','Updates','Updates Available'),('▦','Library','All Games & Mods'),
                                 ('⌕','Discover','Mod Websites'),('↓','Downloads','Update Inbox'),
                                 ('◫','Overview','Overview')]:
            button=ttk.Button(rail,text=glyph,width=3,style='Rail.TButton',
                              command=lambda name=page:self.show_page(name))
            button.pack(fill='x',pady=(0,8),ipady=5)
            self.rail_buttons[page]=button
            self.attach_tooltip(button,title)
        ttk.Separator(rail).pack(fill='x',pady=12)
        more=ttk.Button(rail,text='⚙',width=3,style='Rail.TButton',command=lambda:self.show_page('Profiles & Tools'))
        more.pack(fill='x',ipady=5);self.attach_tooltip(more,'Advanced tools')
        self.nav_list=tk.Listbox(main,exportselection=False) # legacy compatibility, hidden
        workspace=ttk.Frame(body_shell,style='TFrame');workspace.pack(side='left',fill='both',expand=True)
        self.tabs=ttk.Notebook(workspace,style='Sidebar.TNotebook');self.tabs.pack(fill='both',expand=True)
        self.tabs.bind('<<NotebookTabChanged>>',lambda e:self.sync_workspace())
        dashboard=ttk.Frame(self.tabs,padding=(24,20));self.tabs.add(dashboard,text='  Overview  ')
        overview_heading=ttk.Frame(dashboard);overview_heading.pack(fill='x',pady=(0,12))
        ttk.Label(overview_heading,text='Library overview',style='Title.TLabel').pack(anchor='w')
        self.overview_subtitle=tk.StringVar(value='Choose a game to inspect your mods.')
        ttk.Label(overview_heading,textvariable=self.overview_subtitle,style='Subtle.TLabel',wraplength=850).pack(anchor='w',pady=(4,0))
        # Focus the dashboard on three key numbers, not six giant metric cards.
        summary=ttk.Frame(dashboard);summary.pack(fill='x',pady=(0,8))
        for c in range(3):summary.columnconfigure(c,weight=1,uniform='metrics')
        self.stat_labels={}
        for idx,label in enumerate(('Mod folders','Enabled folders','Known sources')):
            panel=ttk.Frame(summary,style='Card.TFrame',padding=(18,12))
            panel.grid(row=0,column=idx,sticky='nsew',padx=(0,10))
            ttk.Label(panel,text=label.upper(),style='CardCaption.TLabel').pack(anchor='w')
            val=ttk.Label(panel,text='—',style='Metric.TLabel');val.pack(anchor='w',pady=(6,0))
            self.stat_labels[label]=val
        secondary=ttk.Frame(dashboard);secondary.pack(fill='x',pady=(4,15))
        for label in ('Indexed IDs','Metadata pending','Audit warnings'):
            cell=ttk.Frame(secondary);cell.pack(side='left',padx=(0,25))
            ttk.Label(cell,text=label+': ',style='Subtle.TLabel').pack(side='left')
            val=ttk.Label(cell,text='—',style='Subtle.TLabel');val.pack(side='left')
            self.stat_labels[label]=val
        dash_actions=ttk.Frame(dashboard);dash_actions.pack(fill='x',pady=(0,15))
        ttk.Button(dash_actions,text='Manage installed mods',command=lambda:self.tabs.select(1),
                   style='Accent.TButton').pack(side='left',padx=(0,8))
        ttk.Button(dash_actions,text='↻  Refresh inventory',command=self.refresh).pack(side='left')
        sub=ttk.Frame(dashboard);sub.pack(fill='x',pady=(0,8))
        ttk.Label(sub,text='Installed packages',style='Section.TLabel').pack(side='left')
        ttk.Label(sub,text='Read-only overview',style='Subtle.TLabel').pack(side='right')
        overview_area=ttk.Frame(dashboard);overview_area.pack(fill='both',expand=True)
        self.overview_tree=ttk.Treeview(overview_area,columns=('name','type','count','enabled'),show='headings',selectmode='browse')
        for name,title,width in [('name','Mod / package',300),('type','Type',160),('count','DLLs',65),('enabled','State',115)]:
            self.overview_tree.heading(name,text=title)
            self.overview_tree.column(name,width=width,stretch=(name=='name'))
        self.overview_tree.pack(side='left',fill='both',expand=True)
        overview_scroll=ttk.Scrollbar(overview_area,command=self.overview_tree.yview)
        overview_scroll.pack(side='right',fill='y');self.overview_tree.configure(yscrollcommand=overview_scroll.set)
        self.overview_tree.bind('<Double-1>',lambda _:self.tabs.select(1))
        installed=ttk.Frame(self.tabs,padding=9);sources=ttk.Frame(self.tabs,padding=12);tools=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(installed,text='  Installed Mods  ')
        # v0.26: consolidated read-only inventory across every registered game.
        self.global_tab=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(self.global_tab,text='  All Games & Mods  ')
        ttk.Label(self.global_tab,text='All installed mods — every registered game',style='Section.TLabel').pack(anchor='w',pady=(0,6))
        ttk.Label(self.global_tab,text='Existing SMAPI manifests and grouped BepInEx/MelonLoader packages. No files are changed. Source links require explicit metadata; similar names are never treated as matches.',wraplength=950).pack(anchor='w',pady=(0,8))
        global_actions=ttk.Frame(self.global_tab);global_actions.pack(fill='x',pady=(0,8))
        ttk.Button(global_actions,text='Scan all registered games',command=self.scan_global_library).pack(side='left')
        ttk.Button(global_actions,text='Export filtered CSV…',command=self.export_global_library_ui).pack(side='left',padx=8)
        ttk.Button(global_actions,text='Go to selected mod',command=self.open_global_mod).pack(side='left')
        filters=ttk.Frame(self.global_tab);filters.pack(fill='x',pady=(0,7))
        ttk.Label(filters,text='Search games and mods:').pack(side='left')
        self.global_query=tk.StringVar(value='')
        self.global_query.trace_add('write',lambda *_:self.fill_global_library())
        ttk.Entry(filters,textvariable=self.global_query).pack(side='left',fill='x',expand=True,padx=8)
        self.global_filter=tk.StringVar(value='All')
        global_combo=ttk.Combobox(filters,textvariable=self.global_filter,state='readonly',width=21,
             values=('All','Enabled','Disabled','Known source','Needs source','Unmanaged'))
        global_combo.pack(side='left')
        global_combo.bind('<<ComboboxSelected>>',lambda *_:self.fill_global_library())
        self.global_info=tk.StringVar(value='Select Scan all registered games to index existing mods. Read-only.')
        ttk.Label(self.global_tab,textvariable=self.global_info,wraplength=990).pack(anchor='w',pady=(0,8))
        global_area=ttk.Frame(self.global_tab);global_area.pack(fill='both',expand=True)
        self.global_tree=ttk.Treeview(global_area,columns=('game','mod','loader','version','status','source','package'),show='headings',selectmode='browse')
        for key,label,width in [('game','Game',170),('mod','Mod / package',220),('loader','Loader',95),('version','Version',82),('status','State',85),('source','Source',140),('package','Type',165)]:
            self.global_tree.heading(key,text=label)
            self.global_tree.column(key,width=width,stretch=key in ('game','mod','package'))
        self.global_tree.pack(side='left',fill='both',expand=True)
        global_scroll=ttk.Scrollbar(global_area,command=self.global_tree.yview);global_scroll.pack(side='right',fill='y')
        self.global_tree.configure(yscrollcommand=global_scroll.set)
        self.global_tree.bind('<Double-1>',lambda *_:self.open_global_mod())
        self.global_report=None;self.global_visible=[];self.global_scan_busy=False

        self.package_tab=ttk.Frame(self.tabs,padding=12);self.tabs.add(self.package_tab,text='  Packages & Loose DLLs  ')
        ttk.Label(self.package_tab,text='Existing mod package inventory',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(self.package_tab,text='Groups nested DLLs under their package folders. Metadata-owned packages can be identified for safer updates; unmanaged folders and loose DLLs are shown without guessing their identity. Read-only.',wraplength=990).pack(anchor='w',pady=(0,8))
        pkgbar=ttk.Frame(self.package_tab);pkgbar.pack(fill='x',pady=(0,8))
        ttk.Button(pkgbar,text='Refresh packages',command=self.refresh).pack(side='left')
        ttk.Button(pkgbar,text='Export packages CSV',command=self.export_packages).pack(side='left',padx=8)
        self.pkg_info=tk.StringVar(value='Select a game to see installed package groups.')
        ttk.Label(self.package_tab,textvariable=self.pkg_info).pack(anchor='w',pady=(0,8))
        pkgarea=ttk.Frame(self.package_tab);pkgarea.pack(fill='both',expand=True)
        self.pkg_tree=ttk.Treeview(pkgarea,columns=('name','type','version','enabled','dlls','path'),show='headings')
        for name,width in [('name',220),('type',175),('version',90),('enabled',90),('dlls',65),('path',380)]:
            self.pkg_tree.heading(name,text=name.title());self.pkg_tree.column(name,width=width,stretch=(name=='path'))
        self.pkg_tree.pack(side='left',fill='both',expand=True)
        pkg_scroll=ttk.Scrollbar(pkgarea,command=self.pkg_tree.yview);pkg_scroll.pack(side='right',fill='y')
        self.pkg_tree.configure(yscrollcommand=pkg_scroll.set)
        self.tabs.add(sources,text='  Mod Websites  ')
        self.tabs.add(tools,text='  Profiles & Tools  ')
        diagnostics=ttk.Frame(self.tabs,padding=12);self.tabs.add(diagnostics,text='  Game Diagnostics  ')
        ttk.Label(diagnostics,text='Steam / Proton / Mod Loader Diagnostics',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(diagnostics,text='Read-only checks for the selected game. Steam app IDs come from matching local appmanifests, not guesses. Proton prefixes may be absent for native games.',wraplength=940).pack(anchor='w',pady=(0,10))
        diagactions=ttk.Frame(diagnostics);diagactions.pack(fill='x',pady=5)
        ttk.Button(diagactions,text='Run checks',command=self.run_game_diagnostics).pack(side='left')
        ttk.Button(diagactions,text='Export JSON report…',command=self.export_game_diagnostics).pack(side='left',padx=8)
        self.diag_info=tk.StringVar(value='Select a game, then run diagnostics. No game files are changed.')
        ttk.Label(diagnostics,textvariable=self.diag_info,wraplength=920).pack(anchor='w',pady=7)
        diagarea=ttk.Frame(diagnostics);diagarea.pack(fill='both',expand=True)
        self.diag_tree=ttk.Treeview(diagarea,columns=('check','status','details'),show='headings')
        for column,width in [('check',185),('status',90),('details',590)]:
            self.diag_tree.heading(column,text=column.capitalize());self.diag_tree.column(column,width=width,stretch=(column=='details'))
        self.diag_tree.pack(side='left',fill='both',expand=True)
        diagscroll=ttk.Scrollbar(diagarea,command=self.diag_tree.yview);diagscroll.pack(side='right',fill='y')
        self.diag_tree.configure(yscrollcommand=diagscroll.set)
        self.diagnostic_report=None;self.diagnostic_game_root=None
        other_launchers=ttk.Frame(self.tabs,padding=12);self.tabs.add(other_launchers,text='  Other Launchers  ')
        ttk.Label(other_launchers,text='Heroic & Lutris game discovery',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(other_launchers,text='Reads local installed-game indexes for Heroic (Epic, GOG, Amazon) and Lutris. Imports only games with existing SMAPI, BepInEx or MelonLoader folders. Does not change launcher settings or game files.',wraplength=940).pack(anchor='w',pady=(0,10))
        launch_bar=ttk.Frame(other_launchers);launch_bar.pack(fill='x',pady=(0,8))
        ttk.Button(launch_bar,text='Refresh launcher inventory',command=self.show_other_launchers).pack(side='left')
        ttk.Button(launch_bar,text='Import detected games',command=self.import_other_launchers).pack(side='left',padx=8)
        ttk.Button(launch_bar,text='Export launcher inventory JSON…',command=self.export_other_launchers).pack(side='left')
        self.launcher_info=tk.StringVar(value='Refresh to inspect Heroic / Lutris installations.')
        ttk.Label(other_launchers,textvariable=self.launcher_info,wraplength=930).pack(anchor='w',pady=(0,9))
        area=ttk.Frame(other_launchers);area.pack(fill='both',expand=True)
        self.launcher_tree=ttk.Treeview(area,columns=('name','launcher','store','framework','managed','path'),show='headings')
        for col,width in [('name',180),('launcher',95),('store',95),('framework',92),('managed',85),('path',350)]:
            self.launcher_tree.heading(col,text=col.title());self.launcher_tree.column(col,width=width,stretch=(col=='path'))
        self.launcher_tree.pack(side='left',fill='both',expand=True)
        launchscroll=ttk.Scrollbar(area,command=self.launcher_tree.yview);launchscroll.pack(side='right',fill='y')
        self.launcher_tree.configure(yscrollcommand=launchscroll.set)
        self.launcher_inventory=[]
        libraries=ttk.Frame(self.tabs,padding=12);self.tabs.add(libraries,text='  Steam Libraries  ')
        ttk.Label(libraries,text='Steam libraries on separate drives',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(libraries,text='UniMod searches Steam metadata, mounted-drive folders and any directories you register below. Add a Steam library root or its steamapps folder. Scanning only reads game manifests and does not alter game files.',wraplength=925).pack(anchor='w',pady=(0,10))
        lbar=ttk.Frame(libraries);lbar.pack(fill='x',pady=(0,8))
        ttk.Button(lbar,text='Add Steam library…',command=self.add_steam_library).pack(side='left')
        ttk.Button(lbar,text='Remove custom entry',command=self.remove_steam_library).pack(side='left',padx=8)
        ttk.Button(lbar,text='Refresh library list',command=self.show_steam_libraries).pack(side='left')
        ttk.Button(lbar,text='Scan games from libraries',command=self.scan_libraries).pack(side='left',padx=8)
        self.library_info=tk.StringVar(value='')
        ttk.Label(libraries,textvariable=self.library_info,wraplength=930).pack(anchor='w',pady=(0,8))
        lbox=ttk.Frame(libraries);lbox.pack(fill='both',expand=True)
        self.library_tree=ttk.Treeview(lbox,columns=('location','origin'),show='headings',selectmode='browse')
        for column,width in [('location',720),('origin',175)]:
            self.library_tree.heading(column,text=column.title());self.library_tree.column(column,width=width,stretch=(column=='location'))
        self.library_tree.pack(side='left',fill='both',expand=True)
        lscroll=ttk.Scrollbar(lbox,command=self.library_tree.yview);lscroll.pack(side='right',fill='y')
        self.library_tree.configure(yscrollcommand=lscroll.set)
        self.show_steam_libraries()
        source_tools=ttk.Frame(self.tabs,padding=12);self.tabs.add(source_tools,text='  Source Matching  ')
        ttk.Label(source_tools,text='Match existing mods to mod websites',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(source_tools,text='Select an installed mod, then Assign source to link it to its official page. Unmatched mods are never guessed from their names. Assignments survive rescans and do not edit the game files.',wraplength=830).pack(anchor='w',pady=(0,12))
        source_actions=ttk.Frame(source_tools);source_actions.pack(fill='x')
        for label,callback in [('Assign selected source',self.assign_source),('Clear selected assignment',self.clear_source),('Export source report CSV',self.export_sources),('Preview auto matches',self.preview_auto_sources)]:
            ttk.Button(source_actions,text=label,command=callback).pack(side='left',padx=(0,8))
        self.source_info=tk.StringVar(value='Select a game to inspect source matches.')
        ttk.Label(source_tools,textvariable=self.source_info,wraplength=950).pack(anchor='w',pady=(12,8))
        matchbar=ttk.Frame(source_tools);matchbar.pack(fill='x',pady=(0,8))
        ttk.Label(matchbar,text='Filter:').pack(side='left')
        self.source_filter=tk.StringVar(value='All')
        source_select=ttk.Combobox(matchbar,textvariable=self.source_filter,state='readonly',width=22,
            values=('All','Needs matching','Linked','Assigned by user','Update keys only'))
        source_select.pack(side='left',padx=(6,12))
        source_select.bind('<<ComboboxSelected>>',lambda event:self.fill_source_table())
        ttk.Label(matchbar,text='Search:').pack(side='left')
        self.source_search=tk.StringVar(value='')
        self.source_search.trace_add('write',lambda *_:self.fill_source_table())
        ttk.Entry(matchbar,textvariable=self.source_search).pack(side='left',fill='x',expand=True,padx=(6,12))
        ttk.Button(matchbar,text='Export matching CSV…',command=self.export_source_reconciliation_ui).pack(side='right')
        sourcearea=ttk.Frame(source_tools);sourcearea.pack(fill='both',expand=True)
        self.source_tree=ttk.Treeview(sourcearea,columns=('mod','status','source','version','enabled','url'),
            show='headings',selectmode='browse')
        for column,width in [('mod',190),('status',170),('source',145),('version',85),('enabled',85),('url',355)]:
            self.source_tree.heading(column,text=column.title(),
                command=lambda col=column:self.sort_source_table(col))
            self.source_tree.column(column,width=width,stretch=(column in ('mod','url')))
        self.source_tree.pack(side='left',fill='both',expand=True)
        source_scroll=ttk.Scrollbar(sourcearea,command=self.source_tree.yview)
        source_scroll.pack(side='right',fill='y')
        self.source_tree.configure(yscrollcommand=source_scroll.set)
        self.source_tree.bind('<Double-1>',lambda event:self.open_source_table_link())
        self.source_order=('mod',False)
        self.source_rows=[]
        sourcebuttons=ttk.Frame(source_tools);sourcebuttons.pack(fill='x',pady=(10,0))
        ttk.Button(sourcebuttons,text='Assign selected mod source…',command=self.assign_source_from_table).pack(side='left',padx=(0,8))
        ttk.Button(sourcebuttons,text='Find candidate pages…',command=self.source_search_candidates).pack(side='left',padx=(0,8))
        ttk.Button(sourcebuttons,text='Match downloaded Nexus ZIPs…',command=self.bepinex_nexus_archive_dialog).pack(side='left',padx=(0,8))
        ttk.Button(sourcebuttons,text='Search without Nexus ZIP…',command=self.bepinex_source_hints_dialog).pack(side='left',padx=(0,8))
        ttk.Button(sourcebuttons,text='Clear assignment',command=self.clear_source_from_table).pack(side='left',padx=(0,8))
        ttk.Button(sourcebuttons,text='Open source page',command=self.open_source_table_link).pack(side='left',padx=(0,8))
        ttk.Button(sourcebuttons,text='Copy source URL',command=self.copy_source_table_link).pack(side='left')

        audit=ttk.Frame(self.tabs,padding=12);self.tabs.add(audit,text='  Installation Audit  ')
        # v0.24: read-only SMAPI dependency inspector for existing mod collections.
        deps_tab=ttk.Frame(self.tabs,padding=12);self.tabs.add(deps_tab,text='  Dependencies  ')
        ttk.Label(deps_tab,text='Installed SMAPI dependency inspector',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(deps_tab,text='Shows required and optional dependencies, disabled providers, duplicate IDs and numeric minimum-version mismatches. Game/SMAPI-provided IDs may look missing. Never modifies mods.',wraplength=920).pack(anchor='w',pady=(0,10))
        deps_bar=ttk.Frame(deps_tab);deps_bar.pack(fill='x',pady=(0,9))
        ttk.Button(deps_bar,text='Inspect current game',command=self.show_dependencies).pack(side='left')
        ttk.Button(deps_bar,text='Export dependency CSV…',command=self.export_dependencies).pack(side='left',padx=8)
        ttk.Label(deps_bar,text='Filter:').pack(side='left',padx=(22,6))
        self.dep_query=tk.StringVar()
        self.dep_query.trace_add('write',lambda *_:self.filter_dependencies())
        ttk.Entry(deps_bar,textvariable=self.dep_query).pack(side='left',fill='x',expand=True)
        self.dep_info=tk.StringVar(value='Select Stardew Valley or another SMAPI game to inspect dependencies.')
        ttk.Label(deps_tab,textvariable=self.dep_info,wraplength=920).pack(anchor='w',pady=(0,8))
        dep_area=ttk.Frame(deps_tab);dep_area.pack(fill='both',expand=True)
        self.dep_tree=ttk.Treeview(dep_area,columns=('mod','dependency','type','required','minimum','installed','status'),show='headings')
        for key,label,width in [('mod','Mod',200),('dependency','Dependency ID',220),('type','Type',135),('required','Required',70),('minimum','Minimum',95),('installed','Installed',95),('status','Status',170)]:
            self.dep_tree.heading(key,text=label);self.dep_tree.column(key,width=width,stretch=(key in ('mod','dependency','status')))
        self.dep_tree.pack(side='left',fill='both',expand=True)
        dep_scroll=ttk.Scrollbar(dep_area,command=self.dep_tree.yview);dep_scroll.pack(side='right',fill='y')
        self.dep_tree.configure(yscrollcommand=dep_scroll.set)
        self.dep_rows=[];self.dep_game_root=None
        changes=ttk.Frame(self.tabs,padding=12);self.tabs.add(changes,text='  Scan Changes  ')
        ttk.Label(changes,text='Compare with a saved baseline',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(changes,text='Save a snapshot of your installed mods, then compare later scans. Snapshots and comparisons never modify mods.',wraplength=900).pack(anchor='w',pady=(0,8))
        changebar=ttk.Frame(changes);changebar.pack(fill='x')
        ttk.Button(changebar,text='Save current baseline',command=self.save_baseline).pack(side='left')
        ttk.Button(changebar,text='Compare current scan',command=self.show_changes).pack(side='left',padx=8)
        ttk.Button(changebar,text='Export changes JSON',command=self.export_changes).pack(side='left')
        self.change_info=tk.StringVar(value='Save a baseline to track future changes.')
        ttk.Label(changes,textvariable=self.change_info).pack(anchor='w',pady=8)
        changeframe=ttk.Frame(changes);changeframe.pack(fill='both',expand=True)
        self.change_tree=ttk.Treeview(changeframe,columns=('change','mod','before','after','relative'),show='headings')
        for c,w in [('change',130),('mod',210),('before',90),('after',90),('relative',350)]:
            self.change_tree.heading(c,text=c.capitalize());self.change_tree.column(c,width=w,stretch=(c=='relative'))
        self.change_tree.pack(side='left',fill='both',expand=True)
        change_scroll=ttk.Scrollbar(changeframe,command=self.change_tree.yview);change_scroll.pack(side='right',fill='y');self.change_tree.configure(yscrollcommand=change_scroll.set)

        ttk.Label(audit,text='Read-only installed-mod audit',style='Section.TLabel').pack(anchor='w',pady=(0,5))
        ttk.Label(audit,text='Flags duplicate enabled SMAPI IDs and required dependencies not detected. Some dependency reports can be false positives.',wraplength=900).pack(anchor='w',pady=(0,8))
        auditbar=ttk.Frame(audit);auditbar.pack(fill='x')
        ttk.Button(auditbar,text='Run audit',command=self.run_audit).pack(side='left')
        ttk.Button(auditbar,text='Export audit JSON',command=self.export_audit).pack(side='left',padx=8)
        self.audit_info=tk.StringVar(value='Select a game and run an audit.');ttk.Label(audit,textvariable=self.audit_info).pack(anchor='w',pady=8)
        auditframe=ttk.Frame(audit);auditframe.pack(fill='both',expand=True)
        self.audit_tree=ttk.Treeview(auditframe,columns=('severity','type','mod','detail'),show='headings')
        for c,w in [('severity',80),('type',180),('mod',170),('detail',500)]:
            self.audit_tree.heading(c,text=c.capitalize());self.audit_tree.column(c,width=w,stretch=(c=='detail'))
        self.audit_tree.pack(side='left',fill='both',expand=True)
        audit_scroll=ttk.Scrollbar(auditframe,command=self.audit_tree.yview);audit_scroll.pack(side='right',fill='y');self.audit_tree.configure(yscrollcommand=audit_scroll.set)
        # Full-width mod library, two slim filter rows and optional inspector.
        installed.configure(padding=(12,8))
        pagebar=ttk.Frame(installed);pagebar.pack(fill='x',pady=(1,7))
        ttk.Label(pagebar,text='Installed mods',style='Section.TLabel').pack(side='left')
        self.count_label=ttk.Label(pagebar,text='0 mods',style='Subtle.TLabel')
        self.count_label.pack(side='right',padx=8)
        self.details_visible=tk.BooleanVar(value=False)
        ttk.Button(pagebar,text='ⓘ Details',command=self.toggle_details,style='Top.TButton').pack(side='right',padx=8)
        ttk.Button(pagebar,text='Open folder',command=self.open_dir,style='Top.TButton').pack(side='right',padx=8)
        ttk.Button(pagebar,text='Find mod sources',command=self.find_sources_easy,style='Accent.TButton').pack(side='right',padx=8)
        filterbar=ttk.Frame(installed);filterbar.pack(fill='x',pady=(0,7))
        self.query=tk.StringVar();self.query.trace_add('write',lambda *_:self.fill_mods())
        self.filter_entry=ttk.Entry(filterbar,textvariable=self.query,font=('DejaVu Sans',10))
        self.filter_entry.pack(side='left',fill='x',expand=True,padx=(0,8),ipady=2)
        self.filter_entry.insert(0,'')
        self.mod_visibility=tk.StringVar(value='All')
        visibility=ttk.Combobox(filterbar,state='readonly',textvariable=self.mod_visibility,
                    values=('All','Enabled','Disabled','Known source','Unknown source'),width=15)
        visibility.pack(side='left',padx=(0,8))
        visibility.bind('<<ComboboxSelected>>',lambda _:self.fill_mods())
        self.group_components=tk.BooleanVar(value=True)
        ttk.Checkbutton(filterbar,text='Group families',variable=self.group_components,command=self.fill_mods).pack(side='left',padx=(2,9))
        self.mod_sort_value=tk.StringVar(value='Name')
        mod_sort=ttk.Combobox(filterbar,state='readonly',textvariable=self.mod_sort_value,
                              values=('Name','Author','Version','Status','Source'),width=11)
        mod_sort.pack(side='left')
        mod_sort.bind('<<ComboboxSelected>>',lambda _:self.sort_installed_table(self.mod_sort_value.get().lower()))
        self.mod_body=ttk.Panedwindow(installed,orient='horizontal');self.mod_body.pack(fill='both',expand=True)
        treearea=ttk.Frame(self.mod_body,style='Panel.TFrame',padding=0)
        self.mod_body.add(treearea,weight=5)
        table_area=ttk.Frame(treearea,style='Panel.TFrame');table_area.pack(fill='both',expand=True)
        columns=('name','status','version','source','author','update','id','path')
        self.tree=ttk.Treeview(table_area,columns=columns,displaycolumns=('author','source','version','status'),
                               show='tree headings',selectmode='browse',style='Mods.Treeview')
        self.tree.heading('#0',text='MOD NAME',command=lambda:self.sort_installed_table('name'))
        self.tree.column('#0',width=475,minwidth=215,stretch=True)
        for col,title,w in [('name','Mod',210),('author','AUTHOR',155),('source','SOURCE',145),('version','VERSION',95),
                            ('status','ENABLED',105),('update','Updates',115),('id','ID',170),('path','Path',240)]:
            self.tree.heading(col,text=title,command=lambda key=col:self.sort_installed_table(key))
            self.tree.column(col,width=w,minwidth=60,stretch=(col=='source'),anchor='w' if col!='status' else 'center')
        self.tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(table_area,command=self.tree.yview)
        scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<Double-1>',self.installed_double_click)
        self.tree.bind('<ButtonRelease-1>',self.installed_status_click,add='+')
        self.tree.bind('<space>',self.installed_toggle_key)
        self.detail=tk.StringVar(value='Select a mod to see its installed location and source.')
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.describe_selected())
        info=ttk.Frame(self.mod_body,style='Panel.TFrame',padding=(15,16));self.detail_pane=info
        ttk.Label(info,text='MOD DETAILS',style='PanelCaption.TLabel').pack(anchor='w',pady=(0,15))
        self.detail_name=tk.StringVar(value='Select a mod')
        self.detail_state=tk.StringVar(value='Choose an entry on the left')
        self.detail_version=tk.StringVar(value='—')
        self.detail_uid=tk.StringVar(value='—')
        self.detail_source=tk.StringVar(value='—')
        self.detail_path=tk.StringVar(value='—')
        ttk.Label(info,textvariable=self.detail_name,style='DetailName.TLabel',wraplength=260).pack(anchor='w',pady=(0,6))
        ttk.Label(info,textvariable=self.detail_state,style='PanelMuted.TLabel').pack(anchor='w',pady=(0,12))
        for title,var in [('VERSION',self.detail_version),('MOD ID',self.detail_uid),
                          ('SOURCE',self.detail_source),('LOCATION',self.detail_path)]:
            ttk.Label(info,text=title,style='PanelCaption.TLabel').pack(anchor='w',pady=(7,2))
            ttk.Label(info,textvariable=var,style='PanelValue.TLabel',wraplength=275,justify='left').pack(anchor='w')
        ttk.Separator(info).pack(fill='x',pady=(15,10))
        self.mod_action_buttons=[]
        for label,cb,sty in [('Enable / disable',self.toggle,'Accent.TButton'),('Open mod folder',self.open_selected,'TButton'),
                             ('Open download page',self.open_release,'TButton'),('Assign source',self.assign_source,'TButton'),
                             ('Replace ZIP with backup',self.replace_selected,'TButton')]:
            button=ttk.Button(info,text=label,command=cb,style=sty)
            button.pack(fill='x',pady=(0,5));self.mod_action_buttons.append(button)
        # Inspector intentionally hidden until asked for, unlike v0.31.
        self._installed_sort=('name',False)
        ttk.Label(sources,text='Discover mods — official provider catalogues',style='Section.TLabel').pack(anchor='w',pady=(0,7))
        ttk.Label(sources,text='Read-only provider searches, including public Nexus Mods metadata. Results are leads, NOT installed-mod proof. Nexus file downloads and account features stay approval-gated.',wraplength=1040).pack(anchor='w',pady=(0,10))
        discovery=ttk.Frame(sources);discovery.pack(fill='x',pady=(0,10))
        self.provider_choice=tk.StringVar(value='Modrinth')
        self.provider_combo=ttk.Combobox(discovery,textvariable=self.provider_choice,
            state='readonly',width=16,values=provider_catalogues.PROVIDERS)
        self.provider_combo.pack(side='left',padx=(0,9))
        self.provider_query=tk.StringVar(value='')
        ttk.Entry(discovery,textvariable=self.provider_query,width=36).pack(side='left',fill='x',expand=True,padx=(0,9))
        ttk.Button(discovery,text='Search catalogue',command=self.provider_begin_search,style='Accent.TButton').pack(side='left')
        credential_row=ttk.Frame(sources);credential_row.pack(fill='x',pady=(0,7))
        ttk.Label(credential_row,text='Community / Game ID:').pack(side='left',padx=(0,4))
        self.provider_scope=tk.StringVar(value='')
        ttk.Entry(credential_row,textvariable=self.provider_scope,width=22).pack(side='left',padx=(0,15))
        ttk.Label(credential_row,text='Optional provider API key:').pack(side='left',padx=(0,5))
        self.provider_key=tk.StringVar(value='')
        ttk.Entry(credential_row,textvariable=self.provider_key,show='•',width=24).pack(side='left',padx=(0,6))
        ttk.Button(credential_row,text='Verify CurseForge game ID…',command=self.provider_verify_curseforge_game).pack(side='left',padx=(5,8))
        ttk.Label(credential_row,text='Memory only; CurseForge / mod.io',style='Subtle.TLabel').pack(side='left')
        modio_row=ttk.Frame(sources);modio_row.pack(fill='x',pady=(0,7))
        ttk.Label(modio_row,text='mod.io User ID (from your API path):').pack(side='left',padx=(0,5))
        self.modio_user_id=tk.StringVar(value='')
        ttk.Entry(modio_row,textvariable=self.modio_user_id,width=16).pack(side='left',padx=(0,8))
        ttk.Button(modio_row,text='Verify mod.io game ID…',command=self.provider_verify_modio_game).pack(side='left',padx=(0,8))
        ttk.Label(modio_row,text='Session key only; read-only catalogue and reviewed modfile downloads',style='Subtle.TLabel').pack(side='left')
        self.modio_verified=None
        self._modio_verification_events=queue.Queue()
        self.curseforge_verified=None
        self._curseforge_verification_events=queue.Queue()
        self.provider_info=tk.StringVar(value='Nexus Mods (public metadata), GitHub and Modrinth need no key. mod.io downloads use a private user key; CurseForge needs approved API access.')
        ttk.Label(sources,textvariable=self.provider_info,wraplength=1050).pack(anchor='w',pady=(0,8))
        provider_area=ttk.Frame(sources);provider_area.pack(fill='both',expand=True)
        self.provider_tree=ttk.Treeview(provider_area,columns=('title','author','version','source','description'),
                                            show='headings',selectmode='browse')
        for col,width in [('title',250),('author',160),('version',110),('source',115),('description',510)]:
            self.provider_tree.heading(col,text=col.capitalize())
            self.provider_tree.column(col,width=width,stretch=(col in ('title','description')))
        self.provider_tree.pack(side='left',fill='both',expand=True)
        provider_scroll=ttk.Scrollbar(provider_area,command=self.provider_tree.yview)
        provider_scroll.pack(side='right',fill='y');self.provider_tree.configure(yscrollcommand=provider_scroll.set)
        self.provider_tree.bind('<Double-1>',lambda *_:self.provider_open_result())
        self.provider_results=[];self.provider_loading=False
        provider_buttons=ttk.Frame(sources);provider_buttons.pack(fill='x',pady=8)
        ttk.Button(provider_buttons,text='Open selected official page',command=self.provider_open_result).pack(side='left')
        ttk.Button(provider_buttons,text='Link reviewed page to selected mod…',command=self.provider_assign_reviewed_source).pack(side='left',padx=8)
        ttk.Button(provider_buttons,text='Browse release files…',command=self.provider_files_dialog,style='Accent.TButton').pack(side='left',padx=9)
        ttk.Button(provider_buttons,text='Test mod.io API…',command=self.provider_modio_diagnostic).pack(side='left',padx=7)
        ttk.Button(provider_buttons,text='Thunderstore installer…',command=lambda:self.show_page('Thunderstore Search')).pack(side='left',padx=9)
        ttk.Button(provider_buttons,text='Nexus account / registration…',command=lambda:self.show_page('Nexus Updates')).pack(side='right')
        ttk.Button(provider_buttons,text='Provider access requirements…',command=self.provider_access_dialog).pack(side='right',padx=8)
        # Nexus status tab: exact-ID lookup only, with a session-only API key.
        nexus=ttk.Frame(self.tabs,padding=12); self.tabs.add(nexus,text='  Nexus Updates  ')
        ttk.Label(nexus,text='Nexus Mods — exact-ID update checks',style='Section.TLabel').pack(anchor='w',pady=(0,6))
        ttk.Label(nexus,text='Nexus requested OAuth 2.0 with PKCE evaluation for registration. The browser login framework is ready for provider-issued client settings; live download authorization remains gated. Private developer API-key testing stays separate. Credentials are memory-only.',wraplength=920).pack(anchor='w',pady=(0,8))
        nxbar=ttk.Frame(nexus); nxbar.pack(fill='x',pady=5)
        ttk.Button(nxbar,text='OAuth PKCE (Nexus approval required)',command=self.nexus_oauth_connect,style='Accent.TButton').pack(side='left',padx=(0,8))
        ttk.Button(nxbar,text='Legacy SSO',command=self.nexus_sso_connect).pack(side='left',padx=(0,8))
        ttk.Button(nxbar,text='Test connection',command=self.nexus_test_connection).pack(side='left',padx=8)
        ttk.Button(nxbar,text='Registration status',command=self.nexus_registration_info).pack(side='left',padx=8)
        devbar=ttk.Frame(nexus)
        self.nexus_key=tk.StringVar()
        ttk.Label(devbar,text='Private developer API key (not saved):').pack(side='left')
        self.nexus_key_entry=ttk.Entry(devbar,textvariable=self.nexus_key,width=38,show='•')
        self.nexus_key_entry.pack(side='left',padx=7)
        ttk.Button(devbar,text='Clear key',command=lambda:self.nexus_key.set('')).pack(side='left')
        ttk.Button(devbar,text='Nexus key page ↗',command=lambda:webbrowser.open('https://www.nexusmods.com/users/myaccount?tab=api')).pack(side='left',padx=8)
        def toggle_dev_key():
            if devbar.winfo_manager():devbar.pack_forget()
            else:devbar.pack(fill='x',pady=(4,8),after=nxbar)
        ttk.Button(nxbar,text='Developer key options ▾',command=toggle_dev_key).pack(side='right',padx=5)
        self.nexus_all_origin=tk.BooleanVar(value=False)
        ttk.Checkbutton(nexus,text='All installed mods for this game came from Nexus (site only; does not identify pages)',
            variable=self.nexus_all_origin,command=self.nexus_collection_toggle).pack(anchor='w',pady=(3,7))
        nxactions=ttk.Frame(nexus); nxactions.pack(fill='x',pady=7)
        ttk.Button(nxactions,text='Check next 25',command=self.nexus_check_next).pack(side='left',padx=(0,8))
        ttk.Button(nxactions,text='Browse / download files…',command=self.nexus_download_selected).pack(side='left',padx=8)
        ttk.Button(nxactions,text='Import NXM download link…',command=self.nexus_download_nxm).pack(side='left',padx=8)
        ttk.Button(nxactions,text='Check selected installed mod',command=self.nexus_check_selected).pack(side='left',padx=(0,8))
        ttk.Button(nxactions,text='Open Nexus mod page',command=self.nexus_open_selected).pack(side='left')
        ttk.Button(nxactions,text='Assign Nexus page to selected mod',command=self.nexus_assign_selected).pack(side='left',padx=(8,0))
        ttk.Button(nxactions,text='Import AIO links…',command=self.nexus_import_aio).pack(side='left',padx=(8,0))
        ttk.Button(nxactions,text='Go to Update Inbox',command=lambda:self.tabs.select(inbox)).pack(side='left',padx=8)
        self.nexus_info=tk.StringVar(value='Choose a game. Only exact Nexus IDs are eligible for checking.')
        ttk.Label(nexus,textvariable=self.nexus_info,wraplength=920).pack(anchor='w',pady=(5,8))
        nxarea=ttk.Frame(nexus);nxarea.pack(fill='both',expand=True)
        self.nexus_tree=ttk.Treeview(nxarea,columns=('mod','local','remote','status','source'),show='headings',selectmode='browse')
        for col,width in [('mod',260),('local',95),('remote',95),('status',160),('source',260)]:
            self.nexus_tree.heading(col,text=col.capitalize()); self.nexus_tree.column(col,width=width,stretch=(col in ('mod','source')))
        self.nexus_tree.pack(side='left',fill='both',expand=True)
        nxscroll=ttk.Scrollbar(nxarea,command=self.nexus_tree.yview);nxscroll.pack(side='right',fill='y')
        self.nexus_tree.configure(yscrollcommand=nxscroll.set)
        self.nexus_tree.bind('<Double-1>',lambda event:self.nexus_open_selected())
        # One simple review-first updates page. Never issues API requests on load.
        updates=ttk.Frame(self.tabs,padding=(16,12));self.tabs.add(updates,text='  Updates Available  ')
        header=ttk.Frame(updates);header.pack(fill='x',pady=(0,8))
        ttk.Label(header,text='Updates for your installed mods',style='Title.TLabel').pack(side='left')
        ttk.Button(header,text='Check connected sources',command=self.unified_check,style='Accent.TButton').pack(side='right',padx=(8,0))
        ttk.Button(header,text='Refresh inventory',command=self.refresh).pack(side='right')
        self.unified_source_button=ttk.Button(header,text='Resolve mod sources…',command=self.unified_identify_sources)
        self.unified_source_button.pack(side='right',padx=(0,8))
        self.unified_info=tk.StringVar(value='Choose a game, then check for updates. Nothing downloads or installs without approval.')
        ttk.Label(updates,textvariable=self.unified_info,style='Subtle.TLabel',wraplength=1100).pack(anchor='w',pady=(0,9))
        ubar=ttk.Frame(updates);ubar.pack(fill='x',pady=(0,8))
        ttk.Label(ubar,text='Find:').pack(side='left')
        self.unified_query=tk.StringVar(value='')
        self.unified_query.trace_add('write',lambda *_:self.unified_render())
        ttk.Entry(ubar,textvariable=self.unified_query,width=36).pack(side='left',padx=8,fill='x',expand=True)
        self.unified_filter=tk.StringVar(value='All')
        ttk.Combobox(ubar,textvariable=self.unified_filter,state='readonly',width=20,
                     values=('All','Updates available','Not checked','Up to date','Needs attention')).pack(side='left',padx=(0,8))
        self.unified_filter.trace_add('write',lambda *_:self.unified_render())
        ttk.Button(ubar,text='Nexus account / developer options',command=lambda:self.show_page('Nexus Updates')).pack(side='right')
        area=ttk.Frame(updates);area.pack(fill='both',expand=True)
        self.unified_tree=ttk.Treeview(area,columns=('name','installed','latest','source','status','parts','download'),show='headings',selectmode='extended')
        for field,label,width in (('name','Mod / family',320),('installed','Installed',100),('latest','Latest checked',120),('source','Source',100),('status','Result',165),('parts','Parts',70),('download','Downloaded ZIP',185)):
            self.unified_tree.heading(field,text=label)
            self.unified_tree.column(field,width=width,stretch=field=='name')
        self.unified_tree.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(area,command=self.unified_tree.yview);scrollbar.pack(side='right',fill='y')
        self.unified_tree.configure(yscrollcommand=scrollbar.set)
        self.unified_tree.bind('<Double-1>',lambda *_:self.unified_open_page())
        actions=ttk.Frame(updates);actions.pack(fill='x',pady=(10,0))
        ttk.Button(actions,text='Open selected mod page',command=self.unified_open_page).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Choose Nexus file…',command=self.unified_choose_file).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Find downloaded updates',command=self.unified_scan_downloads,style='Accent.TButton').pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Review & Install selected…',command=self.unified_review_install).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Select ready ZIPs',command=self.unified_select_ready).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Review & Install batch…',command=self.unified_review_batch,style='Accent.TButton').pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Open full Update Inbox',command=lambda:self.show_page('Update Inbox')).pack(side='left',padx=(0,7))
        ttk.Button(actions,text='Resolve missing sources',command=lambda:self.show_page('Source Matching')).pack(side='right')
        ttk.Label(updates,text='Updates are based on confirmed version responses only. Downloads go into the review queue; no automatic installations.',style='Subtle.TLabel').pack(anchor='w',pady=(9,0))
        # Update inbox: browser-downloaded archives matched against existing SMAPI IDs.
        inbox=ttk.Frame(self.tabs,padding=12);self.tabs.add(inbox,text='  Update Inbox  ');self.inbox_tab=inbox
        ttk.Label(inbox,text='Nexus download queue',style='Section.TLabel').pack(anchor='w',pady=(0,5))
        ttk.Label(inbox,text='Approved Nexus manager links can be queued here. Tokens stay in memory; nothing downloads or installs until you approve it.',wraplength=900).pack(anchor='w',pady=(0,5))
        qbar=ttk.Frame(inbox);qbar.pack(fill='x',pady=(0,5))
        ttk.Button(qbar,text='Paste NXM link…',command=self.nexus_download_nxm).pack(side='left')
        ttk.Button(qbar,text='Download selected (review first)',command=self.nexus_queue_download).pack(side='left',padx=8)
        ttk.Button(qbar,text='Download all ready…',command=self.nexus_queue_download_all).pack(side='left',padx=8)
        ttk.Button(qbar,text='Remove selected',command=self.nexus_queue_remove).pack(side='left',padx=8)
        ttk.Button(qbar,text='Retry selected',command=self.nexus_queue_retry).pack(side='left',padx=8)
        ttk.Button(qbar,text='Cancel batch',command=self.nexus_queue_cancel).pack(side='left',padx=8)
        ttk.Button(qbar,text='Clear finished',command=self.nexus_queue_clear_finished).pack(side='left',padx=8)
        ttk.Button(qbar,text='Enable Nexus browser links',command=self.nexus_enable_browser_links).pack(side='right')
        self.nexus_queue_info=tk.StringVar(value='No Nexus requests queued. Select Mod Manager Download on Nexus after enabling the optional URL handler.')
        ttk.Label(inbox,textvariable=self.nexus_queue_info,wraplength=940).pack(anchor='w',pady=(0,5))
        self.nexus_queue_progress=ttk.Progressbar(inbox,orient='horizontal',mode='determinate',maximum=100)
        self.nexus_queue_progress.pack(fill='x',pady=(0,7))
        self.nexus_queue_tree=ttk.Treeview(inbox,columns=('game','mod','file','status'),show='headings',height=4,selectmode='extended')
        for name,width in [('game',150),('mod',110),('file',110),('status',380)]:
            self.nexus_queue_tree.heading(name,text=name.capitalize())
            self.nexus_queue_tree.column(name,width=width,stretch=(name=='status'))
        self.nexus_queue_tree.pack(fill='x',pady=(0,12))
        self.nexus_queue_tree.bind('<<TreeviewSelect>>',self.nexus_queue_show_selection)
        qtools=ttk.Frame(inbox);qtools.pack(fill='x',pady=(0,7))
        ttk.Button(qtools,text='Review downloaded ZIP in inbox',command=self.nexus_queue_review).pack(side='left')
        ttk.Separator(inbox).pack(fill='x',pady=(0,10))
        ttk.Label(inbox,text='Match ZIP updates to your installed SMAPI and BepInEx mods',style='Section.TLabel').pack(anchor='w',pady=(0,6))
        ttk.Label(inbox,text='Download from the official mod website, then scan ZIPs. SMAPI uses UniqueID; BepInEx requires matching package metadata (owner or HTTPS source), never DLL filenames. Matching does not prove a file is authentic.',wraplength=900).pack(anchor='w',pady=(0,10))
        ibar=ttk.Frame(inbox);ibar.pack(fill='x',pady=3)
        ttk.Label(ibar,text='ZIP folder:').pack(side='left')
        self.inbox_folder=tk.StringVar(value=str(Path.home()/'Downloads'))
        ttk.Entry(ibar,textvariable=self.inbox_folder).pack(side='left',fill='x',expand=True,padx=8)
        ttk.Button(ibar,text='Browse…',command=self.inbox_browse).pack(side='left')
        ttk.Button(ibar,text='Scan ZIPs',command=self.inbox_scan).pack(side='left',padx=(8,0))
        self.inbox_info=tk.StringVar(value='Choose a SMAPI or BepInEx game and scan downloaded ZIPs (read-only).')
        ttk.Label(inbox,textvariable=self.inbox_info,wraplength=940).pack(anchor='w',pady=8)
        iarea=ttk.Frame(inbox);iarea.pack(fill='both',expand=True)
        self.inbox_tree=ttk.Treeview(iarea,columns=('zip','mod','local','download','status','note'),show='headings',selectmode='browse')
        for column,width in [('zip',205),('mod',190),('local',85),('download',85),('status',140),('note',310)]:
            self.inbox_tree.heading(column,text=column.capitalize());self.inbox_tree.column(column,width=width,stretch=(column in ('zip','note')))
        self.inbox_tree.pack(side='left',fill='both',expand=True)
        iscroll=ttk.Scrollbar(iarea,command=self.inbox_tree.yview);iscroll.pack(side='right',fill='y')
        self.inbox_tree.configure(yscrollcommand=iscroll.set)
        iactions=ttk.Frame(inbox);iactions.pack(anchor='e',pady=8)
        ttk.Button(iactions,text='Apply selected update + backup',command=self.inbox_apply).pack(side='left',padx=8)
        ttk.Button(iactions,text='Open archive folder',command=self.inbox_open_folder).pack(side='left')
        # Unified, read-only provider staging. Only SMAPI/BepInEx ZIPs may later
        # pass a separate, explicitly approved installation preflight.
        staged=ttk.Frame(self.tabs,padding=12);self.tabs.add(staged,text='  Provider Inbox  ')
        self.provider_inbox_tab=staged
        ttk.Label(staged,text='Reviewed provider downloads',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(staged,text='Provider files are verified before installation. mod.io ZIPs can be reviewed for matching SMAPI/BepInEx identities; Modrinth JARs and reviewed .mrpack modpacks target compatible Prism/MultiMC instances. All game writes require approval.',wraplength=950).pack(anchor='w',pady=(0,9))
        stagebar=ttk.Frame(staged);stagebar.pack(fill='x',pady=(0,8))
        ttk.Button(stagebar,text='Refresh downloaded files',command=self.provider_stage_refresh).pack(side='left')
        ttk.Button(stagebar,text='Review & install selected…',command=self.provider_stage_install,style='Accent.TButton').pack(side='left',padx=8)
        ttk.Button(stagebar,text='Install Modrinth JAR + required dependencies…',command=self.minecraft_profile_install).pack(side='left',padx=8)
        ttk.Button(stagebar,text='Inspect .mrpack…',command=self.minecraft_mrpack_inspect).pack(side='left',padx=8)
        ttk.Button(stagebar,text='Import .mrpack to Prism/MultiMC…',command=self.minecraft_mrpack_import).pack(side='left',padx=8)
        ttk.Button(stagebar,text='Go to Discover',command=lambda:self.show_page('Mod Websites')).pack(side='right')
        ttk.Button(stagebar,text='Check managed mod.io releases…',command=self.provider_check_modio_updates).pack(side='right',padx=(0,9))
        self.provider_stage_info=tk.StringVar(value='For SMAPI/BepInEx choose a game; for Modrinth select a JAR and a verified Prism/MultiMC profile. Nothing installs automatically.')
        ttk.Label(staged,textvariable=self.provider_stage_info,wraplength=1000).pack(anchor='w',pady=(0,8))
        stagearea=ttk.Frame(staged);stagearea.pack(fill='both',expand=True)
        self.provider_stage_tree=ttk.Treeview(stagearea,columns=('provider','archive','version','game','deps'),show='headings',selectmode='browse')
        for col,label,width in [('provider','Provider',130),('archive','Downloaded file',330),('version','Release',105),('game','Selected game',245),('deps','Dependencies',125)]:
            self.provider_stage_tree.heading(col,text=label);self.provider_stage_tree.column(col,width=width,stretch=col in ('archive','game'))
        self.provider_stage_tree.pack(side='left',fill='both',expand=True)
        stscroll=ttk.Scrollbar(stagearea,command=self.provider_stage_tree.yview);stscroll.pack(side='right',fill='y')
        self.provider_stage_tree.configure(yscrollcommand=stscroll.set)
        self.provider_stage_tree.bind('<Double-1>',lambda *_:self.provider_stage_install())
        self.provider_stage_refresh()
        # Thunderstore catalogue tab: search public listings without authentication.
        thunder=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(thunder,text='  Thunderstore Search  ')
        ttk.Label(thunder,text='Thunderstore public catalogue',style='Section.TLabel').pack(anchor='w',pady=(0,6))
        ttk.Label(thunder,text='Browse public packages. Review dependencies before installing. Only the selected ZIP is installed; previous mods are never overwritten.',wraplength=850).pack(anchor='w',pady=(0,8))
        tsbar=ttk.Frame(thunder);tsbar.pack(fill='x',pady=4)
        ttk.Label(tsbar,text='Community:').pack(side='left')
        self.ts_community=tk.StringVar(value='valheim')
        ttk.Entry(tsbar,textvariable=self.ts_community,width=23).pack(side='left',padx=6)
        ttk.Button(tsbar,text='Load catalogue',command=self.ts_load).pack(side='left')
        ttk.Label(tsbar,text='Search:').pack(side='left',padx=(20,4))
        self.ts_query=tk.StringVar()
        self.ts_query.trace_add('write',lambda *_:self.ts_filter())
        ttk.Entry(tsbar,textvariable=self.ts_query).pack(side='left',fill='x',expand=True)
        self.ts_info=tk.StringVar(value='Choose a community and load its catalogue.')
        ttk.Label(thunder,textvariable=self.ts_info).pack(anchor='w',pady=7)
        tsarea=ttk.Frame(thunder);tsarea.pack(fill='both',expand=True)
        self.ts_tree=ttk.Treeview(tsarea,columns=('name','owner','version','downloads','description'),show='headings')
        for c,w in [('name',210),('owner',150),('version',90),('downloads',100),('description',420)]:
            self.ts_tree.heading(c,text=c.capitalize());self.ts_tree.column(c,width=w,stretch=(c=='description'))
        self.ts_tree.pack(side='left',fill='both',expand=True)
        tsscroll=ttk.Scrollbar(tsarea,command=self.ts_tree.yview);tsscroll.pack(side='right',fill='y')
        self.ts_tree.configure(yscrollcommand=tsscroll.set)
        self.ts_tree.bind('<Double-1>',lambda e:self.ts_open())
        tsactions=ttk.Frame(thunder);tsactions.pack(anchor='e',pady=8)
        ttk.Button(tsactions,text='Undo last managed install',command=self.ts_undo).pack(side='left',padx=6)
        ttk.Button(tsactions,text='Install selected package',command=self.ts_install).pack(side='left',padx=6)
        ttk.Button(tsactions,text='Stage selected ZIP to Provider Inbox',command=self.ts_stage).pack(side='left',padx=6)
        ttk.Button(tsactions,text='Open package webpage',command=self.ts_open).pack(side='left')
        # v0.23: read-only reconciliation of local BepInEx packages against the
        # Thunderstore community selected in the Search tab.
        ts_updates=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(ts_updates,text='  Thunderstore Updates  ')
        ttk.Label(ts_updates,text='Installed Thunderstore packages',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(ts_updates,text='Compares exact owner/name identities in BepInEx package manifests against the currently loaded Thunderstore community. Only matching official package URLs establish a verified community. No files are changed.',wraplength=920).pack(anchor='w',pady=(0,10))
        ts_u_bar=ttk.Frame(ts_updates);ts_u_bar.pack(fill='x',pady=5)
        ttk.Button(ts_u_bar,text='Compare with loaded catalogue',command=self.ts_compare_local).pack(side='left')
        ttk.Button(ts_u_bar,text='Load catalogue and compare',command=self.ts_load_and_compare).pack(side='left',padx=8)
        ttk.Button(ts_u_bar,text='Open official mod page',command=self.ts_open_local).pack(side='left')
        ttk.Button(ts_u_bar,text='Export JSON report…',command=self.ts_export_local).pack(side='right')
        self.ts_local_info=tk.StringVar(value='Select a BepInEx game, load a Thunderstore community catalogue, then compare.')
        ttk.Label(ts_updates,textvariable=self.ts_local_info,wraplength=920).pack(anchor='w',pady=7)
        local_area=ttk.Frame(ts_updates);local_area.pack(fill='both',expand=True)
        self.ts_local_tree=ttk.Treeview(local_area,columns=('package','installed','latest','status','enabled','source','path'),show='headings',selectmode='browse')
        for label,width in [('package',215),('installed',90),('latest',90),('status',180),('enabled',75),('source',160),('path',310)]:
            self.ts_local_tree.heading(label,text=label.title());self.ts_local_tree.column(label,width=width,stretch=(label in ('package','path')))
        self.ts_local_tree.pack(side='left',fill='both',expand=True)
        local_scroll=ttk.Scrollbar(local_area,command=self.ts_local_tree.yview);local_scroll.pack(side='right',fill='y')
        self.ts_local_tree.configure(yscrollcommand=local_scroll.set)
        self.ts_local_tree.bind('<Double-1>',lambda e:self.ts_open_local())
        self.ts_local_rows=[];self.ts_local_community=None;self.ts_local_game_root=None;self.ts_compare_pending=False
        ttk.Label(tools,text='Mod management',style='Section.TLabel').pack(anchor='w',pady=(0,10))
        for label,cb,desc in [
            ('Save profile',self.save_profile,'Save enabled/disabled state for the selected game.'),
            ('Load profile',self.load_profile,'Restore a saved profile. Missing mods are not downloaded.'),
            ('Compare scans',self.show_changes,'Compare existing mods against a saved baseline.'),
            ('Export scan report',self.export_report,'Create a JSON inventory including SMAPI IDs and update keys.'),
            ('Open mods directory',self.open_dir,'Open the detected SMAPI or BepInEx folder.'),
            ('Restore a backup',self.restore_from_backup,'Safely restore a backed-up SMAPI or BepInEx mod, retaining the current copy.'),
        ]:
            line=ttk.Frame(tools);line.pack(fill='x',pady=6)
            ttk.Button(line,text=label,width=24,command=cb).pack(side='left')
            ttk.Label(line,text=desc).pack(side='left',padx=14)
        self.status=tk.StringVar(value='Select a game to inspect existing mods.')
        footer=ttk.Frame(main,style='Header.TFrame',padding=(14,6));footer.pack(fill='x')
        ttk.Label(footer,text='●',style='Online.TLabel').pack(side='left',padx=(0,7))
        ttk.Label(footer,textvariable=self.status,style='Footer.TLabel').pack(side='left')
        ttk.Label(footer,text='UniMod v0.55 test12   •   Local installation',style='Footer.TLabel').pack(side='right')
        for label,_ in self.primary_workspaces:self.nav_list.insert('end',label)
        self.configure_tool_menu()
        self.fill_games();self.auto_detect(silent=True)
        self.tabs.select(installed)
        self.sync_workspace()
        self.after(150,self.scan_global_library)
        if incoming_nxm is not None:
            self.after(250, lambda: self.nexus_enqueue_nxm(incoming_nxm, from_browser=True))
        self.after(100,self._poll_external_requests)
    def scan_global_library(self):
        if self.global_scan_busy:return
        self.global_scan_busy=True
        self.global_info.set('Scanning registered game installations (read-only)…')
        snapshot=[dict(g) for g in self.data.get('games',[])]
        if not hasattr(self,'_global_queue'):self._global_queue=queue.Queue()
        self._global_token=getattr(self,'_global_token',0)+1
        token=self._global_token
        def worker():
            try:report=global_mod_library(snapshot);error=None
            except Exception as exc:report=None;error=str(exc)
            self._global_queue.put((token,report,error))
        threading.Thread(target=worker,daemon=True).start()
        self.after(50,lambda:self.poll_global_library(token))

    def poll_global_library(self,token):
        if token!=self._global_token:return
        try:finished,report,error=self._global_queue.get_nowait()
        except queue.Empty:
            self.after(50,lambda:self.poll_global_library(token));return
        if finished!=token:return
        self.global_scan_busy=False
        if error:
            self.global_info.set('Scan failed: '+error);return
        self.set_global_library(report)

    def set_global_library(self,report):
        self.global_report=report
        self.fill_global_library()

    def filtered_global_library(self):
        if not self.global_report:return []
        query=self.global_query.get().strip().casefold()
        state=self.global_filter.get()
        result=[]
        for mod in self.global_report['mods']:
            if state=='Enabled' and not mod['enabled']:continue
            if state=='Disabled' and mod['enabled']:continue
            if state=='Known source' and not mod['source_url']:continue
            if state=='Needs source' and mod['source_url']:continue
            if state=='Unmanaged' and mod['source_status']!='Unmanaged':continue
            if query and not any(query in str(mod[field]).casefold() for field in ('game','mod','loader','version','source','package_type')):continue
            result.append(mod)
        return result

    def fill_global_library(self):
        if not hasattr(self,'global_tree'):return
        self.global_tree.delete(*self.global_tree.get_children())
        self.global_visible=self.filtered_global_library()
        for index,mod in enumerate(self.global_visible):
            self.global_tree.insert('','end',iid=str(index),values=(mod['game'],mod['mod'],mod['loader'],mod['version'],
                 'Review folder' if mod['source_status']=='Needs review' else ('Enabled' if mod['enabled'] else 'Disabled'),mod['source'],mod['package_type']))
        if self.global_report:
            report=self.global_report
            self.global_info.set(f"{len(self.global_visible)} / {len(report['mods'])} entries shown · {report['games_scanned']} games scanned · {report['linked']} known sources · {report['unmanaged']} unmanaged packages · {len(report['problems'])} inaccessible/error games. Mod files unchanged.")
        else:self.global_info.set('Scan all registered games to view existing mods. Nothing is modified.')

    def open_global_mod(self):
        sel=self.global_tree.selection()
        if not sel:return
        mod=self.global_visible[int(sel[0])]
        for i,game in enumerate(self.data.get('games',[])):
            try:same=(str(Path(game['root']).resolve())==mod['game_root'])
            except (OSError,ValueError,RuntimeError):same=False
            if not same:continue
            self.game_list.selection_clear(0,'end')
            self.game_list.selection_set(i);self.game_list.see(i)
            self.select_game()
            self.tabs.select(1) # Installed Mods is tab 1; Global Library is tab 2.
            for idx,local in enumerate(self.rows):
                package_path=Path(mod['path']);path=Path(local['path'])
                if path==package_path or (package_path.is_dir() and path.is_relative_to(package_path)):
                    if self.tree.exists(str(idx)):
                        self.tree.selection_set(str(idx));self.tree.see(str(idx))
                        self.describe_selected()
                    break
            return
        self.global_info.set('That game is no longer registered. Rescan the library.')

    def export_global_library_ui(self):
        if not self.global_report:
            messagebox.showinfo('Scan first','Scan the registered games before exporting.',parent=self);return
        dest=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='unimod-all-games.csv',filetypes=[('CSV','*.csv')],parent=self)
        if not dest:return
        try:
            count=export_global_mod_library(dest,{'mods':self.filtered_global_library()})
            self.global_info.set(f'Exported {count} visible packages to {dest}. Contains local filesystem paths; review before sharing.')
        except OSError as exc:messagebox.showerror('Export failed',str(exc),parent=self)

    def show_other_launchers(self):
        self.launcher_inventory=launcher_game_inventory()
        managed={str(Path(g['root']).resolve(strict=False)) for g in self.data['games']}
        self.launcher_tree.delete(*self.launcher_tree.get_children())
        for g in self.launcher_inventory:
            self.launcher_tree.insert('','end',values=(g['name'],g['launcher'],g['store'],
                g['kind'].upper(),'Yes' if g['root'] in managed else 'No',g['root']))
        self.launcher_info.set(f'{len(self.launcher_inventory)} eligible modded game(s) found in Heroic / Lutris. Unmodded games are intentionally hidden.')

    def import_other_launchers(self):
        self.auto_detect(silent=True)
        self.show_other_launchers()
        self.status.set('Detected Steam, Heroic and Lutris installs. Existing game files were not modified.')

    def export_other_launchers(self):
        if not self.launcher_inventory:self.show_other_launchers()
        dest=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='unimod-launchers.json',parent=self)
        if not dest:return
        try:
            Path(dest).write_text(json.dumps(self.launcher_inventory,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            self.status.set('Saved launcher inventory to '+dest)
        except OSError as exc:messagebox.showerror('Export failed',str(exc),parent=self)

    def show_steam_libraries(self):
        entries=steam_library_inventory()
        self.library_tree.delete(*self.library_tree.get_children())
        for item in entries:self.library_tree.insert('', 'end',values=(item['path'],item['origin']))
        self.library_info.set(f'{len(entries)} Steam library location(s) found. Entries labelled Custom are saved between launches.')

    def add_steam_library(self):
        selected=filedialog.askdirectory(title='Choose Steam library or steamapps folder')
        if not selected:return
        apps=normalize_steam_library(selected)
        if not apps:
            messagebox.showerror('Not a Steam library','Choose a folder containing steamapps/common, or an existing steamapps folder containing common.',parent=self)
            return
        save_custom_steam_libraries(load_custom_steam_libraries()+[str(apps)])
        self.show_steam_libraries()
        self.status.set(f'Saved Steam library: {apps}. Select Scan games from libraries to import games.')

    def remove_steam_library(self):
        chosen=self.library_tree.selection()
        if not chosen:return
        location=self.library_tree.item(chosen[0],'values')[0]
        current=load_custom_steam_libraries()
        kept=[p for p in current if str(normalize_steam_library(p))!=location]
        if len(current)==len(kept):
            messagebox.showinfo('Automatically detected','This library is automatically detected and has no removable custom entry.',parent=self)
            return
        save_custom_steam_libraries(kept)
        self.show_steam_libraries()

    def scan_libraries(self):
        self.auto_detect()
        self.show_steam_libraries()

    def attach_tooltip(self, widget, label):
        """Accessible tooltip on icon-only navigation; no external UI package."""
        tooltip={'window':None}
        def enter(_):
            if tooltip['window'] is not None:return
            tip=tk.Toplevel(self);tip.wm_overrideredirect(True)
            try:tip.wm_attributes('-topmost',True)
            except tk.TclError:pass
            tip.configure(bg='#25364b')
            ttk.Label(tip,text=label,style='Tooltip.TLabel',padding=(9,5)).pack()
            tip.wm_geometry(f'+{widget.winfo_rootx()+widget.winfo_width()+7}+{widget.winfo_rooty()+3}')
            tooltip['window']=tip
        def leave(_):
            if tooltip['window'] is not None:
                tooltip['window'].destroy();tooltip['window']=None
        widget.bind('<Enter>',enter);widget.bind('<Leave>',leave)

    def change_game_combo(self,event=None):
        idx=self.game_combo.current()
        if idx<0:return
        self.game_list.selection_clear(0,'end')
        self.game_list.selection_set(idx)
        self.select_game()

    def toggle_details(self):
        if self.details_visible.get():
            self.mod_body.forget(self.detail_pane)
            self.details_visible.set(False)
        else:
            self.mod_body.add(self.detail_pane,weight=2)
            self.details_visible.set(True)
            self.describe_selected()

    def installed_double_click(self,event):
        region=self.tree.identify_region(event.x,event.y)
        if region=='heading':return
        iid=self.tree.identify_row(event.y)
        if not iid:return
        if iid in self.family_rows:
            self.tree.item(iid,open=not self.tree.item(iid,'open'))
            return 'break'
        self.tree.selection_set(iid)
        if not self.details_visible.get():self.toggle_details()
        return 'break'

    def installed_status_click(self,event):
        # Column #4 is the state; a single deliberate click toggles the
        # selected component, not its visual family and not unrelated folders.
        if self.tree.identify_region(event.x,event.y)!='cell':return
        if self.tree.identify_column(event.x)!='#4':return
        iid=self.tree.identify_row(event.y)
        if not iid or iid in self.family_rows:return
        self.tree.selection_set(iid)
        if self.picked():self.toggle()

    def installed_toggle_key(self,event):
        if self.tree.selection() and self.picked():self.toggle()
        return 'break'

    def _tab_with_name(self,name):
        """Resolve a known internal notebook page without exposing all pages in the sidebar."""
        for tab in self.tabs.tabs():
            if self.tabs.tab(tab,'text').strip()==name:return tab
        raise ValueError('Unknown UniMod page: '+str(name))

    def show_page(self,name):
        self.tabs.select(self._tab_with_name(name))

    def configure_tool_menu(self):
        """Advanced tools are grouped in one menu instead of 17 sidebar entries."""
        groups=(
            ('Mod maintenance',('Packages & Loose DLLs','Installation Audit','Dependencies','Profiles & Tools','Scan Changes')),
            ('Sources & updates',('Updates Available','Source Matching','Nexus Updates','Thunderstore Search','Thunderstore Updates')),
            ('Games & launchers',('Game Diagnostics','Steam Libraries','Other Launchers')),
        )
        menu=tk.Menu(self.tools_button,tearoff=False,background='#1e2c3c',foreground='#e7effb',
                     activebackground='#345783',activeforeground='#ffffff',borderwidth=0)
        self.tool_groups=groups
        for title,items in groups:
            sub=tk.Menu(menu,tearoff=False,background='#1e2c3c',foreground='#e7effb',
                        activebackground='#345783',activeforeground='#ffffff',borderwidth=0)
            for item in items:
                sub.add_command(label=item,command=lambda dest=item:self.show_page(dest))
            menu.add_cascade(label=title,menu=sub)
        self.tools_button.configure(menu=menu)
        self.tool_menu=menu

    def select_workspace(self):
        selection=self.nav_list.curselection()
        if not selection:return
        idx=int(selection[0])
        if 0<=idx<len(self.primary_workspaces):
            self.show_page(self.primary_workspaces[idx][1])

    def sync_workspace(self):
        if not hasattr(self,'tabs') or not self.tabs.tabs():return
        try:page=self.tabs.tab(self.tabs.select(),'text').strip()
        except tk.TclError:return
        for key,button in getattr(self,'rail_buttons',{}).items():
            button.configure(style='RailActive.TButton' if page==key else 'Rail.TButton')
        if hasattr(self,'tools_button'):
            self.tools_button.configure(text=('Tools  ▾' if page in self.rail_buttons else f'{page}  ▾'))

    def apply_theme(self, theme):
        """Refined native Tk theme; all graphics and styles independently authored."""
        style=ttk.Style(self)
        bg='#121b2a'; panel='#182437';surface='#263347'; sidebar='#0e1623'
        fg='#e8f1ff';muted='#a4b5cc';accent='#6d9eff';muted_2='#8196b0'
        self.configure(background=bg)
        style.configure('TFrame',background=bg)
        style.configure('Header.TFrame',background=sidebar)
        style.configure('Rail.TFrame',background='#0c1524')
        style.configure('Sidebar.TFrame',background=sidebar)
        style.configure('Panel.TFrame',background=panel)
        style.configure('Card.TFrame',background=panel)
        style.configure('TLabel',background=bg,foreground=fg,font=('DejaVu Sans',10))
        style.configure('Title.TLabel',background=bg,foreground=fg,font=('DejaVu Sans',22,'bold'))
        style.configure('Section.TLabel',background=bg,foreground=fg,font=('DejaVu Sans',12,'bold'))
        style.configure('Subtle.TLabel',background=bg,foreground=muted,font=('DejaVu Sans',10))
        style.configure('Muted.TLabel',background=panel,foreground=muted,font=('DejaVu Sans',10))
        style.configure('Metric.TLabel',background=panel,foreground=accent,font=('DejaVu Sans',27,'bold'))
        style.configure('CardCaption.TLabel',background=panel,foreground=muted,font=('DejaVu Sans',9,'bold'))
        style.configure('BrandIcon.TLabel',background=sidebar,foreground=accent,font=('DejaVu Sans',25,'bold'))
        style.configure('Brand.TLabel',background=sidebar,foreground=fg,font=('DejaVu Sans',13,'bold'))
        style.configure('TopMuted.TLabel',background=sidebar,foreground=muted,font=('DejaVu Sans',8,'bold'))
        style.configure('Footer.TLabel',background=sidebar,foreground=muted,font=('DejaVu Sans',9))
        style.configure('Online.TLabel',background=sidebar,foreground='#4dcc8e',font=('DejaVu Sans',12))
        style.configure('Tooltip.TLabel',background='#25364b',foreground=fg,font=('DejaVu Sans',10))
        style.configure('HeaderMuted.TLabel',background=sidebar,foreground=muted_2,font=('DejaVu Sans',8,'bold'))
        style.configure('SideHeading.TLabel',background=sidebar,foreground=muted_2,font=('DejaVu Sans',9,'bold'))
        style.configure('SideNote.TLabel',background=sidebar,foreground=muted_2,font=('DejaVu Sans',9))
        style.configure('SideTool.TMenubutton',background=surface,foreground=fg,font=('DejaVu Sans',10),padding=(10,11))
        style.map('SideTool.TMenubutton',background=[('active','#354a64')])
        style.configure('PanelCaption.TLabel',background=panel,foreground=muted_2,font=('DejaVu Sans',9,'bold'))
        style.configure('PanelMuted.TLabel',background=panel,foreground=accent,font=('DejaVu Sans',10))
        style.configure('PanelValue.TLabel',background=panel,foreground=fg,font=('DejaVu Sans',10))
        style.configure('DetailName.TLabel',background=panel,foreground=fg,font=('DejaVu Sans',15,'bold'))
        style.configure('TNotebook',background=bg,borderwidth=0)
        style.layout('Sidebar.TNotebook.Tab', [])
        style.configure('TNotebook.Tab',background=surface,foreground=fg,padding=(13,8))
        style.map('TNotebook.Tab',background=[('selected','#354d70')],foreground=[('selected','#ffffff')])
        style.configure('TButton',background=surface,foreground=fg,padding=(10,6),font=('DejaVu Sans',10),borderwidth=0)
        style.configure('Top.TButton',background=sidebar,foreground=fg,padding=(11,6),font=('DejaVu Sans',9))
        style.configure('Top.TMenubutton',background=sidebar,foreground=fg,padding=(8,6))
        style.configure('Top.TCombobox',fieldbackground=surface,foreground=fg,background=surface)
        style.configure('Rail.TButton',background='#0c1524',foreground='#9eb0cc',padding=(7,10),font=('DejaVu Sans',15))
        style.configure('RailActive.TButton',background='#29436b',foreground='#9fc4ff',padding=(7,10),font=('DejaVu Sans',15))
        style.map('Rail.TButton',background=[('active','#1c304b')])
        style.map('RailActive.TButton',background=[('active','#315485')])
        style.map('TButton',background=[('active','#344964'),('pressed','#314b71')],foreground=[('disabled',muted_2)])
        style.configure('Side.TButton',background=sidebar,foreground=muted,padding=(8,8))
        style.map('Side.TButton',background=[('active',surface)])
        style.configure('Accent.TButton',background=accent,foreground='#101722',padding=(13,9),font=('DejaVu Sans',10,'bold'))
        style.map('Accent.TButton',background=[('active','#a0c7ff'),('pressed','#528bdf')])
        style.configure('TEntry',fieldbackground=surface,foreground=fg,padding=(10,7),borderwidth=0)
        style.configure('TCombobox',fieldbackground=surface,foreground=fg,background=surface,padding=(7,5))
        style.map('TCombobox',fieldbackground=[('readonly',surface)],foreground=[('readonly',fg)])
        style.configure('Treeview',background=panel,fieldbackground=panel,foreground=fg,rowheight=33,
            font=('DejaVu Sans',10),borderwidth=0)
        style.map('Treeview',background=[('selected','#315781')],foreground=[('selected','#ffffff')])
        style.configure('Mods.Treeview',background=panel,fieldbackground=panel,foreground=fg,rowheight=39,font=('DejaVu Sans',10),borderwidth=0)
        style.map('Mods.Treeview',background=[('selected','#344d71')],foreground=[('selected','#ffffff')])
        style.configure('Treeview.Heading',background='#26364a',foreground='#c5d6eb',font=('DejaVu Sans',10,'bold'),padding=(6,9),borderwidth=0)
        style.map('Treeview.Heading',background=[('active','#354a64')])
        style.configure('TScrollbar',background='#33445b',troughcolor=panel,arrowcolor=muted)
        style.configure('Vertical.TScrollbar',background='#33445b',troughcolor='#151e2b',
            arrowcolor='#93a9c7',borderwidth=0,elementborderwidth=0,arrowsize=11,relief='flat')
        style.map('Vertical.TScrollbar',background=[('active','#3c536e')])
        style.configure('TSeparator',background='#334154')

    def run_game_diagnostics(self):
        game=self.current()
        if not game:
            self.diag_info.set('Select a game first.')
            return
        self.diag_tree.delete(*self.diag_tree.get_children())
        self.diagnostic_report=None;self.diagnostic_game_root=None
        self.diag_info.set('Checking local game and Steam folders…')
        root=game['root'];snapshot=dict(game)
        if not hasattr(self,'_diag_queue'):self._diag_queue=queue.Queue()
        self._diag_token=getattr(self,'_diag_token',0)+1
        token=self._diag_token
        def worker():
            try:report=game_diagnostics(snapshot);error=None
            except Exception as exc:report=None;error=str(exc)
            # The worker does not touch Tk, which can be destroyed while scanning.
            self._diag_queue.put((token,root,report,error))
        threading.Thread(target=worker,daemon=True).start()
        self.after(50,lambda:self._poll_diagnostics(token))

    def _poll_diagnostics(self,token):
        if token!=self._diag_token:return
        while True:
            try:finished,root,report,error=self._diag_queue.get_nowait()
            except queue.Empty:break
            if finished==token:
                self.game_diagnostics_done(root,report,error)
                return
        self.after(50,lambda:self._poll_diagnostics(token))

    def game_diagnostics_done(self,root,report,error):
        if not self.current() or self.current()['root']!=root:return
        if error:
            self.diag_info.set('Diagnostics could not complete: '+error)
            return
        self.diagnostic_report=report;self.diagnostic_game_root=root
        for item in report['checks']:
            self.diag_tree.insert('','end',values=(item['check'],item['status'],item['details']))
        warnings=sum(x['status'] in ('Missing','Warning') for x in report['checks'])
        self.diag_info.set(f'{len(report["checks"])} checks complete; {warnings} warning(s). Informational statuses are not failures.')

    def export_game_diagnostics(self):
        if not self.diagnostic_report or not self.current() or self.current()['root']!=self.diagnostic_game_root:
            messagebox.showinfo('Run diagnostics','Run diagnostics for the selected game first.');return
        target=filedialog.asksaveasfilename(defaultextension='.json',initialfile='unimod-game-diagnostics.json',filetypes=[('JSON report','*.json')])
        if not target:return
        try:
            export_diagnostics(target,self.diagnostic_report)
            self.diag_info.set('Exported diagnostics: '+target+' (contains local installation paths).')
        except OSError as exc:messagebox.showerror('Export failed',str(exc))

    def focus_filter(self):
        self.tabs.select(1)
        self.filter_entry.focus_set()
        self.filter_entry.select_range(0,'end')

    def update_dashboard(self):
        game=self.current()
        mods=self.rows if game else []
        packages=mod_packages(game,mods) if game else []
        health=existing_mod_health(game,mods) if game else {}
        self.overview_subtitle.set((f"{game['name']}  ·  {game['kind'].upper()}  ·  {game['root']}" if game else 'Use Scan installed games or Add game to begin.'))
        for label,key in [('Mod folders','folders'),('Enabled folders','enabled_folders'),('Indexed IDs','mods'),('Metadata pending','unmanaged'),('Known sources','sources'),('Audit warnings','issues')]:
            self.stat_labels[label].configure(text=str(health[key]) if game else '—')
        self.overview_tree.delete(*self.overview_tree.get_children())
        self.pkg_tree.delete(*self.pkg_tree.get_children())
        for group in packages:
            self.overview_tree.insert('','end',values=(group['name'],group['kind'],group['dll_count'] or '—',('Inspect' if group.get('is_folder_only') else ('Enabled' if group['enabled'] else 'Disabled'))))
            self.pkg_tree.insert('','end',values=(group['name'],group['kind'],group['version'],'Yes' if group['enabled'] else 'No',group['dll_count'] or '—',group['path']))
        self.pkg_info.set(f"{len(packages)} installed folders / packages; {health.get('unmanaged',0)} not yet indexed by ID. All remain visible. Unindexed folders are read-only until safely identified.")

    def export_packages(self):
        game=self.current()
        if not game:return
        output=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='unimod-packages.csv',filetypes=[('CSV','*.csv')])
        if not output:return
        records=mod_packages(game,self.rows)
        with Path(output).open('w',encoding='utf-8',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=('name','kind','version','enabled','dll_count','path','source'))
            writer.writeheader();writer.writerows(records)
        self.status.set(f'Exported {len(records)} package groups: {output}')

    def inbox_browse(self):
        folder=filedialog.askdirectory(title='Choose downloaded mod ZIP folder',initialdir=self.inbox_folder.get())
        if folder:self.inbox_folder.set(folder)
    def inbox_scan(self):
        game=self.current()
        if not game:
            messagebox.showinfo('Choose a game','Choose a game installation first.');return
        if game['kind'] not in ('smapi','bepinex'):
            messagebox.showinfo('Unsupported','The update inbox supports SMAPI and BepInEx only.');return
        if self.inbox_busy:return
        self.inbox_busy=True
        self.inbox_info.set('Inspecting downloaded archives (no files are changed)…')
        root=str(Path(game['root']).resolve());folder=self.inbox_folder.get()
        def worker():
            try:result=scan_update_inbox(game,folder);err=None
            except Exception as exc:result=[];err=str(exc)
            self.after(0,lambda:self.inbox_scanned(root,result,err))
        threading.Thread(target=worker,daemon=True).start()
    def inbox_scanned(self,root,results,error):
        self.inbox_busy=False
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=root:return
        self.inbox_results=results
        self.inbox_tree.delete(*self.inbox_tree.get_children())
        for i,r in enumerate(results):
            self.inbox_tree.insert('','end',iid=str(i),values=(Path(r['archive']).name,r['installed'] or r['name'],r['local_version'],r['version'],r['status'],r['note']))
        if error:self.inbox_info.set('Scan failed: '+error);return
        ready=sum(r['status']=='Ready to update' for r in results)
        review=sum(r['status']=='Review version' for r in results)
        self.inbox_info.set(f'{len(results)} ZIPs scanned: {ready} newer updates, {review} need version review. Only unambiguous single-mod ZIPs can be updated. No files changed.')
    def inbox_open_folder(self):
        selected=self.inbox_tree.selection()
        if selected:
            r=self.inbox_results[int(selected[0])]
            subprocess.Popen(['xdg-open',str(Path(r['archive']).parent)])
    def inbox_apply(self):
        game=self.current();selected=self.inbox_tree.selection()
        if not game or not selected:return
        if self.inbox_busy:return
        match=self.inbox_results[int(selected[0])]
        if match['status'] not in ('Ready to update','Review version'):
            messagebox.showinfo('Cannot apply',match['note'] or match['status']);return
        if not messagebox.askyesno('Apply downloaded ZIP?',
                f"Replace {match['installed']} ({match['local_version']}) with {match['name']} ({match['version']})?\n\n"
                f"Archive: {match['archive']}\n\nMatching metadata does NOT verify authenticity. Only proceed with a ZIP from a trusted official source. Close the game first. UniMod keeps a recovery backup."):
            return
        self.inbox_busy=True;self.inbox_info.set('Installing selected ZIP and creating recovery backup…')
        root=str(Path(game['root']).resolve())
        def worker():
            try:backup=apply_downloaded_update(game,match);err=None
            except Exception as exc:backup=None;err=str(exc)
            self.after(0,lambda:self.inbox_applied(root,backup,err))
        threading.Thread(target=worker,daemon=True).start()
    def inbox_applied(self,root,backup,error):
        self.inbox_busy=False
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=root:return
        if error:
            self.inbox_info.set('Update refused/failed: '+error)
            messagebox.showerror('Update failed',error);return
        self.refresh();self.inbox_scan()
        messagebox.showinfo('Mod updated','Downloaded ZIP installed. Previous mod backed up at:\n'+str(backup))
    def unified_render(self):
        """Present all installed families, even before any online check."""
        if not hasattr(self,'unified_tree'):return
        game=self.current()
        extra=smapi_folder_entries(game,self.rows) if game and game.get('kind')=='smapi' else []
        self.unified_rows=match_update_downloads(unified_update_rows(game,self.rows,self.unified_nexus,self.unified_github,extra),self.unified_downloads if game and self.unified_download_root==str(Path(game['root']).resolve()) else [])
        search=self.unified_query.get().strip().casefold()
        mode=self.unified_filter.get()
        self.unified_tree.delete(*self.unified_tree.get_children())
        matched=0
        for i,item in enumerate(self.unified_rows):
            status=item['status']
            if mode=='Updates available' and status!='Update available':continue
            if mode=='Not checked' and status!='Not checked':continue
            if mode=='Up to date' and status not in ('Up to date','Local newer'):continue
            if mode=='Needs attention' and status not in ('Source needed','ID conflict','Check failed','Version review'):continue
            if search and search not in (' '.join((item['name'],item['source'],status,item['identity']))).casefold():continue
            self.unified_tree.insert('','end',iid=str(i),values=(item['name'],item['version'],item['remote_version'] or '—',item['source'],status,item['components'],item['download_status']))
            matched+=1
        count=sum(r['status']=='Update available' for r in self.unified_rows)
        checked=sum(r['status'] in ('Update available','Up to date','Local newer','Version review') for r in self.unified_rows)
        if game:
            self.unified_info.set(f'{len(self.unified_rows)} distinct mod/source entries · {count} confirmed update(s) · {checked} version-checked · showing {matched}. '
                                  f'{sum(r["local_archive"] is not None for r in self.unified_rows)} downloaded update(s) ready for review. Unidentified mods are not assumed current.')
        else:self.unified_info.set('Select a game to review existing mods.')

    def unified_scan_downloads(self, silent=False):
        game=self.current()
        if not game or game['kind'] not in ('smapi','bepinex'):
            if not silent:messagebox.showinfo('Select a supported game','Choose an SMAPI or BepInEx game first.',parent=self)
            return
        if self.unified_download_busy or self.unified_install_busy:return
        self.unified_download_busy=True
        root=str(Path(game['root']).resolve());folder=self.inbox_folder.get()
        if not silent:self.unified_info.set('Finding downloaded ZIPs for your installed mods… read-only')
        def worker():
            try:matches=scan_update_inbox(game,folder);error=None
            except Exception as exc:matches=[];error=str(exc)
            self._unified_events.put(('downloads',root,(matches,error)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def unified_select_ready(self):
        """Only select clearly newer one-to-one archives from *visible* rows."""
        ready=[iid for iid in self.unified_tree.get_children('')
               if self.unified_rows[int(iid)].get('download_status')=='Ready for review']
        self.unified_tree.selection_set(ready)
        self.unified_info.set(f'{len(ready)} visible exact ZIP update(s) selected. Choose Review & Install batch to inspect all of them.')

    def unified_review_batch(self):
        game=self.current()
        if not game or not self.unified_tree.selection():return
        if self.unified_install_busy or self.unified_download_busy or self.inbox_busy:
            messagebox.showinfo('Please wait','A scan or installation is still running.',parent=self);return
        picked=[self.unified_rows[int(iid)] for iid in self.unified_tree.selection()]
        self.unified_install_busy=True
        root=str(Path(game['root']).resolve())
        self.unified_info.set(f'Verifying {len(picked)} ZIPs before batch review… no files changed')
        def worker():
            try:plan=prepare_update_batch(game,picked);error=None
            except Exception as exc:plan=None;error=str(exc)
            self._unified_events.put(('batch_plan',root,(plan,error)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def _approve_update_batch(self,root,plan):
        lines=[f"Review {len(plan['updates'])} exact mod updates:", '']
        for entry in plan['updates']:
            m=entry['match']
            lines.append(f"• {entry['name']}: {m['local_version']} → {m['version']} ({Path(m['archive']).name})")
            if entry['dependency_issues']:
                lines.append(f"    ⚠ {len(entry['dependency_issues'])} possible NEW required dependency issue(s)")
            elif not entry['dependency_supported']:
                lines.append('    Dependency check unavailable for BepInEx')
        lines+=['','Every ZIP must match exactly. ZIP IDs do not prove publisher authenticity.',
                'Close the game before proceeding. Old mod folders are backed up.',
                'If a later update fails, UniMod will attempt to restore earlier ones.',
                'A crash or power outage cannot be fully rolled back.','',
                'Install all selected updates?']
        if not messagebox.askyesno('Review batch — backups & rollback','\n'.join(lines),parent=self):
            self.unified_install_busy=False
            self.unified_info.set('Batch cancelled — no files changed.')
            return
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=root:
            self.unified_install_busy=False
            self.unified_info.set('Game changed; batch cancelled.');return
        self.unified_info.set(f"Installing {len(plan['updates'])} approved mod updates…")
        def worker():
            try:result=execute_update_batch(game,plan);error=None
            except Exception as exc:result=None;error=str(exc)
            self._unified_events.put(('batch_installed',root,(result,error)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def unified_review_install(self):
        game=self.current();row=self.unified_picked()
        if not game or not row:return
        if self.unified_install_busy or self.unified_download_busy or self.inbox_busy:
            messagebox.showinfo('Please wait','An update or scan is still running.',parent=self);return
        match=row.get('local_archive')
        if not match:
            messagebox.showinfo('No unique ready ZIP',
                'Choose Find downloaded updates. If several ZIPs match, open the full Update Inbox to select one. No mod files were changed.',parent=self)
            return
        # Re-read the local archive and version before presenting any approval.
        try:
            if game['kind']=='smapi':
                now=match_downloaded_smapi_archive(game,match['archive'])
            else:now=match_downloaded_bepinex_archive(game,match['archive'])
            if now.get('status') not in ('Ready to update','Review version') or any(
                str(now.get(k,''))!=str(match.get(k,'')) for k in ('uid','version','target_path','sha256')):
                raise ValueError('Mod/archive changed since the last scan; scan again before installing')
            preflight=update_dependency_preflight(game,now,self.rows)
        except Exception as exc:
            messagebox.showerror('Rescan needed',str(exc),parent=self);return
        warnings=preflight['new_issues']
        lines=[f"Mod: {now['installed']}",f"Current: {now['local_version']}  →  ZIP: {now['version']}",
               f"Archive: {Path(now['archive']).name}", '',
               'SMAPI UniqueID / BepInEx package metadata matched. This does NOT verify who published the ZIP.',
               'Only use archives obtained from trusted official mod pages.',
               'Close the game before installing. UniMod will back up the original mod.']
        if warnings:
            lines += ['',f'WARNING: {len(warnings)} NEW required dependency issue(s) may result:']
            lines += [f"• {w['dependency']}: {w['status']} (required by {w['mod']})" for w in warnings[:8]]
            if len(warnings)>8:lines.append(f'… plus {len(warnings)-8} more')
        elif not preflight['supported']:
            lines += ['',preflight['note']]
        elif now['status']=='Review version':
            lines += ['','Version strings are not comparable. Review them manually.']
        else:lines += ['','No NEW missing/invalid required SMAPI dependencies detected.']
        if not messagebox.askyesno('Review & Install — recovery backup', '\n'.join(lines)+'\n\nInstall this update now?',parent=self):return
        self.unified_install_busy=True
        root=str(Path(game['root']).resolve())
        self.unified_info.set('Installing approved ZIP with recovery backup…')
        def worker():
            try:backup=apply_downloaded_update(game,now);error=None
            except Exception as exc:backup=None;error=str(exc)
            self._unified_events.put(('installed',root,(backup,error)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def unified_picked(self):
        selection=self.unified_tree.selection()
        if not selection:return None
        try:return self.unified_rows[int(selection[0])]
        except (ValueError,IndexError):return None

    def unified_open_page(self):
        row=self.unified_picked()
        if row and row.get('url'):webbrowser.open(row['url'])
        else:messagebox.showinfo('Source not identified','This mod needs a confirmed source page. Use Resolve missing sources; UniMod will not guess.',parent=self)

    def unified_choose_file(self):
        row=self.unified_picked();game=self.current()
        if not row or not game:return
        ref=nexus_reference(game,row['mod'])
        if not ref or 'error' in ref:
            messagebox.showinfo('Nexus source required','Select a mod with a verified Nexus page. Other sources open in your browser.',parent=self);return
        key=self.nexus_key.get().strip()
        if not key:
            messagebox.showinfo('Connect to Nexus','Use Nexus account / developer options first. Browser download links also work from Nexus itself.',parent=self)
            return
        if self.nexus_running:return
        self.nexus_running=True
        self.unified_info.set('Checking available Nexus files — this does not download anything…')
        def worker():
            try:
                data=nexus_api_json(nexus_integr.mod_files_url(ref['game_domain'],ref['mod_id']),key)
                files=nexus_integr.normalize_files(data);error=None
            except Exception as exc:files=[];error=str(exc).replace(key,'[redacted]')
            self._unified_events.put(('files',None,(ref,files,error)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def unified_identify_sources(self):
        """Open only the identity workflow supported by the selected game."""
        game=self.current()
        if not game:
            messagebox.showinfo('Choose a game','Select a game first.',parent=self)
            return
        if game.get('kind')=='smapi':
            return self.identify_smapi_sources()
        # BepInEx/MelonLoader do not publish SMAPI UniqueIDs; do not query
        # Stardew's SMAPI catalogue or suggest it can resolve these mods.
        return self.show_page('Source Matching')

    def sync_unified_source_action(self):
        button=getattr(self,'unified_source_button',None)
        if button is None:return
        game=self.current()
        if not game:
            button.configure(text='Select game to resolve sources',state='disabled')
        elif game.get('kind')=='smapi':
            button.configure(text='Identify SMAPI sources automatically',state='normal')
        else:
            button.configure(text='Resolve sources for this game…',state='normal')

    def identify_smapi_sources(self, continue_check=False):
        game=self.current()
        if not game or game.get('kind')!='smapi':
            messagebox.showinfo('Select Stardew Valley','Automatic SMAPI source identification is for Stardew Valley.',parent=self);return
        if self.unified_running:return
        # Network lookup is intended only for still-unknown exact UniqueIDs.
        unresolved=[m for m in self.rows if m.get('uid') and str(m.get('uid')).casefold() not in smapi_catalogue.BUNDLED_SMAPI_IDS and not assigned_source(game,m)
                    and nexus_reference(game,m,include_cache=False) is None
                    and cached_smapi_reference(game,m) is None]
        if not unresolved:
            self.unified_info.set('All known mod IDs are matched or do not need SMAPI lookup.')
            if continue_check:self.unified_check(skip_resolve=True)
            return
        # The automatic pre-check respects a 7-day negative lookup cache.
        # Clicking 'Identify mod sources automatically' is an explicit refresh.
        todo,skipped=smapi_lookup_cache.pending(
            unresolved,SMAPI_NEGATIVE_CACHE,lambda m:source_identity(game,m),
            force=not continue_check)
        if not todo:
            self.unified_info.set(f'SMAPI catalogue had no source for {skipped} unchanged IDs in the last 7 days; skipped repeated lookup. Use Identify mod sources automatically to force a fresh search.')
            if continue_check:self.unified_check(skip_resolve=True)
            return
        root=str(Path(game['root']).resolve())
        self.unified_running=True
        self.unified_info.set(f'Looking up {len(todo)} SMAPI UniqueIDs' + (f' ({skipped} recent no-matches skipped)' if skipped else '') + ' — no Nexus key, no downloads…')
        def worker():
            try:diagnostic=smapi_catalogue.resolve_smapi_ids(todo,diagnostics=True);error=None
            except Exception as exc:diagnostic={'matches':{},'requested':len(todo),'returned':0};error=f'{type(exc).__name__}: {str(exc)[:180]}'
            self._unified_events.put(('smapi_sources',root,(diagnostic,error,continue_check,todo,skipped)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def unified_check(self, skip_resolve=False):
        game=self.current()
        if not game:
            messagebox.showinfo('Choose a game','Select your game first.',parent=self);return
        if self.unified_running:return
        if not skip_resolve and game.get('kind')=='smapi':
            self.identify_smapi_sources(continue_check=True)
            return
        mods=list(self.rows);root=str(Path(game['root']).resolve())
        nexus=[m for m in mods if (r:=nexus_reference(game,m)) and 'error' not in r]
        nexus_to_check=[m for m in nexus if m['path'] not in self.nexus_checked]
        if not nexus_to_check and nexus:nexus_to_check=nexus
        github=[m for m in mods if github_repo(m)]
        key=self.nexus_key.get().strip()  # never persisted or put into messages
        if not github and not (nexus and key):
            self.unified_info.set('No connected sources available. Nexus needs account authorization; open Nexus account / developer options or use Mod Manager Download in your browser.')
            return
        self.unified_running=True;self.unified_root=root
        self.unified_info.set('Checking confirmed mod identities — no downloads or installations…')
        def worker():
            nex={}; gh={}; errors=[]
            if key and nexus:
                try:nex=check_nexus_updates(game,nexus_to_check,key,max_unique=25)
                except Exception as exc:errors.append(str(exc).replace(key,'[redacted]'))
            if github:
                try:gh=check_github_updates(github)
                except Exception as exc:errors.append(str(exc))
            self._unified_events.put(('checks',root,(nex,gh,errors, len(nexus) if not key else 0)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(70,self._poll_unified_events)

    def _poll_unified_events(self):
        try:kind,root,payload=self._unified_events.get_nowait()
        except queue.Empty:
            self.after(70,self._poll_unified_events);return
        if kind=='smapi_sources':
            self.unified_running=False
            report,error,continue_check,queried,skipped=payload
            if self.current() and str(Path(self.current()['root']).resolve())==root:
                if error:self.unified_info.set('SMAPI catalogue lookup unavailable: '+error+'. Existing sources unchanged; use known manifest links or downloaded archives.')
                else:
                    matched=report.get('matches',{})
                    saved=cache_exact_smapi_matches(self.current(),self.rows,matched)
                    # Do not record API failures as negative matches. Successful
                    # empty catalogues are cached per mod/version for 7 days.
                    smapi_lookup_cache.record(queried,report,SMAPI_NEGATIVE_CACHE,
                        lambda m:source_identity(self.current(),m))
                    self.refresh()
                    count=report.get('requested',0)
                    if matched:
                        self.unified_info.set(f"SMAPI lookup checked {count} IDs and identified {len(matched)} Nexus pages ({report.get('matched_by_main',0)} via main-page metadata); {saved['added']} new links saved. {skipped} recent empty lookups skipped. No game files changed.")
                    else:
                        self.unified_info.set(f"SMAPI lookup checked {count} IDs but returned no usable Nexus pages ({report.get('returned',0)} response entries). SMAPI's compatibility catalogue is incomplete. Empty results are cached for 7 days (manual refresh is always available). {skipped} prior no-matches skipped. Existing links preserved; no game files changed.")
                if continue_check and not error and self.nexus_key.get().strip():
                    self.unified_check(skip_resolve=True)
                elif continue_check and not error and any(github_repo(m) for m in self.rows):
                    self.unified_check(skip_resolve=True)
        elif kind=='batch_plan':
            plan,error=payload
            if not self.current() or str(Path(self.current()['root']).resolve())!=root:
                self.unified_install_busy=False
            elif error:
                self.unified_install_busy=False
                self.unified_info.set('Batch review refused: '+error)
                messagebox.showerror('Batch cannot be reviewed',error,parent=self)
            else:self._approve_update_batch(root,plan)
        elif kind=='batch_installed':
            self.unified_install_busy=False
            result,error=payload
            if self.current() and str(Path(self.current()['root']).resolve())==root:
                if error:
                    self.unified_info.set(error)
                    self.refresh()
                    messagebox.showerror('Batch failed — recovery status',error,parent=self)
                else:
                    self.unified_downloads=[];self.unified_download_root=None
                    self.unified_nexus={};self.unified_github={}
                    self.refresh();self.unified_scan_downloads(silent=True)
                    self.unified_info.set(f"Installed {result['count']} updates; recovery backups retained.")
                    messagebox.showinfo('Batch installed',f"Installed {result['count']} updates. Recovery backups retained for each mod.",parent=self)
        elif kind=='downloads':
            self.unified_download_busy=False
            matches,error=payload
            if self.current() and str(Path(self.current()['root']).resolve())==root:
                self.unified_downloads=matches
                self.unified_download_root=root
                self.unified_render()
                if error:self.unified_info.set('Local ZIP scan failed: '+error)
                else:
                    ready=sum(m['status']=='Ready to update' for m in matches)
                    self.unified_info.set(f'{len(matches)} ZIP files checked; {ready} newer exact matches. Select one and choose Review & Install. No files changed.')
        elif kind=='installed':
            self.unified_install_busy=False
            backup,error=payload
            if self.current() and str(Path(self.current()['root']).resolve())==root:
                if error:
                    self.unified_info.set('Installation refused or failed: '+error)
                    messagebox.showerror('Update not installed',error,parent=self)
                else:
                    self.unified_downloads=[];self.unified_download_root=None
                    self.unified_nexus={};self.unified_github={};self.nexus_results={};self.nexus_checked=set();self.update_results={}
                    self.refresh();self.unified_scan_downloads(silent=True)
                    messagebox.showinfo('Mod updated',f'Update installed. Recovery backup saved at:\n{backup}',parent=self)
        elif kind=='files':
            self.nexus_running=False
            ref,files,error=payload
            self.nexus_show_file_choices(ref,files,error)
        elif kind=='checks':
            self.unified_running=False
            if self.current() and str(Path(self.current()['root']).resolve())==root:
                nex,gh,errors,skipped=payload
                self.unified_nexus.update(nex)
                self.unified_github.update(gh)
                self.nexus_results.update(nex)
                self.nexus_checked.update(k for k,v in nex.items() if v.get('status')!='Check failed')
                self.update_results.update(nex);self.update_results.update(gh)
                self.fill_mods();self.unified_render()
                if errors:self.unified_info.set('Update check incomplete: '+' | '.join(errors[:2]))
                elif skipped:self.unified_info.set('Checked available sources; Nexus is not connected. Open Nexus account / developer options to check its exact IDs.')
    def nexus_eligible(self):
        game=self.current()
        if not game:return []
        return [m for m in self.rows if nexus_reference(game,m) is not None]
    def nexus_collection_toggle(self):
        game=self.current()
        if not game or game.get('kind')!='smapi':
            self.nexus_all_origin.set(False)
            messagebox.showinfo('Select a SMAPI game','This setting is for SMAPI mod collections.',parent=self)
            return
        set_nexus_collection_origin(game,self.nexus_all_origin.get())
        self.update_source_status(); self.fill_mods(); self.nexus_refresh()
    def nexus_refresh(self):
        if not hasattr(self,'nexus_tree'):return
        self.nexus_tree.delete(*self.nexus_tree.get_children())
        game=self.current()
        self.nexus_display_rows=list(self.rows) if game else []
        if not game:
            self.nexus_all_origin.set(False)
            self.nexus_info.set('Select a game to check exact Nexus IDs.');return
        self.nexus_all_origin.set(nexus_collection_origin(game))
        eligible=self.nexus_eligible()
        for i,mod in enumerate(self.nexus_display_rows):
            ref=nexus_reference(game,mod);result=self.nexus_results.get(mod['path'],{})
            if ref and 'error' in ref:
                identity='Conflict';status=result.get('status','ID conflict')
            elif ref:
                identity=ref['game_domain']+'/mods/'+ref['mod_id']
                status=result.get('status','Not checked')
            else:
                identity='Nexus page ID needed' if nexus_collection_origin(game) else 'Source unlinked'
                status='Link required' if nexus_collection_origin(game) else 'No exact Nexus ID'
            self.nexus_tree.insert('','end',iid=str(i),values=(mod['name'],mod.get('version',''),result.get('version',''),status,identity))
        checked=sum(m['path'] in self.nexus_results and 'error' not in self.nexus_results[m['path']] for m in eligible)
        missing=sum(nexus_reference(game,m) is None for m in self.nexus_display_rows)
        self.nexus_info.set(f'{len(self.nexus_display_rows)} installed mods; {len(eligible)} exact Nexus identities; {missing} need page links; {checked} successfully checked this session. Origin alone cannot identify a Nexus mod ID.')
    def nexus_selected_row(self):
        selected=self.nexus_tree.selection()
        if not selected:return None
        try:return self.nexus_display_rows[int(selected[0])]
        except (AttributeError,ValueError,IndexError):return None
    def nexus_assign_selected(self):
        game=self.current();mod=self.nexus_selected_row()
        if not game or not mod:
            messagebox.showinfo('Select a mod','Select a row in Nexus Updates first.',parent=self);return
        old=nexus_reference(game,mod)
        url=simpledialog.askstring('Assign Nexus mod page',
            f'Official Nexus Mods page for {mod["name"]}:\n(https://www.nexusmods.com/stardewvalley/mods/123)',
            initialvalue=(old.get('url','') if old and 'error' not in old else ''),parent=self)
        if url is None:return
        ref=parse_nexus_link(url)
        expected=game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name',''))
        if not ref or (expected and ref['game_domain']!=expected):
            messagebox.showerror('Invalid page','Enter an exact official Nexus mod URL for this game.',parent=self);return
        save_source_assignment(game,mod,ref['url'])
        self.nexus_results.pop(mod['path'],None);self.nexus_checked.discard(mod['path'])
        self.update_source_status();self.nexus_refresh();self.fill_mods()
    def nexus_import_aio(self):
        """Review owner-provided exact AIO links; no changes until confirmation."""
        game=self.current()
        if not game or game.get('kind')!='smapi' or game.get('name')!='Stardew Valley':
            messagebox.showinfo('Stardew Valley AIO','Select Stardew Valley to import these AIO links.',parent=self);return
        try:preview=aio_nexus_preview(game,self.rows)
        except (OSError,ValueError) as exc:
            messagebox.showerror('AIO link list',str(exc),parent=self);return
        dlg=tk.Toplevel(self);dlg.title('Review Stardew Valley AIO Nexus links')
        dlg.geometry('1050x630');dlg.minsize(760,420);dlg.transient(self)
        shell=ttk.Frame(dlg,padding=12);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='Match your original AIO Nexus downloads',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(shell,text=('Read-only preview: Exact-name links are suggested for selection. Related pack components need individual review. '
            'Existing IDs and conflicting links will not be replaced. Only local UniMod source assignments are saved; no mods are installed.'),wraplength=970).pack(anchor='w',pady=(0,9))
        counts={}
        for row in preview:counts[row['status']]=counts.get(row['status'],0)+1
        info=tk.StringVar(value=f'{len(preview)} installed entries · {counts.get("Ready — exact name",0)} new exact matches · '
            f'{counts.get("Review related component",0)} related components to review · {counts.get("Already linked",0)} already linked')
        ttk.Label(shell,textvariable=info).pack(anchor='w',pady=(0,9))
        area=ttk.Frame(shell);area.pack(fill='both',expand=True)
        cols=('installed','nexus','evidence','status')
        table=ttk.Treeview(area,columns=cols,show='headings',selectmode='extended')
        for col,title,width in [('installed','Installed mod',280),('nexus','AIO Nexus page',230),
                                ('evidence','Match basis',210),('status','Decision',240)]:
            table.heading(col,text=title);table.column(col,width=width,minwidth=90,stretch=col in ('installed','status'))
        table.pack(side='left',fill='both',expand=True)
        sb=ttk.Scrollbar(area,orient='vertical',command=table.yview);sb.pack(side='right',fill='y')
        table.configure(yscrollcommand=sb.set)
        for i,row in enumerate(preview):
            candidate=row['candidate']
            label=(candidate['name']+'  #'+candidate['mod_id']) if candidate else '—'
            table.insert('','end',iid=str(i),values=(row['mod']['name'],label,row['evidence'],row['status']))
        def select_exact():
            table.selection_set([str(i) for i,r in enumerate(preview) if r['status']=='Ready — exact name'])
        def apply_selected():
            try:ids=sorted(int(v) for v in table.selection())
            except ValueError:return
            if not ids:
                messagebox.showinfo('Choose matches','Select at least one exact or reviewed component row.',parent=dlg);return
            questionable=[preview[i]['mod']['name'] for i in ids if preview[i]['status']=='Review related component']
            if not all(preview[i]['status'] in ('Ready — exact name','Review related component') for i in ids):
                messagebox.showwarning('Selection contains protected rows','Only new exact matches or manually reviewed related components can be assigned.',parent=dlg);return
            prompt=f'Assign {len(ids)} official Nexus page links in UniMod?\n\nNo installed game files will be changed.'
            if questionable:prompt+='\n\nRelated components requiring YOUR review:\n'+'\n'.join(questionable[:12])
            if not messagebox.askyesno('Confirm source assignments',prompt,parent=dlg):return
            try:n=apply_aio_nexus_links(game,preview,ids)
            except (OSError,ValueError) as exc:
                messagebox.showerror('Import refused',str(exc),parent=dlg);return
            for i in ids:
                path=preview[i]['mod']['path']
                self.nexus_results.pop(path,None);self.nexus_checked.discard(path)
            self.update_source_status();self.nexus_refresh();self.fill_mods()
            dlg.destroy()
            messagebox.showinfo('AIO links imported',f'{n} Nexus page links saved to UniMod. No mod folders were changed.\nClick Check next 25 to check versions.',parent=self)
        actions=ttk.Frame(shell);actions.pack(fill='x',pady=(12,0))
        ttk.Button(actions,text='Select new exact matches',command=select_exact).pack(side='left')
        ttk.Button(actions,text='Apply selected links',command=apply_selected).pack(side='left',padx=9)
        ttk.Button(actions,text='Cancel',command=dlg.destroy).pack(side='right')
        select_exact()
        dlg.grab_set()

    def find_sources_easy(self):
        """Normal-user flow: local discovery first, exceptions together, no API key."""
        game=self.current()
        if not game or game.get('kind')!='smapi':
            messagebox.showinfo('Find mod sources','Select a SMAPI game to scan mod downloads.',parent=self)
            return
        folder=Path(self.inbox_folder.get()).expanduser()
        if not folder.is_dir():folder=Path.home()/'Downloads'
        dlg=tk.Toplevel(self);dlg.title('Find mod sources — no account required')
        dlg.geometry('1080x620');dlg.minsize(760,420);dlg.transient(self)
        root=ttk.Frame(dlg,padding=14);root.pack(fill='both',expand=True)
        ttk.Label(root,text='Find mod sources',style='Section.TLabel').pack(anchor='w',pady=(0,7))
        ttk.Label(root,text=('UniMod checks SMAPI IDs and downloaded ZIPs. Exact metadata links are already recognised. '
            'Filename-based suggestions are never trusted automatically. This does not contact Nexus or change installed mods.'),
            wraplength=970).pack(anchor='w',pady=(0,10))
        folder_row=ttk.Frame(root);folder_row.pack(fill='x',pady=(0,8))
        ttk.Label(folder_row,text='Downloads folder').pack(side='left',padx=(0,7))
        selected_folder=tk.StringVar(value=str(folder))
        ttk.Entry(folder_row,textvariable=selected_folder).pack(side='left',fill='x',expand=True)
        def browse():
            path=filedialog.askdirectory(title='Choose folder containing downloaded mod ZIPs',parent=dlg,initialdir=selected_folder.get())
            if path:selected_folder.set(path)
        ttk.Button(folder_row,text='Choose…',command=browse).pack(side='left',padx=(8,0))
        def remember_folder():
            path=Path(selected_folder.get()).expanduser()
            try:
                existing=archive_discovery.load_extra_download_roots(app_dir=APP)
                archive_discovery.save_extra_download_roots(existing+[path],app_dir=APP)
            except (OSError,ValueError) as exc:
                messagebox.showerror('Remember download location',str(exc),parent=dlg)
                return
            messagebox.showinfo('Location saved',
                'UniMod will include this folder in future source scans. The game and mod files are unchanged.',parent=dlg)
        ttk.Button(folder_row,text='Remember folder',command=remember_folder).pack(side='left',padx=(8,0))
        search_common=tk.BooleanVar(value=True)
        ttk.Checkbutton(root,text='Automatically include known Vortex, common and remembered download folders',
                        variable=search_common).pack(anchor='w',pady=(0,8))
        info=tk.StringVar(value='Scanning local mod metadata and downloaded ZIPs…')
        ttk.Label(root,textvariable=info).pack(anchor='w',pady=(0,9))
        columns=('mod','page','basis','status')
        area=ttk.Frame(root);area.pack(fill='both',expand=True)
        tree=ttk.Treeview(area,columns=columns,show='headings',selectmode='extended')
        for col,name,width in [('mod','Installed mod',285),('page','Nexus page',165),('basis','Evidence',340),('status','Result',175)]:
            tree.heading(col,text=name);tree.column(col,width=width,minwidth=80,stretch=col in ('mod','basis'))
        tree.pack(side='left',fill='both',expand=True)
        sb=ttk.Scrollbar(area,command=tree.yview);sb.pack(side='right',fill='y')
        tree.configure(yscrollcommand=sb.set)
        preview=[];busy={'value':False}
        completed=queue.Queue()
        def poll_results():
            try:rows,error=completed.get_nowait()
            except queue.Empty:pass
            else:finished(rows,error)
            if dlg.winfo_exists():dlg.after(80,poll_results)
        dlg.after(80,poll_results)
        def finished(rows, err):
            busy['value']=False
            tree.delete(*tree.get_children());preview[:]=rows
            if err:
                info.set('Local scan failed: '+err);return
            counts={}
            for row in preview:
                counts[row['status']]=counts.get(row['status'],0)+1
            info.set(f"{len(preview)} installed entries · {counts.get('Already identified',0)} identified · "
                     f"{counts.get('Review candidate',0)} suggestions to review · "
                     f"{counts.get('Needs source',0)} still unlinked. No API key required.")
            for i,row in enumerate(preview):
                ref=row['candidate'] or {}
                tree.insert('','end',iid=str(i),values=(row['name'],
                    '#'+ref['mod_id'] if ref.get('mod_id') else '—',row['evidence'],row['status']))
        def scan():
            if busy['value']:return
            busy['value']=True
            info.set('Scanning local ZIP files safely…')
            mods=list(self.rows)
            folder_path=selected_folder.get()
            use_common=search_common.get()
            def work():
                try:rows=simple_source_preview(game,mods,folder_path,include_common=use_common,app_dir=APP);err=None
                except Exception as exc:rows=[];err=str(exc)
                completed.put((rows,err))
            threading.Thread(target=work,daemon=True).start()
        def apply():
            if busy['value']:return
            indices=[int(i) for i in tree.selection() if i.isdigit()]
            if not indices:
                messagebox.showinfo('Select candidates','Select only the downloaded-ZIP suggestions you have verified.',parent=dlg)
                return
            if any(preview[i]['status']!='Review candidate' for i in indices):
                messagebox.showwarning('Protected entries','Only rows labelled Review candidate can be assigned.',parent=dlg)
                return
            if not messagebox.askyesno('Confirm mod sources',
                f'Save {len(indices)} Nexus page suggestion(s) to UniMod configuration?\n\n'
                'Verify these IDs against the actual Nexus pages first. A downloaded ZIP filename can be renamed or forged.\n'
                'No installed game files will be changed.',parent=dlg):return
            try:num=apply_simple_source_matches(game,preview,indices)
            except (ValueError,OSError) as exc:
                messagebox.showerror('Source matching',str(exc),parent=dlg);return
            self.nexus_refresh();self.fill_mods();self.update_source_status()
            info.set(f'{num} reviewed links saved. Your installed mods were not changed.')
            scan()
        def open_candidate():
            selection=tree.selection()
            if not selection:return
            row=preview[int(selection[0])]
            ref=row['candidate'] or {}
            if ref.get('url'):webbrowser.open(ref['url'])
        actions=ttk.Frame(root);actions.pack(fill='x',pady=(10,0))
        ttk.Button(actions,text='Scan download locations',command=scan).pack(side='left')
        ttk.Button(actions,text='Open selected Nexus page',command=open_candidate).pack(side='left',padx=8)
        ttk.Button(actions,text='Save reviewed suggestions',command=apply,style='Accent.TButton').pack(side='left')
        ttk.Button(actions,text='Done',command=dlg.destroy).pack(side='right')
        scan()

    def bepinex_nexus_archive_dialog(self):
        """Review only, no login, provider download or installed-file modifications."""
        game=self.current()
        if not game or game.get('name') not in bepinex_nexus_evidence.SUPPORTED_GAMES or game.get('kind')!='bepinex':
            messagebox.showinfo('Nexus archive matches',
                'This offline matching tool supports Graveyard Keeper and Graveyard Keeper 2 BepInEx mods.',parent=self)
            return
        if not self.rows:
            messagebox.showinfo('No installed DLLs', 'Scan the installed mods for this game first.',parent=self)
            return
        game_root=str(Path(game['root']).resolve())
        mods=list(self.rows)
        dlg=tk.Toplevel(self);dlg.title('Review local Nexus ZIP matches — '+game['name'])
        dlg.geometry('1000x540');dlg.transient(self)
        info=tk.StringVar(value='Match installed DLL hashes against downloaded ZIPs with same-game Nexus .meta sidecars. All results require manual review.')
        ttk.Label(dlg,textvariable=info,wraplength=940).pack(fill='x',padx=12,pady=(12,10))
        folder=tk.StringVar(value=str(Path.home()/'Downloads'))
        bar=ttk.Frame(dlg);bar.pack(fill='x',padx=12,pady=(0,10))
        ttk.Label(bar,text='ZIP folder:').pack(side='left')
        ttk.Entry(bar,textvariable=folder).pack(side='left',fill='x',expand=True,padx=8)
        def choose():
            new=filedialog.askdirectory(parent=dlg,initialdir=folder.get(),title='Choose a folder containing Nexus ZIP files and .meta sidecars')
            if new:folder.set(new)
        ttk.Button(bar,text='Browse…',command=choose).pack(side='right')
        tree=ttk.Treeview(dlg,columns=('mod','status','url','evidence'),show='headings',selectmode='extended')
        for col,width in [('mod',175),('status',165),('url',275),('evidence',350)]:
            tree.heading(col,text=col.title());tree.column(col,width=width,stretch=col in ('mod','evidence'))
        tree.pack(fill='both',expand=True,padx=12,pady=(0,9))
        state={'busy':False,'result':None}
        events=queue.Queue()
        def current_game():
            selected=self.current()
            return bool(selected and selected.get('name')==game.get('name') and str(Path(selected['root']).resolve())==game_root)
        def scan():
            if state['busy']:return
            state['busy']=True;state['result']=None
            scan_folder=folder.get()
            tree.delete(*tree.get_children())
            info.set('Scanning only local downloaded archives, with strict size limits…')
            def run():
                try:
                    result=bepinex_nexus_evidence.preview_archive_evidence(game,mods,scan_folder,
                        known_source=lambda g,m:bool(reconcile_source(g,m).get('url')),
                        identity=source_identity)
                    events.put((result,None))
                except (OSError,ValueError) as exc:events.put((None,str(exc)))
            threading.Thread(target=run,daemon=True).start()
            dlg.after(70,poll)
        def poll():
            if not dlg.winfo_exists():return
            try:result,error=events.get_nowait()
            except queue.Empty:
                dlg.after(70,poll);return
            state['busy']=False
            if error:info.set(error);return
            state['result']=result
            for i,row in enumerate(result['rows']):
                tree.insert('','end',iid=str(i),values=(row['name'],row['status'],
                    (row['candidate'] or {}).get('url',''),row['evidence']))
            info.set(f"{result['archives_with_metadata']} Nexus ZIPs with matching-game metadata scanned · "
                     f"{result['reviewable']} DLL candidates require review. Source links are not automatically authenticated.")
        def open_page():
            result=state['result'];sel=tree.selection()
            if not result or len(sel)!=1:return
            candidate=result['rows'][int(sel[0])]['candidate'] or {}
            ref=parse_nexus_link(candidate.get('url'))
            if ref and ref['game_domain']==bepinex_nexus_evidence.SUPPORTED_GAMES[game['name']]:
                webbrowser.open(ref['url'])
        def commit():
            result=state['result']
            if not result or state['busy']:return
            indices=[int(i) for i in tree.selection()]
            if not indices:
                messagebox.showinfo('Select candidates','Select reviewable DLL rows after checking their Nexus pages.',parent=dlg)
                return
            if not current_game():
                messagebox.showwarning('Game changed','Game selection changed. Reopen source matching.',parent=dlg)
                return
            if not messagebox.askyesno('Confirm Nexus identities',
                f'Save {len(indices)} reviewed source link(s)?\n\n'
                'A matching DLL hash proves identical bytes, NOT publisher authenticity. '
                'The .meta sidecar is untrusted, so verify each Nexus page first.\n\n'
                'No installed mods will be changed.',parent=dlg):return
            try:
                count=apply_bepinex_archive_candidates(game,result['rows'],indices)
            except (ValueError,OSError) as exc:
                messagebox.showerror('No source links saved',str(exc),parent=dlg);return
            self.fill_mods();self.update_source_status();self.update_dashboard()
            info.set(f'{count} reviewed source link(s) saved. Installed DLLs unchanged. Rescan before adding more.')
            state['result']=None
        actions=ttk.Frame(dlg);actions.pack(fill='x',padx=12,pady=(0,12))
        ttk.Button(actions,text='Scan Nexus ZIPs',command=scan).pack(side='left')
        ttk.Button(actions,text='Open selected Nexus page',command=open_page).pack(side='left',padx=8)
        ttk.Button(actions,text='Save reviewed source links',command=commit,style='Accent.TButton').pack(side='left')
        ttk.Button(actions,text='Close',command=dlg.destroy).pack(side='right')
        scan()

    def bepinex_source_hints_dialog(self):
        """Browse unverified, read-only local hints, then use official Nexus search."""
        game=self.current()
        if not game or game.get('kind')!='bepinex' or game.get('name') not in bepinex_search_hints.SUPPORTED_GAMES:
            messagebox.showinfo('Nexus search hints','Choose Graveyard Keeper or Graveyard Keeper 2 BepInEx first.',parent=self)
            return
        if not self.rows:
            messagebox.showinfo('No installed DLLs','Scan the installed mods for this game first.',parent=self)
            return
        game_root=str(Path(game['root']).resolve())
        game_name=game['name']
        try:
            rows=bepinex_search_hints.preview_search_hints(game,list(self.rows),
                known_source=lambda g,m:bool(reconcile_source(g,m).get('url')),
                identity=source_identity)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Local hint scan',str(exc),parent=self);return
        dlg=tk.Toplevel(self);dlg.title('Nexus search hints — '+game_name)
        dlg.geometry('910x525');dlg.transient(self)
        ttk.Label(dlg,text='These are UNVERIFIED search terms from local DLL filenames or manifests, not evidence of Nexus authorship. '
                       'No installed files will be changed.',wraplength=870).pack(fill='x',padx=12,pady=12)
        tree=ttk.Treeview(dlg,columns=('mod','hint','status','basis'),show='headings',selectmode='browse')
        for col,width in [('mod',210),('hint',240),('status',130),('basis',275)]:
            tree.heading(col,text=col.title());tree.column(col,width=width,stretch=col in ('mod','basis'))
        tree.pack(fill='both',expand=True,padx=12,pady=(0,10))
        for i,row in enumerate(rows):tree.insert('','end',iid=str(i),values=(row['name'],row['query'],row['status'],row['basis']))
        info=tk.StringVar(value=f"{sum(r['status']=='Search ready' for r in rows)} possible search terms. Review provider results manually.")
        ttk.Label(dlg,textvariable=info,wraplength=870).pack(fill='x',padx=12,pady=(0,7))
        def find():
            selected=tree.selection()
            if len(selected)!=1:return
            current=self.current()
            if (not current or current.get('name')!=game_name or str(Path(current['root']).resolve())!=game_root):
                messagebox.showwarning('Game changed','Game selection changed. Reopen search hints.',parent=dlg);return
            row=rows[int(selected[0])]
            try:
                query=bepinex_search_hints.validate_search_hint(game,row,
                    identity=source_identity,
                    known_source=lambda g,m:bool(reconcile_source(g,m).get('url')))
                provider_catalogues.clean_search(query)
            except (ValueError,OSError,provider_catalogues.ProviderError) as exc:
                messagebox.showwarning('Rescan required',str(exc),parent=dlg);return
            self.source_candidate_target={
                'game_root':game_root,'source_id':row['identity'],
                'name':row['name'],'game_name':game_name,
                'fingerprint':row['fingerprint'], 'search_query':query,
            }
            self.provider_choice.set('Nexus Mods')
            self.provider_scope.set(row['game_domain'])
            self.provider_query.set(query)
            self.provider_results=[]
            self.provider_tree.delete(*self.provider_tree.get_children())
            self.provider_info.set('Search hint only — NOT a verified identity. Confirm the game, author and mod '
                'page before assigning a link. No Nexus download is enabled.')
            dlg.destroy()
            self.show_page('Mod Websites')
            self.provider_begin_search()
        actions=ttk.Frame(dlg);actions.pack(fill='x',padx=12,pady=(0,12))
        ttk.Button(actions,text='Search selected on Nexus',command=find,style='Accent.TButton').pack(side='left')
        ttk.Button(actions,text='Close',command=dlg.destroy).pack(side='right')

    def source_search_candidates(self):
        """Use selected installed mod as a search term, never as an inferred identity."""
        game=self.current()
        mod=self.source_table_mod()
        if not game or not mod:
            messagebox.showinfo('Choose an installed mod',
                                'Select a mod in Source Matching before searching candidate websites.',parent=self)
            return
        query=str(mod.get('name') or '').strip()
        try:provider_catalogues.clean_search(query)
        except provider_catalogues.ProviderError:
            messagebox.showinfo('Search unavailable',
                                'The selected mod does not have a usable display name. Assign an official URL manually.',parent=self)
            return
        self.source_candidate_target={
            'game_root':str(Path(game['root']).resolve()),
            'source_id':source_identity(game,mod),
            'name':query,
            'search_query':query,
            'game_name':str(game.get('name') or ''),
        }
        # Graveyard Keeper (and GK2 separately) have official Nexus catalogues.
        nexus_domain=(game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name','')))
        if game.get('name') in ('Graveyard Keeper','Graveyard Keeper 2') and nexus_domain:
            self.provider_choice.set('Nexus Mods')
            self.provider_scope.set(nexus_domain)
        else:
            self.provider_choice.set('GitHub')
        self.provider_query.set(query)
        self.provider_results=[]
        self.provider_tree.delete(*self.provider_tree.get_children())
        self.provider_info.set(f'Search candidates for {query} ({game.get("name", "game")}). '
                               'Results are NOT verified identities. Open the page, confirm game and publisher, '
                               'then explicitly link it. No automatic installation.')
        self.show_page('Mod Websites')
        self.provider_begin_search()

    def provider_assign_reviewed_source(self):
        """Link one *user-reviewed* catalogue page; never treat name-search as proof."""
        target=self.source_candidate_target
        if not target:
            messagebox.showinfo('Choose a mod first',
                                'Use Source Matching → Find candidate pages to select an installed mod.',parent=self)
            return
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=target['game_root'] or str(game.get('name'))!=target.get('game_name'):
            messagebox.showwarning('Game changed',
                                   'The game selection changed. Return to Source Matching and select the intended mod.',parent=self)
            return
        matching=[m for m in self.rows if source_identity(game,m)==target['source_id']]
        if len(matching)!=1:
            messagebox.showwarning('Mod changed',
                                   'The installed mod is no longer uniquely present. Refresh Source Matching.',parent=self)
            return
        if target.get('fingerprint') is not None:
            try:
                bepinex_search_hints.validate_search_hint(game, {
                    'status':'Search ready','mod':matching[0], 'identity':target['source_id'],
                    'fingerprint':target['fingerprint'], 'game_domain':bepinex_search_hints.SUPPORTED_GAMES.get(game.get('name')),
                    'query':target['search_query']},identity=source_identity,
                    known_source=lambda g,m:bool(reconcile_source(g,m).get('url')))
            except (ValueError,OSError) as exc:
                messagebox.showwarning('Mod changed','The installed DLL changed or the source is already linked. Rescan before assigning.',parent=self)
                return
        chosen=self.provider_tree.selection()
        if len(chosen)!=1:
            messagebox.showinfo('Choose a candidate',
                                'Select one official catalogue result and review its website.',parent=self)
            return
        try:result=self.provider_results[int(chosen[0])]
        except (TypeError,ValueError,IndexError,KeyError):return
        url=result.get('url')
        if not validate_source_link(url):
            messagebox.showwarning('Untrusted link','The selected provider URL is not a supported HTTPS mod page.',parent=self)
            return
        if result.get('provider')=='Nexus Mods':
            ref=parse_nexus_link(url)
            expected=game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name',''))
            if not ref or not expected or ref['game_domain'] != expected:
                messagebox.showwarning('Wrong Nexus game',
                    'This is not an exact Nexus mod page for the selected game.',parent=self)
                return
        if result.get('provider')=='mod.io':
            verified=self.modio_verified
            identity=str(result.get('identity') or '')
            digest=hashlib.sha256(self.provider_key.get().strip().encode()).digest()
            if (not verified or verified[:3]!=(identity.split('/')[0],self.modio_user_id.get().strip(),digest)
                or re.sub('[^a-z0-9]','',game.get('name','').casefold())
                   !=re.sub('[^a-z0-9]','',verified[3].casefold())):
                messagebox.showwarning('Wrong mod.io game',
                    'Verify the matching mod.io game and user API path before linking an installed mod.',parent=self)
                return
        if result.get('provider')=='CurseForge':
            verified=self.curseforge_verified
            token=hashlib.sha256(self.provider_key.get().strip().encode()).digest()
            identity=str(result.get('identity') or '')
            # Unlike Nexus game slugs, CurseForge game IDs cannot safely be
            # inferred from a display URL. Require this exact session key,
            # verified ID, and same selected local game before any source link.
            if (not verified or identity.split('/')[0]!=verified[0] or token!=verified[1]
                or re.sub('[^a-z0-9]','',game.get('name','').casefold())
                   !=re.sub('[^a-z0-9]','',verified[2].casefold())):
                messagebox.showwarning('Wrong CurseForge game',
                    'Verify the matching CurseForge game ID for this installed game before linking any mod.',parent=self)
                return
        mod=matching[0]
        old=assigned_source(game,mod)
        replacement=('\nThis replaces the existing manual source assignment.'
                     if old and old['url']!=url else '')
        if not messagebox.askyesno('Confirm reviewed source',
            'Installed mod: '+target['name']+'\nGame: '+target['game_name']+
            '\nCandidate: '+str(result.get('title') or '')+'\nPublisher: '+str(result.get('author') or '')+
            '\nURL: '+url+'\n\nA name-search result does NOT prove this is the same mod. '
            'Only continue after checking the official page, publisher and supported game.'+
            replacement+'\n\nSave this link in UniMod settings (game files remain unchanged)?',parent=self):
            return
        try:save_source_assignment(game,mod,url)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Source assignment failed',str(exc),parent=self)
            return
        self.fill_mods();self.update_source_status();self.update_dashboard()
        self.status.set(f'Reviewed source assigned to {target["name"]}; installed files not changed.')
        self.source_candidate_target=None
        self.show_page('Source Matching')

    def provider_access_dialog(self):
        """Explain the current provider's approval gate, never display the key."""
        provider=self.provider_choice.get()
        info=provider_access.access_info(provider,key_present=bool(self.provider_key.get().strip()))
        dlg=tk.Toplevel(self);dlg.title(provider+' — provider access')
        dlg.geometry('650x350');dlg.transient(self)
        shell=ttk.Frame(dlg,padding=16);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text=provider+' access requirements',style='Section.TLabel').pack(anchor='w',pady=(0,14))
        ttk.Label(shell,text=info['status'],wraplength=590).pack(anchor='w',pady=(0,12))
        ttk.Label(shell,text='Next step: '+info['next'],wraplength=590).pack(anchor='w',pady=(0,12))
        ttk.Label(shell,text=info['key'],wraplength=590).pack(anchor='w',pady=(0,12))
        ttk.Label(shell,text='Keys entered in UniMod are session-only. Public Nexus metadata does not require a key.',
                  wraplength=590,style='Subtle.TLabel').pack(anchor='w')
        actions=ttk.Frame(shell);actions.pack(side='bottom',fill='x',pady=(14,0))
        if info['url']:
            ttk.Button(actions,text='Open official instructions',command=lambda:webbrowser.open(info['url'])).pack(side='left')
        ttk.Button(actions,text='Close',command=dlg.destroy).pack(side='right')

    def provider_verify_curseforge_game(self):
        """Get a game title from CurseForge; require the user to confirm it."""
        if getattr(self,'_curseforge_verifying',False):return
        gid=self.provider_scope.get().strip();key=self.provider_key.get().strip()
        try:
            provider_catalogues.numeric(gid)
            if len(key)<8:raise provider_catalogues.ProviderError('Enter an approved CurseForge API key first.')
        except provider_catalogues.ProviderError as exc:
            self.provider_info.set(str(exc));return
        self._curseforge_verifying=True
        self.provider_info.set('Verifying game ID with CurseForge (read-only)…')
        def run():
            try: result=provider_catalogues.curseforge_game(gid,key);error=None
            except provider_catalogues.ProviderError as exc:result=None;error=str(exc)
            except Exception:result=None;error='Could not verify CurseForge game.'
            self._curseforge_verification_events.put((gid,hashlib.sha256(key.encode()).digest(),result,error))
        threading.Thread(target=run,daemon=True).start()
        self.after(100,self._poll_curseforge_verification)

    def _poll_curseforge_verification(self):
        try:gid,digest,record,error=self._curseforge_verification_events.get_nowait()
        except queue.Empty:
            if getattr(self,'_curseforge_verifying',False):self.after(100,self._poll_curseforge_verification)
            return
        self._curseforge_verifying=False
        if error:
            self.provider_info.set(error);return
        if self.provider_scope.get().strip()!=gid or hashlib.sha256(self.provider_key.get().strip().encode()).digest()!=digest:
            self.provider_info.set('CurseForge game/key changed during lookup; verify again.');return
        if messagebox.askyesno('Confirm CurseForge game',
             f"Verified game: {record['name']}\nGame ID: {gid}\n\nUse this exact game catalogue for this session?",
             parent=self):
            self.curseforge_verified=(gid,digest,record['name'])
            self.provider_choice.set('CurseForge')
            self.provider_info.set(f"CurseForge game verified: {record['name']} (#{gid}). Search and inspect files; no download enabled.")
        else:self.provider_info.set('Game selection not confirmed. No changes made.')

    def provider_verify_modio_game(self):
        """Review a game title under the user's unique mod.io API account path."""
        if getattr(self,'_modio_verifying',False):return
        try:
            gid=provider_catalogues.numeric(self.provider_scope.get().strip())
            uid=provider_catalogues.numeric(self.modio_user_id.get().strip())
            key=self.provider_key.get().strip()
            if len(key)<8:raise provider_catalogues.ProviderError('Enter your local mod.io API key first.')
        except provider_catalogues.ProviderError as exc:
            self.provider_info.set(str(exc));return
        self._modio_verifying=True
        self.provider_info.set('Verifying the mod.io game using your user API path (read-only)…')
        def worker():
            try:record=provider_catalogues.modio_game(gid,key,user_id=uid);error=None
            except provider_catalogues.ProviderError as exc:record=None;error=str(exc)
            except Exception:record=None;error='Could not verify the mod.io game.'
            self._modio_verification_events.put((gid,uid,hashlib.sha256(key.encode()).digest(),record,error))
        threading.Thread(target=worker,daemon=True).start()
        self.after(100,self._poll_modio_verification)

    def _poll_modio_verification(self):
        try:gid,uid,digest,record,error=self._modio_verification_events.get_nowait()
        except queue.Empty:
            if getattr(self,'_modio_verifying',False):self.after(100,self._poll_modio_verification)
            return
        self._modio_verifying=False
        if error:self.provider_info.set(error);return
        if (gid!=self.provider_scope.get().strip() or uid!=self.modio_user_id.get().strip()
            or digest!=hashlib.sha256(self.provider_key.get().strip().encode()).digest()):
            self.modio_verified=None
            self.provider_info.set('mod.io game/account/key changed during verification. Verify again.')
            return
        if messagebox.askyesno('Confirm mod.io game',
            'Verified mod.io game: '+record['name']+' (ID '+gid+')\n\n'
            'Confirm this is the game you intend to search. No files will be downloaded.',parent=self):
            self.modio_verified=(gid,uid,digest,record['name'])
            self.provider_choice.set('mod.io')
            self.provider_info.set(f"mod.io game verified: {record['name']} (#{gid}). Read-only catalogue available.")
        else:
            self.modio_verified=None
            self.provider_info.set('mod.io game not confirmed. No changes made.')

    def provider_curseforge_files_dialog(self,ref):
        """Show only metadata from approved CurseForge API: no download link or staging."""
        identity=ref.get('identity') or ''
        key=self.provider_key.get().strip()
        try:
            if not self.curseforge_verified or self.curseforge_verified[:2]!=(identity.split('/')[0],hashlib.sha256(key.encode()).digest()):
                raise provider_catalogues.ProviderError('Verify the CurseForge game ID with the current session key first.')
        except provider_catalogues.ProviderError as exc:
            messagebox.showwarning('CurseForge game not verified',str(exc),parent=self);return
        dlg=tk.Toplevel(self);dlg.title('CurseForge — file metadata (read-only)')
        dlg.geometry('880x490')
        ttk.Label(dlg,text=ref.get('title','CurseForge mod'),style='Section.TLabel').pack(anchor='w',padx=12,pady=(12,3))
        ttk.Label(dlg,text='Browse release names, versions and sizes. Downloading and installing CurseForge files is disabled.',wraplength=820).pack(anchor='w',padx=12)
        status=tk.StringVar(value='Loading official CurseForge release metadata…')
        ttk.Label(dlg,textvariable=status,wraplength=830).pack(anchor='w',padx=12,pady=(8,8))
        tree=ttk.Treeview(dlg,columns=('file','type','versions','size','date'),show='headings')
        for col,width in [('file',280),('type',80),('versions',230),('size',90),('date',130)]:
            tree.heading(col,text=col.title());tree.column(col,width=width,stretch=col in ('file','versions'))
        tree.pack(fill='both',expand=True,padx=12,pady=(0,10))
        buttons=ttk.Frame(dlg);buttons.pack(fill='x',padx=12,pady=(0,12))
        ttk.Button(buttons,text='Open official mod page',command=lambda:webbrowser.open(ref['url'])).pack(side='left')
        ttk.Button(buttons,text='Close',command=dlg.destroy).pack(side='right')
        events=queue.Queue()
        def worker():
            try:rows=provider_catalogues.curseforge_files(identity,key);events.put((rows,None))
            except provider_catalogues.ProviderError as exc:events.put((None,str(exc)))
            except Exception:events.put((None,'CurseForge file lookup failed.'))
        def poll():
            if not dlg.winfo_exists():return
            try:rows,error=events.get_nowait()
            except queue.Empty:dlg.after(100,poll);return
            if error:status.set(error);return
            for i,item in enumerate(rows):
                tree.insert('','end',iid=str(i),values=(item['filename'],item['release_type'],
                    ', '.join(item['versions'][:5]) or 'Unspecified',
                    f"{item['size']/1024/1024:.1f} MiB",item['date'][:10]))
            status.set(f'{len(rows)} file records found (first page only). Metadata is not installation approval.')
        threading.Thread(target=worker,daemon=True).start();dlg.after(100,poll)

    def provider_begin_search(self):
        if self.provider_loading:return
        provider=self.provider_choice.get()
        term=self.provider_query.get()
        scope=self.provider_scope.get()
        key=self.provider_key.get()    # memory-only, never sent to GUI event queue
        try:
            provider_catalogues.clean_search(term)
            if provider in ('CurseForge','mod.io'):
                provider_catalogues.numeric(scope)
                if len(key.strip())<8:
                    raise provider_catalogues.ProviderError('This provider requires an API key.')
                if provider=='CurseForge' and (not self.curseforge_verified or
                    self.curseforge_verified[:2] != (scope.strip(),hashlib.sha256(key.strip().encode()).digest())):
                    raise provider_catalogues.ProviderError('Verify and confirm the CurseForge game ID first.')
                if provider=='mod.io':
                    uid=provider_catalogues.numeric(self.modio_user_id.get().strip())
                    if (not self.modio_verified or self.modio_verified[:3] !=
                        (scope.strip(),uid,hashlib.sha256(key.strip().encode()).digest())):
                        raise provider_catalogues.ProviderError('Verify and confirm the mod.io game under your own user API path first.')
            elif provider=='Thunderstore':
                provider_catalogues.slug(scope)
            elif provider=='Nexus Mods':
                game=self.current()
                expected=game.get('nexus_domain') or NEXUS_GAME_DOMAINS.get(game.get('name','')) if game else None
                if not expected:
                    raise provider_catalogues.ProviderError('Select a game with a known Nexus catalogue first.')
                provider_catalogues.nexus_game_domain(expected)
                scope=expected  # Never search an arbitrary game from stale text input.
                self.provider_scope.set(expected)
        except provider_catalogues.ProviderError as exc:
            self.provider_info.set(str(exc));return
        self.provider_loading=True
        self.after(80,self._poll_provider_events)
        self.provider_info.set('Searching '+provider+'… (no installation or source assignment)')
        def worker():
            try:
                records=provider_catalogues.search(provider,term,community=scope,game_id=scope,key=key,
                    user_id=uid if provider=='mod.io' else None)
                self._provider_events.put(('provider_results',records,provider))
            except provider_catalogues.ProviderError as exc:
                self._provider_events.put(('provider_error',str(exc),provider))
            except Exception:
                # Never expose provider URL, API key, or server-returned text.
                self._provider_events.put(('provider_error','Provider request failed. Try again later.',provider))
        threading.Thread(target=worker,daemon=True).start()

    def _poll_provider_events(self):
        try: kind, value, provider=self._provider_events.get_nowait()
        except queue.Empty:
            if self.provider_loading:self.after(80,self._poll_provider_events)
            return
        if kind=='provider_results':
            self.provider_show_results(value,provider)
        else:
            self.provider_loading=False
            self.provider_info.set(value)

    def provider_show_results(self,records,provider):
        self.provider_loading=False
        target=self.source_candidate_target
        same_game=(target and self.current() and
                   str(Path(self.current()['root']).resolve())==target.get('game_root') and
                   str(self.current().get('name'))==target.get('game_name'))
        if same_game:
            domain=(self.current().get('nexus_domain') or
                    NEXUS_GAME_DOMAINS.get(self.current().get('name',''))) if provider=='Nexus Mods' else None
            # Preserve record object identities for selected catalogue rows, while
            # sorting only temporary UI records (no source assignment occurs).
            graded=[]
            for i, rec in enumerate(records):
                grade=candidate_review.review_hint(target.get('search_query') or target['name'],rec,domain)
                rec['review_hint']=grade['hint']
                graded.append((-grade['band'],i,rec))
            records=[rec for _,_,rec in sorted(graded)]
        self.provider_results=records
        self.provider_tree.delete(*self.provider_tree.get_children())
        for i,rec in enumerate(records):
            detail=rec.get('description','')
            if same_game:
                detail=(rec.get('review_hint','Unverified result')+' | '+detail)[:510]
            self.provider_tree.insert('','end',iid=str(i),values=(rec['title'],rec['author'],
                         rec['version'],rec['provider'],detail))
        if same_game:
            self.provider_info.set(f'{len(records)} {provider} results, ordered by title-search relevance only. '
                'These are NOT verified identities. Open each official page, check the uploader and game, then approve any link explicitly.')
        else:
            self.provider_info.set(f'{len(records)} {provider} results. Select a result to open the official website. No automatic source matches are made.')

    def provider_open_result(self):
        selection=self.provider_tree.selection()
        if not selection:return
        try: url=self.provider_results[int(selection[0])]['url']
        except (IndexError,ValueError,KeyError,TypeError):return
        # URLs originate from safe provider-specific constructors/parsers.
        webbrowser.open(url)

    def provider_modio_diagnostic(self):
        """Check a selected mod's live read-only API path without changing files."""
        if getattr(self, '_modio_diagnostic_busy', False):
            return
        try:
            selection = self.provider_tree.selection()
            if len(selection) != 1:
                raise modio_files.ModioError('Select one mod.io search result first.')
            ref = self.provider_results[int(selection[0])]
            if ref.get('provider') != 'mod.io':
                raise modio_files.ModioError('Select an official mod.io search result.')
            gid, mid = modio_files._identity(ref.get('identity'))
            uid = provider_catalogues.numeric(self.modio_user_id.get().strip())
            key = self.provider_key.get().strip()
            digest = hashlib.sha256(key.encode()).digest()
            verified = self.modio_verified
            game = self.current()
            if (self.provider_choice.get() != 'mod.io' or not game or not verified
                    or verified[:3] != (gid, uid, digest)
                    or self.provider_scope.get().strip() != gid
                    or re.sub('[^a-z0-9]', '', game.get('name', '').casefold()) !=
                       re.sub('[^a-z0-9]', '', verified[3].casefold())):
                raise modio_files.ModioError('Verify the current installed game, mod.io User ID, and session key first.')
            game_root = str(Path(game['root']).resolve(strict=True))
            identity = gid + '/' + mid
        except (modio_files.ModioError, provider_catalogues.ProviderError,
                IndexError, KeyError, TypeError, ValueError, OSError) as exc:
            messagebox.showwarning('mod.io API diagnostic', str(exc), parent=self)
            return

        self._modio_diagnostic_busy = True
        self._modio_diagnostic_events = queue.Queue()
        self.provider_info.set('Testing mod.io game, release list and exact-file metadata (GET only)…')

        def worker():
            try:
                report = modio_diagnostics.check_modio_access(
                    identity, user_id=uid, api_key=key)
                error = None
            except (modio_files.ModioError, provider_catalogues.ProviderError) as exc:
                report = None
                error = str(exc)
            except Exception:
                report = None
                error = 'The mod.io API diagnostic could not complete.'
            # Never queue the key, signed URLs, or provider raw responses.
            self._modio_diagnostic_events.put(
                (game_root, identity, uid, digest, report, error))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_modio_diagnostic)

    def _poll_modio_diagnostic(self):
        try:
            game_root, identity, uid, digest, report, error = self._modio_diagnostic_events.get_nowait()
        except queue.Empty:
            if self._modio_diagnostic_busy and self.winfo_exists():
                self.after(100, self._poll_modio_diagnostic)
            return
        self._modio_diagnostic_busy = False
        if not self.winfo_exists():
            return
        game = self.current()
        selected = self.provider_tree.selection()
        try:
            same_selection = (len(selected) == 1 and
                              self.provider_results[int(selected[0])].get('provider') == 'mod.io' and
                              self.provider_results[int(selected[0])].get('identity') == identity)
            same_game = game and str(Path(game['root']).resolve(strict=True)) == game_root
            same_session = (self.provider_choice.get() == 'mod.io' and
                            self.modio_verified is not None and
                            self.modio_verified[:3] == (identity.split('/')[0], uid, digest) and
                            self.provider_scope.get().strip() == identity.split('/')[0] and
                            self.modio_user_id.get().strip() == uid and
                            hashlib.sha256(self.provider_key.get().strip().encode()).digest() == digest)
        except (OSError, ValueError, IndexError, TypeError, KeyError):
            same_selection = same_game = same_session = False
        if not (same_selection and same_game and same_session):
            self.provider_info.set('mod.io game, selection or credentials changed; diagnostic results discarded.')
            return
        if error:
            self.provider_info.set('mod.io API diagnostic: ' + error)
            messagebox.showwarning('mod.io API diagnostic', error, parent=self)
            return
        self.provider_info.set('mod.io API diagnostic completed; no file downloaded or installed.')
        messagebox.showinfo('mod.io API diagnostic',
            f"Game ID: {report['game_id']} | Mod ID: {report['mod_id']}\n"
            f"Status: {report['status']}\n"
            f"Eligible ZIP releases on first page: {report['eligible_zip_files']}\n"
            f"Exact file checked: {report['checked_file_id'] or 'none'}\n\n"
            'Only API metadata was requested. No ZIP was downloaded, game files were not changed, '
            'and the session key was not saved. Live install and rollback testing is still required.',
            parent=self)

    def provider_files_dialog(self):
        """Reviewed file selection: no source assignment or installation from search."""
        selection=self.provider_tree.selection()
        if not selection:
            messagebox.showinfo('Discover files','Select a search result first.',parent=self);return
        try: ref=self.provider_results[int(selection[0])]
        except (IndexError,ValueError,KeyError,TypeError):return
        provider=ref.get('provider')
        if provider=='CurseForge':
            self.provider_curseforge_files_dialog(ref)
            return
        if provider not in ('GitHub','Modrinth','mod.io'):
            messagebox.showinfo('Files not available',
                f'{provider} file downloads are not yet integrated here. Open the official mod page instead.',parent=self)
            return
        identity=ref.get('identity') or ''
        modio_context=None
        if provider=='mod.io':
            game=self.current()
            try:
                gid,mid=modio_files._identity(identity)
                uid=provider_catalogues.numeric(self.modio_user_id.get().strip())
                key=self.provider_key.get().strip()
                verified=self.modio_verified
                digest=hashlib.sha256(key.encode()).digest()
                if (not game or not verified or verified[:3]!=(gid,uid,digest)
                    or re.sub('[^a-z0-9]','',game.get('name','').casefold()) !=
                        re.sub('[^a-z0-9]','',verified[3].casefold())):
                    raise modio_files.ModioError('Verify that the mod.io game matches the current installed game before browsing files.')
                modio_context=(uid,key,str(Path(game['root']).resolve()),str(game.get('name') or ''))
            except (modio_files.ModioError,provider_catalogues.ProviderError) as exc:
                messagebox.showwarning('mod.io game check',str(exc),parent=self)
                return
        dialog=tk.Toplevel(self)
        dialog.title(f'{provider} — release files (review only)')
        dialog.geometry('950x590');dialog.minsize(710,430)
        controls=ttk.Frame(dialog,padding=12);controls.pack(fill='x')
        ttk.Label(controls,text=ref.get('title') or identity,style='Section.TLabel').pack(anchor='w')
        ttk.Label(controls,text=('mod.io ZIPs download into your inbox after a fresh exact-file lookup and checksum check. '
              'Installation is only available for identifiable SMAPI/BepInEx archives and always requires separate approval.'
              if provider=='mod.io' else 'Files download to your inbox, never directly into the game. Verify compatibility before installing.'),
                  wraplength=860).pack(anchor='w',pady=(3,8))
        filters=ttk.Frame(controls);filters.pack(fill='x',pady=6)
        ttk.Label(filters,text='Game version:').pack(side='left')
        game_version=tk.StringVar()
        ttk.Entry(filters,textvariable=game_version,width=14).pack(side='left',padx=(5,12))
        ttk.Label(filters,text='Loader:').pack(side='left')
        loader=tk.StringVar()
        ttk.Entry(filters,textvariable=loader,width=16).pack(side='left',padx=(5,12))
        if provider=='GitHub':
            ttk.Label(filters,text='GitHub does not publish standard compatibility metadata.',
                      style='Subtle.TLabel').pack(side='left',padx=8)
        info=tk.StringVar(value='Select Fetch files to load releases. Nothing installs automatically.')
        ttk.Label(controls,textvariable=info,wraplength=870).pack(anchor='w',pady=(3,7))
        area=ttk.Frame(dialog,padding=(12,0,12,0));area.pack(fill='both',expand=True)
        cols=('version','filename','size','compat','dependencies')
        tree=ttk.Treeview(area,columns=cols,show='headings',selectmode='browse')
        for col,title,width in [('version','VERSION',110),('filename','FILE',330),('size','SIZE',90),
                                ('compat','COMPATIBILITY',260),('dependencies','DEPENDENCIES',135)]:
            tree.heading(col,text=title);tree.column(col,width=width,minwidth=60,stretch=(col in ('filename','compat')))
        tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(area,command=tree.yview);scroll.pack(side='right',fill='y')
        tree.configure(yscrollcommand=scroll.set)
        state={'rows':[],'busy':False};events=queue.Queue()
        def poll():
            try:kind,payload=events.get_nowait()
            except queue.Empty:
                if state['busy'] and dialog.winfo_exists():dialog.after(90,poll)
                return
            if not dialog.winfo_exists():return
            state['busy']=False;load_btn.configure(state='normal');download_btn.configure(state='normal')
            if kind=='error':
                info.set(payload);return
            if kind=='download':
                info.set('Saved '+str(payload)+'. Open Provider Inbox to review compatibility and installation.')
                self.provider_stage_refresh()
                return
            state['rows']=payload;tree.delete(*tree.get_children())
            for i,row in enumerate(payload):
                versions=', '.join(row['game_versions'][:4]) or 'Unverified'
                loaders=', '.join(row['loaders'][:4])
                compat=(' / '.join(filter(None,[versions,loaders])) if provider=='Modrinth'
                        else 'Unverified — inspect release notes')
                size=f"{row['size']/1024/1024:.1f} MB"
                tree.insert('','end',iid=str(i),values=(row['version'],row['filename'],size,compat,
                                     f"{len(row['dependencies'])} declared" if row['dependencies'] else 'Not specified'))
            info.set(f'{len(payload)} files. Choose one file to stage; check its game version and dependencies first.')
        def fetch_files():
            if state['busy']:return
            state['busy']=True;load_btn.configure(state='disabled');download_btn.configure(state='disabled')
            info.set('Loading '+provider+' versions and file metadata…')
            gv=game_version.get().strip() if provider=='Modrinth' else ''
            ld=loader.get().strip() if provider=='Modrinth' else ''
            def work():
                try:
                    rows=(modio_files.list_modfiles(identity,user_id=modio_context[0],api_key=modio_context[1])
                          if provider=='mod.io' else provider_downloads.list_files(provider,identity,game_version=gv,loader=ld))
                    events.put(('rows',rows))
                except (provider_downloads.DownloadError,provider_catalogues.ProviderError) as exc:
                    events.put(('error',str(exc)))
                except Exception:
                    events.put(('error','Provider listing failed; check your connection.'))
            threading.Thread(target=work,daemon=True).start();dialog.after(100,poll)
        def stage_file():
            if state['busy'] or not tree.selection():return
            try:row=state['rows'][int(tree.selection()[0])]
            except (IndexError,ValueError,TypeError):return
            where=Path(self.inbox_folder.get()).expanduser()
            if not where.is_dir():
                messagebox.showerror('Download folder','Choose an existing Downloads folder on the Downloads screen.',parent=dialog)
                return
            if provider=='mod.io':
                game=self.current()
                if (not game or str(Path(game['root']).resolve())!=modio_context[2]
                    or str(game.get('name') or '')!=modio_context[3]
                    or self.modio_user_id.get().strip()!=modio_context[0]
                    or self.provider_key.get().strip()!=modio_context[1]):
                    messagebox.showwarning('mod.io game changed','Current game or mod.io session key changed. Search again.',parent=dialog)
                    return
            details=(f"{row['filename']} ({row['size']/1024/1024:.1f} MB)\n"
                     f"Provider: {provider}\nRelease: {row['version']}\n"
                     f"Compatibility: {', '.join(row['game_versions'][:8]) or 'Not verified'}\n"
                     f"Loader: {', '.join(row['loaders'][:8]) or 'Not verified'}\n"
                     f"Dependencies: {len(row['dependencies'])} listed (not auto-installed)\n\n"
                     'Download into the inbox only? No game files will be changed.')
            if not messagebox.askyesno('Review selected download',details,parent=dialog):return
            game_root_at_review=(self.current().get('root','') if self.current() else '')
            state['busy']=True;load_btn.configure(state='disabled');download_btn.configure(state='disabled')
            info.set('Downloading selected file to inbox (no installation)…')
            def work():
                try:
                    output=provider_staging.stage_download(
                        row,where,PROVIDER_STAGE_FILE,
                        game_root=('' if provider=='Modrinth' else modio_context[2] if provider=='mod.io' else game_root_at_review),
                        downloader=(lambda record,location:modio_files.download_selected(
                            record,location,user_id=modio_context[0],api_key=modio_context[1])) if provider=='mod.io' else None)
                    events.put(('download',output.name))
                except (provider_downloads.DownloadError,FileExistsError) as exc:
                    events.put(('error',str(exc)))
                except Exception:
                    events.put(('error','Download failed. No existing mod was modified.'))
            threading.Thread(target=work,daemon=True).start();dialog.after(100,poll)
        actions=ttk.Frame(dialog,padding=12);actions.pack(fill='x')
        load_btn=ttk.Button(actions,text='Fetch files',command=fetch_files,style='Accent.TButton')
        load_btn.pack(side='left')
        download_btn=ttk.Button(actions,text='Download selected to inbox',command=stage_file)
        download_btn.pack(side='left',padx=8)
        ttk.Button(actions,text='Official page ↗',command=lambda:webbrowser.open(ref['url'])).pack(side='left')
        ttk.Button(actions,text='Close',command=dialog.destroy).pack(side='right')

    def provider_check_modio_updates(self):
        """Read-only check for exact mod.io identities from UniMod install receipts."""
        if getattr(self,'_modio_check_busy',False):return
        game=self.current()
        try:
            verified=self.modio_verified
            if not game or game.get('kind') not in ('smapi','bepinex') or not verified:
                raise modio_files.ModioError('Select a supported installed game and verify its mod.io game ID in Discover first.')
            gid,uid,digest,title=verified
            key=self.provider_key.get().strip()
            if (self.provider_choice.get()!='mod.io' or self.provider_scope.get().strip()!=gid
                or self.modio_user_id.get().strip()!=uid
                or hashlib.sha256(key.encode()).digest()!=digest
                or re.sub('[^a-z0-9]','',game.get('name','').casefold())!=
                   re.sub('[^a-z0-9]','',title.casefold())):
                raise modio_files.ModioError('mod.io game/account/key has changed. Verify the selected game again.')
            managed=modio_managed.managed_installs(game,read_receipts(),game_id=gid)
            if not managed:
                messagebox.showinfo('Managed mod.io check',
                    'No unchanged, provenance-tracked mod.io installations for this game. '
                    'Older installations may require one new reviewed installation to establish exact file-ID tracking. '
                    'No game files were changed.',parent=self)
                return
            game_root=str(Path(game['root']).resolve())
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            messagebox.showwarning('Managed mod.io check',str(exc),parent=self);return
        self._modio_check_busy=True
        self._modio_check_events=queue.Queue()
        self.provider_stage_info.set(f'Checking available mod.io files for {len(managed)} verified managed installation(s)…')
        def worker():
            updates=[];errors=0
            for installed in managed[:20]:
                try:
                    rows=modio_files.list_modfiles(installed['identity'],user_id=uid,api_key=key)
                    current=next((row.get('date_added',0) for row in rows
                                  if row.get('version_id')==installed['version_id']),None)
                    if current is None:
                        # Older installed files may fall beyond the newest 100.
                        # Retrieve their exact metadata; never infer dates from IDs.
                        current=modio_files.get_modfile_date(installed['identity'],installed['version_id'],
                                                               user_id=uid,api_key=key)
                    updates.extend(modio_managed.newer_release_candidates(installed,rows,
                                             current_date_added=current)[:3])
                except (modio_files.ModioError,provider_catalogues.ProviderError,ValueError):
                    errors+=1
                except Exception:
                    errors+=1
            self._modio_check_events.put((game_root,gid,uid,digest,updates,errors,len(managed)))
        threading.Thread(target=worker,daemon=True).start()
        self.after(90,self._poll_modio_check)

    def _poll_modio_check(self):
        try: result=self._modio_check_events.get_nowait()
        except queue.Empty:
            if self._modio_check_busy and self.winfo_exists():self.after(90,self._poll_modio_check)
            return
        self._provider_modio_check_finished(*result)

    def _provider_modio_check_finished(self,game_root,gid,uid,digest,updates,errors,count):
        self._modio_check_busy=False
        if not self.winfo_exists():return
        game=self.current()
        if (not game or str(Path(game['root']).resolve())!=game_root
            or self.modio_verified is None or self.modio_verified[:3]!=(gid,uid,digest)
            or hashlib.sha256(self.provider_key.get().strip().encode()).digest()!=digest):
            self.provider_stage_info.set('Game or mod.io credentials changed. Discarded update check results.')
            return
        mods={x['identity'] for x in updates}
        verified=sum(1 for row in updates if row['review_status']=='Newer publication date')
        self.provider_stage_info.set(f'{verified} verified newer release file(s), {len(updates)-verified} unverified alternative(s), {errors} failed checks. Nothing downloaded or installed.')
        if updates:
            lines=[f"{row['identity']}: installed file #{row['installed_file_id']} / review file #{row['available_file_id']} ({row['version'] or 'unlabelled'}) — {row['review_status']}"
                   for row in updates[:12]]
            messagebox.showinfo('mod.io releases to review',
                '\n'.join(lines)+'\n\nPublication dates are not compatibility guarantees. Unverified files need manual review. Open the exact mod.io project in Discover before staging an approved ZIP. No game files were changed.',parent=self)
        else:
            messagebox.showinfo('Managed mod.io check',
                f'No newer or unverified alternative ZIP releases were found among the queried results for {count} tracked mod(s). '
                f'{errors} request(s) failed. Filtered or failed listings do not prove a mod is up to date.',parent=self)

    def provider_stage_refresh(self):
        if not hasattr(self,'provider_stage_tree'):return
        self.provider_stage_rows=provider_staging.read_staged(PROVIDER_STAGE_FILE)
        self.provider_stage_tree.delete(*self.provider_stage_tree.get_children())
        for index,entry in enumerate(self.provider_stage_rows):
            dep_count=len(entry.get('dependencies',[])) if isinstance(entry.get('dependencies'),list) else '?'
            self.provider_stage_tree.insert('','end',iid=str(index),values=(entry.get('provider',''),entry.get('filename',''),
                     entry.get('version',''),Path(entry.get('game_root','')).name if entry.get('game_root') else 'Unassigned',str(dep_count)+' declared'))
        self.provider_stage_info.set(f'{len(self.provider_stage_rows)} staged files. Select a matching installed game and choose Review & install. ZIPs require verified package identities; no automatic installs.')

    def minecraft_mrpack_inspect(self):
        """Read-only modpack contents review, not an importer."""
        chosen=self.provider_stage_tree.selection()
        if not chosen:
            messagebox.showinfo('Modrinth modpack','Select a staged .mrpack first.',parent=self);return
        try:entry=dict(self.provider_stage_rows[int(chosen[0])])
        except (IndexError,TypeError,ValueError):return
        try:report=minecraft_mrpack.inspect_pack(entry)
        except (minecraft_mrpack.PackError,OSError,ValueError) as exc:
            messagebox.showwarning('Modpack inspection blocked',str(exc),parent=self);return
        loader=', '.join(key+' '+value for key,value in report['loader'].items())
        messagebox.showinfo('Modrinth pack — read-only preview',
            f"{report['name']}\nMinecraft {report['minecraft']} / {loader}\n"
            f"Download files: {report['file_count']} ({report['bytes']/1024/1024:.1f} MiB)\n"
            f"Client overrides: {report['override_count']}\n"
            f"Optional files: {report['optional_count']}\n"
            f"Files without supported CDN downloads: {report['unsupported_urls']}\n\n"
            'This is a read-only preview. Use Import .mrpack to Prism/MultiMC for a separate compatibility review and approval.',parent=self)

    def minecraft_mrpack_import(self):
        """Review a staged pack against one existing profile before any downloads."""
        if self._stage_running:return
        chosen=self.provider_stage_tree.selection()
        if not chosen:
            messagebox.showinfo('Modrinth modpack','Select a staged .mrpack first.',parent=self);return
        try:entry=dict(self.provider_stage_rows[int(chosen[0])])
        except (IndexError,TypeError,ValueError):return
        if entry.get('provider')!='Modrinth' or not str(entry.get('filename','')).lower().endswith('.mrpack'):
            messagebox.showwarning('Modrinth modpack','Select a verified .mrpack download.',parent=self);return
        profiles=minecraft_profiles.discover_instances()
        folder=(profiles[0]['root'] if len(profiles)==1 else filedialog.askdirectory(
            parent=self,title='Choose an existing Prism/MultiMC instance (containing mmc-pack.json)'))
        if not folder:return
        self._stage_running=True
        self.provider_stage_info.set('Reviewing modpack paths, archive and exact Minecraft/loader versions…')
        def work():
            try:plan=minecraft_mrpack.plan_import(entry,folder);error=None
            except Exception as exc:plan=None;error=str(exc)
            self.after(0,lambda:self._minecraft_mrpack_plan_finished(plan,error))
        threading.Thread(target=work,daemon=True).start()

    def _minecraft_mrpack_choose_optional(self, candidates):
        """Review optional client downloads. None cancels, [] skips all."""
        dialog=tk.Toplevel(self)
        dialog.title('Choose optional Modrinth pack files')
        dialog.geometry('700x400')
        dialog.transient(self)
        ttk.Label(dialog,text='Optional client files are OFF by default. Select only those you want installed.',
                  wraplength=650).pack(anchor='w',padx=12,pady=(12,7))
        frame=ttk.Frame(dialog);frame.pack(fill='both',expand=True,padx=12)
        scroll=ttk.Scrollbar(frame,orient='vertical')
        choices=tk.Listbox(frame,selectmode='multiple',yscrollcommand=scroll.set,exportselection=False)
        scroll.configure(command=choices.yview)
        choices.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        for item in candidates:
            label=f"{item['path']}   ({item['size']/1024/1024:.2f} MiB)"
            if not item['available']:label+=' — unavailable (unsupported host or overlap)'
            choices.insert('end',label)
            if not item['available']:choices.itemconfig('end',fg='gray')
        selected={'value':None}
        def finish(mode):
            if mode=='cancel':selected['value']=None
            elif mode=='skip':selected['value']=[]
            else:
                indices=choices.curselection()
                if any(not candidates[i]['available'] for i in indices):
                    messagebox.showwarning('Optional file unavailable',
                        'One or more selected optional files cannot be installed safely.',parent=dialog)
                    return
                selected['value']=[candidates[i]['path'] for i in indices]
            dialog.destroy()
        actions=ttk.Frame(dialog);actions.pack(fill='x',padx=12,pady=12)
        ttk.Button(actions,text='Cancel import',command=lambda:finish('cancel')).pack(side='left')
        ttk.Button(actions,text='Skip optional files',command=lambda:finish('skip')).pack(side='right',padx=(8,0))
        ttk.Button(actions,text='Review selected files',command=lambda:finish('selected')).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW',lambda:finish('cancel'))
        dialog.grab_set();self.wait_window(dialog)
        return selected['value']

    def _minecraft_mrpack_plan_finished(self,plan,error,offer_options=True):
        if not self.winfo_exists():return
        if error:
            self._stage_running=False
            self.provider_stage_info.set('Modpack preflight blocked: '+error)
            messagebox.showwarning('Modpack import blocked',error,parent=self);return
        if offer_options and plan['optional_candidates']:
            selected=self._minecraft_mrpack_choose_optional(plan['optional_candidates'])
            if selected is None:
                self._stage_running=False
                self.provider_stage_info.set('Modpack import cancelled. No downloads or game changes.')
                return
            if selected:
                self.provider_stage_info.set('Rechecking selected optional files and backup sizes…')
                def recheck():
                    try:
                        updated=minecraft_mrpack.plan_import(plan['receipt'],plan['profile']['root'],selected)
                        error=None
                    except Exception as exc:updated=None;error=str(exc)
                    self.after(0,lambda:self._minecraft_mrpack_plan_finished(updated,error,False))
                threading.Thread(target=recheck,daemon=True).start()
                return
        if not plan['writes']:
            self._stage_running=False
            self.provider_stage_info.set('No installable modpack files were selected. Nothing changed.')
            messagebox.showinfo('Nothing to import',
                'No required files or optional files were selected. Nothing was installed.',parent=self)
            return
        info=plan['profile']
        question=(f"Pack: {plan['pack_name']} ({plan['version_id']})\n"
                  f"Existing instance: {info['root']}\n"
                  f"Minecraft {info['version']}, {info['loader']} {info['loader_version']}\n\n"
                  f"Files to install: {len(plan['writes'])}\n"
                  f"CDN downloads: {plan['download_count']} ({plan['download_bytes']/1024/1024:.1f} MiB)\n"
                  f"Files to overwrite (backed up): {plan['overwrite_count']} "
                  f"({plan['backup_bytes']/1024/1024:.1f} MiB)\n"
                  f"Optional selected: {len(plan['selected_optional'])}\n"
                  f"Optional/server-only downloads skipped: {plan['optional_skipped']}\n\n"
                  'Only official Modrinth CDN downloads are accepted; hashes and file sizes are verified. '
                  'Existing game files are backed up and restored on an import error.\n\n'
                  'Close Minecraft before proceeding. Import these files to the selected profile?')
        if not messagebox.askyesno('Review Minecraft modpack installation',question,parent=self):
            self._stage_running=False
            self.provider_stage_info.set('Modpack import cancelled. No downloads or game changes.');return
        self.provider_stage_info.set('Downloading and verifying all required modpack files before game changes…')
        def work():
            try:
                result=minecraft_mrpack.install_import(plan,APP/'recovery'/'minecraft-packs',
                                             APP/'minecraft-pack-receipts.json')
                error=None
            except Exception as exc:result=None;error=str(exc)
            self.after(0,lambda:self._minecraft_mrpack_install_finished(result,error))
        threading.Thread(target=work,daemon=True).start()

    def _minecraft_mrpack_install_finished(self,result,error):
        self._stage_running=False
        if not self.winfo_exists():return
        if error:
            self.provider_stage_info.set('Modpack import blocked/failed: '+error)
            messagebox.showerror('Modpack import failed',error,parent=self);return
        self.provider_stage_info.set('Imported '+str(result['installed'])+' files into '+result['profile'])
        messagebox.showinfo('Modpack imported',
            f"Installed {result['installed']} files into:\n{result['profile']}\n\n"
            f"Recovery backups: {result['backup']}\n"
            f"Optional installed: {len(result['selected_optional'])}\n"
            f"Optional/server-only files skipped: {result['skipped_optional']}",parent=self)
        self.provider_stage_refresh()

    def minecraft_profile_install(self):
        """Review dependency closure before any network download or game writes."""
        if self._stage_running:return
        chosen=self.provider_stage_tree.selection()
        if not chosen:
            messagebox.showinfo('Minecraft profile','Select a staged Modrinth JAR first.',parent=self);return
        try:entry=dict(self.provider_stage_rows[int(chosen[0])])
        except (ValueError,IndexError,TypeError):return
        if entry.get('provider')!='Modrinth' or not entry.get('filename','').lower().endswith('.jar'):
            messagebox.showwarning('Minecraft profile','Select a verified Modrinth JAR. Modpacks are still download-only.',parent=self);return
        profiles=minecraft_profiles.discover_instances()
        folder=(profiles[0]['root'] if len(profiles)==1 else filedialog.askdirectory(
            parent=self,title='Choose Prism/MultiMC instance folder (containing mmc-pack.json)'))
        if not folder:return
        journal=APP/'minecraft-install-receipts.json'
        self._stage_running=True
        self.provider_stage_info.set('Checking Minecraft compatibility and resolving required Modrinth dependencies…')
        def worker():
            try:plan=minecraft_dependencies.plan_dependencies(entry,folder,journal);error=None
            except Exception as exc:plan=None;error=str(exc)
            self.after(0,lambda:self._minecraft_plan_finished(plan,error))
        threading.Thread(target=worker,daemon=True).start()

    def _minecraft_plan_finished(self,plan,error):
        if not self.winfo_exists():return
        if error:
            self._stage_running=False
            self.provider_stage_info.set('Minecraft preflight refused: '+error)
            messagebox.showwarning('Minecraft installation blocked',error,parent=self);return
        deps=plan['dependencies']
        detail='\n'.join('  • '+row['identity']+' / '+row['version']+' / '+row['filename'] for row in deps)
        info=plan['profile'];parent=plan['parent']
        question=(f"Minecraft profile: {info['root']}\nMinecraft: {info['version']} / {info['loader']}\n"
                  f"Selected JAR: {parent['filename']}\n"
                  f"Missing required dependencies: {len(deps)} "
                  f"({plan['bytes']/1024/1024:.1f} MiB to download)\n\n"
                  +(detail+'\n\n' if detail else 'All required dependencies already verified.\n\n')+
                  'Download required JARs from Modrinth, verify them, and install to this profile? '
                  'Updates keep recovery backups. Close Minecraft before proceeding.')
        if not messagebox.askyesno('Review complete Minecraft install',question,parent=self):
            self._stage_running=False
            self.provider_stage_info.set('Minecraft install cancelled before downloads or game changes.');return
        self.provider_stage_info.set('Downloading verified dependencies before changing Minecraft profile…')
        journal=APP/'minecraft-install-receipts.json';recovery=APP/'recovery'/'minecraft'
        def worker():
            try:
                result=minecraft_dependencies.install_plan(plan,APP/'downloads'/'minecraft-dependencies',
                                    PROVIDER_STAGE_FILE,journal,recovery)
                error=None
            except Exception as exc:result=None;error=str(exc)
            self.after(0,lambda:self._minecraft_install_finished(result,error))
        threading.Thread(target=worker,daemon=True).start()

    def _minecraft_install_finished(self,result,error):
        self._stage_running=False
        if not self.winfo_exists():return
        if error:
            self.provider_stage_info.set('Minecraft install refused or failed: '+error)
            messagebox.showerror('Minecraft install failed',error,parent=self);return
        n=result.get('dependency_count',0)
        self.provider_stage_info.set('Installed '+result['path']+f' with {n} required dependencies.')
        messagebox.showinfo('Minecraft mod installed',
            'Installed: '+result['path']+f'\nNew required dependencies: {n}'+
            (('\nBackup: '+result['backup']) if result['backup'] else ''),parent=self)
        self.provider_stage_refresh()

    def provider_stage_install(self):
        if self._stage_running:return
        game=self.current();chosen=self.provider_stage_tree.selection()
        if not chosen or not game:
            messagebox.showinfo('Provider Inbox','Select a configured game and one downloaded file.',parent=self);return
        try:entry=dict(self.provider_stage_rows[int(chosen[0])])
        except (ValueError,TypeError,IndexError):return
        self._stage_running=True
        self.provider_stage_info.set('Checking archive, installed identities and required dependencies…')
        game_root=str(Path(game['root']).resolve())
        def work():
            result=provider_install_preflight(game,entry)
            self.after(0,lambda:self._provider_stage_checked(game_root,entry,result))
        threading.Thread(target=work,daemon=True).start()

    def _provider_stage_checked(self,game_root,entry,result):
        if not self.winfo_exists():return
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=game_root:
            self._stage_running=False;return
        action=result.get('status','Blocked')
        if action not in ('Install new','Update existing'):
            self._stage_running=False
            self.provider_stage_info.set(action+': '+result.get('detail',''))
            messagebox.showwarning('Provider install unavailable',action+'\n\n'+result.get('detail',''),parent=self)
            return
        info=(f"Provider: {entry.get('provider')}\nFile: {entry.get('filename')}\n"
              f"Game: {game.get('name') or game_root}\nAction: {action}\n\n{result.get('detail','')}\n\n"
              'The game must be closed. Provider metadata and an archive hash do not guarantee that the mod is safe or compatible. '
              'Backups are retained for updates; new installations have managed undo receipts.\n\nProceed?')
        if not messagebox.askyesno('Review provider installation',info,parent=self):
            self._stage_running=False;self.provider_stage_info.set('Installation cancelled; no game files changed.');return
        self.provider_stage_info.set('Installing reviewed ZIP with package identity checks…')
        def install():
            try:outcome=provider_install_reviewed(game,entry);error=None
            except Exception as exc:outcome=None;error=str(exc)
            self.after(0,lambda:self._provider_stage_finished(game_root,outcome,error))
        threading.Thread(target=install,daemon=True).start()

    def _provider_stage_finished(self,game_root,outcome,error):
        self._stage_running=False
        if not self.winfo_exists():return
        if error:
            self.provider_stage_info.set('Install refused or failed: '+error)
            messagebox.showerror('Provider install failed',error,parent=self);return
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=game_root:return
        self.refresh();self.provider_stage_refresh()
        info=('Previous mod backed up at: '+outcome['backup'] if outcome['action']=='updated' else
              str(len(outcome['paths']))+' new managed folder(s) recorded for recovery.')
        if outcome.get('history_warning'):
            info+='\nUpdate succeeded, but mod.io provenance could not be saved. Automatic release checks will not recognise this update.'
        messagebox.showinfo('Provider installation completed',info,parent=self)

    def ts_stage(self):
        """Download selected Thunderstore package to shared inbox; never install here."""
        selection=self.ts_tree.selection()
        if not selection:return
        try:pkg=self.ts_filtered[int(selection[0])]
        except (ValueError,IndexError,TypeError):return
        where=Path(self.inbox_folder.get()).expanduser()
        if not where.is_dir():
            messagebox.showerror('Download folder','Choose an existing Downloads folder.',parent=self);return
        game=self.current()
        if not game:
            messagebox.showinfo('Game required','Select a game before staging this package.',parent=self);return
        if not messagebox.askyesno('Stage Thunderstore ZIP?',
                f"Download {pkg.get('full_name',pkg.get('name','package'))} to your Provider Inbox?\n\n"
                'No game files will be changed. Dependencies must be resolved before installation.',parent=self):return
        self.ts_info.set('Staging Thunderstore package…')
        def work():
            try:
                provider_staging.stage_download({'provider':'Thunderstore',**pkg},where,PROVIDER_STAGE_FILE,game_root=game['root'])
                error=None
            except Exception as exc:error=str(exc)
            self.after(0,lambda:self._ts_stage_finished(error))
        threading.Thread(target=work,daemon=True).start()

    def _ts_stage_finished(self,error):
        if error:self.ts_info.set('Stage failed: '+error)
        else:
            self.ts_info.set('Thunderstore ZIP staged. Open Provider Inbox to review installation.')
            self.provider_stage_refresh()

    def nexus_oauth_connect(self):
        """Development login: OAuth tokens are memory-only, never placed in API-key widgets.

        Nexus must confirm the client ID, endpoints and loopback callback before
        authenticated REST download integration can be activated.
        """
        if self.nexus_running:return
        try: cfg=nexus_oauth.OAuthConfig.from_environment()
        except (RuntimeError,ValueError) as exc:
            messagebox.showinfo('Nexus OAuth registration required',str(exc) +
                '\nUniMod uses Authorization Code + PKCE. Ask Nexus for the OAuth client ID, '                'exact authorize/token URLs, scopes and permitted redirect URI.',parent=self)
            return
        self.nexus_running=True
        self.nexus_info.set('Waiting for Nexus OAuth browser consent. Authentication stays in memory only…')
        def work():
            try:
                tokens=nexus_oauth.browser_login(cfg,lambda url:self.after(0,lambda:webbrowser.open(url)))
                err=None
            except Exception:
                tokens=None;err='Browser authorization not completed. Confirm the registered OAuth settings.'
            self.after(0,lambda:self.nexus_oauth_done(tokens,err))
        threading.Thread(target=work,daemon=True).start()

    def nexus_oauth_done(self,tokens,error):
        self.nexus_running=False
        if error:
            self.nexus_info.set(error);return
        self.nexus_oauth_tokens=tokens
        self.nexus_info.set('OAuth browser sign-in completed for this session. REST download integration '                            'remains disabled until Nexus confirms compatible endpoints/scopes.')

    def nexus_registration_info(self):
        slug = nexus_integr.registered_app_slug()
        messagebox.showinfo('Nexus application registration',
            ('Registered app slug: '+slug if slug else
            'Nexus ticket #273059: OAuth public client information is pending. We have an OAuth PKCE development framework. Contact support@nexusmods.com with the build, '
            'source, app description and logo. Once Nexus provides a slug, set '
            'UNIMOD_NEXUS_APP_SLUG in the launcher environment. Until then, use a '
            'session-only personal key for private testing.'),parent=self)

    def nexus_sso_connect(self):
        if self.nexus_running:return
        try: slug=nexus_integr.registered_app_slug()
        except ValueError as exc:
            messagebox.showerror('Nexus sign-in',str(exc),parent=self);return
        if not slug:
            self.nexus_registration_info();return
        self.nexus_running=True
        self.nexus_info.set('Waiting for approval in your browser. No credentials are stored on disk…')
        def worker():
            try: key=nexus_integr.sso_sign_in(slug,lambda url:self.after(0,lambda:webbrowser.open(url)));error=None
            except Exception as exc:key=None;error=str(exc)
            self.after(0,lambda:self.nexus_sso_done(key,error))
        threading.Thread(target=worker,daemon=True).start()

    def nexus_sso_done(self,key,error):
        self.nexus_running=False
        if error:
            self.nexus_info.set('Nexus sign-in not completed: '+error)
        else:
            self.nexus_key.set(key)
            self.nexus_info.set('Nexus account connected for this session. You can browse files or check updates.')

    def nexus_selected_download_ref(self):
        game=self.current();mod=self.nexus_selected_row() or self.picked()
        if not game or not mod:
            messagebox.showinfo('Choose a mod','Select an installed mod first.',parent=self);return None
        ref=nexus_reference(game,mod)
        if not ref or 'error' in ref:
            messagebox.showinfo('Source needed','Link this mod to its exact Nexus Mods page first.',parent=self);return None
        return ref

    def nexus_download_selected(self):
        if self.nexus_running:return
        ref=self.nexus_selected_download_ref()
        if ref is None:return
        key=self.nexus_key.get().strip()
        if not key:
            messagebox.showinfo('Nexus sign-in','Connect your Nexus account or use a private testing key.',parent=self);return
        self.nexus_running=True
        self.nexus_info.set('Retrieving the file list from Nexus (read-only)…')
        def worker():
            try:
                data=nexus_api_json(nexus_integr.mod_files_url(ref['game_domain'],ref['mod_id']),key)
                files=nexus_integr.normalize_files(data);error=None
            except Exception as exc: files=[];error=str(exc).replace(key,'[redacted]')
            self.after(0,lambda:self.nexus_show_file_choices(ref,files,error))
        threading.Thread(target=worker,daemon=True).start()

    def nexus_show_file_choices(self,ref,files,error):
        self.nexus_running=False
        if error:
            self.nexus_info.set('Nexus file listing failed: '+error);return
        if not files:
            self.nexus_info.set('No downloadable files found. Try the official mod page.');return
        dlg=tk.Toplevel(self);dlg.title('Choose a Nexus file — UniMod');dlg.geometry('790x450');dlg.transient(self)
        root=ttk.Frame(dlg,padding=12);root.pack(fill='both',expand=True)
        ttk.Label(root,text='Select the exact file to download — nothing is installed automatically.',wraplength=720).pack(anchor='w',pady=(0,12))
        tree=ttk.Treeview(root,columns=('name','version','category','id'),show='headings',selectmode='browse')
        for col,width in [('name',390),('version',105),('category',125),('id',80)]:
            tree.heading(col,text=col.title());tree.column(col,width=width)
        for i,f in enumerate(files):tree.insert('','end',iid=str(i),values=(f['name'],f['version'],f['category'],f['file_id']))
        tree.pack(fill='both',expand=True)
        def go():
            selected=tree.selection()
            if not selected:return
            file=files[int(selected[0])]
            dlg.destroy()
            if messagebox.askyesno('Confirm download',
                f"Queue {file['name']} (file #{file['file_id']}) for a reviewed download?\n\n"
                'No game mods will be changed. For non-Premium accounts, use the official Nexus browser download and import its NXM link.',parent=self):
                self.nexus_begin_download(ref,file, nxm=None)
        bar=ttk.Frame(root);bar.pack(fill='x',pady=10)
        ttk.Button(bar,text='Download selected',command=go).pack(side='left')
        ttk.Button(bar,text='Open official Nexus files page',command=lambda:webbrowser.open(ref['url']+'?tab=files')).pack(side='left',padx=8)
        ttk.Button(bar,text='Cancel',command=dlg.destroy).pack(side='right')

    def nexus_enable_browser_links(self):
        executable=os.environ.get('APPIMAGE','')
        if not executable:
            messagebox.showinfo('Nexus browser integration',
                'For source installations, open the v0.38 README for instructions. '
                'Run the UniMod AppImage and select Enable browser links to register it as an NXM handler.',parent=self)
            return
        if not messagebox.askyesno('Enable Nexus browser links',
            'Register this UniMod AppImage as your Linux handler for nxm:// links?\n\n'
            'The browser will send its Mod Manager Download link to UniMod, where you must review the request before downloading.\n\n'
            'You can change the handler later in KDE Default Applications.',parent=self):return
        try:destination=nxm_handler.install(executable)
        except (ValueError,RuntimeError,OSError) as exc:
            messagebox.showerror('Browser integration',str(exc),parent=self)
            return
        messagebox.showinfo('Browser integration enabled',
            'Nexus Mod Manager Download links will now open UniMod for review.\n\nDesktop entry: '+str(destination),parent=self)

    def nexus_download_nxm(self):
        value=simpledialog.askstring('Nexus manager download',
            'Paste the nxm:// link from the Nexus Mod Manager Download button.\n'
            'It will be queued for review; nothing downloads yet.',parent=self)
        if value:self.nexus_enqueue_nxm(value)

    def nexus_enqueue_nxm(self, value, from_browser=False):
        # The browser token stays in memory only. New links are forwarded to
        # this running window over an owner-only UNIX socket.
        try:
            entry=self.nexus_queue.add_nxm(value)
        except (ValueError,TypeError) as exc:
            messagebox.showerror('Invalid Nexus manager link',str(exc),parent=self)
            return
        self.nexus_queue_refresh()
        self.nexus_queue_tree.selection_set(str(entry.id))
        self.nexus_queue_tree.see(str(entry.id))
        if from_browser:
            self.deiconify()
            self.lift()
        self.tabs.select(self.inbox_tab)
        self.nexus_queue_info.set('Nexus link queued for review — choose Download selected to proceed. Nothing has been installed.')

    def nexus_queue_refresh(self):
        tree=self.nexus_queue_tree
        selected=tree.selection()
        for child in tree.get_children():tree.delete(child)
        for row in self.nexus_queue.public_rows():
            status=row['status']
            if status=='Downloading' and row['received']:
                current=row['received']/1048576
                if row['total']:
                    status+=f'  {int(row["received"] * 100 / row["total"])}% ({current:.1f} MiB)'
                else:
                    status+=f'  {current:.1f} MiB'
            tree.insert('','end',iid=str(row['id']),values=(row['game'],row['mod'],row['file'],status))
        if selected and tree.exists(selected[0]):tree.selection_set(selected[0])

    def nexus_queue_show_selection(self, event=None):
        selected=self.nexus_queue_tree.selection()
        if len(selected)==1:
            entry=self.nexus_queue.get(int(selected[0]))
            if entry and entry.note:
                self.nexus_queue_info.set(entry.note)

    def nexus_queue_remove(self):
        selected=self.nexus_queue_tree.selection()
        if not selected:return
        removed=sum(bool(self.nexus_queue.remove(int(i))) for i in selected)
        self.nexus_queue_refresh()
        self.nexus_queue_info.set(f'Removed {removed} request(s). Downloaded files are unchanged.')

    def nexus_queue_retry(self):
        if self.nexus_running:
            self.nexus_queue_info.set('Wait for the current batch to finish before retrying.')
            return
        selection=self.nexus_queue_tree.selection()
        changed=sum(bool(self.nexus_queue.retry(int(i))) for i in selection)
        self.nexus_queue_refresh()
        self.nexus_queue_info.set(f'{changed} request(s) ready for another reviewed attempt. Expired browser links must be reopened on Nexus.')

    def nexus_queue_cancel(self):
        if self.nexus_running and self._nexus_cancel_event is not None:
            self._nexus_cancel_event.set()
            self.nexus_queue_info.set('Cancelling the current transfer and remaining queued items. Temporary partial files will be discarded.')
        else:
            self.nexus_queue_info.set('No active download batch to cancel.')

    def nexus_queue_review(self):
        selection=self.nexus_queue_tree.selection()
        if len(selection)!=1:
            messagebox.showinfo('Choose a file','Select one completed download first.',parent=self)
            return
        entry=self.nexus_queue.get(int(selection[0]))
        if not entry or entry.status!='Downloaded' or not Path(entry.saved_path).is_file():
            messagebox.showinfo('Download unavailable','Select a completed, existing download. Files are never installed automatically.',parent=self)
            return
        archive=Path(entry.saved_path)
        self.inbox_folder.set(str(archive.parent))
        self.tabs.select(self.inbox_tab)
        if archive.suffix.lower()=='.zip':
            # Scan the archive with existing SMAPI/BepInEx preflight logic.
            self.inbox_scan()
            self.nexus_queue_info.set('Downloaded ZIP sent to Update Inbox for review. Select an exact match to apply with backup.')
        else:
            self.nexus_queue_info.set('Downloaded archive is available in the inbox. Automatic update matching currently requires ZIP.')
            messagebox.showinfo('Review archive','The ZIP update scanner does not support this archive format. No game files were changed.',parent=self)

    def nexus_queue_clear_finished(self):
        removed=self.nexus_queue.clear_finished()
        self.nexus_queue_refresh()
        self.nexus_queue_info.set(f'Cleared {removed} completed request(s). Downloaded files remain in your inbox.')

    def _poll_external_requests(self):
        if self.instance_bridge is not None:
            while True:
                try: action, value=self.instance_bridge.events.get_nowait()
                except queue.Empty: break
                if action=='nxm': self.nexus_enqueue_nxm(value,from_browser=True)
                else:
                    self.deiconify(); self.lift()
        if self.winfo_exists(): self.after(100,self._poll_external_requests)

    def _poll_queue_download_events(self):
        while True:
            try:kind, entry, result, error=self._queue_events.get_nowait()
            except queue.Empty:break
            if kind=='start':
                entry.status='Downloading';entry.note='';entry.received=0;entry.total=0
                self.nexus_queue_progress['value']=0
                self.nexus_queue_info.set(f'Downloading {entry.game} / mod #{entry.mod} / file #{entry.file}…')
            elif kind=='progress':
                entry.received=result;entry.total=error
                if error:
                    self.nexus_queue_progress['value']=min(100,int(result*100/error))
                    self.nexus_queue_info.set(f'Downloading mod #{entry.mod}: {result/1048576:.1f} / {error/1048576:.1f} MiB')
                else:
                    self.nexus_queue_info.set(f'Downloading mod #{entry.mod}: {result/1048576:.1f} MiB')
            elif kind=='cancelled':
                self._nexus_batch_remaining-=1
                entry.status='Cancelled';entry.note='Cancelled by user. No partial archive was saved.'
                entry.received=0;entry.total=0
            elif kind=='done':
                self._nexus_batch_remaining-=1
                if error:
                    entry.status='Needs attention';entry.note='Download failed: '+error
                    self.nexus_queue_info.set(entry.note)
                else:
                    self.nexus_queue.mark_downloaded(entry,result)
                    # Save non-secret provenance for future source reconciliation.
                    # A receipt is never sufficient for unattended installation.
                    try:
                        if result.suffix.casefold()=='.zip':
                            identities=_archive_manifest_identities(result)
                            source_receipts.record_receipt(result,entry.game,entry.mod,entry.file,
                                identities,NEXUS_RECEIPTS)
                    except (OSError,ValueError,UnicodeError,zipfile.BadZipFile,RuntimeError,EOFError):
                        pass  # A successful download remains usable without a receipt.
                    self.nexus_queue_info.set(f'Saved {result.name}. Installation still requires review in Update Inbox.')
            elif kind=='finished':
                self.nexus_running=False
                self._nexus_cancel_event=None
                self.nexus_queue_progress['value']=0
                if self._nexus_batch_remaining==0:
                    completed=sum(row.status=='Downloaded' for row in self.nexus_queue._items)
                    cancelled=sum(row.status=='Cancelled' for row in self.nexus_queue._items)
                    failed=sum(row.status=='Needs attention' for row in self.nexus_queue._items)
                    self.nexus_queue_info.set(f'Batch finished: {completed} downloaded, {cancelled} cancelled, {failed} need attention. No mods installed.')
                    if completed and self.current():self.unified_scan_downloads(silent=True)
            self.nexus_queue_refresh()
        if self.nexus_running or not self._queue_events.empty():
            self.after(90,self._poll_queue_download_events)

    def nexus_begin_download(self,ref,file,nxm=None):
        # All website file choices and NXM links enter the *same* review queue.
        try:
            if nxm is not None:
                entry=self.nexus_queue._add(ref['game_domain'],str(ref['mod_id']),
                    str(file['file_id']),file.get('filename') or 'mod.zip',nxm)
            else:
                entry=self.nexus_queue.add_file(ref['game_domain'],ref['mod_id'],file['file_id'],
                    file.get('filename') or f"nexus-{ref['mod_id']}-{file['file_id']}.zip")
        except (KeyError,ValueError,TypeError) as exc:
            messagebox.showerror('Cannot queue Nexus file',str(exc),parent=self)
            return
        self.nexus_queue_refresh()
        self.nexus_queue_tree.selection_set(str(entry.id))
        self.tabs.select(self.inbox_tab)
        self.nexus_queue_info.set('Download queued. Select it and approve Download selected to begin.')

    def nexus_queue_download(self):
        selected=self.nexus_queue_tree.selection()
        if len(selected)!=1:
            messagebox.showinfo('Choose a request','Select exactly one Nexus request, or use Download all ready.',parent=self)
            return
        entry=self.nexus_queue.get(int(selected[0]))
        self._start_nexus_batch([entry] if entry else [])

    def nexus_queue_download_all(self):
        self._start_nexus_batch(self.nexus_queue.ready_items())

    def _start_nexus_batch(self,entries):
        if self.nexus_running:return
        entries=[e for e in entries if e and e.status in ('Ready to review','Needs attention')]
        if not entries:
            self.nexus_queue_info.set('No requests are waiting for download.');return
        key=self.nexus_key.get().strip()
        if not key:
            self.nexus_queue_info.set('Connect Nexus account or use a private development key before downloading.')
            messagebox.showinfo('Nexus account needed','Connect your Nexus account with an approved app, or use your own key for private testing.',parent=self)
            return
        if not messagebox.askyesno('Review Nexus download batch',
                f'Download {len(entries)} Nexus file(s) to the inbox, one at a time?\n\n'
                'Nothing will be installed. Account restrictions still apply, and files with failed requests will be left for review.',parent=self):
            return
        inbox=str(Path(self.inbox_folder.get()).expanduser())
        self.nexus_running=True
        self._nexus_cancel_event=threading.Event()
        cancel_event=self._nexus_cancel_event
        self._nexus_batch_remaining=len(entries)
        for entry in entries:
            entry.status='Queued for download';entry.note='';entry.received=0;entry.total=0
        self.nexus_queue_refresh()
        # Snapshot token-bearing requests into this transient worker scope only.
        requests=[(entry,entry.game,entry.mod,entry.file,entry.nxm,entry.filename) for entry in entries]
        def worker():
            for entry,game,mod,file_id,nxm,filename in requests:
                if cancel_event.is_set():
                    self._queue_events.put(('cancelled',entry,None,None))
                    continue
                self._queue_events.put(('start',entry,None,None))
                last_update=[0.0]
                def progress(received,total):
                    now=time.monotonic()
                    if now-last_update[0]>=0.15 or (total and received>=total):
                        self._queue_events.put(('progress',entry,received,total))
                        last_update[0]=now
                try:
                    url=nexus_integr.download_link_url(game,mod,file_id,nxm)
                    mirrors=nexus_api_json(url,key)
                    if cancel_event.is_set():
                        raise nexus_integr.DownloadCancelled('Cancelled before download')
                    location=nexus_integr.select_download_url(mirrors)
                    result=nexus_integr.download_archive(location,inbox,filename,verify_archive=True,
                        progress=progress,cancel_event=cancel_event)
                    self._queue_events.put(('done',entry,result,None))
                except nexus_integr.DownloadCancelled:
                    self._queue_events.put(('cancelled',entry,None,None))
                except Exception as exc:
                    error=nexus_integr.redacted_error(exc,key,(nxm or {}).get('key'))
                    self._queue_events.put(('done',entry,None,error))
            self._queue_events.put(('finished',None,None,None))
        threading.Thread(target=worker,name='unimod-reviewed-downloads',daemon=True).start()
        self.after(90,self._poll_queue_download_events)

    def nexus_queue_done(self,entry,result,error):
        # Kept as a compatibility entry point for older GUI tests.
        self._queue_events.put(('done',entry,result,error))
        self._queue_events.put(('finished',None,None,None))
        self.after(10,self._poll_queue_download_events)

    def nexus_test_connection(self):
        if self.nexus_running:return
        key=self.nexus_key.get().strip()
        if not key:
            messagebox.showinfo('API key needed','Enter a Nexus personal API key first.',parent=self);return
        self.nexus_running=True
        self.nexus_info.set('Testing Nexus API authentication and HTTPS connectivity…')
        def worker():
            try:nexus_validate_key(key);error=None
            except Exception as exc:error=str(exc).replace(key,'[redacted]')
            self.after(0,lambda:self.nexus_connection_done(error))
        threading.Thread(target=worker,daemon=True).start()
    def nexus_connection_done(self,error):
        self.nexus_running=False
        if error:
            self.nexus_info.set('Nexus connection test failed: '+error)
            messagebox.showerror('Nexus connection test',error,parent=self)
        else:
            self.nexus_info.set('Nexus API authentication successful. You can now check versions for linked mods.')
    def nexus_check_next(self):
        game=self.current()
        if not game:messagebox.showinfo('Choose a game','Select a game first.');return
        eligible=[m for m in self.nexus_eligible() if m['path'] not in self.nexus_checked]
        if not eligible:
            messagebox.showinfo('Nexus updates','No unchecked Nexus IDs remain; assign the official page for unlinked mods.',parent=self);return
        self.nexus_start(eligible[:25])
    def nexus_check_selected(self):
        mod=self.nexus_selected_row() or self.picked();game=self.current()
        if not mod or not game:
            messagebox.showinfo('Select a mod','Select a mod in Nexus Updates first.');return
        ref=nexus_reference(game,mod)
        if ref is None or 'error' in ref:
            messagebox.showinfo('Exact Nexus page needed','Link the official Nexus mod page before checking versions.',parent=self);return
        self.nexus_start([mod])
    def nexus_start(self, mods):
        if self.nexus_running:return
        key=self.nexus_key.get().strip()
        if not key:
            messagebox.showinfo('Nexus API key needed','Enter a personal Nexus API key for read-only testing; it is not saved.');return
        game=self.current()
        root=str(Path(game['root']).resolve())
        self.nexus_running=True
        self.nexus_info.set('Checking Nexus API for exact mod IDs…')
        def worker():
            try:results=check_nexus_updates(game,mods,key);err=None
            except Exception as exc:results={};err=str(exc).replace(key,'[redacted]')
            self.after(0,lambda:self.nexus_done(root,[m['path'] for m in mods],results,err))
        threading.Thread(target=worker,daemon=True).start()
    def nexus_done(self,root,requested,results,error):
        self.nexus_running=False
        game=self.current()
        if not game or str(Path(game['root']).resolve())!=root:return
        if error:
            self.nexus_info.set('Nexus request failed: '+error)
            messagebox.showerror('Nexus request failed',error);return
        self.nexus_results.update(results)
        self.unified_nexus.update(results)
        self.unified_render()
        self.nexus_checked.update(path for path,result in results.items() if result['status']!='Check failed')
        self.nexus_refresh()
        failures=[r for r in results.values() if r['status']=='Check failed']
        if failures:
            distinct=list(dict.fromkeys(r.get('error','Request failed') for r in failures))
            self.nexus_info.set(f'{len(failures)} Nexus check(s) failed. '+ ' | '.join(distinct[:2]) +' — You can retry after correcting the issue.')
        self.update_results.update(results)
        self.fill_mods()
    def nexus_open_selected(self):
        game=self.current();mod=self.nexus_selected_row()
        if not game or not mod:return
        ref=nexus_reference(game,mod)
        if ref and ref.get('url'):webbrowser.open(ref['url'])
        else: self.nexus_assign_selected()
    def ts_load_and_compare(self):
        game=self.current()
        if not game or game.get('kind')!='bepinex':
            messagebox.showinfo('Select BepInEx game','Choose a BepInEx game first.',parent=self);return
        self.ts_compare_pending=True
        self.ts_load()

    def ts_compare_local(self):
        game=self.current()
        if not game or game.get('kind')!='bepinex':
            self.ts_local_info.set('Choose a BepInEx game for this report.');return
        if self.ts_loaded_community is None or self.ts_loaded_community != self.ts_community.get().strip().casefold():
            self.ts_local_info.set('Load the selected Thunderstore community first.');return
        try:
            self.ts_local_rows=thunderstore_installed_report(game,self.ts_results,self.ts_loaded_community)
        except (OSError,ValueError) as exc:
            self.ts_local_info.set('Cannot compare: '+str(exc));return
        self.ts_local_community=self.ts_loaded_community
        self.ts_local_game_root=str(Path(game['root']).resolve())
        self.ts_local_tree.delete(*self.ts_local_tree.get_children())
        for i,r in enumerate(self.ts_local_rows):
            self.ts_local_tree.insert('','end',iid=str(i),values=(r['package'],r['installed'],r['latest'],r['status'],
                'Yes' if r['enabled'] else 'No',r['confidence'],r['path']))
        changes=sum(r['status']=='Update available' for r in self.ts_local_rows)
        unverified=sum(r['status'] in ('Community unverified','Different community','Conflicting source ID') for r in self.ts_local_rows)
        self.ts_local_info.set(f'{len(self.ts_local_rows)} installed manifest(s) • {changes} verified update(s) • {unverified} unverified/mismatched. Read-only; disabled packages are included.')
        self.tabs.select(next(t for t in self.tabs.tabs() if self.tabs.tab(t,'text').strip()=='Thunderstore Updates'))

    def ts_open_local(self):
        selected=self.ts_local_tree.selection()
        if not selected:return
        row=self.ts_local_rows[int(selected[0])]
        if row.get('url') and row['confidence']=='Verified metadata':webbrowser.open(row['url'])
        else:messagebox.showinfo('Source not verified','This package does not have a verified official Thunderstore page for the selected community.',parent=self)

    def ts_export_local(self):
        game=self.current()
        if not game or not self.ts_local_community or self.ts_local_community != self.ts_loaded_community or self.ts_local_game_root!=str(Path(game['root']).resolve()):
            messagebox.showinfo('Compare first','Run the local Thunderstore comparison before exporting.',parent=self);return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',initialfile='unimod-thunderstore-updates.json',filetypes=[('JSON','*.json')])
        if not path:return
        try:
            payload={'version':'0.34','community':self.ts_local_community,'game':game,
                     'generated':datetime.datetime.now().isoformat(),'results':self.ts_local_rows}
            Path(path).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            self.status.set('Exported read-only Thunderstore comparison: '+path)
        except OSError as exc:messagebox.showerror('Export failed',str(exc),parent=self)

    def ts_load(self):
        community=self.ts_community.get().strip()
        if not THUNDERSTORE_COMMUNITY_RE.fullmatch(community):
            self.ts_compare_pending=False
            messagebox.showerror('Invalid community','Enter a valid Thunderstore community slug.');return
        self.ts_request_serial+=1
        request_id=self.ts_request_serial
        # Remove stale results before switching communities. Otherwise users could
        # accidentally browse/install results from a previous community.
        self.ts_results=[];self.ts_loaded_community=None;self.ts_filter()
        self.ts_local_rows=[];self.ts_local_community=None;self.ts_local_game_root=None
        self.ts_local_tree.delete(*self.ts_local_tree.get_children())
        self.ts_local_info.set('Refreshing catalogue — previous comparisons were cleared.')
        self.ts_info.set('Loading public Thunderstore catalogue…')
        def worker():
            try: result=thunderstore_catalogue(community);err=None
            except Exception as exc: result=[];err=str(exc)
            self.after(0,lambda:self.ts_loaded(result,err,community,request_id))
        threading.Thread(target=worker,daemon=True).start()
    def ts_loaded(self,result,error,community=None,request_id=None):
        if request_id is not None and request_id!=self.ts_request_serial:return
        self.ts_results=result
        self.ts_loaded_community=(community or self.ts_community.get()).strip().casefold() if not error else None
        if error:
            self.ts_info.set('Catalogue failed: '+error)
        else:
            self.ts_info.set(f'{len(result)} packages loaded. Search results locally; no mods have been changed.')
        self.ts_filter()
        if self.ts_compare_pending:
            self.ts_compare_pending=False
            if not error:self.ts_compare_local()

    def ts_filter(self):
        if not hasattr(self,'ts_tree'):return
        query=self.ts_query.get().strip().casefold()
        self.ts_filtered=[x for x in self.ts_results if query in (x['name']+' '+x['owner']+' '+x['description']).casefold()][:500]
        self.ts_tree.delete(*self.ts_tree.get_children())
        for i,package in enumerate(self.ts_filtered):
            self.ts_tree.insert('', 'end', iid=str(i),values=(package['name'],package['owner'],package['version'],package['downloads'],package['description'][:140]))
    def ts_open(self):
        selected=self.ts_tree.selection()
        if not selected:return
        index=int(selected[0])
        if index<len(self.ts_filtered):webbrowser.open(self.ts_filtered[index]['url'])
    def ts_install(self):
        selection=self.ts_tree.selection()
        if not selection:return
        package=self.ts_filtered[int(selection[0])]
        game=self.current()
        if not game or game.get('kind') not in ('smapi','bepinex'):
            messagebox.showwarning('Unsupported game','Select a SMAPI or BepInEx game. Thunderstore packages may not be compatible with every game.');return
        deps=package.get('dependencies',[])
        try: plan=dependency_plan(package,self.ts_results,[r for r in read_receipts() if r.get('game')==str(Path(game['root']).resolve())],installed_thunderstore_packages(game))
        except ValueError as exc:messagebox.showerror('Dependency conflict',str(exc));return
        missing=[x for x in plan if x['status'] not in ('tracked','installed locally')]
        dep_summary='\n'.join('  • '+x['dependency']+' — '+x['status'] for x in plan[:25])
        details=(f"Game: {game['name']}\nPackage: {package['owner']}-{package['name']}\n"
                 f"Version: {package['version']}\nDependencies ({len(deps)}): " +
                 (', '.join(deps[:15]) if deps else 'None listed') +
                 '\n\nDependency review (receipts and explicit local metadata):\n'+(dep_summary or '  No dependencies')+
                 '\n\nYou can choose automatic dependency installation in the next dialog. Existing mods are not overwritten. '
                 'Only proceed if this package is compatible with this game. Continue?')
        if missing:
            details+='\n\nWARNING: '+str(len(missing))+' dependencies are unconfirmed or unavailable. Installation may not work.'
        if not messagebox.askyesno('Review Thunderstore installation',details):return
        mode=messagebox.askyesnocancel('Install dependencies?',
            'Yes: install target and all missing dependencies as one recoverable transaction.\n'
            'No: install target only (existing behaviour).\nCancel: stop.')
        if mode is None:return
        self.ts_info.set('Downloading and installing selected package…')
        def worker():
            try:
                if mode:
                    batch=thunderstore_install_transaction(game,package,self.ts_results)
                    receipt={'package':f'{len(batch)} package(s) in one transaction','transaction':True}
                else:receipt=thunderstore_install(game,package)
                error=None
            except Exception as exc:receipt=None;error=str(exc)
            self.after(0,lambda:self.ts_install_done(receipt,error))
        threading.Thread(target=worker,daemon=True).start()
    def ts_install_done(self,receipt,error):
        if error:
            self.ts_info.set('Install failed: '+error);messagebox.showerror('Install failed',error)
        else:
            self.ts_info.set('Installed '+receipt['package']+'; managed receipt saved.')
            self.refresh();messagebox.showinfo('Installed', 'Install recorded. '+('Dependencies installed when required. ' if receipt.get('transaction') else 'Dependencies were not installed automatically. ')+'Use Undo to move managed files to recovery storage.')
    def ts_undo(self):
        game=self.current()
        if not game:return
        matches=[r for r in read_receipts() if r.get('game')==str(Path(game['root']).resolve())]
        if not matches:
            messagebox.showinfo('Nothing to undo','No tracked Thunderstore installations for this game.');return
        receipt=matches[-1]
        if not messagebox.askyesno('Recover managed install',f"Move {receipt['package']} to UniMod recovery storage? No files will be deleted."):return
        try:
            moved=undo_thunderstore_install(receipt,game)
            self.refresh();messagebox.showinfo('Moved to recovery',f'{len(moved)} item(s) moved into ~/.config/unimod/recovery/')
        except Exception as exc:messagebox.showerror('Undo failed',str(exc))
    def sort_installed_table(self,column):
        descending=(self._installed_sort[0]==column and not self._installed_sort[1])
        def sort_siblings(parent):
            children=list(self.tree.get_children(parent))
            children.sort(key=lambda rid:(self.tree.item(rid,'text') if column=='name'
                else self.tree.set(rid,column)).casefold(),reverse=descending)
            for index,rid in enumerate(children):
                self.tree.move(rid,parent,index)
                sort_siblings(rid)
        sort_siblings('')
        self._installed_sort=(column,descending)

    def describe_selected(self):
        selection=self.tree.selection() if hasattr(self,'tree') else ()
        family=getattr(self,'family_rows',{}).get(selection[0]) if selection else None
        if family:
            members=family['members']
            title=family['name']
            note=('Some components have the same SMAPI ID — review duplicates.' if family['duplicate_ids']
                  else 'Each component has a separate folder and manifest.')
            self.detail.set(f"{title}: {len(members)} installed components. {note} Expand the group and select a child for actions.")
            if hasattr(self,'detail_name'):
                self.detail_name.set(title)
                self.detail_state.set(f"{len(members)} components · visual group only")
                self.detail_version.set('Multiple components')
                self.detail_uid.set('Select a component for its ID')
                self.detail_source.set('Individual component sources')
                self.detail_path.set('Expand this group to inspect folders')
            self.update_mod_action_buttons(False)
            return
        m=self.picked()
        if not m:
            folder=self.selected_inventory_row()
            if folder and folder.get('is_folder_only'):
                self.detail.set(f"Installed folder: {folder['kind']}. Its SMAPI identity is not indexed yet: {folder['path']}. No changes will be made.")
                m=folder
            else:
                self.detail.set('Select a mod to see its installed location and source.')
        if m and not m.get('is_folder_only'):
            self.detail.set(f"{m['name']}  •  {m['version']}  •  {(assigned_source(self.current(),m) or {}).get('site') or reconcile_source(self.current(),m)['source']}  •  {m['path']}")
        if not hasattr(self,'detail_name'):return
        if not m:
            self.update_mod_action_buttons(False)
            for var,value in [(self.detail_name,'Select a mod'),(self.detail_state,'Choose an entry on the left'),
                (self.detail_version,'—'),(self.detail_uid,'—'),(self.detail_source,'—'),(self.detail_path,'—')]:var.set(value)
            return
        only=m.get('is_folder_only',False)
        match=reconcile_source(self.current(),m) if not only else {'source':'Not indexed','url':''}
        source=match.get('source','Unknown') if match.get('url') else 'No known source'
        self.detail_name.set(m.get('name','Unknown'))
        self.detail_state.set('Folder available for inspection' if only else ('● Enabled' if m['enabled'] else '○ Disabled'))
        self.detail_version.set(m.get('version','—') or '—')
        self.detail_uid.set(m.get('uid','—') or '—')
        self.detail_source.set(source)
        self.detail_path.set(m.get('path','—'))
        self.update_mod_action_buttons(not only)

    def update_mod_action_buttons(self,active):
        for button in getattr(self,'mod_action_buttons',[]):
            button.configure(state='normal' if active else 'disabled')

    def current(self):
        if self.selected is None or self.selected>=len(self.data['games']):return None
        return self.data['games'][self.selected]
    def fill_games(self):
        self.game_list.delete(0,'end')
        self.game_list.configure(height=max(2,min(5,len(self.data['games']))))
        for game in self.data['games']:self.game_list.insert('end',game['name'])
        if hasattr(self,'game_combo'):
            self.game_combo['values']=[g['name'] for g in self.data['games']]
            if self.selected is not None and self.selected<len(self.data['games']):self.game_combo.current(self.selected)
            else:self.game_combo_value.set('No games detected')
        if self.selected is not None and self.selected<len(self.data['games']):self.game_list.selection_set(self.selected);self.refresh()
    def select_game(self):
        sel=self.game_list.curselection()
        if sel:
            changed=(self.selected!=sel[0])
            self.selected=sel[0]
            if changed:self.unified_nexus={};self.unified_github={};self.unified_root=None;self.nexus_results={};self.nexus_checked=set();self.diagnostic_report=None;self.diagnostic_game_root=None;self.diag_tree.delete(*self.diag_tree.get_children())
            if changed:
                self.ts_local_rows=[];self.ts_local_game_root=None;self.ts_local_community=None
                self.ts_local_tree.delete(*self.ts_local_tree.get_children())
                self.ts_local_info.set('Selected game changed. Compare installed packages again.')
                self.inbox_results=[];self.unified_downloads=[];self.unified_download_root=None
                self.inbox_tree.delete(*self.inbox_tree.get_children())
                self.inbox_info.set('Select Scan ZIPs for this game; previous results were cleared.')
            self.refresh()
    def auto_detect(self,silent=False):
        found=detect_games();known={str(Path(g['root']).resolve()) for g in self.data['games']};added=0
        for g in found:
            if str(Path(g['root']).resolve()) not in known:self.data['games'].append(g);known.add(str(Path(g['root']).resolve()));added+=1
        cfg_save(self.data)
        if self.selected is None and self.data['games']:self.selected=0
        self.fill_games()
        if not silent:self.status.set(f'Detected {len(found)} modded installations across Steam, Heroic and Lutris; added {added} new game(s).')
    def add_game(self):
        p=filedialog.askdirectory(title='Choose game installation folder')
        if not p:return
        name=simpledialog.askstring('Game title','Game name:',initialvalue=Path(p).name,parent=self)
        if not name:return
        guess=infer_mod_layout(p,name) or ('smapi' if 'stardew' in name.lower() else 'bepinex')
        kind=simpledialog.askstring('Mod layout','Type smapi, bepinex, melonloader, or generic:',initialvalue=guess,parent=self)
        if not kind:return
        kind=kind.lower().strip()
        if kind not in ('smapi','bepinex','melonloader','generic'):messagebox.showerror('Invalid type','Choose smapi, bepinex, melonloader, or generic');return
        self.data['games'].append({'name':name,'root':p,'kind':kind});cfg_save(self.data);self.selected=len(self.data['games'])-1;self.unified_nexus={};self.unified_github={};self.nexus_results={};self.fill_games()
    def remove_game(self):
        if self.current() and messagebox.askyesno('Remove game','Remove this game from UniMod? Game files are not deleted.'):
            self.data['games'].pop(self.selected);self.selected=0 if self.data['games'] else None;self.unified_nexus={};self.unified_github={};self.nexus_results={};cfg_save(self.data);self.fill_games();self.refresh()
    def refresh(self):
        self.tree.delete(*self.tree.get_children());game=self.current()
        self.sync_unified_source_action()
        if hasattr(self,'detail_name'):self.describe_selected()
        self.rows=[]
        if not game:
            self.dep_rows=[];self.dep_game_root=None;self.filter_dependencies()
            self.source_rows=[];self.fill_source_table()
            self.update_dashboard();self.unified_render();return
        self.rows=items(game);self.update_results=dict(self.nexus_results);inventory_update(game,self.rows);self.fill_mods()
        self.show_dependencies()
        self.update_source_status();self.nexus_refresh();self.update_dashboard();self.unified_render();self.status.set(f"{game['name']}: {len(mod_packages(game,self.rows))} mod folders/packages | {len(self.rows)} indexed IDs | {len(backups_for_game(game))} backups. Scan did not modify game files.")
    def fill_mods(self):
        previous=self.tree.selection()
        previous_path=None
        if previous:
            old=getattr(self,'display_rows',[])
            if previous[0].isdigit() and int(previous[0])<len(old):
                previous_path=old[int(previous[0])].get('path')
        # Preserve collapsed families after search/filter changes.
        closed=set(getattr(self,'collapsed_families',set()))
        for rid in self.tree.get_children(''):
            if rid.startswith('family:') and not self.tree.item(rid,'open'):
                fam=getattr(self,'family_rows',{}).get(rid)
                if fam:closed.add(fam['name'].casefold())
            elif rid.startswith('family:') and self.tree.item(rid,'open'):
                fam=getattr(self,'family_rows',{}).get(rid)
                if fam:closed.discard(fam['name'].casefold())
        self.collapsed_families=closed
        self.tree.delete(*self.tree.get_children(''))
        self.family_rows={}
        game=self.current()
        extra=smapi_folder_entries(game,self.rows) if game else []
        self.display_rows=list(self.rows)+extra
        self._family_group_cache={}
        if game and game['kind']=='smapi':
            for family in mod_family_groups(self.rows):
                if family['grouped']:
                    for i in family['indices']:self._family_group_cache[i]=family['name']
        q=self.query.get().strip().casefold() if hasattr(self,'query') else ''
        mode=self.mod_visibility.get() if hasattr(self,'mod_visibility') else 'All'
        visible=[]
        for i,m in enumerate(self.display_rows):
            only=m.get('is_folder_only',False)
            match=reconcile_source(game,m) if not only else {'source':'Unknown','url':''}
            src=match['source'] if match['url'] else ('Not indexed' if only else 'Unknown')
            if mode=='Enabled' and not m['enabled']:continue
            if mode=='Disabled' and m['enabled']:continue
            if mode=='Known source' and not match['url']:continue
            if mode=='Unknown source' and match['url']:continue
            # Match family names as well as individual component metadata.
            if q and q not in ' '.join([m['name'],m.get('uid',''),src,
                         m.get('relative',m['path']),m.get('kind','')]).casefold():
                # Family-name match for components is handled below.
                if not (game and game['kind']=='smapi' and
                    q in self._family_name_for_index(i).casefold()):continue
            visible.append((i,m,src))
        def add_item(index,mod,source,parent=''):
            only=mod.get('is_folder_only',False)
            status='—' if only else ('●  On' if mod['enabled'] else '○  Off')
            update=mod['kind'] if only else self.update_results.get(mod['path'],{}).get('status','Not checked')
            self.tree.insert(parent,'end',iid=str(index),text=mod['name'],
                values=(mod['name'],status,mod['version'],source,mod.get('author','') or '—',update,mod.get('uid',''),mod['path']),
                tags=('folder_only',) if only else ())
        grouped=bool(getattr(self,'group_components',None) and self.group_components.get()
                     and game and game['kind']=='smapi')
        if grouped:
            family_index=self._family_group_cache
            buckets={};ordered=[]
            for i,m,source in visible:
                name=family_index.get(i)
                key=name.casefold() if name else f'__solo:{i}'
                if key not in buckets:buckets[key]=[];ordered.append(key)
                buckets[key].append((i,m,source))
            for key in ordered:
                entries=buckets[key]
                fam_name=family_index.get(entries[0][0])
                if fam_name and all(not m.get('is_folder_only') for _,m,_ in entries):
                    iid=f'family:{entries[0][0]}'
                    component_ids=[x[1].get('uid','').casefold() for x in entries if x[1].get('uid')]
                    duplicate=len(component_ids)!=len(set(component_ids))
                    fam={'name':fam_name,'members':[x[1] for x in entries],
                         'indices':[x[0] for x in entries],'duplicate_ids':duplicate}
                    self.family_rows[iid]=fam
                    status='Review' if duplicate else '—'
                    self.tree.insert('','end',iid=iid,text=f'{fam_name}  ({len(entries)} components)',
                        values=(fam_name,status,'—','Multiple','—','Not checked','',''),
                        tags=('family_group',),open=bool(q) or fam_name.casefold() not in closed)
                    for i,m,source in entries:add_item(i,m,source,iid)
                else:
                    for i,m,source in entries:add_item(i,m,source)
        else:
            for i,m,source in visible:add_item(i,m,source)
        self.tree.tag_configure('folder_only',foreground='#a6b9d7')
        self.tree.tag_configure('family_group',foreground='#8cbcff')
        self.tree.tag_configure('odd',background='#1d2b40')
        for n,rid in enumerate(self.tree.get_children('')):
            if n%2:self.tree.item(rid,tags=tuple(self.tree.item(rid,'tags'))+('odd',))
        if hasattr(self,'count_label'):
            family_count=len(self.family_rows)
            self.count_label.configure(text=f'{len(visible)} components · {len(self.tree.get_children())} rows'
                + (f' · {family_count} groups' if family_count else ''))
        selected=None
        if previous_path:
            for i,m,_ in visible:
                if m.get('path')==previous_path and self.tree.exists(str(i)):
                    selected=str(i);break
        if selected is None:
            selected=next((p for p in previous if self.tree.exists(p)),None)
        if selected is None:
            children=self.tree.get_children('')
            selected=children[0] if children else None
        if selected is not None:self.tree.selection_set(selected)
        self.describe_selected()

    def _family_name_for_index(self,index):
        return self._family_group_cache.get(index,'')

    def show_dependencies(self):
        game=self.current()
        if not game or game['kind']!='smapi':
            self.dep_rows=[];self.dep_game_root=None
            self.dep_info.set('Dependency inspection requires an SMAPI game. Select a supported game first.')
            self.filter_dependencies()
            return
        self.dep_rows=smapi_dependency_report(self.rows)
        self.dep_game_root=str(Path(game['root']).resolve())
        self.filter_dependencies()

    def filter_dependencies(self):
        if not hasattr(self,'dep_tree'):return
        self.dep_tree.delete(*self.dep_tree.get_children())
        query=self.dep_query.get().strip().casefold()
        visible=[entry for entry in self.dep_rows if not query or query in ' '.join(
            str(entry.get(k,'')) for k in ('mod','mod_id','dependency','type','status')).casefold()]
        for entry in visible:
            self.dep_tree.insert('','end',values=(entry['mod'],entry['dependency'],entry['type'],
                'Yes' if entry['required'] else 'No',entry['minimum_version'] or '—',
                entry['installed_versions'] or '—',entry['status']))
        warnings=sum(x['required'] and x['mod_enabled'] and x['status'] in
                     ('Missing','Disabled provider','Below minimum','Ambiguous providers','Version unverified')
                     for x in self.dep_rows)
        self.dep_info.set(f'{len(visible)} / {len(self.dep_rows)} dependency links · {warnings} potentially unresolved required links. Some IDs are provided by the game or SMAPI.')

    def export_dependencies(self):
        game=self.current()
        if not game or game['kind']!='smapi':return
        if self.dep_game_root!=str(Path(game['root']).resolve()):self.show_dependencies()
        target=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='unimod-smapi-dependencies.csv',filetypes=[('CSV','*.csv')])
        if not target:return
        try:
            export_smapi_dependencies(target,self.dep_rows)
            self.status.set(f'Exported {len(self.dep_rows)} SMAPI dependency links (contains installed mod paths): {target}')
        except OSError as exc:messagebox.showerror('Export failed',str(exc))

    def save_baseline(self):
        game=self.current()
        if not game:return
        if not messagebox.askyesno('Save baseline','Save current mod state as the new comparison baseline? An older baseline will be replaced.'):
            return
        try:
            path=save_snapshot(game,items(game));self.show_changes()
            self.status.set(f'Saved baseline: {path}. No game files changed.')
        except Exception as exc:messagebox.showerror('Snapshot failed',str(exc))
    def show_changes(self):
        game=self.current()
        if not game:return
        saved=load_snapshot(game)
        self.change_tree.delete(*self.change_tree.get_children())
        changes=compare_snapshot(saved,items(game))
        for entry in changes:
            self.change_tree.insert('','end',values=tuple(entry[k] for k in ('change','mod','before','after','relative')))
        self.change_info.set(('No baseline saved yet.' if saved is None else
            f'{len(changes)} change(s) since {saved["created"]}. Missing means absent from this scan, not necessarily deleted.'))
        self.tabs.select(next(i for i in self.tabs.tabs() if self.tabs.tab(i,'text').strip()=='Scan Changes'))
    def export_changes(self):
        game=self.current()
        if not game:return
        saved=load_snapshot(game)
        if saved is None:
            messagebox.showinfo('No baseline','Save a baseline before exporting comparisons.');return
        filename=filedialog.asksaveasfilename(defaultextension='.json',initialfile='unimod-changes.json',filetypes=[('JSON','*.json')])
        if not filename:return
        changes=compare_snapshot(saved,items(game))
        Path(filename).write_text(json.dumps({'game':game,'baseline':saved['created'],'changes':changes},indent=2),encoding='utf-8')
        self.status.set(f'Exported {len(changes)} changes to {filename}')
    def run_audit(self):
        game=self.current()
        if not game:return
        self.audit_results=audit_mods(items(game),game['kind'])
        self.audit_tree.delete(*self.audit_tree.get_children())
        for issue in self.audit_results:
            self.audit_tree.insert('','end',values=tuple(issue[k] for k in ('severity','type','mod','detail')))
        self.audit_info.set(f'{len(self.audit_results)} potential issue(s). No mod files changed.')
        self.tabs.select(next(i for i in self.tabs.tabs() if self.tabs.tab(i,'text').strip()=='Installation Audit'))
    def export_audit(self):
        game=self.current()
        if not game:return
        self.run_audit()
        output=filedialog.asksaveasfilename(defaultextension='.json',initialfile='unimod-audit.json',filetypes=[('JSON','*.json')])
        if output:
            payload={'version':'0.34','game':game,'audited_at':datetime.datetime.now().isoformat(),'issues':self.audit_results}
            Path(output).write_text(json.dumps(payload,indent=2),encoding='utf-8')
            self.status.set(f'Exported audit to {output}')
    def export_report(self):
        game=self.current()
        if not game:return
        output=filedialog.asksaveasfilename(defaultextension='.json',initialfile='unimod-scan.json',filetypes=[('JSON','*.json')])
        if not output:return
        report={'version':'0.34','game':game,'scanned_at':datetime.datetime.now().isoformat(),
                'mods':[{**m,'source':source_of(m)} for m in items(game)]}
        Path(output).write_text(json.dumps(report,indent=2));self.status.set(f'Exported {len(report["mods"])} entries: {output}')
    def check_updates(self):
        game=self.current()
        if not game:return
        mods=list(self.rows)
        repos={github_repo(m) for m in mods if github_repo(m)}
        if not repos:
            messagebox.showinfo('GitHub updates','No installed SMAPI mods have GitHub:owner/repository UpdateKeys. Check Nexus Updates or Source Matching for other sites.');return
        self.status.set(f'Checking {len(repos)} GitHub repositories (read-only)…')
        def worker():
            result=check_github_updates(mods)
            self.after(0,lambda:self.updates_done(result))
        threading.Thread(target=worker,daemon=True).start()
    def updates_done(self,result):
        self.update_results=result;self.fill_mods()
        available=sum(v['status']=='Update available' for v in result.values())
        failed=sum(v['status']=='Check failed' for v in result.values())
        self.status.set(f'GitHub check complete: {available} potential updates, {failed} failed checks, {len(result)} mods checked. No files changed.')
    def fill_source_table(self):
        if not hasattr(self,'source_tree'):return
        self.source_tree.delete(*self.source_tree.get_children())
        query=self.source_search.get().casefold().strip()
        mode=self.source_filter.get()
        order,reverse=self.source_order
        records=[]
        for i,row in enumerate(self.source_rows):
            linked=bool(row['url'])
            if mode=='Needs matching' and linked:continue
            if mode=='Linked' and not linked:continue
            if mode=='Assigned by user' and row['status']!='Assigned by user':continue
            if mode=='Update keys only' and row['status']!='Key only — review needed':continue
            searchable=' '.join(str(row.get(k,'')) for k in ('name','uid','version','source','status','url','path'))
            if query and query not in searchable.casefold():continue
            records.append((i,row))
        sortkeys={'mod':'name','status':'status','source':'source','version':'version',
                  'enabled':'enabled','url':'url'}
        field=sortkeys.get(order,'name')
        records.sort(key=lambda entry:(str(entry[1][field]).casefold(),entry[0]),reverse=reverse)
        for index,row in records:
            self.source_tree.insert('','end',iid=str(index),
                values=(row['name'],row['status'],row['source'],row['version'],
                        'Yes' if row['enabled'] else 'No',row['url']))

    def sort_source_table(self,field):
        previous,descending=self.source_order
        self.source_order=(field,not descending if previous==field else False)
        self.fill_source_table()

    def source_table_mod(self):
        choice=self.source_tree.selection()
        if not choice:return None
        index=int(choice[0])
        return self.rows[index] if 0<=index<len(self.rows) else None

    def source_table_record(self):
        choice=self.source_tree.selection()
        if not choice:return None
        index=int(choice[0])
        return self.source_rows[index] if 0<=index<len(self.source_rows) else None

    def assign_source_from_table(self):
        game=self.current();mod=self.source_table_mod()
        if not game or not mod:
            messagebox.showinfo('Choose a mod','Select a mod in the Source Matching table.');return
        current=(assigned_source(game,mod) or {}).get('url')
        if not current:
            current=(self.source_table_record() or {}).get('url','')
        url=simpledialog.askstring('Assign source',f'Official mod page for {mod["name"]}:',
                                   initialvalue=current,parent=self)
        if url is None:return
        try:
            save_source_assignment(game,mod,url)
            self.fill_mods();self.update_source_status();self.update_dashboard()
        except ValueError as exc:messagebox.showerror('Invalid source',str(exc))

    def clear_source_from_table(self):
        game=self.current();mod=self.source_table_mod()
        if not game or not mod:return
        clear_source_assignment(game,mod)
        self.fill_mods();self.update_source_status();self.update_dashboard()

    def open_source_table_link(self):
        record=self.source_table_record()
        if record and validate_source_link(record['url']):webbrowser.open(record['url'])

    def copy_source_table_link(self):
        record=self.source_table_record()
        if record and validate_source_link(record['url']):
            self.clipboard_clear();self.clipboard_append(record['url'])
            self.status.set('Source link copied to clipboard; review before downloading anything.')

    def export_source_reconciliation_ui(self):
        game=self.current()
        if not game:return
        path=filedialog.asksaveasfilename(title='Export source matches',defaultextension='.csv',
            initialfile='unimod-source-matching.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            total=export_source_reconciliation(path,game,self.rows)
            self.status.set(f'Exported {total} source records to {path}')
        except OSError as exc:messagebox.showerror('Export failed',str(exc))

    def assign_source(self):
        game=self.current();mod=self.picked()
        if not game or not mod:
            messagebox.showinfo('Select a mod','Select a mod in Installed Mods first.');return
        old=assigned_source(game,mod)
        suggested=reconcile_source(game,mod)['url']
        url=simpledialog.askstring('Assign mod source',f"Official website page for {mod['name']}:",initialvalue=old['url'] if old else suggested,parent=self)
        if url is None:return
        try:
            save_source_assignment(game,mod,url)
            self.fill_mods();self.describe_selected();self.update_source_status()
        except ValueError as exc:messagebox.showerror('Invalid source',str(exc))
    def clear_source(self):
        game=self.current();mod=self.picked()
        if not game or not mod:return
        clear_source_assignment(game,mod)
        self.fill_mods();self.describe_selected();self.update_source_status()
    def preview_auto_sources(self):
        game=self.current()
        if not game:return
        matches=auto_source_matches(game,items(game))
        popup=tk.Toplevel(self)
        popup.title('Metadata source matches — preview')
        popup.geometry('780x420')
        ttk.Label(popup,text=f'{len(matches)} recognised source links from installed mod metadata. Read-only preview.',padding=10).pack(anchor='w')
        view=ttk.Treeview(popup,columns=('mod','site','url'),show='headings')
        for col,width in [('mod',200),('site',110),('url',440)]:
            view.heading(col,text=col.capitalize());view.column(col,width=width)
        view.pack(fill='both',expand=True,padx=10,pady=5)
        for match in matches:view.insert('', 'end',values=(match['name'],match['site'],match['url']))
        ttk.Button(popup,text='Close',command=popup.destroy).pack(pady=8)
    def export_sources(self):
        game=self.current()
        if not game:return
        path=filedialog.asksaveasfilename(title='Export source matches',defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile='unimod-sources.csv')
        if not path:return
        try:
            count=export_source_csv(path,game,items(game))
            self.status.set(f'Exported {count} mod source records to {path}')
        except OSError as exc:messagebox.showerror('Export failed',str(exc))
    def update_source_status(self):
        game=self.current()
        if not game:return
        self.source_rows=source_reconciliation(game,self.rows)
        linked=sum(bool(row['url']) for row in self.source_rows)
        assigned=sum(row['status']=='Assigned by user' for row in self.source_rows)
        uncertain=sum(row['status'] in ('Conflicting Nexus keys','Key only — review needed') for row in self.source_rows)
        self.source_info.set(f'{len(self.source_rows)} installed entries · {linked} have identifiable links ({assigned} assigned) · {uncertain} need review · {len(self.source_rows)-linked} without direct source links. Local matching only; no name guessing or downloads.')
        self.fill_source_table()
    def open_release(self):
        mod=self.picked()
        if not mod:return
        match=reconcile_source(self.current(),mod)
        if match['url'] and validate_source_link(match['url']):
            webbrowser.open(match['url']);return
        result=self.update_results.get(mod['path'],{})
        if result.get('url') and validate_source_link(result['url']):
            webbrowser.open(result['url']);return
        messagebox.showinfo('Source needs review',
                            'No exact source link is available. Open Source Matching to assign an official mod page.')
    def replace_selected(self):
        game=self.current();mod=self.picked()
        if not game or not mod:return
        if game['kind'] not in ('smapi','bepinex'):
            messagebox.showinfo('Not supported','Safe ZIP replacement requires SMAPI or BepInEx.');return
        archive=filedialog.askopenfilename(title='Choose updated mod ZIP',filetypes=[('ZIP archives','*.zip')])
        if not archive:return
        if not messagebox.askyesno('Confirm replacement',
                f'Replace {mod["name"]} with the matching mod from this ZIP?\nA recovery backup will be kept under ~/.config/unimod/backups/'):
            return
        try:
            if game['kind']=='smapi':
                backup=replace_smapi_zip(game,mod,archive)
            else:
                inspected=match_downloaded_bepinex_archive(game,archive)
                if inspected['status'] not in ('Ready to update','Review version') or not Path(mod['path']).resolve().is_relative_to(Path(inspected['target_path']).resolve()):
                    raise ValueError('This ZIP does not match the selected BepInEx package. Use Update Inbox for details.')
                backup=apply_downloaded_bepinex_update(game,inspected)
            self.refresh();messagebox.showinfo('Updated',f'Updated mod. Backup: {backup}')
        except Exception as e:messagebox.showerror('Update refused / failed',str(e))

    def restore_from_backup(self):
        game=self.current()
        if not game:return
        entries=backups_for_game(game)
        if not entries:
            messagebox.showinfo('Backups','No recorded mod backups found for this game.');return
        window=tk.Toplevel(self);window.title('Restore mod backup');window.geometry('780x360');window.transient(self)
        ttk.Label(window,text='Select a backup to restore. The current mod will be retained separately.',wraplength=740).pack(padx=15,pady=12)
        lb=tk.Listbox(window,exportselection=False);lb.pack(fill='both',expand=True,padx=15)
        for e in entries:lb.insert('end',f"{e['saved_at']}   {e['mod_uid']}   {Path(e['original_path']).name}")
        def do_restore():
            selection=lb.curselection()
            if not selection:return
            entry=entries[selection[0]]
            if not messagebox.askyesno('Confirm restoration',f"Restore {entry['mod_uid']} from backup?\nThe current folder will be preserved. Close the game first.",parent=window):return
            try:
                old=restore_backup(game,entry);window.destroy();self.refresh()
                messagebox.showinfo('Restored',f"Restored. Previous copy: {old or 'none'}")
            except Exception as exc:messagebox.showerror('Restore failed',str(exc),parent=window)
        ttk.Button(window,text='Restore selected backup',command=do_restore).pack(pady=12)

    def selected_inventory_row(self):
        chosen=self.tree.selection()
        if not chosen:return None
        try:i=int(chosen[0])
        except (ValueError,TypeError):return None # group header is presentation-only
        rows=getattr(self,'display_rows',self.rows)
        return rows[i] if 0 <= i < len(rows) else None
    def picked(self):
        row=self.selected_inventory_row()
        return row if row is not None and not row.get('is_folder_only') else None
    def toggle(self):
        game=self.current();m=self.picked()
        if not game or not m:return
        src=top_level_mod_path(game,m)
        group=[x for x in self.rows if top_level_mod_path(game,x)==src]
        if len(group)>1 and not messagebox.askyesno('Grouped mods',f'This folder contains {len(group)} detected mods. Enable/disable the entire folder?'):return
        try:
            # A grouped toggle uses the same preflight and rollback path as profiles.
            document=profile_document(game)
            document['mods']={src.name:not m['enabled']}
            plan=plan_profile_switch(game,document)
            apply_profile_plan(plan)
            self.refresh()
        except Exception as e:messagebox.showerror('Move failed',str(e))
    def open_dir(self):
        if self.current():mod_root(self.current()).mkdir(parents=True,exist_ok=True);subprocess.Popen(['xdg-open',str(mod_root(self.current()))])
    def open_selected(self):
        selected=self.tree.selection()
        if selected and selected[0] in getattr(self,'family_rows',{}):
            iid=selected[0];self.tree.item(iid,open=not self.tree.item(iid,'open'))
            return
        m=self.selected_inventory_row()
        if m:
            target=Path(m['path']) if m.get('is_folder_only') else Path(m['path']).parent
            subprocess.Popen(['xdg-open',str(target)])
    def install_archive(self):
        game=self.current()
        if not game:messagebox.showinfo('Choose a game','Select a game first');return
        p=filedialog.askopenfilename(filetypes=[('ZIP archives','*.zip')]);
        if not p:return
        try:
            result=install_zip(game,p);self.refresh();messagebox.showinfo('Installed','Installed: '+', '.join(result))
        except Exception as e:messagebox.showerror('Install failed',str(e))
    def install_url(self):
        game=self.current()
        if not game:messagebox.showinfo('Choose a game','Select a game first');return
        url=simpledialog.askstring('Direct download URL','Paste an HTTPS URL for a ZIP file (not a Nexus / web page URL):',parent=self)
        if not url:return
        self.status.set('Downloading mod archive…');self.update_idletasks()
        def worker():
            try:
                with tempfile.TemporaryDirectory() as td:
                    f=Path(td)/'mod.zip';download(url,f);result=install_zip(game,f)
                self.after(0,lambda:self.download_done('Installed: '+', '.join(result),None))
            except Exception as e:self.after(0,lambda msg=str(e):self.download_done(None,msg))
        threading.Thread(target=worker,daemon=True).start()
    def download_done(self,success,error):
        self.refresh()
        if error:messagebox.showerror('Download / install failed',error)
        else:messagebox.showinfo('Completed',success)
    def profile_dir(self):
        p=APP/'profiles';p.mkdir(exist_ok=True);return p
    def save_profile(self):
        game=self.current()
        if not game:return
        name=simpledialog.askstring('Save profile','Profile name:',parent=self)
        if not name:return
        filename=re.sub(r'[^a-zA-Z0-9_.-]','_',name).strip('. ')
        if not filename:messagebox.showerror('Invalid profile','Enter a usable profile name.');return
        try:
            document=profile_document(game)
            location=self.profile_dir()/(filename+'.json')
            tmp=location.with_suffix('.tmp')
            tmp.write_text(json.dumps(document,indent=2))
            tmp.replace(location)
            self.status.set(f'Saved profile {location.name} ({len(document["mods"])} grouped payloads)')
        except Exception as e:messagebox.showerror('Cannot save profile',str(e))

    def load_profile(self):
        game=self.current()
        if not game:return
        f=filedialog.askopenfilename(initialdir=self.profile_dir(),filetypes=[('JSON profiles','*.json')])
        if not f:return
        try:
            document=json.loads(Path(f).read_text())
            plan=plan_profile_switch(game,document)
        except Exception as e:
            messagebox.showerror('Cannot preview profile',str(e));return
        self.profile_preview_window(game,document,plan,Path(f).name)

    def profile_preview_window(self,game,document,plan,filename):
        """Show all grouped moves and unresolved entries before any files are changed."""
        window=tk.Toplevel(self);window.title('Profile preview — '+filename)
        window.geometry('790x480');window.minsize(610,340)
        window.transient(self)
        holder=ttk.Frame(window,padding=16);holder.pack(fill='both',expand=True)
        ttk.Label(holder,text='Preview profile switch',style='Section.TLabel').pack(anchor='w')
        ttk.Label(holder,text=f'{len(plan["changes"])} folder/file moves · {plan["unchanged"]} unchanged · '
                  f'{len(plan["missing"])} missing · {len(plan["unmanaged"])} not in profile',
                  wraplength=740).pack(anchor='w',pady=(6,10))
        view=ttk.Frame(holder);view.pack(fill='both',expand=True)
        table=ttk.Treeview(view,columns=('payload','action','contained'),show='headings')
        for column,label,width in (('payload','Payload',300),('action','Action',220),('contained','Detected mods',120)):
            table.heading(column,text=label);table.column(column,width=width,stretch=True)
        scrollbar=ttk.Scrollbar(view,orient='vertical',command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        table.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        for operation in plan['changes']:
            table.insert('','end',values=(operation['name'],
                          'Enable' if operation['to_enabled'] else 'Disable',operation['mod_count']))
        if plan['missing']:
            ttk.Label(holder,text='Missing (will not be installed): '+', '.join(plan['missing'][:20])+
                      (' …' if len(plan['missing'])>20 else ''),wraplength=730).pack(anchor='w',pady=(10,2))
        ttk.Label(holder,text='Close the game before applying. All targets are checked again immediately before moving. '
                  'If a move fails, completed moves are rolled back where possible.',wraplength=730).pack(anchor='w',pady=9)
        buttons=ttk.Frame(holder);buttons.pack(anchor='e',fill='x')
        ttk.Button(buttons,text='Cancel',command=window.destroy).pack(side='right',padx=(8,0))
        def apply_preview():
            try:
                fresh=plan_profile_switch(game,document)
                def signature(p):
                    return [(x['name'],str(x['source']),str(x['destination'])) for x in p['changes']]
                if signature(fresh)!=signature(plan):
                    raise ValueError('Mods changed since the preview. Open the profile again to review the changes.')
                count=apply_profile_plan(fresh)
                window.destroy();self.refresh()
                messagebox.showinfo('Profile applied',f'Moved {count} grouped mod payload(s). '
                       f'{len(fresh["missing"])} missing profile entries were left untouched.')
            except Exception as exc:messagebox.showerror('Profile switch stopped',str(exc),parent=window)
        ttk.Button(buttons,text='Apply reviewed changes',command=apply_preview,
                   state='normal' if plan['changes'] else 'disabled',style='Accent.TButton').pack(side='right')

if __name__=='__main__':
    if '--register-nxm' in sys.argv:
        executable=os.environ.get('APPIMAGE')
        if not executable:
            raise SystemExit('Run --register-nxm from the UniMod AppImage, not the source launcher')
        print('NXM browser handler installed: '+str(nxm_handler.install(executable)))
    elif '--smoke-test' in sys.argv:
        app=App();app.update();app.destroy()
        print('UNIMOD_GUI_SMOKE_OK')
    elif '--modio-self-test' in sys.argv:
        from modio_selftest import run as run_modio_selftest
        run_modio_selftest()
        print('UNIMOD_MODIO_SELFTEST_OK (offline, temporary files only)')
    elif '--nexus-readiness' in sys.argv:
        r=provider_catalogues.readiness(nexus_integr.registered_app_slug())
        try:
            nexus_oauth.OAuthConfig.from_environment()
            r['oauth_pkce']={'framework':'implemented', 'registered_configuration':'present',
                             'live_integration':'pending Nexus approval and endpoint confirmation'}
        except (RuntimeError,ValueError):
            r['oauth_pkce']={'framework':'implemented', 'registered_configuration':'not supplied',
                             'live_integration':'pending Nexus approval and endpoint confirmation'}
        print(json.dumps(r,indent=2))
    elif '--steam-libraries' in sys.argv:
        print(json.dumps(steam_library_inventory(),indent=2))
    elif '--launcher-games' in sys.argv:
        print(json.dumps(launcher_game_inventory(),indent=2))
    elif '--version' in sys.argv:
        print('UniMod 0.55 test12')
    else:
        incoming = None
        if '--nxm' in sys.argv:
            if len(sys.argv)!=3 or sys.argv[1]!='--nxm':
                raise SystemExit('Usage: unimod.py --nxm <official-nxm-link>')
            try: nexus_integr.parse_nxm_link(sys.argv[2])
            except ValueError: raise SystemExit('Invalid or expired Nexus manager link') from None
            incoming=sys.argv[2]
        bridge=instance_bridge.SingleInstance()
        if bridge.acquire():
            try:
                bridge.start()
                App(incoming_nxm=incoming,bridge=bridge).mainloop()
            finally:
                bridge.close()
        elif not instance_bridge.send_to_running(bridge.folder,incoming):
            raise SystemExit('UniMod is already starting; please retry the link in a moment.')
