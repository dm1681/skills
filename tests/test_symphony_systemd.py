"""Opt-in real cgroup proof, containing only generated fake runtime/worker processes.

SKILLS_SYMPHONY_SYSTEMD_TEST=1 uv run python -m unittest discover -s tests -p test_symphony_systemd.py -v
Never operates an existing unit or an actual Symphony/Codex runtime.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

import symphony_lifecycle as lifecycle
import symphony_project as project

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('SKILLS_SYMPHONY_SYSTEMD_TEST') == '1',
                     'requires explicit isolated systemd user-manager rehearsal')
class RealManagerTests(unittest.TestCase):
    def wait_for(self, predicate):
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.05)
        self.fail('Timed out waiting for fake unit lifecycle')

    def test_atomic_launch_parent_crash_scoped_stop_and_stuck_descendant(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.dict(os.environ, {'SKILLS_SYMPHONY_STATE': str(root/'state')}):
                config = project.setup(root, repo_url='https://github.com/fixture/'+uuid.uuid4().hex,
                                       project_id='fake', project_slug='fake', setup_issue='FAKE-1',
                                       validation_command='true', dashboard_enabled=False)
                fake = root/'fake-runtime'
                fake.write_text('#!'+sys.executable+'\n' + '''import json, os, pathlib, signal, subprocess, sys, time
root = pathlib.Path.cwd()
child = subprocess.Popen([sys.executable, '-c', "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)" if (root/'stuck').exists() else 'import time; time.sleep(300)'])
(root/'pids.json').write_text(json.dumps([os.getpid(), child.pid]))
while True: time.sleep(1)
''')
                fake.chmod(0o700)
                key = lifecycle.repository_identity(config)
                manager = lifecycle.Manager()
                # Fails, rather than silently skips, when explicitly requested but
                # unavailable. No unit mutation has occurred at this point.
                manager.show(key)
                unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])
                try:
                    with mock.patch.object(lifecycle, '__file__', str(ROOT/'tests/fixtures/symphony/managed_fake.py')):
                        def launch(_):
                            try:
                                lifecycle.start(config, accept_preview=True)
                                return True
                            except project.Error:
                                return False
                        with ThreadPoolExecutor(max_workers=8) as pool:
                            self.assertEqual(sum(pool.map(launch, range(8))), 1)
                    self.wait_for(lambda: (root/'pids.json').exists())
                    self.assertTrue(lifecycle.describe(config)['can_stop'])
                    # Kill only this test unit's helper; fake runtime/worker remain
                    # in its cgroup, proving the parent-lifetime boundary.
                    subprocess.run(['systemctl', '--user', 'kill', '--kill-whom=main', '--signal=SIGKILL', lifecycle.unit(key)], check=True, capture_output=True)
                    time.sleep(.2)
                    self.assertFalse(lifecycle.describe(config)['can_start'])
                    lifecycle.stop(config, invocation=lifecycle.read(key)['invocation'])
                    self.wait_for(lambda: not lifecycle.busy(manager.show(key)))
                    self.assertIsNone(unrelated.poll())
                    (root/'pids.json').unlink()
                    (root/'stuck').touch()
                    with mock.patch.object(lifecycle, '__file__', str(ROOT/'tests/fixtures/symphony/managed_fake.py')):
                        lifecycle.start(config, accept_preview=True)
                    self.wait_for(lambda: (root/'pids.json').exists())
                    time.sleep(.2)  # Child installs the fixture-only SIGTERM handler.
                    lifecycle.stop(config, invocation=lifecycle.read(key)['invocation'])
                    self.wait_for(lambda: manager.show(key).get('ActiveState') == 'deactivating')
                    self.assertFalse(lifecycle.describe(config)['can_start'])
                    self.assertIsNone(unrelated.poll())
                finally:
                    # Explicit test teardown, scoped to the unique fixture unit.
                    # Production Stop never escalates to SIGKILL.
                    if lifecycle.busy(manager.show(key)):
                        subprocess.run(['systemctl', '--user', 'kill', '--kill-whom=all', '--signal=SIGKILL', lifecycle.unit(key)], check=True, capture_output=True)
                        self.wait_for(lambda: not lifecycle.busy(manager.show(key)))
                    unrelated.terminate()
                    unrelated.wait(timeout=5)
