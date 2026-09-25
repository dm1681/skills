"""External publishing credentials and worker skill upgrade boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import symphony_artifacts as artifacts
import symphony_project as symphony


class ArtifactWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.root = self.project / "workers"
        self.cwd = self.root / "DIE-123"
        self.cwd.mkdir(parents=True)
        self.key = self.base / "publisher-token"
        self.token = "fixture." + "x" * 43
        self.key.write_text(self.token)
        self.key.chmod(0o600)
        self.config = {"project_dir": str(self.project), "workspace_root": str(self.root), artifacts.FIELD: str(self.key)}
        self.node = mock.patch.object(artifacts.shutil, "which", return_value="/fake/node")
        self.node.start(); self.addCleanup(self.node.stop)
        self.version = mock.patch.object(artifacts.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v22.23.3\n", ""))
        self.run = self.version.start(); self.addCleanup(self.version.stop)

    def test_file_path_overrides_raw_token_without_leaking_key(self):
        original = {"PATH": "/fake", "ARTIFACT_PUBLISH_TOKEN": "stale-secret", "UNCHANGED": "yes"}
        env = artifacts.environment(self.config, original)
        self.assertEqual(str(self.key), env['ARTIFACT_PUBLISH_TOKEN_FILE'])
        self.assertNotIn('ARTIFACT_PUBLISH_TOKEN', env)
        self.assertNotIn(self.token, repr(env))
        self.assertEqual('stale-secret', original['ARTIFACT_PUBLISH_TOKEN'])
        self.assertEqual('yes', env['UNCHANGED'])

    def test_unconfigured_projects_keep_existing_environment(self):
        self.assertEqual({'PATH': '/fake'}, artifacts.environment({}, {'PATH': '/fake'}))
        self.run.assert_not_called()

    def test_missing_malformed_or_exposed_key_has_redacted_error(self):
        for content in ['malformed-private-value', self.token]:
            self.key.write_text(content)
            if content == self.token:
                if os.name != 'posix':continue
                self.key.chmod(0o644)
            with self.assertRaises(artifacts.Error) as caught:
                artifacts.environment(self.config, {'PATH': '/fake'})
            self.assertNotIn(content, str(caught.exception))
        self.key.unlink()
        with self.assertRaisesRegex(artifacts.Error, 'owner-only'):
            artifacts.environment(self.config, {'PATH': '/fake'})

    def test_key_paths_inside_project_or_workers_are_rejected(self):
        for path in [self.project/'secret', self.cwd/'secret', Path('relative-key')]:
            with self.assertRaises(artifacts.Error):artifacts.validate({**self.config, artifacts.FIELD: str(path)})

    def test_old_node_reports_actionable_requirement(self):
        self.run.return_value = subprocess.CompletedProcess([], 0, 'v20.0.0', '')
        with self.assertRaisesRegex(artifacts.Error, 'Node.js 22'):
            artifacts.environment(self.config, {'PATH': '/fake'})

    def test_sandbox_probe_never_puts_token_in_command_or_output(self):
        env=artifacts.environment(self.config, {'PATH': '/fake'})
        self.run.return_value=subprocess.CompletedProcess([],0,'artifact-key-readable','')
        artifacts.probe('/fake/codex',self.cwd,env)
        self.assertNotIn(self.token,repr(self.run.call_args))
        self.assertIn('ARTIFACT_PUBLISH_TOKEN_FILE',repr(self.run.call_args))
        self.run.return_value=subprocess.CompletedProcess([],1,'',self.token)
        with self.assertRaises(artifacts.Error) as caught:artifacts.probe('/fake/codex',self.cwd,env)
        self.assertNotIn(self.token,str(caught.exception))

    def test_existing_clones_receive_new_skills_without_replacing_edits(self):
        root=self.cwd/'.agents/skills'
        existing=root/'research';existing.mkdir(parents=True)
        (existing/'SKILL.md').write_text('local research edit')
        symphony.provision_missing_worker_skills(self.cwd)
        self.assertEqual('local research edit',(existing/'SKILL.md').read_text())
        self.assertTrue((root/'ponytail/SKILL.md').is_file())
        self.assertTrue((root/'cloudflare-artifacts/scripts/publish.mjs').is_file())
        self.assertEqual(set(symphony.WORKER_SKILLS+symphony.DELIVERY_SKILLS),{p.name for p in root.iterdir() if p.is_dir()})
        self.assertIn("ponytail", symphony.install.receipt_skills(root))
        self.assertIn("cloudflare-artifacts", symphony.install.receipt_skills(root))
        symphony.provision_missing_worker_skills(self.cwd)
        self.assertEqual('local research edit',(existing/'SKILL.md').read_text())

    @unittest.skipIf(os.name=='nt','Symlink privileges vary on Windows')
    def test_symlinked_key_and_skill_root_are_rejected(self):
        link=self.base/'key-link';link.symlink_to(self.key)
        with self.assertRaises(artifacts.Error):artifacts.environment({**self.config,artifacts.FIELD:str(link)},{'PATH':'/fake'})
        (self.cwd/'.agents').symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(artifacts.Error):symphony.provision_missing_worker_skills(self.cwd)
