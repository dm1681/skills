"""Lifecycle contract tests. No real service manager or production tracker writes."""
from concurrent.futures import ProcessPoolExecutor
import contextlib
import io
import json
import os
from pathlib import Path
import socket
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
import symphony_lifecycle as lifecycle
import symphony_monitor as monitor
import symphony_project as project
import symphony_registry as registry


class FakeManager:
    """Disk-backed manager fixture shared by independent test processes.

Does not claim to test systemd itself; unit property assertions separately pin
that adapter. The fixture only ever signals its explicitly created children.
"""
    def __init__(self, root):
        self.root = Path(root)

    def path(self, key):
        return self.root / ('unit-' + key + '.json')

    def show(self, key):
        try:
            return json.loads(self.path(key).read_text())
        except FileNotFoundError:
            return {}

    def launch(self, key, config, env):
        with registry.locked(self.path(key)):
            if lifecycle.busy(self.show(key)):
                raise project.Error('Existing fixture unit')
            invocation = os.urandom(16).hex()
            value = {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
                     'Description': 'Skills Symphony ' + key, 'Transient': 'yes',
                     'InvocationID': invocation, 'ExitType': 'cgroup', 'KillMode': 'control-group',
                     'Restart': 'no', 'SendSIGKILL': 'no', 'TimeoutStopUSec': 'infinity'}
            self.path(key).write_text(json.dumps(value))
            with (self.root / 'launches').open('a') as stream:
                stream.write(key + '\n')
            lifecycle.write(key, {'phase': 'running', 'invocation': invocation,
                                  'readiness': 'Passed fixture readiness'})

    def stop(self, key):
        value = self.show(key)
        value['ActiveState'] = 'deactivating'
        self.path(key).write_text(json.dumps(value))

    def finish(self, key):
        self.path(key).unlink()


def concurrent_start(args):
    config, root, registry_file, kind = args
    manager = FakeManager(root)
    try:
        if kind == 'ui':
            item = registry.read(Path(registry_file))[0]
            lifecycle.Control(Path(registry_file), manager=manager).action({
                'action': 'start', 'id': item['id'], 'repository_id': lifecycle.repository_identity(config),
                'acknowledge': True, 'invocation': None})
        else:
            with mock.patch.object(lifecycle, 'Manager', return_value=manager):
                project.start(Path(config['project_dir']), accept_preview=True)
        return 'started'
    except project.Error:
        return 'refused'


