"""Nexus OAuth 2.0 Authorization Code + S256 PKCE development framework.

This module never supplies a client ID or guesses the provider's OAuth URLs.
It is safe to test locally with an injected token transport; actual Nexus sign-in
requires the registered client details and callback rules issued by Nexus.
Tokens, code verifiers and authorization codes are never persisted or logged.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

APP_NAME = 'UniMod'
APP_VERSION = '0.54.0'
MAX_TOKEN_RESPONSE = 64 * 1024


def _nexus_https(value):
    parsed = urllib.parse.urlsplit(value)
    hostname = (parsed.hostname or '').lower()
    if (parsed.scheme != 'https' or parsed.username or parsed.password or
            parsed.port not in (None, 443) or not hostname or
            not (hostname == 'nexusmods.com' or hostname.endswith('.nexusmods.com')) or
            parsed.query or parsed.fragment):
        raise ValueError('OAuth endpoint must be HTTPS on a Nexus Mods-owned host')
    return value


def _redirect(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or
            parsed.port is None or parsed.port < 1024 or parsed.username or parsed.password or
            parsed.path != '/callback' or parsed.query or parsed.fragment):
        raise ValueError('OAuth callback must be http://127.0.0.1:<port>/callback')
    return value


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scope: str = 'public'

    def __post_init__(self):
        if not self.client_id or len(self.client_id) > 180 or not self.client_id.isascii() or not all(
                c.isalnum() or c in '_-.' for c in self.client_id):
            raise ValueError('OAuth client ID must be issued by Nexus Mods')
        _nexus_https(self.authorize_url)
        _nexus_https(self.token_url)
        _redirect(self.redirect_uri)
        if not self.scope or len(self.scope) > 160 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_- ' for c in self.scope):
            raise ValueError('Invalid OAuth scope')

    @classmethod
    def from_environment(cls, env=None):
        env = os.environ if env is None else env
        names = ('UNIMOD_NEXUS_OAUTH_CLIENT_ID', 'UNIMOD_NEXUS_OAUTH_AUTHORIZE_URL',
                 'UNIMOD_NEXUS_OAUTH_TOKEN_URL', 'UNIMOD_NEXUS_OAUTH_REDIRECT_URI')
        values = [str(env.get(n, '')).strip() for n in names]
        if not all(values):
            raise RuntimeError('Nexus OAuth is awaiting the registered client ID, OAuth URLs and approved callback URI')
        return cls(*values, scope=str(env.get('UNIMOD_NEXUS_OAUTH_SCOPE', 'public')))


class PKCELogin:
    """Single-use authorization. Never expose code verifier or state via UI logs."""
    def __init__(self, config, *, random_bytes=None):
        self.config = config
        random_bytes = random_bytes or secrets.token_bytes
        self.verifier = base64.urlsafe_b64encode(random_bytes(48)).decode('ascii').rstrip('=')
        self.state = base64.urlsafe_b64encode(random_bytes(32)).decode('ascii').rstrip('=')
        if not 43 <= len(self.verifier) <= 128 or len(self.state) < 32:
            raise ValueError('Invalid random PKCE material')
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
        self._used = False

    def browser_url(self):
        cfg = self.config
        return cfg.authorize_url + '?' + urllib.parse.urlencode({
            'response_type': 'code', 'client_id': cfg.client_id,
            'redirect_uri': cfg.redirect_uri, 'scope': cfg.scope,
            'state': self.state, 'code_challenge': self.challenge,
            'code_challenge_method': 'S256',
        })

    def accept_callback(self, uri):
        """Return one-time code after strict redirect and constant-time state validation."""
        if self._used:
            raise ValueError('OAuth callback already consumed')
        expected = urllib.parse.urlsplit(self.config.redirect_uri)
        received = urllib.parse.urlsplit(uri)
        if (received.scheme, received.hostname, received.port, received.path) != (
                expected.scheme, expected.hostname, expected.port, expected.path) or received.fragment:
            raise ValueError('OAuth callback location mismatch')
        values = urllib.parse.parse_qs(received.query, keep_blank_values=True, strict_parsing=True)
        if any(len(v) != 1 for v in values.values()) or len(received.query) > 4096:
            raise ValueError('Invalid OAuth callback parameters')
        state = values.get('state', [''])[0]
        if not hmac.compare_digest(state, self.state):
            raise ValueError('OAuth callback state mismatch')
        self._used = True  # even a denied request cannot be replayed
        if 'error' in values:
            raise RuntimeError('Nexus authorization was cancelled or declined')
        code = values.get('code', [''])[0]
        if not code or len(code) > 2048:
            raise ValueError('OAuth callback contained no valid authorization code')
        return code


def _token_request(cfg, fields, transport=None):
    """POST form data; transport injection is used for offline integration tests."""
    body = urllib.parse.urlencode(fields).encode('utf-8')
    request = urllib.request.Request(cfg.token_url, body, method='POST', headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'Application-Name': APP_NAME,
        'Application-Version': APP_VERSION,
        'User-Agent': APP_NAME + '/' + APP_VERSION,
    })
    if transport is None:
        class DenyRedirects(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError('OAuth token endpoint may not redirect')
        transport = urllib.request.build_opener(DenyRedirects()).open
    try:
        with transport(request, timeout=20) as response:
            payload = response.read(MAX_TOKEN_RESPONSE + 1)
    except Exception:
        raise RuntimeError('Nexus OAuth token request failed; verify registration and retry') from None
    if len(payload) > MAX_TOKEN_RESPONSE:
        raise ValueError('OAuth token response exceeded the size limit')
    try:
        doc = json.loads(payload)
    except (ValueError, TypeError):
        raise ValueError('Invalid OAuth token response') from None
    if not isinstance(doc, dict) or not isinstance(doc.get('access_token'), str) or len(doc['access_token']) < 16:
        raise ValueError('OAuth token response did not include an access token')
    if doc.get('token_type', 'Bearer').lower() != 'bearer':
        raise ValueError('Unsupported OAuth token type')
    return {k: doc[k] for k in ('access_token', 'refresh_token', 'token_type', 'expires_in', 'scope') if k in doc}


def exchange_code(login, code, transport=None):
    if not login._used:
        raise RuntimeError('OAuth callback must be verified before exchanging its code')
    if not code or len(code) > 2048:
        raise ValueError('Invalid authorization code')
    # A separate login instance is needed for a second attempt, because the
    # authorization code and verifier are valid only for one grant.
    return _token_request(login.config, {
        'grant_type': 'authorization_code', 'client_id': login.config.client_id,
        'redirect_uri': login.config.redirect_uri, 'code': code,
        'code_verifier': login.verifier,
    }, transport=transport)


def refresh_token(cfg, refresh, transport=None):
    if not isinstance(refresh, str) or not refresh:
        raise ValueError('Missing OAuth refresh token')
    return _token_request(cfg, {'grant_type': 'refresh_token', 'client_id': cfg.client_id,
                                'refresh_token': refresh}, transport=transport)


def bearer_headers(tokens):
    token = tokens.get('access_token') if isinstance(tokens, dict) else None
    if not isinstance(token, str) or len(token) < 16 or any(c.isspace() for c in token):
        raise ValueError('Missing valid OAuth access token')
    return {'Authorization': 'Bearer ' + token,
            'Application-Name': APP_NAME, 'Application-Version': APP_VERSION}


def browser_login(cfg, open_browser, timeout_seconds=180, transport=None):
    """Localhost callback server used only after Nexus confirms the redirect URI.

    Runs synchronously and should be called from a GUI worker, not the UI thread.
    Binds IPv4 loopback only, validates state and callback path; no public listener.
    """
    login = PKCELogin(cfg)
    redirect = urllib.parse.urlsplit(cfg.redirect_uri)
    result = {'callback': None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                # Drop Host header ambiguity; only bound IPv4 loopback is supported.
                if self.headers.get('Host', '') not in (f'127.0.0.1:{redirect.port}',):
                    raise ValueError('Unexpected callback host')
                candidate = cfg.redirect_uri + ('?' + urllib.parse.urlsplit(self.path).query)
                if urllib.parse.urlsplit(self.path).path != '/callback':
                    raise ValueError('Unexpected callback path')
                code = login.accept_callback(candidate)
                result['callback'] = code
                status, message = 200, b'UniMod authorization received. Return to UniMod.'
            except Exception:
                # Do not disclose callback details in local response or logs.
                status, message = 400, b'Invalid or declined UniMod authorization. Return to UniMod.'
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(message)))
            self.end_headers()
            self.wfile.write(message)
        def log_message(self, *_):
            pass

    server = HTTPServer(('127.0.0.1', redirect.port), Handler)
    server.timeout = 1
    try:
        open_browser(login.browser_url())
        import time
        deadline = time.monotonic() + min(300, max(30, int(timeout_seconds)))
        while time.monotonic() < deadline and result['callback'] is None:
            server.handle_request()
        if result['callback'] is None:
            raise TimeoutError('Nexus browser authorization was not completed')
        return exchange_code(login, result['callback'], transport=transport)
    finally:
        server.server_close()
