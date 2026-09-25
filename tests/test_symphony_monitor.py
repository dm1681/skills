from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request

import symphony_dashboard as dashboard
import symphony_monitor as monitor
import symphony_registry as registry
import symphony_project

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/symphony/state.json').read_text())


def register_child(args):
    path, port = args
    registry.register('/synthetic/' + str(port), f'http://localhost:{port}', path=Path(path))


class Fixture:
    def __init__(self):
        self.payload = copy.deepcopy(FIXTURE)
        self.code = 200
        self.delay = 0
        self.requests = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                owner.requests.append(('GET', self.path))
                time.sleep(owner.delay)
                self.send_response(owner.code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Location', 'http://example.com/private')
                self.end_headers()
                try:
                    self.wfile.write(owner.payload if isinstance(owner.payload, bytes) else json.dumps(owner.payload).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def do_POST(self):
                owner.requests.append(('POST', self.path))
                self.send_error(405)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@unittest.skipUnless(os.name == "posix", "Linux/WSL monitoring registry")
class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'registry.json'
        self.env = mock.patch.dict(os.environ, {'SKILLS_SYMPHONY_REGISTRY': str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def fixture(self):
        result = Fixture()
        self.addCleanup(result.close)
        return result

    def test_endpoint_validation_and_canonicalization(self):
        self.assertEqual(registry.endpoint('http://localhost:8788/'), 'http://127.0.0.1:8788')
        self.assertEqual(registry.endpoint('http://[::1]:8788'), 'http://[::1]:8788')
        for value in ['http://example.com:80', 'http://127.0.0.1.evil:80', 'http://127.1:80',
                      'https://localhost:80', 'http://user:secret@localhost:80', 'http://localhost:80/a',
                      'http://localhost:80?key=secret', 'http://localhost:80#secret', 'http://localhost',
                      'http://0.0.0.0:80', 'file:///tmp/a', 'http://localhost:0', 'http://localhost:65536',
                      'http://localhost:80\n', 'http://[::ffff:127.0.0.1]:80']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                registry.endpoint(value)

    @unittest.skipUnless(os.name == 'posix', 'Linux/WSL registry')
    def test_concurrent_updates_deduplication_and_permissions(self):
        with ProcessPoolExecutor(max_workers=4) as pool:
            list(pool.map(register_child, [(str(self.path), p) for p in range(20000, 20012)] * 2))
        entries = registry.read(self.path)
        self.assertEqual(len(entries), 12)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        old = entries[0]
        updated = registry.register('/different/label', old['endpoint'], path=self.path)
        self.assertEqual(old['id'], updated['id'])
        self.assertEqual(len(registry.read(self.path)), 12)
        self.assertEqual(set(updated), {'id', 'name', 'project_path', 'endpoint', 'mode'})

    def test_disabled_config_import_is_metadata_only(self):
        config = {'project_dir': self.temp.name, 'dashboard_port': None, 'secret': 'DO_NOT_COPY'}
        registry.register_config(config)
        self.assertIsNone(registry.read(self.path)[0]['endpoint'])
        self.assertNotIn('DO_NOT_COPY', self.path.read_text())
        config['dashboard_port'] = 23456
        registry.register_config(config)
        self.assertEqual(len(registry.read(self.path)), 1)

    def test_adapter_preserves_partial_fields_without_private_data(self):
        state = monitor.project_state(FIXTURE)
        self.assertEqual(state['counts'], {'running': 1, 'retrying': 1})
        text = json.dumps(state)
        for private in ['PRIVATE', 'workspace_path', 'rate_limits', 'last_message']:
            self.assertNotIn(private, text)
        partial = copy.deepcopy(FIXTURE)
        partial['running'][0] = {'issue_id': 'only-identity', 'last_event': '<script>bad()</script>',
                                 'issue_url': 'javascript:alert(1)', 'tokens': {'total_tokens': True}}
        partial.pop('codex_totals')
        state = monitor.project_state(partial)
        row = state['sessions'][0]
        for key in ['title', 'activity', 'issue_url', 'started_at']:
            self.assertIsNone(row[key])
        self.assertIsNone(row['tokens']['total_tokens'])
        self.assertIsNone(state['usage']['total_tokens'])
        for invalid in [{}, [], {'error': {'code': 'snapshot_timeout'}}, {**FIXTURE, 'running': None},
                        {**FIXTURE, 'running': [{}]}, {**FIXTURE, 'generated_at': 'bad'}]:
            with self.assertRaises(monitor.Incompatible):
                monitor.project_state(invalid)

    def test_identity_and_counts_do_not_collide_across_instances(self):
        now = monitor.timestamp(FIXTURE['generated_at'])
        m = monitor.Monitor(clock=lambda: now, loader=lambda *_: monitor.project_state(FIXTURE))
        m.entries = [registry.entry('/alpha', 'http://localhost:20001'), registry.entry('/beta', 'http://localhost:20002')]
        for item in m.entries:
            m.observe(item)
        data = m.snapshot()
        self.assertEqual(data['counts'], {'running': 2, 'retrying': 2})
        self.assertEqual(data['usage']['total_tokens']['value'], 500)
        self.assertNotEqual(data['instances'][0]['id'], data['instances'][1]['id'])
        self.assertEqual(data['instances'][0]['sessions'][0]['issue'], data['instances'][1]['sessions'][0]['issue'])

    def test_failure_staleness_restart_and_recovery(self):
        now = [monitor.timestamp(FIXTURE['generated_at'])]
        payload = monitor.project_state(FIXTURE)
        m = monitor.Monitor(clock=lambda: now[0], loader=lambda *_: copy.deepcopy(payload))
        item = registry.entry('/alpha', 'http://localhost:20001')
        m.entries = [item]
        m.observe(item)
        self.assertEqual(m.snapshot()['instances'][0]['health'], 'active')
        now[0] += 100
        self.assertEqual(m.snapshot()['instances'][0]['health'], 'stale')
        self.assertEqual(m.snapshot()['counts']['running'], 0)
        m.loader = mock.Mock(side_effect=OSError('SECRET'))
        m.observe(item)
        data = m.snapshot()
        self.assertEqual(data['instances'][0]['health'], 'unreachable')
        self.assertIsNotNone(data['instances'][0]['last_success'])
        self.assertEqual(data['instances'][0]['sessions'], [])
        self.assertNotIn('SECRET', json.dumps(data))
        m.loader = mock.Mock(side_effect=monitor.Incompatible())
        m.observe(item)
        self.assertEqual(m.snapshot()['instances'][0]['health'], 'incompatible')
        payload.update(generated_at=now[0], sessions=[], counts={'running': 0, 'retrying': 0}, usage=dict.fromkeys(monitor.METRICS, 0))
        m.loader = lambda *_: payload
        m.observe(item)
        self.assertEqual(m.snapshot()['instances'][0]['health'], 'idle')
        self.assertEqual(m.snapshot()['usage']['total_tokens']['value'], 0)

    def test_http_timeout_malformed_redirect_and_get_only(self):
        f = self.fixture()
        self.assertEqual(monitor.fetch(f.url, 1)['counts']['running'], 1)
        f.payload = b'{malformed'
        with self.assertRaises(monitor.Incompatible):
            monitor.fetch(f.url, 1)
        f.code = 302
        with self.assertRaises(OSError):
            monitor.fetch(f.url, 1)
        f.code, f.delay = 200, .5
        start = time.monotonic()
        with self.assertRaises((OSError, monitor.http.client.HTTPException)):
            monitor.fetch(f.url, .1)
        self.assertLess(time.monotonic()-start, .4)
        self.assertTrue(all(r == ('GET', '/api/v1/state') for r in f.requests))

    def test_independent_polling_registry_reload_and_shutdown(self):
        slow = self.fixture()
        healthy = self.fixture()
        slow.delay = .8
        healthy.payload['generated_at'] = datetime.now(timezone.utc).isoformat()
        registry.register('/slow', slow.url)
        registry.register('/healthy', healthy.url)
        m = monitor.Monitor(self.path, interval=1, timeout=.2)
        m.start()
        self.addCleanup(m.close)
        deadline = time.monotonic()+2
        while time.monotonic()<deadline:
            if m.snapshot()['counts']['running'] == 1:
                break
            time.sleep(.02)
        self.assertEqual(m.snapshot()['counts']['running'], 1)
        registry.register('/disabled', None)
        time.sleep(1.1)
        self.assertEqual(m.snapshot()['coverage']['registered'], 3)
        m.close()
        self.assertTrue(all(not thread.is_alive() for _, thread in m.workers.values()))

    def test_browser_api_security_and_no_lifecycle_effects(self):
        f = self.fixture()
        f.payload['generated_at'] = datetime.now(timezone.utc).isoformat()
        with mock.patch.object(symphony_project, 'start', side_effect=AssertionError), mock.patch.object(symphony_project, 'check', side_effect=AssertionError), mock.patch.object(subprocess, 'run', side_effect=AssertionError), mock.patch.object(os, 'execv', side_effect=AssertionError):
            registry.register('/synthetic', f.url, '<script>alert(1)</script>')
            m = monitor.Monitor(self.path, interval=1)
            m.start()
            server = dashboard.server(m, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f'http://127.0.0.1:{server.server_port}'
                for path in ['/', '/app.js', '/style.css', '/api/state', '/api/state']:
                    with urllib.request.urlopen(url+path) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
                request = urllib.request.Request(url+'/api/state', headers={'Host':'evil.example'})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 403)
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(urllib.request.Request(url+'/api/v1/refresh', data=b''))
            finally:
                server.shutdown()
                server.server_close()
                m.close()
                thread.join()
        self.assertTrue(all(r == ('GET', '/api/v1/state') for r in f.requests))

    def test_cli_registration_outside_project_and_invalid_endpoint(self):
        command = [sys.executable, str(ROOT/'skills_cli.py'), 'symphony', 'register', '--project-dir', self.temp.name, '--endpoint']
        result = subprocess.run(command+['http://localhost:21234'], cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.path.read_bytes()
        result = subprocess.run(command+['http://example.com:80'], cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_registry_and_port_conflict_fail_without_rebinding(self):
        self.path.write_text('{')
        with self.assertRaises(ValueError):
            registry.register('/project', 'http://localhost:12345')
        self.assertEqual(self.path.read_text(), '{')
        m = monitor.Monitor(self.path)
        m.reconcile()
        self.assertTrue(m.snapshot()['registry_error'])
        f = self.fixture()
        with self.assertRaisesRegex(ValueError, 'No service was changed'):
            dashboard.serve(self.path, port=f.server.server_port)
        self.assertEqual(monitor.fetch(f.url, 1)['counts']['running'], 1)


if __name__ == '__main__':
    unittest.main()
