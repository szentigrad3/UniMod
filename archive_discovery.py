"""Bounded, read-only discovery of existing ZIP downloads.

Only specifically named download locations are scanned. Never walk the game
installation or an arbitrary home directory automatically. Archive bytes are
not opened here; the existing guarded SMAPI manifest reader validates them.
"""
from pathlib import Path
import os
import json

MAX_VISITED_DIRS = 500
MAX_ARCHIVES = 180
MAX_DEPTH = 3
MAX_FILE_SIZE = 512 * 1024 * 1024
MAX_EXTRA_LOCATIONS = 10
MAX_CONFIG_BYTES = 32768


def known_manager_download_roots(home=None):
    """Conservative known Vortex download paths, not a filesystem search.

    Vortex may use other/custom folders; those can be added once in settings.
    Paths from other Windows users are never enumerated.
    """
    home = Path(home).expanduser() if home is not None else Path.home()
    return [home / '.config' / 'Vortex' / 'downloads',
            home / '.config' / 'vortex' / 'downloads',
            home / '.local' / 'share' / 'vortex' / 'downloads',
            home / 'Vortex' / 'downloads',
            home / '.wine' / 'drive_c' / 'users' / home.name / 'AppData' / 'Roaming' / 'Vortex' / 'downloads',
            home / '.wine' / 'drive_c' / 'users' / home.name / 'AppData' / 'Local' / 'Vortex' / 'downloads']


def _locations_config(app_dir=None, home=None):
    base = Path(app_dir).expanduser() if app_dir is not None else (
        Path(home).expanduser() if home is not None else Path.home()) / '.config' / 'unimod'
    return base / 'download-locations.json'


def load_extra_download_roots(app_dir=None, home=None):
    """Read explicitly approved search roots, never following config symlinks."""
    config = _locations_config(app_dir, home)
    try:
        if config.is_symlink() or not config.is_file() or config.stat().st_size > MAX_CONFIG_BYTES:
            return []
        data = json.loads(config.read_text(encoding='utf-8'))
        roots = data.get('roots') if isinstance(data,dict) and data.get('schema') == 1 else None
        if not isinstance(roots,list) or len(roots) > MAX_EXTRA_LOCATIONS:
            return []
        paths = []
        for entry in roots:
            if not isinstance(entry,str) or len(entry)>4096 or '\x00' in entry:
                return []
            p=Path(entry)
            if not p.is_absolute() or p.is_symlink():
                return []
            if str(p) not in {str(q) for q in paths}: paths.append(p)
        return paths
    except (OSError, UnicodeError, ValueError):
        return []


def save_extra_download_roots(roots, app_dir=None, home=None):
    """Explicit user opt-in. Atomically write a small owner-private settings file."""
    if len(roots)>MAX_EXTRA_LOCATIONS:
        raise ValueError('Too many extra download folders')
    paths=[]
    for path in roots:
        p=Path(path).expanduser()
        if not p.is_absolute() or p.is_symlink() or not p.is_dir():
            raise ValueError('Folder must exist and cannot be a symlink')
        if len(str(p))>4096 or '\x00' in str(p):
            raise ValueError('Invalid folder name')
        if str(p) not in {str(q) for q in paths}:paths.append(p)
    config=_locations_config(app_dir,home)
    if config.is_symlink():raise ValueError('Unsafe configuration symlink')
    config.parent.mkdir(parents=True,exist_ok=True)
    tmp=config.with_name(config.name+'.tmp')
    if tmp.is_symlink():raise ValueError('Unsafe temporary configuration symlink')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump({'schema':1,'roots':[str(x) for x in paths]},f,indent=2)
            f.write('\n')
        os.replace(tmp,config)
    finally:
        if tmp.exists():tmp.unlink()
    return paths


def common_download_roots(home=None, app_dir=None):
    home = Path(home).expanduser() if home is not None else Path.home()
    app_dir = Path(app_dir).expanduser() if app_dir is not None else home / '.config' / 'unimod'
    return ([home / 'Downloads', home / 'downloads', home / 'Download',
            app_dir / 'downloads', app_dir / 'download-inbox'] +
            known_manager_download_roots(home) + load_extra_download_roots(app_dir,home))


def find_archives(primary=None, *, include_common=False, home=None,
                  app_dir=None, max_archives=MAX_ARCHIVES, max_depth=MAX_DEPTH,
                  max_dirs=MAX_VISITED_DIRS):
    """Return unique newest ZIPs, with strict total scan bounds.

    No symlink directory traversal. Does not recurse outside explicit roots.
    A single skipped/unreadable archive does not interrupt the scan.
    """
    if not (1 <= max_archives <= MAX_ARCHIVES and 0 <= max_depth <= MAX_DEPTH
            and 1 <= max_dirs <= MAX_VISITED_DIRS):
        raise ValueError('Invalid discovery limits')
    roots = []
    if primary is not None and str(primary).strip():
        roots.append(Path(primary).expanduser())
    if include_common:
        roots.extend(common_download_roots(home, app_dir))
    found = {}
    seen_dirs = set()
    visited = 0
    for root in roots:
        try:
            if root.is_symlink() or not root.is_dir():
                continue
        except OSError:
            continue
        queue = [(root, 0)]
        while queue and visited < max_dirs:
            directory, depth = queue.pop(0)
            try:
                if directory.is_symlink():
                    continue
                # Resolve for de-duplication only; explicit directory walk never follows symlinks.
                ident = (directory.stat().st_dev, directory.stat().st_ino)
                if ident in seen_dirs:
                    continue
                seen_dirs.add(ident)
                visited += 1
                with os.scandir(directory) as entries:
                    children = sorted(entries, key=lambda ent: ent.name.casefold())
                for child in children:
                    try:
                        if child.is_symlink():
                            continue
                        if child.is_dir(follow_symlinks=False):
                            if depth < max_depth and not child.name.startswith('.'):
                                queue.append((Path(child.path), depth + 1))
                            continue
                        if child.name.lower().endswith('.zip') and child.is_file(follow_symlinks=False):
                            st = child.stat(follow_symlinks=False)
                            if 0 < st.st_size <= MAX_FILE_SIZE:
                                file_ident = (st.st_dev, st.st_ino)
                                old = found.get(file_ident)
                                if old is None or st.st_mtime > old[0]:
                                    found[file_ident] = (st.st_mtime, Path(child.path))
                    except (OSError, ValueError):
                        continue
            except (OSError, ValueError):
                continue
    return [path for _, path in sorted(found.values(), key=lambda x: (-x[0], str(x[1])))[:max_archives]]
