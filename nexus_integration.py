"""Nexus Mods private-test/registration-ready integration for UniMod.

No API credentials are saved or logged.  Interactive SSO requires a registered
application slug supplied by Nexus Mods.  Free downloads require the browser-
authorized NXM download link; we do not bypass site restrictions.
"""
import hashlib
import json
import os
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

APP_NAME = 'UniMod'
APP_VERSION = '0.54.0'
API_HOST = 'api.nexusmods.com'
SSO_HOST = 'sso.nexusmods.com'
DOM = re.compile(r'[a-z][a-z0-9-]{1,79}\Z')
IDENT = re.compile(r'[1-9][0-9]{0,11}\Z')
SLUG = re.compile(r'[a-z][a-z0-9_-]{2,79}\Z')
MAX_JSON = 2 * 1024 * 1024
MAX_DOWNLOAD = 2 * 1024 * 1024 * 1024


def registered_app_slug(env=None):
    """No default slug: approval and identifier must come from Nexus Mods."""
    value = (env or os.environ).get('UNIMOD_NEXUS_APP_SLUG', '').strip().lower()
    if not value:
        return None
    if not SLUG.fullmatch(value):
        raise ValueError('Invalid Nexus application slug')
    return value


def authorization_url(request_id, slug):
    if not SLUG.fullmatch(str(slug)):
        raise ValueError('Nexus application registration is required for SSO')
    try:
        rid = str(uuid.UUID(str(request_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid SSO request identifier') from None
    return ('https://www.nexusmods.com/sso?' +
            urllib.parse.urlencode({'id': rid, 'application': slug}))


def sso_sign_in(slug, browser_callback, connect=None, timeout_seconds=150, uuid_factory=uuid.uuid4):
    """Protocol 2 login, returns *session-only* API key.  Injectable socket for tests.

    websocket-client is an optional dependency.  On connection loss, the user can
    retry a new request; secret-bearing socket frames never enter logs/errors.
    """
    request_id = str(uuid_factory())
    url = authorization_url(request_id, slug)
    if connect is None:
        try:
            import websocket
        except ImportError:
            raise RuntimeError('SSO needs python-websocket-client. Install it before connecting.') from None
        connect = lambda: websocket.create_connection('wss://' + SSO_HOST, timeout=12,
                                                       sslopt={'cert_reqs': ssl.CERT_REQUIRED})
    sock = connect()
    try:
        sock.send(json.dumps({'id': request_id, 'token': None, 'protocol': 2}))
        browser_callback(url)
        deadline = time.monotonic() + min(300, max(15, timeout_seconds))
        last_ping = time.monotonic()
        while time.monotonic() < deadline:
            if hasattr(sock, 'settimeout'):
                sock.settimeout(2)
            try:
                msg = sock.recv()
            except Exception as exc:
                # Only a socket read timeout may be retried. Don't expose raw
                # protocol frames or exception strings (might contain API keys).
                if isinstance(exc, TimeoutError) or 'timeout' in type(exc).__name__.lower():
                    if time.monotonic() - last_ping >= 25 and hasattr(sock, 'ping'):
                        sock.ping()
                        last_ping = time.monotonic()
                    continue
                raise RuntimeError('Nexus SSO connection closed before approval') from None
            try:
                frame = json.loads(msg)
            except (json.JSONDecodeError, ValueError, TypeError):
                raise RuntimeError('Unexpected Nexus SSO response') from None
            if not isinstance(frame, dict) or frame.get('success') is False:
                raise RuntimeError('Nexus SSO did not approve the request')
            data = frame.get('data') or {}
            if not isinstance(data, dict):
                raise RuntimeError('Unexpected Nexus SSO response')
            if 'api_key' in data:
                key = data['api_key']
                if not isinstance(key, str) or len(key.strip()) < 16:
                    raise RuntimeError('Nexus SSO returned an invalid key')
                return key.strip()
        raise TimeoutError('Nexus login timed out; please try again')
    finally:
        try: sock.close()
        except Exception: pass


def _identity(game, mod, file_id=None):
    if not DOM.fullmatch(str(game)) or not IDENT.fullmatch(str(mod)):
        raise ValueError('Invalid Nexus game or mod identifier')
    if file_id is not None and not IDENT.fullmatch(str(file_id)):
        raise ValueError('Invalid Nexus file identifier')


def parse_nxm_link(value):
    """Only accept official NXM mod file links, no other schemes or hosts."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Invalid NXM link')
    try: url = urllib.parse.urlsplit(value.strip())
    except ValueError: raise ValueError('Invalid NXM link') from None
    if url.scheme != 'nxm' or not url.netloc or url.username or url.password or url.fragment:
        raise ValueError('Not a Nexus mod-manager download link')
    if url.port is not None:
        raise ValueError('Invalid NXM link port')
    game = url.hostname or ''
    match = re.fullmatch(r'/mods/([1-9][0-9]{0,11})/files/([1-9][0-9]{0,11})/?', url.path)
    if not match or not DOM.fullmatch(game):
        raise ValueError('Unrecognised Nexus mod-manager link')
    mod_id, file_id = match.groups()
    args = urllib.parse.parse_qs(url.query, keep_blank_values=True)
    # These params originate on the official browser site for free accounts.
    key = (args.get('key') or [''])[0]
    expires = (args.get('expires') or [''])[0]
    user_id = (args.get('user_id') or [''])[0]
    if key or expires:
        if not key or len(key) > 256 or not re.fullmatch(r'[\w-]{5,256}', key):
            raise ValueError('Invalid browser download token')
        if not expires.isdigit() or len(expires) > 12:
            raise ValueError('Invalid browser download expiry')
        if int(expires) < int(time.time()):
            raise ValueError('This Nexus download link has expired. Open the official page again.')
    if user_id and not user_id.isdigit():
        raise ValueError('Invalid Nexus user identifier')
    return {'game_domain': game, 'mod_id': mod_id, 'file_id': file_id,
            'key': key, 'expires': expires, 'user_id': user_id,
            'page': f'https://www.nexusmods.com/{game}/mods/{mod_id}?tab=files'}


def mod_files_url(game, mod):
    _identity(game, mod)
    return f'https://{API_HOST}/v1/games/{game}/mods/{mod}/files.json'


def download_link_url(game, mod, file_id, nxm=None):
    _identity(game, mod, file_id)
    base = f'https://{API_HOST}/v1/games/{game}/mods/{mod}/files/{file_id}/download_link.json'
    if nxm is None:
        return base
    if any(str(nxm[k]) != str(value) for k, value in (
            ('game_domain', game), ('mod_id', mod), ('file_id', file_id))):
        raise ValueError('NXM link does not match the selected game/mod file')
    if not nxm.get('key'):
        return base
    return base + '?' + urllib.parse.urlencode({'key': nxm['key'], 'expires': nxm['expires']})


def normalize_files(data):
    """v1 files API only, explicit per-file choice. Never blindly pick latest."""
    if not isinstance(data, dict) or not isinstance(data.get('files'), list):
        raise ValueError('Unexpected Nexus file listing')
    rows = []
    for f in data['files'][:250]:
        if not isinstance(f, dict): continue
        id_ = str(f.get('file_id', ''))
        if not IDENT.fullmatch(id_): continue
        if f.get('is_deleted') is True or f.get('is_removed') is True: continue
        rows.append({'file_id': id_, 'name': str(f.get('name') or f'File {id_}')[:200],
                     'version': str(f.get('version') or '')[:80],
                     'category': str(f.get('category_name') or '')[:100],
                     'size_kb': f.get('size_in_bytes') or f.get('size_kb') or 0,
                     'filename': str(f.get('file_name') or '')[:170]})
    return rows


def safe_nexus_url(url):
    """Allow only known official API/CDN host families, HTTPS without credentials."""
    if not isinstance(url, str) or len(url) > 8192: return False
    try: p = urllib.parse.urlsplit(url)
    except ValueError: return False
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):return False
    host=(p.hostname or '').lower()
    return any(host == root or host.endswith('.' + root)
               for root in ('nexusmods.com', 'nexus-cdn.com'))


def select_download_url(payload):
    if not isinstance(payload, list):
        raise ValueError('Unexpected Nexus download response')
    for record in payload:
        if isinstance(record, dict):
            url = record.get('URI') or record.get('uri')
            if safe_nexus_url(url): return url
    raise ValueError('No approved HTTPS Nexus download mirror available; download through the browser')


class RestrictRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_nexus_url(newurl):
            raise ValueError('Nexus download redirected to an unapproved host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DownloadCancelled(Exception):
    """User cancelled a transfer; the temporary file must be discarded."""


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise DownloadCancelled('Download cancelled; no partial file was retained')


def download_archive(url, directory, suggested_name, opener=None, max_size=MAX_DOWNLOAD,
                     verify_archive=False, progress=None, cancel_event=None):
    """Download into Inbox, never install/overwrite. Temp file + atomic rename."""
    if not safe_nexus_url(url):
        raise ValueError('Not an approved Nexus HTTPS download location')
    name = Path(str(suggested_name)).name
    name = re.sub(r'[^a-zA-Z0-9_.() -]', '_', name).strip('. ')
    if not name or len(name) > 170 or not name.lower().endswith(('.zip', '.7z', '.rar')):
        raise ValueError('Choose a safe mod archive filename (ZIP, 7z, or RAR)')
    directory = Path(directory).expanduser().resolve()
    if not directory.is_dir(): raise ValueError('Choose an existing download folder')
    dest=directory / name
    if dest.exists(): raise FileExistsError('This download already exists; no file was replaced')
    _check_cancel(cancel_event)
    opener = opener or urllib.request.build_opener(RestrictRedirects())
    request = urllib.request.Request(url, headers={'User-Agent': f'{APP_NAME}/{APP_VERSION}'})
    temp_path = None
    try:
        with opener.open(request, timeout=40) as response:
            # Also validate the final resolved response URI after redirects.
            if not safe_nexus_url(response.geturl()):
                raise ValueError('Nexus download response came from an unapproved host')
            # Content-Length is an untrusted hint. Never permit it to bypass max_size.
            raw_total = getattr(response, 'headers', {}).get('Content-Length', '0')
            expected = int(raw_total) if str(raw_total).isdigit() else 0
            if expected > max_size: raise ValueError('Nexus archive exceeds configured download limit')
            with tempfile.NamedTemporaryFile('wb', dir=directory, prefix='.unimod-', suffix='.part', delete=False) as temp:
                temp_path=Path(temp.name)
                total=0
                while True:
                    _check_cancel(cancel_event)
                    chunk=response.read(512 * 1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total > max_size: raise ValueError('Nexus archive exceeds configured download limit')
                    temp.write(chunk)
                    if progress is not None:
                        progress(total, expected)
                    _check_cancel(cancel_event)
        _check_cancel(cancel_event)
        if not total: raise ValueError('Empty Nexus archive')
        if verify_archive:
            with temp_path.open('rb') as stream:signature=stream.read(8)
            if signature.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08')):
                true_suffix='.zip'
            elif signature.startswith(b'7z\xbc\xaf\x27\x1c'):
                true_suffix='.7z'
            elif signature.startswith((b'Rar!\x1a\x07\x00',b'Rar!\x1a\x07\x01')):
                true_suffix='.rar'
            else:
                raise ValueError('Nexus response was not a recognised mod archive (ZIP, 7z or RAR)')
            # A free-account NXM URL does not contain the original filename.
            # Use the format actually received, not the guessed .zip suffix.
            dest=dest.with_suffix(true_suffix)
        if dest.exists():raise FileExistsError('Download destination appeared during transfer')
        # Exclusive final creation protects against races and accidental overwrites.
        _check_cancel(cancel_event)
        os.link(temp_path, dest)
        return dest
    finally:
        if temp_path is not None:
            try:temp_path.unlink(missing_ok=True)
            except OSError:pass


def redacted_error(exception, *secrets):
    """UI-safe message, with browser download tokens removed before display."""
    message=str(exception)[:1000]
    for secret in secrets:
        if secret:
            message=message.replace(str(secret),'[redacted]')
    message=re.sub(r'(?i)([?&](?:key|token|expires|user_id|apikey|api_key)=)[^&\s]+',
                   r'\1[redacted]',message)
    return message
