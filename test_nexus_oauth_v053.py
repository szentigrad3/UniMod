import base64
import hashlib
import io
import json
import unittest
import urllib.parse
from unittest.mock import patch
import nexus_oauth as oauth

C = oauth.OAuthConfig('unimod-dev', 'https://www.nexusmods.com/oauth/authorize',
                      'https://www.nexusmods.com/oauth/token',
                      'http://127.0.0.1:8765/callback')


class Response:
    def __init__(self, payload): self.data = io.BytesIO(json.dumps(payload).encode())
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, n=-1): return self.data.read(n)


class NexusOAuthTests(unittest.TestCase):
    def test_registration_gated(self):
        with self.assertRaisesRegex(RuntimeError, 'awaiting'):
            oauth.OAuthConfig.from_environment({})

    def test_configuration_allows_only_nexus_hosts_and_local_callback(self):
        for url in ('https://nexusmods.com.attacker.test/oauth/token', 'http://nexusmods.com/oauth/token',
                    'https://evil@nexusmods.com/oauth/token', 'https://nexusmods.com:1337/oauth/token'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                oauth.OAuthConfig('unimod', C.authorize_url, url, C.redirect_uri)
        for callback in ('http://localhost:8765/callback', 'http://127.0.0.1:8765/evil',
                         'https://127.0.0.1:8765/callback', 'http://192.168.0.1:8765/callback'):
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                oauth.OAuthConfig('unimod', C.authorize_url, C.token_url, callback)

    def test_pkce_s256_and_state(self):
        login = oauth.PKCELogin(C)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(login.browser_url()).query)
        self.assertEqual(params['code_challenge_method'], ['S256'])
        expected = base64.urlsafe_b64encode(hashlib.sha256(login.verifier.encode()).digest()).decode().rstrip('=')
        self.assertEqual(params['code_challenge'], [expected])
        self.assertEqual(params['state'], [login.state])
        self.assertNotIn(login.verifier, login.browser_url())

    def test_rejects_replay_state_mismatch_and_duplicate(self):
        login = oauth.PKCELogin(C)
        for callback in (C.redirect_uri + '?state=wrong&code=secret',
                         C.redirect_uri + '?state=' + login.state + '&state=bad&code=secret',
                         'http://127.0.0.1:9999/callback?state=' + login.state + '&code=secret'):
            with self.assertRaises(ValueError): login.accept_callback(callback)
        callback = C.redirect_uri + '?state=' + login.state + '&code=secret'
        self.assertEqual(login.accept_callback(callback), 'secret')
        with self.assertRaises(ValueError): login.accept_callback(callback)

    def test_denied_grant_fails_closed(self):
        login = oauth.PKCELogin(C)
        with self.assertRaises(RuntimeError):
            login.accept_callback(C.redirect_uri + '?state=' + login.state + '&error=access_denied')
        with self.assertRaises(ValueError):
            login.accept_callback(C.redirect_uri + '?state=' + login.state + '&code=a')

    def test_token_exchange_contains_verifier_without_leaking(self):
        login = oauth.PKCELogin(C)
        with self.assertRaises(RuntimeError):
            oauth.exchange_code(login, 'not-authorized')
        code = login.accept_callback(C.redirect_uri + '?state=' + login.state + '&code=one-time-code')
        requests = []
        def transport(request, timeout):
            requests.append(request)
            return Response({'access_token': 'A' * 32, 'refresh_token': 'R' * 32, 'token_type': 'Bearer'})
        result = oauth.exchange_code(login, code, transport=transport)
        data = urllib.parse.parse_qs(requests[0].data.decode())
        self.assertEqual(data['code_verifier'], [login.verifier])
        self.assertEqual(data['grant_type'], ['authorization_code'])
        self.assertEqual(requests[0].get_header('Application-name'), 'UniMod')
        self.assertEqual(result['access_token'], 'A'*32)

    def test_refresh_without_refresh_token_is_rejected(self):
        with self.assertRaises(ValueError): oauth.refresh_token(C, '')

    def test_tokens_and_errors_redacted(self):
        def transport(req, timeout): raise RuntimeError('secret=verysecret')
        login = oauth.PKCELogin(C)
        code = login.accept_callback(C.redirect_uri + '?state=' + login.state + '&code=test')
        with self.assertRaises(RuntimeError) as ctx:
            oauth.exchange_code(login, code, transport=transport)
        self.assertNotIn('verysecret', str(ctx.exception))
        self.assertEqual(oauth.bearer_headers({'access_token':'1234567890123456'})['Authorization'],
                         'Bearer 1234567890123456')


if __name__ == '__main__': unittest.main()

class NexusOAuthLoopbackTests(unittest.TestCase):
    def test_end_to_end_simulated_browser_consent(self):
        import socket
        import urllib.request
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cfg = oauth.OAuthConfig('unimod-test', C.authorize_url, C.token_url,
                                f'http://127.0.0.1:{port}/callback')
        requests=[]
        def browser(auth_url):
            params=urllib.parse.parse_qs(urllib.parse.urlsplit(auth_url).query)
            self.assertEqual(params['code_challenge_method'], ['S256'])
            callback=cfg.redirect_uri+'?'+urllib.parse.urlencode({'state':params['state'][0],
                                                                  'code':'mock-code'})
            import threading
            def visit():
                with urllib.request.urlopen(callback,timeout=5) as response:
                    self.assertEqual(response.status,200)
            threading.Thread(target=visit,daemon=True).start()
        def transport(req,timeout):
            requests.append(urllib.parse.parse_qs(req.data.decode()))
            return Response({'access_token':'A'*32, 'token_type':'Bearer'})
        tokens=oauth.browser_login(cfg,browser,timeout_seconds=30,transport=transport)
        self.assertEqual(tokens['access_token'],'A'*32)
        self.assertEqual(requests[0]['code'],['mock-code'])
        self.assertEqual(len(requests[0]['code_verifier'][0]),64)
