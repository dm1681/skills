from __future__ import annotations

import contextlib
import io
import json
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install
import skills_cli
import symphony_identity as identity
import symphony_project as project


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.token = secrets.token_hex(24)
        self.config = dict(project_dir=str(self.root), repo_url='git@github-work:team/repo.git',
                           github_repo='team/repo', github_account='worker-account',
                           credential_provider=str(self.root / 'provider'),
                           git_author_name='Worker', git_author_email='worker@example.invalid')

    def response(self, stdout='', code=0):
        return subprocess.CompletedProcess([], code, stdout, self.token)

    def test_projects_override_ambient_identity_without_mutating_parent(self):
        inherited = dict(os.environ, GH_TOKEN=self.token, GITHUB_TOKEN=self.token,
                         GH_HOST='other.example', GH_REPO='other/repo', GH_DEBUG='api',
                         GIT_AUTHOR_NAME='Other', GIT_COMMITTER_EMAIL='other@example.invalid',
                         GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='url.other.insteadOf',
                         GIT_CONFIG_VALUE_0='https://github.com', GIT_TRACE='1', LINEAR_API_KEY=self.token)
        before = dict(inherited)
        with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account\n')]) as run:
            env = identity.environment(self.config, inherited)
        self.assertEqual(inherited, before)
        self.assertEqual('team/repo', env['GH_REPO'])
        self.assertEqual('github.com', env['GH_HOST'])
        self.assertEqual(self.token, env['GH_TOKEN'])
        self.assertEqual('Worker', env['GIT_AUTHOR_NAME'])
        self.assertEqual('worker@example.invalid', env['GIT_COMMITTER_EMAIL'])
        for name in ('LINEAR_API_KEY', 'GITHUB_TOKEN', 'GH_DEBUG', 'GIT_TRACE'):
            self.assertNotIn(name, env)
        self.assertNotIn('GH_TOKEN', run.call_args_list[0].kwargs['env'])
        other = {**self.config, 'github_repo': 'second/repo', 'repo_url': 'git@second:second/repo.git',
                 'github_account': 'second', 'git_author_name': 'Second'}
        with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token[::-1]), self.response('second')]):
            second = identity.environment(other, inherited)
        self.assertEqual('second/repo', second['GH_REPO'])
        self.assertEqual('Second', second['GIT_AUTHOR_NAME'])
        self.assertEqual('team/repo', env['GH_REPO'])

    def test_ssh_alias_config_and_executable_are_quoted_and_provider_is_not_needed(self):
        ssh_config = self.root / 'SSH settings'
        ssh_config.write_text('Host work-alias\n  HostName github.com\n')
        config = {**self.config, 'ssh_host': 'work-alias', 'ssh_config': str(ssh_config),
                  'ssh_executable': '/mounted path/ssh.exe'}
        with mock.patch.object(identity.subprocess, 'run') as run:
            env = identity.environment(config, {'GIT_SSH_COMMAND': 'wrong', 'GIT_SSH': 'wrong'}, credentials=False)
        run.assert_not_called()
        self.assertEqual([' /mounted path/ssh.exe'.strip(), '-F', str(ssh_config), '-o', 'BatchMode=yes'], shlex.split(env['GIT_SSH_COMMAND']))
        self.assertNotIn('GIT_SSH', env)
        self.assertEqual('git@work-alias:team/repo.git', identity.clone_url(config))
        self.assertEqual('ssh', env['GIT_SSH_VARIANT'])

    def test_provider_errors_never_disclose_stdout_stderr_or_exception_details(self):
        failures = [self.response(self.token, 1), OSError(self.token),
                    subprocess.TimeoutExpired(self.token, 30, output=self.token, stderr=self.token),
                    self.response(''), self.response(self.token + '\nextra')]
        for failure in failures:
            with self.subTest(kind=type(failure).__name__):
                kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with mock.patch.object(identity.subprocess, 'run', **kwargs), self.assertRaises(install.InstallError) as caught:
                    identity.environment(self.config)
                self.assertNotIn(self.token, str(caught.exception))
                self.assertIn('provider', str(caught.exception).lower())

    def test_wrong_account_and_failed_api_refuse_launch(self):
        for result in [self.response('someone-else'), self.response(self.token, 1)]:
            with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), result]), self.assertRaises(install.InstallError) as caught:
                identity.environment(self.config)
            self.assertNotIn(self.token, str(caught.exception))

    def test_config_rejects_incomplete_mismatched_or_secret_bearing_settings(self):
        for changes in [dict(github_account=''), dict(credential_provider=''),
                        dict(github_repo='different/repo'), dict(credential_provider='relative'),
                        dict(git_author_email=''), dict(ssh_host='-oProxyCommand=bad'),
                        dict(ssh_config='relative'), dict(github_repo='team/repo?token=bad'),
                        dict(repo_url='https://user:' + self.token + '@github.com/team/repo.git'),
                        dict(git_author_name='bad\nname')]:
            with self.subTest(fields=list(changes)), self.assertRaises(install.InstallError) as caught:
                identity.validate({**self.config, **changes})
            self.assertNotIn(self.token, str(caught.exception))

    def test_separate_git_and_pr_checks_use_read_only_commands_and_safe_errors(self):
        with mock.patch.object(identity.subprocess, 'run', return_value=self.response()) as run:
            self.assertEqual([], identity.check_access(self.config, 'git'))
        self.assertEqual(1, run.call_count)
        self.assertEqual(['git', 'ls-remote', '--exit-code', '--', self.config['repo_url'], 'HEAD'], run.call_args.args[0])
        with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account'), self.response('true'), self.response('[]')]) as run:
            self.assertEqual([], identity.check_access(self.config, 'pr'))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn('repos/team/repo/pulls?per_page=1', commands[-1])
        self.assertFalse(any('push' in cmd or 'POST' in cmd or 'PATCH' in cmd for cmd in commands))
        with mock.patch.object(identity.subprocess, 'run', return_value=self.response(self.token, 1)):
            problems = identity.check_access(self.config, 'git')
        self.assertIn('SSH alias/config', problems[0])
        self.assertNotIn(self.token, str(problems))

    def test_repository_only_identity_cannot_fall_back_to_default_account(self):
        config = {'github_repo': 'team/repo', 'repo_url': 'git@work:team/repo.git'}
        with mock.patch.object(identity.subprocess, 'run') as run:
            with self.assertRaisesRegex(install.InstallError, 'requires github_repo, github_account and credential_provider'):
                identity.environment(config, {'GH_TOKEN': self.token})
        run.assert_not_called()

    def test_provider_keeps_bounded_timeout(self):
        with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account')]) as run:
            identity.environment(self.config)
        self.assertEqual([30, 30], [call.kwargs['timeout'] for call in run.call_args_list])

    def test_pr_permission_failure_and_missing_repo_are_actionable(self):
        with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account'), self.response('false')]):
            self.assertIn('push permission', identity.check_access(self.config, 'pr')[0])
        self.assertIn('github_repo', identity.check_access({'project_dir': str(self.root)}, 'pr')[0])

    def test_https_git_uses_runtime_provider_and_credential_helper(self):
        config = {**self.config, 'repo_url': 'https://github.com/team/repo.git'}
        with mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account'), self.response('ref')]) as run:
            self.assertEqual([], identity.check_access(config, 'git'))
        env = run.call_args.kwargs['env']
        self.assertEqual('!gh auth git-credential', env['GIT_CONFIG_VALUE_1'])
        self.assertNotIn(self.token, str(run.call_args.args))

    def test_authentication_ignores_unrelated_saved_github_accounts(self):
        config = {**self.config, 'codex': 'codex'}
        with mock.patch.object(project.shutil, 'which', return_value='/tool'), \
             mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account'), self.response()]) as run:
            self.assertEqual([], project.authentication_problems(config))
        self.assertEqual(['codex', 'login', 'status'], run.call_args.args[0])
        self.assertFalse(any(call.args[0][:3] == ['gh', 'auth', 'status'] for call in run.call_args_list))

    def test_setup_cli_persists_only_public_configuration_and_preserves_other_project(self):
        other = self.root / 'other'
        other.mkdir()
        project.setup(other, repo_url='git@elsewhere:other/repo.git')
        before = project.config_path(other).read_bytes()
        arguments = ['symphony', 'setup', '--project-dir', str(self.root), '--repo-url', self.config['repo_url']]
        for field in identity.FIELDS:
            if self.config.get(field):
                arguments += ['--' + field.replace('_', '-'), self.config[field]]
        with mock.patch.object(identity.subprocess, 'run', side_effect=AssertionError('setup resolved credentials')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, skills_cli.main(arguments))
        self.assertEqual(before, project.config_path(other).read_bytes())
        config = project.load(self.root)
        self.assertEqual('worker-account', config['github_account'])
        for path in (self.root / '.symphony').iterdir():
            self.assertNotIn(self.token, path.read_text())
        with mock.patch.object(identity, 'check_access', return_value=['safe failure']) as check, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(3, skills_cli.main(['symphony', 'check-pr', '--project-dir', str(self.root)]))
        self.assertEqual('pr', check.call_args.args[1])
        self.assertIn('safe failure', output.getvalue())

    def test_worker_launch_receives_scoped_identity_without_writing_it(self):
        config = project.setup(self.root, **{key: value for key, value in self.config.items() if key != 'project_dir'})
        worker = Path(config['workspace_root']) / 'DIE-123'
        worker.mkdir(parents=True)
        marker = worker / '.symphony-worker.json'
        marker.write_text(json.dumps(dict(kind='symphony', project_dir=str(self.root))))
        before = marker.read_bytes()
        with mock.patch.object(Path, 'cwd', return_value=worker), mock.patch.object(project, 'worker_overrides', return_value=[]), \
             mock.patch.object(identity.subprocess, 'run', side_effect=[self.response(self.token), self.response('worker-account')]), \
             mock.patch.object(project.symphony_worker, 'run_server', return_value=0) as server, self.assertRaises(SystemExit):
            project.run_worker(self.root)
        env = server.call_args.args[-1]
        self.assertEqual(self.token, env['GH_TOKEN'])
        self.assertEqual('team/repo', env['GH_REPO'])
        self.assertEqual('symphony', env['SKILLS_SESSION_KIND'])
        self.assertEqual(before, marker.read_bytes())

    def test_local_clone_commit_push_preserves_global_author_and_config(self):
        source = self.root / 'source'
        source.mkdir()
        home_config = self.root / 'global-git-config'
        home_config.write_text('[user]\n name = Personal\n email = personal@example.invalid\n')
        inherited = dict(os.environ, GIT_CONFIG_GLOBAL=str(home_config), GIT_CONFIG_NOSYSTEM='1')
        # Explicit author environment overrides global config without changing it.
        git = lambda cwd, *args, env=inherited: subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True, text=True)
        git(source, 'init', '--quiet', '--template=', '--initial-branch=main')
        git(source, '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-m', 'source')
        public = dict(repo_url=str(source), git_author_name='Worker', git_author_email='worker@example.invalid', validation_command='python -m unittest')
        config = project.setup(self.root, **public)
        worker = Path(config['workspace_root']) / 'DIE-123'
        worker.mkdir(parents=True)
        before = home_config.read_bytes()
        with mock.patch.dict(os.environ, inherited, clear=True), mock.patch.object(Path, 'cwd', return_value=worker), \
             mock.patch.object(identity.subprocess, 'run', wraps=subprocess.run) as commands:
            project.prepare_workspace(self.root)
        provisioning = [call for call in commands.call_args_list if call.args[0][:2] in (['git', 'clone'], ['git', 'checkout'])]
        self.assertEqual(2, len(provisioning))
        self.assertTrue(all(call.kwargs['timeout'] is None for call in provisioning))
        env = identity.environment(config, inherited)
        git(worker, '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-m', 'worker', env=env)
        git(worker, '-c', 'core.hooksPath=/dev/null', 'push', 'origin', 'HEAD:refs/heads/test-worker', env=env)
        actual = git(source, 'log', '-1', '--format=%an <%ae>|%cn <%ce>', 'test-worker').stdout.strip()
        self.assertEqual('Worker <worker@example.invalid>|Worker <worker@example.invalid>', actual)
        self.assertEqual(before, home_config.read_bytes())
        self.assertEqual('Personal', git(source, 'config', 'user.name').stdout.strip())
        self.assertNotIn(self.token, (worker / '.git/config').read_text())

    @unittest.skipIf(os.name == 'nt', 'POSIX runtime provider executable contract')
    def test_real_provider_and_fake_github_complete_pr_check_without_persisting_token(self):
        provider = Path(self.config['credential_provider'])
        provider.write_text('#!' + sys.executable + '\nimport os\nprint(os.environ["TEST_SENTINEL"])\n')
        provider.chmod(0o700)
        gh = self.root / 'gh'
        gh.write_text('#!' + sys.executable + '\nimport os, sys\nassert os.environ["GH_TOKEN"] == os.environ["TEST_SENTINEL"]\nassert os.environ["GH_REPO"] == "team/repo"\nprint("worker-account" if "user" in sys.argv else "true" if ".permissions.push" in sys.argv else "[]")\n')
        gh.chmod(0o700)
        with mock.patch.dict(os.environ, {'PATH': str(self.root) + os.pathsep + os.environ['PATH'], 'TEST_SENTINEL': self.token}):
            self.assertEqual([], identity.check_access(self.config, 'pr'))
        for path in self.root.iterdir():
            self.assertNotIn(self.token, path.read_text())

    @unittest.skipIf(os.name == 'nt', 'POSIX runtime provider executable contract')
    def test_real_runtime_provider_failure_output_is_suppressed(self):
        provider = Path(self.config['credential_provider'])
        # The random sentinel exists only in the subprocess environment, not the fixture.
        provider.write_text('#!' + sys.executable + '\nimport os, sys\nprint(os.environ["TEST_SENTINEL"])\nprint(os.environ["TEST_SENTINEL"], file=sys.stderr)\nsys.exit(7)\n')
        provider.chmod(0o700)
        with self.assertRaises(install.InstallError) as caught:
            identity.environment(self.config, {**os.environ, 'TEST_SENTINEL': self.token})
        self.assertNotIn(self.token, str(caught.exception))
        self.assertNotIn(self.token, provider.read_text())


if __name__ == '__main__':
    unittest.main()
