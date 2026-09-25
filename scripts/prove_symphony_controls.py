#!/usr/bin/env python3
"""Browser proof with isolated fake processes; never operates real user services.

The manager fixture exercises the shared UI/control helper. It does not validate
systemd cgroup semantics; that acceptance remains a separate runtime check.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


def fixture(port):
    payload = json.loads((ROOT / 'tests/fixtures/symphony/state.json').read_text())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            if self.path != '/api/v1/state':
                self.send_error(404)
                return
            payload['generated_at'] = datetime.now(timezone.utc).isoformat()
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def main(output):
    from playwright.sync_api import sync_playwright
    import symphony_dashboard as dashboard
    import symphony_lifecycle as lifecycle
    import symphony_monitor as monitor
    import symphony_project as project
    import symphony_registry as registry
    from test_symphony_lifecycle import FakeManager

    output.mkdir(parents=True, exist_ok=True)
    class ProcessManager(FakeManager):
        def __init__(self, root):
            super().__init__(root)
            self.children = {}
            self.fail = set()
        def launch(self, key, config, env):
            super().launch(key, config, env)
            if key in self.fail:
                self.finish(key)
                lifecycle.write(key, {'phase':'failed', 'readiness':'Failed', 'error':'Not ready: fixture setup issue must be Done'})
                return
            self.children[key] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--fixture-port', str(config['dashboard_port'])],
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop(self, key):
            super().stop(key)
            child = self.children.pop(key)
            child.terminate()
            child.wait(timeout=5)
            self.finish(key)

    with tempfile.TemporaryDirectory(dir=ROOT / '.symphony') as temporary:
        root = Path(temporary)
        os.environ['SKILLS_SYMPHONY_REGISTRY'] = str(root/'registry.json')
        os.environ['SKILLS_SYMPHONY_STATE'] = str(root/'state')
        manager = ProcessManager(root)
        configs, items = [], []
        for name in ('Alpha', 'Beta'):
            path = root/name
            path.mkdir()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            config = project.setup(path, repo_url=f'https://github.com/fixture/{name}', dashboard_port=port,
                                   project_id='fixture', project_slug='fixture', setup_issue='DIE-1', validation_command='true')
            configs.append(config)
            items.append(registry.register_config(config, managed=True))
        keys = [lifecycle.repository_identity(c) for c in configs]
        lifecycle.start(configs[0], accept_preview=True, manager=manager)
        control = lifecycle.Control(manager=manager)
        m = monitor.Monitor(interval=1, timeout=.2, control=control)
        httpd = dashboard.server(m, 0, control)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        m.start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width':1440, 'height':1300})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept())
                address = f'http://127.0.0.1:{httpd.server_port}'
                page.goto(address)
                page.wait_for_function("() => document.body.textContent.includes('Process: stopped') && document.body.textContent.includes('Process: running/active')")
                assert len(manager.children) == 1
                page.screenshot(path=str(output/'two-repositories.png'), full_page=True)
                beta = page.locator('.instance').filter(has=page.locator('h3', has_text='Beta'))
                beta.get_by_role('button', name='Start', exact=True).click()
                page.wait_for_function("() => [...document.querySelectorAll('.controls strong')].filter(n => n.textContent === 'Process: running/active').length === 2")
                assert len(manager.children) == 2
                page.screenshot(path=str(output/'started.png'), full_page=True)
                state = page.request.get(address+'/api/state').json()
                data = {'id':items[1]['id'], 'repository_id':keys[1], 'action':'start', 'acknowledge':True, 'invocation':None}
                response = page.request.post(address+'/api/action', data=data,
                                             headers={'Origin':address, 'X-Symphony-CSRF':state['csrf_token']})
                assert response.status == 409
                assert len(manager.children) == 2
                duplicate_status = response.status
                beta.get_by_role('button', name='Stop', exact=True).click()
                page.wait_for_function("() => document.body.textContent.includes('Process: stopped')")
                assert len(manager.children) == 1 and keys[0] in manager.children
                page.screenshot(path=str(output/'stopped.png'), full_page=True)
                manager.fail.add(keys[1])
                beta.get_by_role('button', name='Start', exact=True).click()
                page.wait_for_function("() => document.body.textContent.includes('fixture setup issue must be Done')")
                assert len(manager.children) == 1
                page.screenshot(path=str(output/'readiness-failure.png'), full_page=True)
                manager.fail.clear()
                beta.get_by_role('button', name='Start', exact=True).click()
                page.wait_for_function("() => [...document.querySelectorAll('.controls strong')].filter(n => n.textContent === 'Process: running/active').length === 2")
                page.screenshot(path=str(output/'recovered.png'), full_page=True)
                second = browser.new_page()
                second.goto(address)
                second.wait_for_function("() => document.querySelectorAll('.instance').length === 2")
                page.close()
                second.reload()
                assert len(manager.children) == 2
                browser.close()
            assert not errors, errors
            (output/'results.json').write_text(json.dumps({'passed':True, 'manager':'deterministic fixture, not systemd',
                'real_fake_processes':2, 'duplicate_start_http_status':duplicate_status,
                'checks':['stopped and running repositories','explicit Start','explicit Stop isolates repository',
                          'duplicate refusal','readiness failure starts no process','recovery','multiple tabs and browser closure'],
                'browser_errors':errors, 'limitation':'Real user-manager/cgroup tests remain blocked by user-bus access'}, indent=2)+'\n')
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()
            m.close()
            for key in list(manager.children):
                manager.stop(key)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--fixture-port', type=int)
    args = parser.parse_args()
    if args.fixture_port:
        fixture(args.fixture_port)
    elif args.output:
        (ROOT / '.symphony').mkdir(exist_ok=True)
        main(args.output.resolve())
    else:
        parser.error('--output is required')
