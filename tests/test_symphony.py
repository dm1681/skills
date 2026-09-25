from __future__ import annotations

import contextlib
import io
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install
import skills_cli
import symphony_project as symphony


class SymphonyTests(unittest.TestCase):
    def setUp(self):
        self.probe = mock.patch.object(symphony, "probe_worker", return_value=[])
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.auth = mock.patch.object(symphony, "authentication_problems", return_value=[])
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry_env = mock.patch.dict(os.environ, {"SKILLS_SYMPHONY_REGISTRY": str(Path(self.temp.name) / "registry.json")})
        self.registry_env.start()
        self.addCleanup(self.registry_env.stop)
        self.project = Path(self.temp.name) / 'project with spaces'
        self.project.mkdir()
        subprocess.run(['git', 'init', '--quiet', '--template='], cwd=self.project, check=True)
        self.config = symphony.setup(self.project, project_id='project-uuid', project_slug='project-slug', setup_issue='DIE-100', repo_url='git@github-dm1681:dm1681/example.git', validation_command='python3 -m unittest')

    def response(self, state='Done', kind='completed', project='project-uuid'):
        return {'issue': {'id': 'issue-uuid', 'identifier': 'DIE-100', 'state': {'name': state, 'type': kind}, 'project': {'id': project, 'slugId': 'project-slug'}, 'team': {'states': {'nodes': [{'name': n} for n in ['Backlog', 'Todo', 'In Progress', 'Human Review', 'Merging', 'Rework', 'Done']]}}}}

    def test_setup_is_idempotent_and_never_starts_process_or_tracker(self):
        paths = list((self.project / '.symphony').iterdir())
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        with mock.patch.object(symphony, 'linear_gate', side_effect=AssertionError('setup queried tracker')), mock.patch.object(os, 'execv', side_effect=AssertionError('setup dispatched')):
            symphony.setup(self.project)
        self.assertEqual(before[paths[0]][0], paths[0].read_bytes())
        workflow = self.project / '.symphony/WORKFLOW.md'
        self.assertEqual(before[workflow], (workflow.read_bytes(), workflow.stat().st_mtime_ns))

    def test_managed_workflow_hash_survives_host_newline_translation(self):
        real_open = Path.open
        def windows_text_open(path, mode='r', *args, **kwargs):
            if 'b' not in mode and any(flag in mode for flag in ('w', 'x')):
                kwargs.setdefault('newline', '\r\n')
            return real_open(path, mode, *args, **kwargs)
        workflow = self.project / 'managed.md'
        with mock.patch.object(Path, 'open', windows_text_open):
            digest = symphony.write_managed(workflow, 'first\nsecond\n')
            self.assertEqual(hashlib.sha256(workflow.read_bytes()).hexdigest(), digest)
            self.assertEqual(digest, symphony.write_managed(workflow, 'first\nsecond\n', digest))
            updated = symphony.write_managed(workflow, 'changed\n', digest)
        self.assertEqual(hashlib.sha256(workflow.read_bytes()).hexdigest(), updated)

    def test_user_edited_workflow_is_preserved_on_setup(self):
        workflow = self.project / '.symphony/WORKFLOW.md'
        workflow.write_text('user work')
        before = symphony.config_path(self.project).read_bytes()
        with self.assertRaisesRegex(install.InstallError, 'Preserving edited file'):
            symphony.setup(self.project, dashboard_port=9999)
        self.assertEqual('user work', workflow.read_text())
        self.assertEqual(before, symphony.config_path(self.project).read_bytes())

    def test_configuration_update_preserves_project_identity_and_can_disable_dashboard(self):
        updated = symphony.setup(self.project, dashboard_enabled=False)
        self.assertIsNone(updated['dashboard_port'])
        self.assertEqual('DIE-100', updated['setup_issue'])
        updated = symphony.setup(self.project, dashboard_port=12345)
        workflow = (self.project / '.symphony/WORKFLOW.md').read_text().split('---')[1]
        server = json.loads(workflow)['server']
        self.assertEqual({'host': '127.0.0.1', 'port': 12345}, server)

    def test_gate_accepts_exact_done_issue_in_exact_project(self):
        issue = symphony.linear_gate(self.config, lambda *_: self.response())
        self.assertEqual('issue-uuid', issue['id'])

    def test_gate_rejects_canceled_incomplete_wrong_project_and_unverifiable(self):
        responses = [self.response('Canceled', 'canceled'), self.response('Todo', 'unstarted'), self.response(project='other-project'), {'issue': None}, {}, self.response('Done', 'canceled')]
        for response in responses:
            with self.subTest(response=response), self.assertRaises(install.InstallError):
                symphony.linear_gate(self.config, lambda *_: response)
        changed_slug = self.response()
        changed_slug['issue']['project']['slugId'] = 'wrong'
        with self.assertRaises(install.InstallError):
            symphony.linear_gate(self.config, lambda *_: changed_slug)

    def test_gate_rejects_done_when_team_lifecycle_is_incomplete(self):
        response = self.response()
        response['issue']['team']['states']['nodes'] = [{'name': 'Done'}]
        with self.assertRaisesRegex(install.InstallError, 'missing Symphony states'):
            symphony.linear_gate(self.config, lambda *_: response)

    def test_missing_mapping_does_not_query_tracker(self):
        query = mock.Mock()
        with self.assertRaises(install.InstallError):
            symphony.linear_gate({**self.config, 'setup_issue': ''}, query)
        query.assert_not_called()

    def test_live_gate_transport_failure_is_closed(self):
        with mock.patch.dict(os.environ, {'LINEAR_API_KEY': 'test-secret'}), mock.patch('urllib.request.urlopen', side_effect=OSError('network failure')):
            with self.assertRaisesRegex(install.InstallError, 'no workers started'):
                symphony.linear_gate(self.config)
        self.assertNotIn('test-secret', symphony.config_path(self.project).read_text())

    def test_start_requires_preview_acknowledgement_and_uses_linear_app(self):
        with mock.patch('symphony_linear.run', return_value=0) as launch:
            with self.assertRaisesRegex(install.InstallError, 'accept-preview'):
                symphony.start(self.project)
            launch.assert_not_called()
            self.assertEqual(0, symphony.start(self.project, accept_preview=True))
            launch.assert_called_once_with(self.project, __import__('symphony_linear').DEFAULT_FILE, True)

    def test_online_cli_check_uses_linear_app(self):
        with mock.patch('symphony_linear.check_project', return_value=[]) as check, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, skills_cli.main(['symphony', 'check', '--project-dir', str(self.project)]))
        check.assert_called_once_with(self.project.resolve())

    def test_setup_rejects_workspace_root_that_could_remove_interactive_project(self):
        for path in [self.project, self.project.parent]:
            with self.assertRaisesRegex(install.InstallError, 'interactive project'):
                symphony.setup(self.project, workspace_root=path)

    def test_edited_configuration_is_rejected_before_startup_probes(self):
        path = symphony.config_path(self.project)
        for field, value in (
            ('workspace_root', str(self.project.parent)),
            ('codex', None), ('runtime_source', []), ('generated', []),
            ('dashboard_port', True), ('revision', 'unreviewed'),
        ):
            with self.subTest(field=field):
                path.write_text(json.dumps({**self.config, field: value}))
                with mock.patch.object(symphony.subprocess, 'run') as run, \
                     self.assertRaises(install.InstallError):
                    symphony.check(self.project)
                run.assert_not_called()
        invalid = dict(self.config)
        del invalid['workspace_root']
        path.write_text(json.dumps(invalid))
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(2, skills_cli.main(['symphony', 'check', '--project-dir', str(self.project)]))
        self.assertNotIn('Traceback', errors.getvalue())

    def test_load_refuses_symlinked_configuration(self):
        path = symphony.config_path(self.project)
        original = self.project / 'outside-config.json'
        path.rename(original)
        path.symlink_to(original)
        with self.assertRaisesRegex(install.InstallError, 'symlink'):
            symphony.load(self.project)

    def test_hook_refuses_other_directories_before_clone(self):
        with mock.patch.object(Path, 'cwd', return_value=self.project), mock.patch.object(subprocess, 'run') as run:
            with self.assertRaises(install.InstallError):
                symphony.prepare_workspace(self.project)
        run.assert_not_called()

    def test_offline_check_cannot_report_ready(self):
        problems = symphony.check(self.project, remote=False)
        self.assertTrue(any('not checked offline' in p for p in problems))

    def test_cli_setup_and_check_need_no_textual(self):
        with mock.patch.dict('sys.modules', {'textual': None}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, skills_cli.main(['symphony', 'setup', '--project-dir', str(self.project), '--no-dashboard']))
            self.assertEqual(3, skills_cli.main(['symphony', 'check', '--project-dir', str(self.project), '--offline']))
        self.assertIn('no workers started', output.getvalue())
        self.assertIsNone(symphony.load(self.project)['dashboard_port'])

    def test_hook_clones_isolated_repo_and_preserves_project_guidance(self):
        source = Path(self.temp.name) / 'source'
        source.mkdir()
        subprocess.run(['git', 'init', '--quiet', '--template=', '--initial-branch=main'], cwd=source, check=True)
        (source/'AGENTS.md').write_text('Project standards remain authoritative.')
        subprocess.run(['git','add','AGENTS.md'],cwd=source,check=True)
        subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false','commit','--quiet','-m','fixture'],cwd=source,check=True)
        subprocess.run(['git', 'checkout', '--quiet', '-b', 'release'], cwd=source, check=True)
        (source / 'release-only').write_text('configured base')
        subprocess.run(['git', 'add', 'release-only'], cwd=source, check=True)
        subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false','commit','--quiet','-m','release fixture'],cwd=source,check=True)
        subprocess.run(['git', 'checkout', '--quiet', 'main'], cwd=source, check=True)
        config = symphony.setup(self.project, repo_url=str(source), base_branch='release')
        issue = Path(config['workspace_root']) / 'DIE-123'
        issue.mkdir(parents=True)
        with mock.patch.object(Path, 'cwd', return_value=issue):
            symphony.prepare_workspace(self.project)
        self.assertEqual('codex/DIE-123', subprocess.check_output(['git','branch','--show-current'],cwd=issue,text=True).strip())
        self.assertEqual('configured base', (issue/'release-only').read_text())
        self.assertEqual('Project standards remain authoritative.', (issue/'AGENTS.md').read_text())
        self.assertEqual('symphony', json.loads((issue/'.symphony-worker.json').read_text())['kind'])
        self.assertFalse((issue/'.agents/skills/implement').exists())
        self.assertTrue((issue/'.agents/skills/land/land_watch.py').is_file())
        self.assertEqual('', subprocess.check_output(['git','status','--porcelain'],cwd=issue,text=True).strip())
        with mock.patch.object(Path,'cwd',return_value=issue), self.assertRaisesRegex(install.InstallError,'not empty'):
            symphony.prepare_workspace(self.project)

    def test_worker_selection_disables_all_unselected_paths_and_fails_on_ignored_override(self):
        names = symphony.WORKER_SKILLS + symphony.DELIVERY_SKILLS
        rows = [{'name': name, 'path': str(self.project / '.agents/skills' / name / 'SKILL.md'), 'enabled': True} for name in names]
        unwanted = {'name': 'viz-driven-dev', 'path': str(self.project / 'elsewhere/SKILL.md'), 'enabled': True}
        with mock.patch.object(symphony, 'skills_list', side_effect=[rows+[unwanted], rows+[{**unwanted,'enabled':False}]]):
            flags = symphony.worker_overrides({'codex':'codex', 'model_routing':'off'}, self.project)
        self.assertIn('enabled=false', flags[1])
        with mock.patch.object(symphony, 'skills_list', return_value=rows+[unwanted]), self.assertRaisesRegex(install.InstallError, 'refusing worker launch'):
            symphony.worker_overrides({'codex':'codex', 'model_routing':'off'}, self.project)


