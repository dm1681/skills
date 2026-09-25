"""Evidence-layer and explicit rehearsal regressions using isolated fixtures."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import skills_cli
import symphony_project as project
import symphony_readiness as readiness
import symphony_rehearsal as rehearsal
import symphony_identity


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = project.setup(self.root, repo_url='git@example:owner/repo.git', validation_command='false')
        self.patches = contextlib.ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(readiness.sys, 'platform', 'linux'))
        for name in ('probe_worker', 'authentication_problems'):
            self.patches.enter_context(mock.patch.object(project, name, return_value=[]))
        self.patches.enter_context(mock.patch.object(project, 'linear_gate', return_value={}))
        self.patches.enter_context(mock.patch.object(project, 'verify_runtime', return_value=self.root))
        self.patches.enter_context(mock.patch.object(project, 'runtime_binary', return_value=self.root / '.symphony/project.json'))
        self.patches.enter_context(mock.patch.object(shutil, 'which', return_value=sys.executable))
        self.access = self.patches.enter_context(mock.patch.object(symphony_identity, 'check_access', return_value=[]))

    def rows(self, **kwargs):
        return {r['name']:r for r in readiness.report(self.root, **kwargs)['checks']}

    def test_startup_success_never_claims_delivery_and_skips_are_explicit(self):
        report = readiness.report(self.root)
        self.assertTrue(report['startup_ready'])
        self.assertFalse(report['delivery_ready'])
        rows = {r['name']:r for r in report['checks']}
        for name in ('pr_access', 'bootstrap_validation', 'process_startup', 'worker_delivery'):
            self.assertEqual('skipped', rows[name]['status'])
            self.assertTrue(rows[name]['remediation'])
        self.access.assert_called_once_with(self.config, 'git')
        self.assertIn('delivery unverified', readiness.render(report))

    def test_git_denial_and_missing_tools_are_failed_with_remediation(self):
        with mock.patch.object(project, 'probe_worker', return_value=['Git commit denied']), \
             mock.patch.object(shutil, 'which', return_value=None):
            rows = self.rows()
        self.assertEqual('fail', rows['tools']['status'])
        self.assertEqual('skipped', rows['worker_sandbox']['status'])
        with mock.patch.object(project, 'probe_worker', return_value=['Git commit denied']):
            rows = self.rows()
        self.assertEqual('fail', rows['worker_sandbox']['status'])
        self.assertIn('Git commit denied', rows['worker_sandbox']['detail'])

    def test_wrong_account_fails_in_integrated_report(self):
        self.config = project.setup(self.root, github_repo='owner/repo', github_account='right', credential_provider=str(self.root/'provider'))
        self.access.side_effect = lambda config, kind: ['Credential provider account differs from github_account'] if kind == 'pr' else []
        rows = self.rows()
        self.assertEqual('fail', rows['pr_access']['status'])
        self.assertIn('account differs', rows['pr_access']['detail'])

    def test_missing_declared_tool_is_checked_even_without_native_probe(self):
        project.setup(self.root, bootstrap={'required_tools':['missing-fixture-tool']})
        self.patches.close()
        with mock.patch.object(project, 'probe_worker', return_value=[]), mock.patch.object(project, 'verify_runtime', side_effect=project.Error('missing runtime')):
            rows = self.rows(remote=False)
        self.assertEqual('fail', rows['bootstrap_prerequisites']['status'])
        self.assertIn('missing-fixture-tool', rows['bootstrap_prerequisites']['detail'])

    def test_offline_never_runs_remote_or_bootstrap_and_cannot_pass(self):
        with mock.patch.object(rehearsal, 'validate_fresh_clone') as fresh:
            report = readiness.report(self.root, remote=False, bootstrap=True)
        self.assertFalse(report['startup_ready'])
        self.access.assert_not_called()
        fresh.assert_not_called()

    def test_bootstrap_only_runs_when_explicit_and_failure_blocks_report(self):
        with mock.patch.object(rehearsal, 'validate_fresh_clone', side_effect=project.Error('validation failed')) as fresh:
            self.rows()
            fresh.assert_not_called()
            rows = self.rows(bootstrap=True, timeout=12)
        fresh.assert_called_once_with(self.root, timeout=12)
        self.assertEqual('fail', rows['bootstrap_validation']['status'])

    def test_cli_json_exposes_skipped_delivery_without_textual(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, mock.patch.dict(sys.modules, {'textual':None}):
            code = skills_cli.main(['symphony','check','--project-dir',str(self.root),'--json'])
        self.assertEqual(0, code)
        self.assertFalse(json.loads(output.getvalue())['delivery_ready'])


@unittest.skipUnless(sys.platform == 'linux', 'Linux/WSL rehearsal process policy')
class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = mock.patch.dict(os.environ, {'HOME':str(self.root), 'SKILLS_PLUGIN_STATUS':'off'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.git('init','-q','--template=','--initial-branch=main',cwd=self.source)
        (self.source/'README.md').write_text('fixture')
        self.git('add','.',cwd=self.source)
        self.git('commit','-qm','seed',cwd=self.source)
        self.git('commit','--allow-empty','-qm','base tip',cwd=self.source)
        self.config = project.setup(self.source, repo_url=str(self.source), validation_command='true')

    def git(self, *args, cwd):
        return subprocess.check_output(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                                        '-c','commit.gpgsign=false',*args],cwd=cwd,text=True).strip()

    def evidence(self):
        return list((self.source/'.symphony/evidence').glob('*/evidence.json'))

    def test_rehearsal_requires_authorization_before_any_side_effect(self):
        with mock.patch.object(project,'load') as load:
            with self.assertRaisesRegex(project.Error,'accept-rehearsal'):
                rehearsal.rehearse(self.source)
        load.assert_not_called()
        self.assertEqual([],self.evidence())

    def test_fresh_clone_uses_shared_bootstrap_and_cleans_clone_keeps_evidence(self):
        project.setup(self.source, bootstrap={'python':sys.executable})
        with mock.patch.object(rehearsal,'validate') as validate:
            path = rehearsal.validate_fresh_clone(self.source)
        record = json.loads(path.read_text())
        self.assertEqual('pass',record['status'])
        self.assertFalse(Path(record['workspace']).exists())
        cwd = validate.call_args.args[2]
        env = validate.call_args.args[3]
        self.assertEqual(str(cwd/'.symphony-cache/uv'),env['UV_CACHE_DIR'])
        self.assertEqual('complete',record['local_cleanup'])
        self.assertEqual('main',self.git('branch','--show-current',cwd=self.source))

    def test_isolated_validation_preserves_clone_cache_environment(self):
        project.setup(self.source, repo_url=str(self.source),
                             validation_command=('test "$(uv cache dir)" = "$PWD/.symphony-cache/uv" && '
                                                 'test -z "${AWS_SECRET_ACCESS_KEY+x}" && '
                                                 'python3 -c "import asyncio; asyncio.run(asyncio.to_thread(lambda: None))"'))
        with mock.patch.dict(os.environ, {'AWS_SECRET_ACCESS_KEY':'fixture-secret'}):
            path=rehearsal.validate_fresh_clone(self.source, timeout=20)
        self.assertEqual('pass',json.loads(path.read_text())['status'])

    def test_fresh_clone_rejects_validation_that_changes_tracked_files(self):
        project.setup(self.source, repo_url=str(self.source),
                      validation_command="python3 -c \"from pathlib import Path; Path('README.md').write_text('changed')\"")
        with self.assertRaisesRegex(project.Error, 'evidence:'):
            rehearsal.validate_fresh_clone(self.source)
        record=json.loads(self.evidence()[0].read_text())
        self.assertEqual('fail',next(row for row in record['checks'] if row['name']=='validation')['status'])

    def test_bootstrap_failure_has_durable_evidence_and_cleanup(self):
        project.setup(self.source, bootstrap={'required_tools':['missing-symphony-test-tool']})
        with self.assertRaisesRegex(project.Error,'evidence:'):
            rehearsal.validate_fresh_clone(self.source)
        record=json.loads(self.evidence()[0].read_text())
        self.assertEqual('fail',record['status'])
        self.assertFalse(Path(record['workspace']).exists())
        self.assertEqual('fail',next(r for r in record['checks'] if r['name']=='bootstrap')['status'])
        self.assertEqual('skipped',record['checks'][-1]['status'])

    def test_timeout_kills_process_group_and_redacts_command_output(self):
        before=time.monotonic()
        with self.assertRaisesRegex(project.Error,'deadline'):
            rehearsal.run([sys.executable,'-c','import time; time.sleep(60)'], self.root, dict(os.environ), time.monotonic()+.1)
        self.assertLess(time.monotonic()-before,4)
        with self.assertRaises(project.Error) as caught:
            rehearsal.run([sys.executable,'-c','print("secret"); raise SystemExit(8)'],self.root,dict(os.environ),time.monotonic()+5)
        self.assertNotIn('secret',str(caught.exception))

    def test_whole_operation_deadline_covers_identity_probe(self):
        with mock.patch.object(symphony_identity,'environment',side_effect=lambda *_: time.sleep(20)):
            before=time.monotonic()
            with self.assertRaisesRegex(project.Error,'evidence:'):
                rehearsal.validate_fresh_clone(self.source,timeout=1)
            self.assertLess(time.monotonic()-before,4)
        self.assertEqual('fail',json.loads(self.evidence()[0].read_text())['status'])

    def test_synthetic_worker_to_pr_receipt_and_extra_change_denial(self):
        # Local Git clone and commit are real; remote API/write boundaries are fixtures.
        config={**self.config,'github_repo':'owner/repo'}
        real_run=rehearsal.run
        for extra in (False,True,"canonical-case", "config", "hidden-tracked", "hidden-untracked", "marker-blob", "base-moved", "wrong-parent", "validation-tracked"):
            with self.subTest(extra=extra):
                def model(config,proj,cwd,env,prompt,deadline):
                    if extra == 'wrong-parent':
                        self.git('reset','--hard','HEAD~',cwd=cwd)
                    (cwd/'symphony-rehearsal.txt').write_text('wrong committed content\n' if extra == 'marker-blob' else cwd.name+'\n')
                    if extra is True: (cwd/'unexpected').write_text('must not publish')
                    if extra == 'config': self.git('config','core.sshCommand','untrusted',cwd=cwd)
                    self.git('add','.',cwd=cwd);self.git('commit','-qm','rehearsal',cwd=cwd)
                    if extra == 'marker-blob':
                        (cwd/'symphony-rehearsal.txt').write_text(cwd.name+'\n')
                        self.git('update-index','--assume-unchanged','symphony-rehearsal.txt',cwd=cwd)
                    if extra == 'hidden-tracked':
                        self.git('update-index', '--assume-unchanged', 'README.md', cwd=cwd)
                        (cwd/'README.md').write_text('hidden validation bypass')
                    if extra == 'hidden-untracked':
                        with (cwd/'.git/info/exclude').open('a') as stream:
                            stream.write('\nhidden-helper\n')
                        (cwd/'hidden-helper').write_text('hidden validation bypass')
                def validate(config, proj, cwd, env, deadline):
                    self.assertTrue(cwd.name.startswith('validation-'))
                    self.assertEqual('fixture', (cwd/'README.md').read_text())
                    self.assertFalse((cwd/'hidden-helper').exists())
                    self.assertEqual('symphony-rehearsal.txt', self.git('diff', '--name-only', 'HEAD~', 'HEAD', cwd=cwd))
                    if extra == 'validation-tracked':
                        (cwd/'README.md').write_text('validation rewrote tracked source')
                calls=[]
                def run(command,cwd,env,deadline,**kwargs):
                    calls.append(command)
                    name=Path(command[0]).name
                    if name=='gh' or (name=='git' and 'push' in command):
                        self.assertEqual('controller-fixture-token', env.get('GH_TOKEN'))
                    if name=='git' and 'push' in command:
                        self.assertTrue(cwd.name.startswith('publication-'))
                        self.assertNotIn('.symphony-worker.json', [p.name for p in cwd.iterdir()])
                        return ''
                    if name=='gh' and command[1:3]==['pr','create']:
                        self.assertEqual('evidence',cwd.parent.name)
                        return 'https://github.com/Owner/Repo/pull/1' if extra=='canonical-case' else 'https://github.com/owner/repo/pull/1'
                    if name=='gh' and command[1:3]==['pr','view']:
                        url='https://github.com/Owner/Repo/pull/1' if extra=='canonical-case' else 'https://github.com/owner/repo/pull/1'
                        return json.dumps({'url':url,'state':'OPEN','isDraft':True,
                                           'headRefOid':self.git('rev-parse','HEAD',cwd=Path(config['workspace_root'])/command[3].split('/')[-1]),'baseRefName':'main',
                                           'baseRefOid':('0'*40 if extra == 'base-moved' else self.git('rev-parse','main',cwd=self.source))})
                    return real_run(command,cwd,env,deadline,**kwargs)
                with mock.patch.object(project,'load',return_value=config), mock.patch.object(symphony_identity,'check_access',return_value=[]), \
                     mock.patch.object(symphony_identity,'environment',return_value={**os.environ, 'GH_TOKEN':'controller-fixture-token'}), mock.patch.object(symphony_identity,'clone_url',return_value=str(self.source)), \
                     mock.patch.object(rehearsal,'model_turn',side_effect=model), mock.patch.object(rehearsal,'validate',side_effect=validate), \
                     mock.patch.object(rehearsal,'run',side_effect=run):
                    if extra is True or extra in ('config', 'marker-blob', 'base-moved', 'wrong-parent', 'validation-tracked'):
                        with self.assertRaisesRegex(project.Error,'retained workspace'):
                            rehearsal.rehearse(self.source,accept=True)
                        if extra != 'base-moved':
                            self.assertFalse(any(Path(c[0]).name=='git' and 'push' in c for c in calls))
                    else:
                        path=rehearsal.rehearse(self.source,accept=True)
                        record=json.loads(path.read_text())
                        self.assertEqual('pass',record['status'])
                        self.assertEqual('Human Review',record['review_boundary'])
                        self.assertFalse(record['merged'])
                        self.assertTrue(Path(record['workspace']).is_dir())
                        self.assertTrue(any('--draft' in c for c in calls))
                        self.assertTrue(any(Path(c[0]).name=='git' and 'push' in c and c[-1].startswith(record['head_sha'] + ':') for c in calls))
                        self.assertTrue(any(Path(c[0]).name=='gh' and c[1:3]==['pr','view'] and 'baseRefOid' in c[-1] for c in calls))
                        self.assertFalse(list(Path(config['workspace_root']).glob('validation-*')))

    def test_native_protocol_turn_uses_shared_roots_and_no_approvals(self):
        cwd=self.root/'workers'/'fixture'
        cwd.mkdir(parents=True)
        self.git('init','-q','--template=',cwd=cwd)
        (cwd/'.symphony-worker.json').write_text(json.dumps({'kind':'symphony','project_dir':str(self.source)}))
        executable=self.root/'fake-codex'
        executable.write_text('#!'+sys.executable+'\n'+'''import json, os, pathlib, sys
assert not any(key in os.environ for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN', 'GIT_CONFIG_VALUE_0', 'SSH_AUTH_SOCK', 'GIT_ASKPASS', 'AWS_SECRET_ACCESS_KEY'))
for line in sys.stdin:
    request=json.loads(line)
    method=request.get('method')
    if method=='initialize': result={}
    elif method=='thread/start': result={'thread':{'id':'thread'}}
    elif method=='turn/start':
        pathlib.Path('request.json').write_text(json.dumps(request))
        print(json.dumps({'id':3,'result':{'turn':{'id':'turn'}}}),flush=True)
        print(json.dumps({'method':'turn/completed','params':{'turn':{'id':'turn','status':'completed'}}}),flush=True)
        continue
    else: continue
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
''')
        executable.chmod(0o700)
        config={**self.config,'codex':str(executable),'workspace_root':str(cwd.parent),
                'git_author_name':'Symphony', 'git_author_email':'symphony@example.invalid'}
        env = {**os.environ, 'GH_TOKEN':'fixture-secret', 'GITHUB_TOKEN':'fixture-secret',
               'GH_ENTERPRISE_TOKEN':'fixture-secret', 'GITHUB_ENTERPRISE_TOKEN':'fixture-secret',
               'GIT_CONFIG_VALUE_0':'fixture-secret', 'SSH_AUTH_SOCK':'fixture-agent', 'GIT_ASKPASS':'fixture-helper',
               'AWS_SECRET_ACCESS_KEY':'fixture-secret'}
        def discovery(config, cwd, *, env):
            self.assertFalse('GH_TOKEN' in env)
            self.assertEqual('Symphony', env['GIT_AUTHOR_NAME'])
            self.assertEqual('symphony@example.invalid', env['GIT_COMMITTER_EMAIL'])
            return []
        with mock.patch.object(project,'worker_overrides',side_effect=discovery):
            rehearsal.model_turn(config,self.source,cwd,env,'synthetic',time.monotonic()+5)
        self.assertEqual('fixture-secret', env['GH_TOKEN'])
        request=json.loads((cwd/'request.json').read_text())
        params=request['params']
        self.assertEqual('never',params['approvalPolicy'])
        self.assertEqual([str(cwd),str(cwd/'.git')],params['sandboxPolicy']['writableRoots'])
        self.assertTrue(params['sandboxPolicy']['networkAccess'])
        self.assertTrue(params['sandboxPolicy']['excludeSlashTmp'])

    def test_controller_binary_skips_worker_path(self):
        worker=self.root/'worker'
        worker.mkdir()
        controller=self.root/'controller'
        controller.mkdir()
        fake=worker/'fixture-tool'
        fake.write_text('#!/bin/sh\nexit 1\n')
        fake.chmod(0o700)
        trusted=controller/'fixture-tool'
        trusted.write_text('#!/bin/sh\nexit 0\n')
        trusted.chmod(0o700)
        binary=rehearsal.controller_binary('fixture-tool', {'PATH':str(worker)+os.pathsep+str(controller)}, worker)
        self.assertEqual(trusted,Path(binary))

    def test_validation_failure_prevents_remote_writes(self):
        config={**self.config,'github_repo':'owner/repo'}
        def model(config,proj,cwd,env,prompt,deadline):
            (cwd/'symphony-rehearsal.txt').write_text(cwd.name+'\n')
            self.git('add','.',cwd=cwd);self.git('commit','-qm','rehearsal',cwd=cwd)
        with mock.patch.object(project,'load',return_value=config), \
             mock.patch.object(symphony_identity,'check_access',return_value=[]), \
             mock.patch.object(symphony_identity,'environment',return_value=dict(os.environ)), \
             mock.patch.object(symphony_identity,'clone_url',return_value=str(self.source)), \
             mock.patch.object(rehearsal,'model_turn',side_effect=model), \
             mock.patch.object(rehearsal,'validate',side_effect=project.Error('failed validation')):
            with self.assertRaisesRegex(project.Error,'retained workspace'):
                rehearsal.rehearse(self.source,accept=True)
        record=json.loads(self.evidence()[0].read_text())
        rows={r['name']:r for r in record['checks']}
        self.assertEqual('fail',rows['validation']['status'])
        self.assertEqual('skipped',rows['push']['status'])
        self.assertEqual('skipped',rows['draft_pr']['status'])
        self.assertFalse(list(Path(config['workspace_root']).glob('validation-*')))
