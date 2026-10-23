"""Read-only managed mod.io release checks scoped to locally verified installs.

A retained UniMod installation receipt and unchanged manifest provide reviewable
local evidence, NOT automatic authority to replace files. No network requests,
credentials, URLs, or file writes occur in this module.
"""
import hashlib
import re
from pathlib import Path

_ID = re.compile(r'[1-9][0-9]{0,11}\Z')
_PACKAGE = re.compile(r'mod\.io:([1-9][0-9]{0,11})/([1-9][0-9]{0,11})\Z')
_MAX_MANIFEST = 1024 * 1024


def _manifest_fingerprint(game, path):
    """Return bounded, non-symlink manifest evidence for a game-owned mod folder."""
    if not isinstance(game, dict) or game.get('kind') not in ('smapi', 'bepinex'):
        return None
    try:
        root = (Path(game['root']).resolve(strict=True) / 'Mods') if game['kind'] == 'smapi' else (Path(game['root']).resolve(strict=True) / 'BepInEx' / 'plugins')
        root = root.resolve(strict=True)
        folder = Path(path)
        # Never follow symbolic package folders or the manifest itself.
        if folder.is_symlink() or not folder.is_dir() or not folder.resolve(strict=True).is_relative_to(root):
            return None
        if folder.resolve(strict=True) == root:
            return None
        manifest = folder / 'manifest.json'
        if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > _MAX_MANIFEST:
            return None
        body = manifest.read_bytes()
        if len(body) > _MAX_MANIFEST:
            return None
        return hashlib.sha256(body).hexdigest()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return None


def provenance(game, paths, receipt):
    """Create exact game/file-ID evidence after an approved successful install."""
    if not isinstance(receipt, dict) or receipt.get('provider') != 'mod.io':
        return {}
    identity = str(receipt.get('identity') or '')
    if not _PACKAGE.fullmatch('mod.io:' + identity):
        return {}
    fid = str(receipt.get('version_id') or '')
    if not _ID.fullmatch(fid) or not isinstance(paths, list) or not 1 <= len(paths) <= 24:
        return {}
    evidence = []
    for path in paths:
        digest = _manifest_fingerprint(game, path)
        if digest is None:
            return {}
        evidence.append({'path': str(Path(path).resolve()), 'manifest_sha256': digest})
    if len(set(x['path'] for x in evidence)) != len(evidence):
        return {}
    return {'version_id': fid, 'modio_evidence': evidence}


def managed_installs(game, receipts, *, game_id):
    """Find unmodified UniMod-managed installs, ignoring stale/ambiguous records."""
    gid = str(game_id)
    if not _ID.fullmatch(gid) or not isinstance(receipts, list) or not isinstance(game, dict):
        return []
    try:
        game_root = str(Path(game['root']).resolve(strict=True))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return []
    latest = {}
    # Most recent retained receipt for one exact mod identity takes precedence.
    for row in receipts[-1000:]:
        if not isinstance(row, dict) or row.get('game') != game_root:
            continue
        name = row.get('package')
        matched = _PACKAGE.fullmatch(name) if isinstance(name, str) else None
        if not matched or matched.group(1) != gid:
            continue
        latest[name] = row
    result = []
    for name, row in latest.items():
        fid = row.get('version_id')
        evidence = row.get('modio_evidence')
        if not isinstance(fid, str) or not _ID.fullmatch(fid) or not isinstance(evidence, list) or not 1 <= len(evidence) <= 24:
            continue
        if any(not isinstance(x, dict) or not isinstance(x.get('path'), str)
               or not 1 <= len(x['path']) <= 4096 for x in evidence):
            continue
        if row.get('paths') != [x['path'] for x in evidence]:
            continue
        if len({x['path'] for x in evidence}) != len(evidence):
            continue
        if any(not isinstance(x, dict) or not isinstance(x.get('manifest_sha256'), str)
               or not re.fullmatch(r'[a-f0-9]{64}\Z', x['manifest_sha256'])
               or _manifest_fingerprint(game, x.get('path')) != x['manifest_sha256'] for x in evidence):
            continue
        result.append({'identity': name.removeprefix('mod.io:'), 'version_id': fid,
                       'version': str(row.get('version') or '')[:80], 'paths': list(row['paths'])})
    return sorted(result, key=lambda x: x['identity'])


def release_candidates(installed, listed):
    """Review-only alternatives; file IDs are not assumed to be semantic versions."""
    if not isinstance(installed, dict) or not isinstance(listed, list):
        return []
    identity = installed.get('identity')
    current = installed.get('version_id')
    if not isinstance(identity, str) or not _PACKAGE.fullmatch('mod.io:' + identity) or not isinstance(current, str) or not _ID.fullmatch(current):
        return []
    result = []
    seen = set()
    for row in listed[:100]:
        if not isinstance(row, dict) or row.get('provider') != 'mod.io' or row.get('identity') != identity:
            continue
        fid = row.get('version_id')
        if not isinstance(fid, str) or not _ID.fullmatch(fid) or fid == current or fid in seen:
            continue
        seen.add(fid)
        result.append({'identity': identity, 'installed_file_id': current,
                       'available_file_id': fid, 'version': str(row.get('version') or '')[:80]})
    return result
