"""Local Nexus download provenance receipts. No API keys, NXM links or CDN URLs.

These are evidence of what UniMod downloaded, NOT proof that an existing
installed mod comes from that page. Consumers must match exact SMAPI IDs and
continue using the review workflow. A receipt never triggers installation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone

SHA256 = re.compile(r'[a-f0-9]{64}\Z')
DIGITS = re.compile(r'[1-9][0-9]{0,11}\Z')
DOMAIN = re.compile(r'[a-z0-9][a-z0-9-]{1,60}\Z')
MAX_FILE_BYTES = 8 * 1024 ** 3
MAX_DB_BYTES = 2 * 1024 ** 2
MAX_ENTRIES = 1000
MAX_IDENTITIES = 120


def _valid(row):
    if not isinstance(row, dict): return False
    if not isinstance(row.get('sha256'), str) or not SHA256.fullmatch(row['sha256']): return False
    if not isinstance(row.get('size'), int) or not 0 < row['size'] <= MAX_FILE_BYTES: return False
    if not isinstance(row.get('game_domain'), str) or not DOMAIN.fullmatch(row['game_domain']): return False
    if not all(isinstance(row.get(k), str) and DIGITS.fullmatch(row[k]) for k in ('mod_id', 'file_id')): return False
    uids = row.get('smapi_ids')
    if not isinstance(uids, list) or len(uids) > MAX_IDENTITIES: return False
    if not all(isinstance(u, str) and 0 < len(u) <= 200 and '\x00' not in u for u in uids): return False
    return True


def load_receipts(db):
    """Ignore untrusted/oversized/corrupt local JSON; never follow DB symlinks."""
    path = Path(db)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DB_BYTES: return []
        data = json.loads(path.read_text(encoding='utf-8'))
        rows = data.get('receipts') if isinstance(data, dict) and data.get('schema') == 1 else None
        if not isinstance(rows, list): return []
        return [r for r in rows[:MAX_ENTRIES] if _valid(r)]
    except (OSError, ValueError, UnicodeError):
        return []


def fingerprint(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Refusing symlinked download')
    size = path.stat().st_size
    if not 0 < size <= MAX_FILE_BYTES: raise ValueError('Invalid archive size')
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    if size != path.stat().st_size: raise ValueError('Download changed while hashing')
    return digest.hexdigest(), size


def record_receipt(archive, game_domain, mod_id, file_id, identities, db):
    """Store provider identifiers only after an approved, finished ZIP download.

    Caller must pass SMAPI identities extracted from that archive. No source
    records are created for unknown/unsupported archives or empty identity sets.
    """
    ids = sorted({str(i['uid']).strip() for i in identities if isinstance(i, dict) and i.get('uid')})
    if not ids or len(ids) > MAX_IDENTITIES: return None
    sha, size = fingerprint(archive)
    row = {'sha256':sha, 'size':size, 'game_domain':str(game_domain),
           'mod_id':str(mod_id), 'file_id':str(file_id), 'smapi_ids':ids,
           'recorded_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    if not _valid(row): raise ValueError('Invalid Nexus receipt identifiers')
    db = Path(db)
    if db.is_symlink(): raise ValueError('Refusing symlinked receipt database')
    current = load_receipts(db)
    # Repeated downloads of identical bytes for different Nexus pages remain
    # separate evidence; the caller must surface a conflict for review.
    current = [r for r in current if not (r['sha256']==sha and r['game_domain']==row['game_domain']
                     and r['mod_id']==row['mod_id'] and r['file_id']==row['file_id'])]
    current = (current + [row])[-MAX_ENTRIES:]
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_name(db.name + '.tmp')
    if tmp.is_symlink(): raise ValueError('Unsafe receipt temporary file')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'schema':1, 'receipts':current}, handle, indent=2)
            handle.write('\n')
        os.replace(tmp, db)
    finally:
        if tmp.exists(): tmp.unlink()
    return row


def find_receipt(archive, game_domain, db):
    """Match the *bytes* of an archive, not a filename or inferred mod title."""
    existing = [r for r in load_receipts(db) if r['game_domain']==game_domain]
    if not existing: return []
    try: sha, size = fingerprint(archive)
    except (OSError, ValueError): return []
    return [r for r in existing if r['sha256']==sha and r['size']==size]


def uid_candidates(game_domain, installed_uids, db):
    """Return reviewable source evidence, even if a downloaded ZIP was moved.

    Receipts alone are not a safe proof of installed-file authenticity.
    """
    targets = {str(uid).casefold() for uid in installed_uids if uid}
    evidence = {}
    for r in load_receipts(db):
        if r['game_domain'] != game_domain: continue
        for uid in r['smapi_ids']:
            ident = uid.casefold()
            if ident in targets:
                evidence.setdefault(ident, []).append({
                    'uid':uid, 'mod_id':r['mod_id'],
                    'url':f"https://www.nexusmods.com/{game_domain}/mods/{r['mod_id']}",
                    'filename':'UniMod download history',
                    'evidence':f"UniMod approved Nexus download receipt (file #{r['file_id']})"})
    return evidence
