import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.request

import symphony_linear as app


@unittest.skipUnless(os.name == "posix", "Linux/WSL service integration")
class LinearAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'app.json'
        self.path.write_text(json.dumps({'client_id': 'client', 'client_secret': 'private-secret',
                                         'organization_id': 'workspace'}))
        self.path.chmod(0o600)
        self.client = app.AppClient(self.path)

    def identity(self, is_app=True, workspace='workspace'):
        return 200, json.dumps({'data': {'viewer': {'id': 'bot', 'name': 'Symphony',
                                 'app': is_app, 'organization': {'id': workspace}}}}).encode()

    def token(self, value='app-token'):
        return 200, json.dumps({'access_token': value, 'token_type': 'Bearer', 'expires_in': 3600}).encode()

    def test_refreshes_on_401_and_never_uses_personal_token(self):
        results = [self.token(), self.identity(), (401, b'{}'), self.token('renewed'),
                   self.identity(), (200, b'{"data":{}}')]
        with mock.patch.dict(os.environ, {'LINEAR_API_KEY': 'personal-secret'}), mock.patch.object(app, 'request', side_effect=results) as request:
            self.assertEqual((200, b'{"data":{}}'), self.client.graphql(b'{"query":"{viewer{id}}"}'))
        self.assertEqual('Bearer renewed', request.call_args.args[2]['Authorization'])
        self.assertNotIn('personal-secret', str(request.call_args_list))
        self.assertEqual('client_credentials', dict(__import__('urllib.parse', fromlist=['parse_qsl']).parse_qsl(request.call_args_list[0].args[1].decode()))['grant_type'])

    def test_rejects_human_or_wrong_workspace_before_forwarding(self):
        for identity in (self.identity(False), self.identity(workspace='other')):
            with self.subTest(identity=identity), mock.patch.object(app, 'request', side_effect=[self.token(), identity]) as request:
                with self.assertRaises(app.Error):
                    self.client.graphql(b'{"query":"mutation { dangerous }"}')
                self.assertEqual(2, request.call_count)
                self.assertIsNone(self.client.token)

    @unittest.skipUnless(os.name == 'posix', 'Linux credential ownership contract')
    def test_rejects_public_credentials_and_symlink(self):
        self.path.chmod(0o644)
        with self.assertRaises(app.Error):
            app.read_credentials(self.path)
        self.path.chmod(0o600)
        link = self.path.with_name('link'); link.symlink_to(self.path)
        with self.assertRaises(OSError):
            app.read_credentials(link)

    def test_gateway_authentication_and_origin_rejection(self):
        client = mock.Mock()
        client.graphql.return_value = (200, b'{"data":{}}')
        with app.gateway(client) as (endpoint, secret):
            for headers in ({}, {'Authorization': secret, 'Origin': 'https://evil.example'},
                            {'Authorization': secret, 'Host': 'evil.example'}):
                req = urllib.request.Request(endpoint, data=b'{"query":"{viewer{id}}"}', headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(req)
                self.assertEqual(403, error.exception.code)
            client.graphql.assert_not_called()
            req = urllib.request.Request(endpoint, data=b'{"query":"{viewer{id}}"}', headers={'Authorization': secret})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(b'{"data":{}}', response.read())
            client.graphql.assert_called_once()

    def test_gateway_redacts_upstream_errors(self):
        client = mock.Mock(); client.graphql.side_effect = ValueError('private-secret')
        with app.gateway(client) as (endpoint, secret):
            req = urllib.request.Request(endpoint, data=b'{"query":"x"}', headers={'Authorization': secret})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            self.assertNotIn(b'private-secret', error.exception.read())

    def test_existing_token_reused_and_expiry_renews(self):
        with mock.patch.object(app, 'request', side_effect=[self.token(), self.identity(), (200, b'{}'), (200, b'{}'), self.token('next'), self.identity(), (200,b'{}')]) as request:
            self.client.graphql(b'{}'); self.client.graphql(b'{}')
            self.assertEqual(4,request.call_count)
            self.client.deadline = 0
            self.client.graphql(b'{}')
            self.assertEqual('Bearer next',request.call_args.args[2]['Authorization'])

    def test_no_retry_after_mutation_network_error(self):
        self.client.token = 'app'; self.client.deadline = float('inf')
        with mock.patch.object(app, 'request', side_effect=OSError('ambiguous delivery')) as request:
            with self.assertRaises(OSError):
                self.client.graphql(b'{"query":"mutation {commentCreate}"}')
            request.assert_called_once()

    def test_project_check_uses_app_gateway_and_restores_environment(self):
        import symphony_project
        def checked(_project):
            self.assertEqual('gateway-key', os.environ['LINEAR_API_KEY'])
            self.assertEqual('1', os.environ['SYMPHONY_LINEAR_APP'])
            return []
        with mock.patch.object(app.AppClient, 'authenticate'), \
             mock.patch.object(app, 'gateway', return_value=contextlib.nullcontext(('http://127.0.0.1:8766/graphql', 'gateway-key'))), \
             mock.patch.object(symphony_project, 'check', side_effect=checked) as check, \
             mock.patch.dict(os.environ, {'LINEAR_API_KEY': 'personal-key'}):
            self.assertEqual([], app.check_project(Path(self.temp.name)))
            self.assertEqual('personal-key', os.environ['LINEAR_API_KEY'])
            self.assertNotIn('SYMPHONY_LINEAR_APP', os.environ)
        check.assert_called_once()
