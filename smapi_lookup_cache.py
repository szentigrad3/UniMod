"""Local rate-friendly bookkeeping for *unsuccessful* exact SMAPI source lookups.

This file is only an optimization, never evidence that a mod isn't on Nexus.
API/network errors are not negative matches. Manual lookups bypass this cache.
"""
import hashlib
import json
import math
import time
from pathlib import Path

TTL_SECONDS = 7 * 24 * 60 * 60
MAX_ROWS = 2500


def fingerprint(mod):
    """Doesn't write update keys, file paths or mod names into the cache."""
    keys = mod.get('update_keys') or []
    if not isinstance(keys, list):
        keys = []
    safe_keys = sorted(x.casefold() for x in keys if isinstance(x, str) and len(x) <= 256)
    data = [str(mod.get('uid') or '').strip().casefold(),
            str(mod.get('version') or '').strip(), safe_keys]
    return hashlib.sha256(json.dumps(data, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _key(identity_value):
    # Isolate games without persisting installation paths or user folder names.
    return hashlib.sha256(str(identity_value).encode('utf-8')).hexdigest()


def load(path):
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(raw, dict) or raw.get('schema') != 1 or not isinstance(raw.get('entries'), dict):
        return {}
    return {k: v for k, v in list(raw['entries'].items())[:MAX_ROWS]
            if isinstance(k, str) and len(k) <= 512 and isinstance(v, dict)
            and isinstance(v.get('fingerprint'), str) and len(v['fingerprint']) == 64
            and isinstance(v.get('timestamp'), (int, float)) and math.isfinite(v['timestamp'])}


def pending(mods, path, identity, now=None, force=False):
    """Return fresh candidates; negative cache is bypassed for manual lookups."""
    if force:
        return list(mods), 0
    now = time.time() if now is None else now
    cache = load(path)
    todo = []
    skipped = 0
    for mod in mods:
        key = _key(identity(mod))
        row = cache.get(key, {})
        if (row.get('fingerprint') == fingerprint(mod)
                and 0 <= now - row.get('timestamp', -1) < TTL_SECONDS):
            skipped += 1
        else:
            todo.append(mod)
    return todo, skipped


def record(mods, report, path, identity, now=None):
    """Store only successful API *non-matches*, not network/per-ID errors.

    Caller must invoke this only after a valid SMAPI response. Existing
    positive IDs are managed separately by UniMod's exact-ID cache.
    """
    now = time.time() if now is None else now
    cache = load(path)
    matched = report.get('matches', {})
    failed = {str(x).casefold() for x in report.get('error_ids', ())}
    for mod in mods:
        uid = str(mod.get('uid') or '').strip().casefold()
        key = _key(identity(mod))
        if uid in matched or uid in failed:
            cache.pop(key, None)
        else:
            cache[key] = {'fingerprint': fingerprint(mod), 'timestamp': now}
    # Limit unbounded growth; retain newest cache records.
    if len(cache) > MAX_ROWS:
        cache = dict(sorted(cache.items(), key=lambda kv: kv[1]['timestamp'], reverse=True)[:MAX_ROWS])
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text(json.dumps({'schema': 1, 'entries': cache}, sort_keys=True) + '\n', encoding='utf-8')
    temp.replace(target)
    return len(mods) - len(matched) - len(failed)