@unittest.skipUnless(sys.platform == 'linux', 'Linux user-service lifecycle')
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / 'registry.json'
        self.patch = mock.patch.dict(os.environ, {'SKILLS_SYMPHONY_STATE': str(self.root / 'state'),
                                                'SKILLS_SYMPHONY_REGISTRY': str(self.registry), 'INVOCATION_ID': ''})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.directory = self.root / 'repo'
        self.directory.mkdir()
        self.config = project.setup(self.directory, repo_url='https://github.com/Owner/Example.git',
                                    project_id='fixture', project_slug='fixture', setup_issue='DIE-1',
                                    validation_command='true', dashboard_enabled=False)
        self.manager = FakeManager(self.root)
        self.key = lifecycle.repository_identity(self.config)

    def item(self):
        return registry.register_config(self.config, managed=True)

    def test_identity_alias_worktree_duplicate_checkout_and_independent_repo(self):
        same = [dict(self.config, project_dir=str(self.root / 'duplicate')),
                dict(self.config, repo_url='git@work:Owner/Example.git', repository_host='github.com'),
                dict(self.config, repo_url='ssh://git@github.com/owner/example'),
                dict(self.config, repo_url='https://github.com/owner/example')]
        for config in same:
            self.assertEqual(self.key, lifecycle.repository_identity(config))
        self.assertNotEqual(self.key, lifecycle.repository_identity(dict(self.config, repo_url='https://github.com/owner/other')))
        self.assertNotEqual(self.key, lifecycle.repository_identity(dict(self.config, repo_url='git@unknown:Owner/Example.git')))
        subprocess.run(['git', 'init', '-q', '--template=', str(self.directory)], check=True)
        subprocess.run(['git', '-C', str(self.directory), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)
        worktree = self.root / 'worktree'
        subprocess.run(['git', '-C', str(self.directory), 'worktree', 'add', '--detach', '-q', str(worktree)], check=True)
        alias = self.root / 'alias'
        alias.symlink_to(self.directory, target_is_directory=True)
        key = lifecycle.repository_identity(dict(self.config, repo_url=''))
        for directory in (worktree, alias):
            self.assertEqual(key, lifecycle.repository_identity(dict(self.config, repo_url='', project_dir=str(directory))))
        for url in ['https://token@github.com/owner/repo', 'https://github.com/owner/repo?secret=x', 'ssh://git@github.com:22/owner/repo', 'https://github.com/../repo']:
            with self.assertRaises(project.Error):
                lifecycle.repository_identity(dict(self.config, repo_url=url))

    def test_parallel_ui_ui_cli_cli_and_mixed_starts(self):
        self.item()
        for kinds in (['ui']*8, ['cli']*8, ['ui', 'cli']*4):
            with ProcessPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(concurrent_start, [(self.config, str(self.root), str(self.registry), k) for k in kinds]))
            self.assertEqual(results.count('started'), 1, results)
            self.assertEqual(len((self.root / 'launches').read_text().splitlines()), 1)
            self.manager.finish(self.key)
            lifecycle.write(self.key, {'phase': 'stopped'})
            (self.root / 'launches').unlink()

    def test_shutdown_reserves_identity_and_does_not_touch_other_repository(self):
        other = dict(self.config, repo_url='https://github.com/owner/other')
        other_key = lifecycle.start(other, accept_preview=True, manager=self.manager)
        lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        invocation = lifecycle.read(self.key)['invocation']
        lifecycle.stop(self.config, invocation=invocation, manager=self.manager)
        value = lifecycle.read(self.key)
        value['stop_at'] = time.time()-40
        lifecycle.write(self.key, value)
        state = lifecycle.describe(self.config, manager=self.manager)
        self.assertEqual(state['state'], 'stopping')
        self.assertIn('30 seconds', state['error'])
        self.assertFalse(state['can_start'])
        with self.assertRaises(project.Error):
            lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        self.assertEqual(self.manager.show(other_key)['ActiveState'], 'active')
        self.manager.finish(self.key)
        lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        with self.assertRaisesRegex(project.Error, 'changed'):
            lifecycle.stop(self.config, invocation=invocation, manager=self.manager)

    def test_http_failure_and_monitor_restart_do_not_release_ownership(self):
        self.item()
        lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        for _ in range(2):
            control = lifecycle.Control(self.registry, manager=self.manager)
            item = registry.read(self.registry)[0]
            control.observe(item)
            state = control.snapshot(dict(item, health='unreachable'))
            self.assertEqual(state['state'], 'running/unknown')
            self.assertFalse(state['can_start'])
            self.assertTrue(state['can_stop'])

    def test_unmanaged_import_blocks_even_without_http_and_has_no_stop(self):
        registry.register_config(self.config)
        lifecycle.reconcile_imports(self.config)
        with self.assertRaisesRegex(project.Error, 'reserved'):
            lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        self.assertFalse(lifecycle.describe(self.config, manager=self.manager)['can_stop'])
        lifecycle.confirm_stopped(self.config, manager=self.manager)
        self.assertTrue(lifecycle.describe(self.config, manager=self.manager)['can_start'])

    def test_pid_reuse_and_forged_unit_properties_never_authorize_stop(self):
        lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        invocation = lifecycle.read(self.key)['invocation']
        for field, forged in [('InvocationID', 'reused'), ('Transient', 'no'), ('KillMode', 'process'),
                              ('Restart', 'always'), ('Description', 'unrelated'), ('ExitType', 'main')]:
            original = self.manager.show(self.key)
            self.manager.path(self.key).write_text(json.dumps(dict(original, **{field: forged})))
            self.assertFalse(lifecycle.describe(self.config, manager=self.manager)['can_stop'])
            with self.assertRaises(project.Error):
                lifecycle.stop(self.config, invocation=invocation, manager=self.manager)
            self.manager.path(self.key).write_text(json.dumps(original))

    def test_crashed_main_process_keeps_descendants_reserved(self):
        lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        value = self.manager.show(self.key)
        value['MainPID'] = '0'
        self.manager.path(self.key).write_text(json.dumps(value))
        status = lifecycle.describe(self.config, manager=self.manager)
        self.assertEqual(status['state'], 'failed')
        self.assertFalse(status['can_start'])
        self.assertTrue(status['can_stop'])
        self.assertIn('descendants', status['error'])

    def test_crash_failed_creation_stale_metadata_port_conflict_and_missing_bus(self):
        self.item()
        lifecycle.write(self.key, {'phase': 'running', 'invocation': 'old'})
        self.assertEqual(lifecycle.describe(self.config, manager=self.manager)['state'], 'failed')
        self.assertTrue(lifecycle.describe(self.config, manager=self.manager)['can_start'])
        with mock.patch.object(self.manager, 'launch', side_effect=lifecycle.LaunchFailed('failed')):
            with self.assertRaises(project.Error):
                lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        self.assertEqual(lifecycle.read(self.key)['phase'], 'failed')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            config = dict(self.config, dashboard_port=sock.getsockname()[1])
            with self.assertRaisesRegex(project.Error, 'occupied'):
                lifecycle.start(config, accept_preview=True, manager=self.manager)
        with mock.patch.object(self.manager, 'show', side_effect=project.Error('No bus')):
            with self.assertRaises(project.Error):
                lifecycle.start(self.config, accept_preview=True, manager=self.manager)
        self.assertFalse((self.root / 'launches').exists())

    def test_registration_changes_are_observed_without_dashboard_restart(self):
        item = registry.register_config(self.config)
        control = lifecycle.Control(self.registry, manager=self.manager)
        m = monitor.Monitor(self.registry, interval=1, control=control)
        m.start()
        self.addCleanup(m.close)
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            if m.snapshot()['instances'] and m.snapshot()['instances'][0]['lifecycle'].get('error'):
                break
            time.sleep(.02)
        self.assertFalse(m.snapshot()['instances'][0]['lifecycle']['can_start'])
        self.item()
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            if m.snapshot()['instances'][0]['lifecycle']['can_start']:
                break
            time.sleep(.02)
        self.assertTrue(m.snapshot()['instances'][0]['lifecycle']['can_start'])

    def test_automatic_service_wrapper_is_refused(self):
        with mock.patch.dict(os.environ, {'INVOCATION_ID': 'wrapper'}), mock.patch.object(Path, 'read_text', return_value='0::/user.slice/legacy.service'), mock.patch.object(subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'Restart=always\nInvocationID=wrapper\n', '')
            with self.assertRaisesRegex(project.Error, 'Restart=no'):
                lifecycle.check_service_wrapper()
            run.return_value = subprocess.CompletedProcess([], 0, 'Restart=no\nInvocationID=wrapper\n', '')
            lifecycle.check_service_wrapper()

    def test_private_entry_cannot_bypass_service_ownership(self):
        with mock.patch.object(lifecycle.Manager, 'show', return_value={}), mock.patch.dict(os.environ, {'INVOCATION_ID': ''}), mock.patch.object(project, 'check') as check:
            self.assertEqual(lifecycle.service(self.key, str(self.directory), str(lifecycle.state_root())), 2)
            check.assert_not_called()

    def service_context(self, env=None):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        env = dict(os.environ, **(env or {}))
        group = Path('/proc/self/cgroup').read_text().strip().split('::')[-1]
        stack.enter_context(mock.patch.dict(os.environ, {'INVOCATION_ID': 'fixture'}))
        stack.enter_context(mock.patch.object(lifecycle.Manager, 'show', return_value={
            'InvocationID': 'fixture', 'Description': 'Skills Symphony '+self.key, 'ControlGroup': group}))
        stdin = io.TextIOWrapper(io.BytesIO((json.dumps(env)+'\n').encode()))
        stack.enter_context(mock.patch.object(sys, 'stdin', stdin))
        return stack

    def test_readiness_failure_rechecks_and_redacts_secrets_without_launch(self):
        self.service_context({'LINEAR_API_KEY': 'PRIVATE_SECRET'})
        with mock.patch.object(project, 'check', return_value=['Setup issue must be Done; PRIVATE_SECRET']) as check, mock.patch.object(subprocess, 'Popen') as spawn:
            self.assertEqual(lifecycle.service(self.key, str(self.directory), str(lifecycle.state_root())), 2)
            check.assert_called_once_with(self.directory)
            spawn.assert_not_called()
        text = lifecycle.state_path(self.key).read_text()
        self.assertIn('Setup issue must be Done', text)
        self.assertNotIn('PRIVATE_SECRET', text)
        self.assertEqual(lifecycle.read(self.key)['phase'], 'failed')

    def test_service_preserves_runtime_arguments_and_records_exit_failure(self):
        self.service_context()
        child = mock.Mock()
        child.wait.return_value = 17
        with mock.patch.object(project, 'check', return_value=[]), mock.patch.object(project, 'runtime_binary', return_value=Path('/fixture/runtime')), mock.patch.object(subprocess, 'Popen', return_value=child) as spawn:
            self.assertEqual(lifecycle.service(self.key, str(self.directory), str(lifecycle.state_root())), 2)
            spawn.assert_called_once_with(['/fixture/runtime', project.PREVIEW_FLAG, str(self.directory / '.symphony/WORKFLOW.md')])
        self.assertEqual(lifecycle.read(self.key)['phase'], 'failed')

    def test_manager_launch_contract_no_secrets_in_argv_or_logs(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        with mock.patch.object(subprocess, 'Popen', return_value=proc) as spawn, mock.patch.object(lifecycle.Manager, 'show', return_value={'InvocationID': 'new'}):
            lifecycle.Manager().launch(self.key, self.config, {'LINEAR_API_KEY': 'PRIVATE_SECRET'})
        command = spawn.call_args.args[0]
        for flag in ['--property=ExitType=cgroup', '--property=KillMode=control-group', '--property=SendSIGKILL=no', '--property=TimeoutStopSec=infinity', '--property=Restart=no']:
            self.assertIn(flag, command)
        self.assertNotIn('PRIVATE_SECRET', repr(spawn.call_args))
        self.assertIn(b'PRIVATE_SECRET', proc.stdin.write.call_args.args[0])
        self.assertEqual(spawn.call_args.kwargs['stderr'], subprocess.DEVNULL)
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])

    def test_forgery_validation_and_passive_http_never_launch(self):
        item = self.item()
        control = lifecycle.Control(self.registry, manager=self.manager)
        m = monitor.Monitor(self.registry, interval=1, control=control)
        m.entries = [item]
        control.observe(item)
        server = dashboard.server(m, 0, control)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        token = json.load(urllib.request.urlopen(url+'/api/state'))['csrf_token']
        data = {'id': item['id'], 'repository_id': self.key, 'action': 'start', 'acknowledge': True, 'invocation': None}
        headers = {'Origin': url, 'Content-Type': 'application/json', 'X-Symphony-CSRF': token}
        invalid_headers = [dict(headers, Origin='http://evil.example'), dict(headers, Host='evil.example'),
                           dict(headers, **{'X-Symphony-CSRF': 'forged'}),
                           dict(headers, **{'Sec-Fetch-Site': 'cross-site'}),
                           {k:v for k,v in headers.items() if k != 'Origin'}]
        for forged in invalid_headers:
            request = urllib.request.Request(url+'/api/action', data=json.dumps(data).encode(), headers=forged)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
        for extra in [{'pid': os.getpid()}, {'command': 'PRIVATE_SECRET'}, {'project_path': '/'}, {'id':'../../elsewhere'}, {'repository_id':'0'*64}, {'acknowledge':False}]:
            request = urllib.request.Request(url+'/api/action', data=json.dumps(dict(data, **extra)).encode(), headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 409)
            self.assertNotIn(b'PRIVATE_SECRET', error.exception.read())
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(url+'/api/action')
        self.assertFalse((self.root / 'launches').exists())
        request = urllib.request.Request(url+'/api/action', data=json.dumps(data).encode(), headers=headers)
        self.assertEqual(urllib.request.urlopen(request).status, 202)
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(len((self.root / 'launches').read_text().splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
