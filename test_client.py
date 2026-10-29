import json
import os
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from app import Handler, ThreadingHTTPServer
from client import HabbliveClient, UpstreamError, SameSiteRedirect
from test_app import fixture

LOGIN = '<form method="post"><input name="username"><input type="password" name="password"></form>'


class LoginTests(unittest.TestCase):
    @patch.dict(os.environ, {'HABBLIVE_USERNAME': 'test-account', 'HABBLIVE_PASSWORD': 'dummy-test-value'})
    def test_login_then_profile_and_cache(self):
        c = HabbliveClient()
        with patch.object(c, 'request', side_effect=[LOGIN, LOGIN, '<h1>Home</h1>', fixture()]) as request:
            result = c.lookup('Teste')
            self.assertEqual(result['id'], 358)
            self.assertEqual(request.call_count, 4)
            self.assertEqual(request.call_args_list[2].args[1]['username'], 'test-account')
            result['badges'].clear()
            again = c.lookup('Teste')
            self.assertEqual(len(again['badges']), 1)
            self.assertEqual(request.call_count, 4)

    @patch.dict(os.environ, {'HABBLIVE_USERNAME': 'test-account', 'HABBLIVE_PASSWORD': 'dummy-test-value'})
    def test_failed_login_stops_and_cools_down(self):
        c = HabbliveClient()
        with patch.object(c, 'request', return_value=LOGIN):
            with self.assertRaises(UpstreamError) as error:
                c.lookup('Teste')
            self.assertEqual(error.exception.code, 'HABBLIVE_LOGIN_FAILED')
            with self.assertRaises(UpstreamError) as error:
                c.login()
            self.assertEqual(error.exception.code, 'LOGIN_COOLDOWN')

    def test_public_response_does_not_login(self):
        c = HabbliveClient()
        with patch.object(c, 'request', return_value=fixture()) as request, patch.object(c, 'login') as login:
            self.assertEqual(c.lookup('Teste')['username'], 'Teste')
            login.assert_not_called()
            self.assertEqual(request.call_count, 1)

    def test_reject_wrong_profile_and_invalid_input(self):
        c = HabbliveClient()
        with patch.object(c, 'request', return_value=fixture(name='Outro')):
            with self.assertRaises(UpstreamError) as error:
                c.lookup('Teste')
            self.assertEqual(error.exception.code, 'PROFILE_MISMATCH')
        with self.assertRaises(UpstreamError):
            c.lookup('../admin')

    def test_credentials_cannot_redirect_off_site(self):
        with self.assertRaises(UpstreamError):
            SameSiteRedirect().redirect_request(Request('https://habblive.in/'), None, 302, '', {}, 'https://example.com/')

    @patch.dict(os.environ, {'INTEGRATION_API_KEY': 'test-only-integration-key'})
    def test_http_requires_key_and_returns_only_profile(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/perfil?user=Teste'
            with self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 401)
            with patch('client.client.lookup', return_value={'username': 'Teste'}) as lookup:
                request = Request(url, headers={'Authorization': 'Bearer test-only-integration-key'})
                with urlopen(request) as response:
                    self.assertEqual(json.load(response), {'data': {'username': 'Teste'}})
                lookup.assert_called_once_with('Teste', 1)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
