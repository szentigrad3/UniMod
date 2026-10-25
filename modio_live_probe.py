"""Temporary, install-free verification of a selected public mod.io ZIP.

Uses the existing exact-file refresh, HTTPS redirect restrictions, bounded
streaming and provider checksum validation. Downloaded bytes stay inside a
TemporaryDirectory and are deleted on both success and failure. No game paths,
receipts, authentication data or signed URLs appear in the result.
"""
import hashlib
import tempfile
from pathlib import Path

import modio_files

MAX_PROBE_BYTES = 64 * 1024 * 1024


class ProbeError(ValueError):
    """Safe, non-secret user-facing probe validation message."""


def probe_download(record, *, user_id, api_key, fetch=None, opener=None,
                   max_bytes=MAX_PROBE_BYTES, temp_parent=None):
    """Download and hash one verified ZIP, then delete it without staging/installing."""
    if not isinstance(record, dict) or record.get('provider') != 'mod.io':
        raise ProbeError('Select a mod.io release ZIP for the temporary test.')
    game, mod = modio_files._identity(record.get('identity'))
    fid = str(record.get('version_id') or '')
    if not fid.isascii() or not fid.isdecimal() or not 1 <= len(fid) <= 12 or fid[0] == '0':
        raise ProbeError('Select an exact mod.io release file.')
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_PROBE_BYTES:
        raise ProbeError('Invalid temporary download limit.')
    size = record.get('size')
    if type(size) is not int or not 0 < size <= max_bytes:
        raise ProbeError('Choose a ZIP no larger than 64 MiB for the temporary download test.')
    if not isinstance(record.get('filename'), str) or not record['filename'].lower().endswith('.zip'):
        raise ProbeError('The temporary test only accepts verified ZIP files.')
    # The refreshed exact-file metadata must match the reviewed package.
    # The hard stream limit also applies if a CDN sends extra bytes.
    with tempfile.TemporaryDirectory(prefix='unimod-modio-probe-', dir=temp_parent) as tmp:
        output = modio_files.download_selected(record, tmp, user_id=user_id,
                                               api_key=api_key, fetch=fetch,
                                               opener=opener, max_size=max_bytes)
        digest = hashlib.sha256()
        with Path(output).open('rb') as stream:
            for piece in iter(lambda: stream.read(262144), b''):
                digest.update(piece)
        return {'status': 'Downloaded and verified; temporary ZIP deleted',
                'game_id': game, 'mod_id': mod, 'file_id': fid,
                'bytes_verified': size, 'sha256': digest.hexdigest(),
                'installed': False, 'staged': False, 'temporary': True}