class AuthenticationTests(unittest.TestCase):
    def test_failed_logins_block_readiness_without_leaking_diagnostics(self):
        secret = "credential-that-must-not-be-printed"
        result = subprocess.CompletedProcess([], 1, stdout=secret, stderr=secret)
        with mock.patch.object(symphony.shutil, 'which', return_value='/test/tool'), \
             mock.patch.object(symphony.subprocess, 'run', return_value=result):
            problems = symphony.authentication_problems({'codex': '/test/codex'})
        self.assertEqual(2, len(problems))
        self.assertTrue(all('not authenticated' in p for p in problems))
        self.assertNotIn(secret, str(problems))

    def test_success_and_timeouts_have_distinct_results(self):
        with mock.patch.object(symphony.shutil, 'which', return_value='/test/tool'), \
             mock.patch.object(symphony.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual([], symphony.authentication_problems({'codex': '/test/codex'}))
        with mock.patch.object(symphony.shutil, 'which', return_value='/test/tool'), \
             mock.patch.object(symphony.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tool', 20)):
            problems = symphony.authentication_problems({'codex': '/test/codex'})
        self.assertEqual(2, len(problems))
        self.assertTrue(all('timed out' in p for p in problems))


class CuratedMigrationTests(unittest.TestCase):
    def test_curated_migration_backs_up_forks_and_keeps_unrelated_skills(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'skills'
            root.mkdir()
            for name in ('tdd','triage'):
                (root/name).mkdir(); (root/name/'SKILL.md').write_text('original '+name)
            install.record_external_install(root, 'matt-skills', ['tdd','triage'], 'v1.2.3', install.MATT_SKILLS_COMMIT)
            with self.assertRaises(install.InstallError):
                install.install_curated([root], emit=lambda _:None)
            install.install_curated([root], force=True, emit=lambda _:None)
            self.assertEqual('original triage', (root/'triage/SKILL.md').read_text())
            self.assertIsNone(install.ownership(root,'tdd').by_external)
            self.assertTrue(install.ownership(root,'tdd').by_receipt)
            self.assertEqual('matt-skills', install.ownership(root,'triage').by_external)
            self.assertTrue(list(root.parent.glob('.skills-backups/skills/tdd-*')))

    def test_curated_preflight_preserves_legacy_other_collection(self):
        with tempfile.TemporaryDirectory() as raw:
            first, legacy = Path(raw) / 'first', Path(raw) / 'legacy'
            (legacy / install.PSTACK.marker).mkdir(parents=True)
            (legacy / 'tdd').mkdir()
            entrypoint = legacy / 'tdd/SKILL.md'
            entrypoint.write_text('legacy pstack work')
            with self.assertRaisesRegex(install.InstallError, 'owned by pstack'):
                install.install_curated([first, legacy], force=True, allow_conflicts=False, emit=lambda _: None)
            self.assertFalse(first.exists())
            self.assertEqual('legacy pstack work', entrypoint.read_text())
            install.install_curated([legacy], force=True, emit=lambda _: None)
            # After an explicit takeover, its receipt wins over the old marker.
            install.install_curated([legacy], force=True, allow_conflicts=False, emit=lambda _: None)
            self.assertTrue(install.ownership(legacy, 'tdd').by_receipt)

    def test_curated_preflight_checks_mode_before_writing_any_root(self):
        for initial, requested in (('copy', 'link'), ('link', 'copy')):
            with self.subTest(mode=requested), tempfile.TemporaryDirectory() as raw:
                first, second = Path(raw) / 'first', Path(raw) / 'second'
                install.install_one(install.SOURCE_ROOT / 'tdd', second, initial, False, False)
                with self.assertRaisesRegex(install.InstallError, 'mode differs'):
                    install.install_curated([first, second], mode=requested, emit=lambda _: None)
                self.assertFalse(first.exists())
                self.assertTrue(install.destination_matches_mode(second / 'tdd', initial))

    def test_curated_install_keeps_unrelated_receipts(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)/'skills'
            install.install_one(install.SOURCE_ROOT/'ponytail', root, 'copy', False, False)
            install.write_receipt(root, ['ponytail'], 'copy', False)
            with contextlib.redirect_stdout(io.StringIO()):
                code = install.main(['--home',raw,'--target',str(root),'--curated-skills'])
            self.assertEqual(0, code)
            self.assertIn('ponytail', install.receipt_skills(root))
            self.assertEqual(set(install.CURATED_SKILLS)|{'ponytail'},set(install.receipt_skills(root)))

    def test_curated_alias_rejects_old_revision_before_installing(self):
        with tempfile.TemporaryDirectory() as raw, self.assertRaisesRegex(install.InstallError,'retired'):
            install.install_matt_skills([], [Path(raw)], False, False, ref='main')
