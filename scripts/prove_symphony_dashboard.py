#!/usr/bin/env python3
"""Synthetic browser acceptance proof. Requires an existing Playwright installation."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_symphony_monitor import Fixture
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixtures = [Fixture(), Fixture()]
    processes = []
    try:
        with tempfile.TemporaryDirectory(dir=ROOT / '.symphony') as temporary:
            env = {**os.environ, 'SKILLS_SYMPHONY_REGISTRY': str(Path(temporary) / 'registry.json')}
            base = [sys.executable, str(ROOT / 'skills_cli.py'), 'symphony']
            for index, fixture in enumerate(fixtures):
                fixture.payload['generated_at'] = datetime.now(timezone.utc).isoformat()
                fixture.payload['running'][0]['started_at'] = datetime.now(timezone.utc).isoformat()
                fixture.payload['running'][0]['last_event_at'] = datetime.now(timezone.utc).isoformat()
                fixture.payload['running'][0]['session_id'] = f'fixture-session-{index}'
                name = ['Alpha', 'Beta <script>window.PWNED=1</script>'][index]
                command = base + ['register', '--project-dir', temporary+f'/project-{index}', '--endpoint', fixture.url, '--name', name]
                subprocess.run(command, cwd=temporary, env=env, check=True, capture_output=True)
                subprocess.run(command, cwd=temporary, env=env, check=True, capture_output=True)
            subprocess.run(base+['register', '--project-dir', temporary+'/disabled', '--disabled'], cwd=temporary, env=env, check=True, capture_output=True)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            proc = subprocess.Popen(base+['dashboard', '--port', str(port), '--refresh', '1', '--timeout', '.2'], cwd=temporary, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append(proc)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width':1440,'height':1100})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                address=f'http://127.0.0.1:{port}'
                for attempt in range(50):
                    try:
                        page.goto(address)
                        break
                    except Exception:
                        time.sleep(.1)
                page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 4")
                assert page.locator('.instance').count()==3
                assert page.locator('.metric strong').nth(0).inner_text()=='2'
                assert page.locator('a[href^="https://linear.app/"]').count()==2
                assert page.evaluate('window.PWNED') is None
                response=page.request.get(address+'/api/state').text()
                assert 'PRIVATE_' not in response
                page.screenshot(path=str(output/'overview.png'), full_page=True)
                page.select_option('#project', temporary+'/project-0')
                page.wait_for_function("() => document.querySelectorAll('.instance').length === 1")
                page.select_option('#status', 'retrying')
                assert page.locator('tbody tr').count()==1
                page.screenshot(path=str(output/'filtered.png'), full_page=True)
                page.select_option('#project', '')
                page.select_option('#status', '')
                fixtures[1].code=503
                page.wait_for_function("() => document.querySelector('.badge.unreachable') !== null")
                assert page.locator('.metric strong').nth(0).inner_text()=='1'
                page.screenshot(path=str(output/'offline.png'), full_page=True)
                fixtures[1].code=200
                fixtures[1].payload=b'not-json'
                page.wait_for_function("() => document.querySelector('.badge.incompatible') !== null")
                page.screenshot(path=str(output/'incompatible.png'), full_page=True)
                fixtures[1].payload=json.loads(json.dumps(fixtures[0].payload))
                for fixture in fixtures:
                    fixture.payload['generated_at']=datetime.now(timezone.utc).isoformat()
                page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 4")
                page.screenshot(path=str(output/'recovered.png'), full_page=True)
                Path(env['SKILLS_SYMPHONY_REGISTRY']).write_text(json.dumps({'schema':1,'instances':[]}))
                page.wait_for_function("() => document.querySelector('#instances').textContent.includes('No registered instances')")
                page.screenshot(path=str(output/'empty.png'), full_page=True)
                assert not errors, errors
                browser.close()
            requests = [request for fixture in fixtures for request in fixture.requests]
            assert requests and all(tuple(request)==('GET','/api/v1/state') for request in requests)
            (output/'results.json').write_text(json.dumps({'passed':True,'instances':2,'shared_issue':'DIE-123', 'duplicate_counting':False,'checks':['outside-project launch','project/status filters','Linear/source links','escaping','private text excluded','disabled','offline','incompatible','recovery','empty','GET state only'], 'browser_errors':errors,'fixture_requests':len(requests)},indent=2)+'\n')
    finally:
        for proc in processes:
            proc.terminate()
            proc.wait(timeout=5)
        for fixture in fixtures:
            fixture.close()


if __name__=='__main__':
    main()
