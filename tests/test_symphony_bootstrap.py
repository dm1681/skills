from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import skills_cli
import symphony_bootstrap as bootstrap
import symphony_project as symphony


@unittest.skipIf(os.name == "nt", "Linux/WSL worker bootstrap and executable fixtures")
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS exposes its temp directory through /var -> /private/var;
        # worker markers use the canonical project path from setup.
        self.root = Path(self.temp.name).resolve()
        self.cwd = self.root / "worker with spaces"
        self.cwd.mkdir()
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.root), "SKILLS_PLUGIN_STATUS": "off"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.spec = {"python": sys.executable, "python_version": f"{sys.version_info.major}.{sys.version_info.minor}"}

    def test_invalid_declarations_fail_before_execution(self):
        for spec in (None, [], {"unknown": True}, {"python": ""}, {"python": "./python"},
                     {"python_version": "3.12"}, {"dependencies": "uv"},
                     {**self.spec, "python_version": ">=3"}, {"required_tools": "git"},
                     {"required_tools": [None]}, {"dependencies": "pip"},
                     {"download_policy": "automatic"}, {"timeout_seconds": True},
                     {"timeout_seconds": 0}, {"cache_dir": "../cache"},
                     {"cache_dir": "/tmp/cache"}, {"cache_dir": ".git/cache"},
                     {"cache_dir": "cache*"}, {"cache_dir": ".venv"}):
            with self.subTest(spec=spec), mock.patch.object(subprocess, "run") as run:
                with self.assertRaises(bootstrap.Error):
                    bootstrap.environment(spec, self.cwd)
                run.assert_not_called()

    def test_source_only_is_a_noop(self):
        with mock.patch.object(subprocess, "run") as run:
            bootstrap.prepare({}, self.cwd)
        run.assert_not_called()
        self.assertEqual([], list(self.cwd.iterdir()))

    def test_preinstalled_python_and_isolated_cache(self):
        with mock.patch.dict(os.environ, {"UV_PYTHON": "/wrong", "UV_OFFLINE": "false",
                                         "VIRTUAL_ENV": "/interactive", "PYTHONPATH": "/interactive"}):
            env = bootstrap.environment({**self.spec, "cache_dir": "cache with spaces"}, self.cwd)
        self.assertEqual(sys.executable, env["SYMPHONY_PYTHON"])
        self.assertEqual("never", env["UV_PYTHON_DOWNLOADS"])
        self.assertEqual("true", env["UV_OFFLINE"])
        self.assertEqual(str(self.cwd / "cache with spaces" / "uv"), env["UV_CACHE_DIR"])
        self.assertNotIn("VIRTUAL_ENV", env)
        self.assertNotIn("PYTHONPATH", env)

    def test_bootstrap_composes_with_scoped_identity_without_mutating_it(self):
        identity = {"PATH": os.environ["PATH"], "GIT_AUTHOR_NAME": "Fixture",
                    "GIT_SSH_COMMAND": "ssh -F /fixture/config", "GH_TOKEN": "fixture-token"}
        env = bootstrap.environment(self.spec, self.cwd, base_env=identity)
        for key, value in identity.items():
            self.assertEqual(value, env[key])
        self.assertNotIn("UV_PYTHON", identity)

    def test_missing_interpreter_tool_and_wrong_version_are_actionable(self):
        for spec, message in (({"python": "symphony-missing-python"}, "preinstall"),
                              ({"required_tools": ["symphony-missing-ffmpeg"]}, "preinstall"),
                              ({**self.spec, "python_version": "0.1"}, "version mismatch")):
            with self.subTest(spec=spec), self.assertRaisesRegex(bootstrap.Error, message):
                bootstrap.environment(spec, self.cwd)

    def test_cache_file_symlink_and_permission_failures(self):
        (self.cwd / "file").write_text("occupied")
        (self.cwd / "link").symlink_to(self.root, target_is_directory=True)
        for cache, message in (("file", "not writable"), ("link", "outside")):
            with self.subTest(cache=cache), self.assertRaisesRegex(bootstrap.Error, message):
                bootstrap.environment({"cache_dir": cache}, self.cwd)
        with mock.patch.object(tempfile, "TemporaryFile", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(bootstrap.Error, "not writable"):
                bootstrap.environment({"cache_dir": "denied"}, self.cwd)
        if os.name == "posix" and os.geteuid() != 0:
            locked = self.cwd / "locked"
            locked.mkdir(mode=0o500)
            try:
                with self.assertRaisesRegex(bootstrap.Error, "not writable"):
                    bootstrap.environment({"cache_dir": "locked"}, self.cwd)
            finally:
                locked.chmod(0o700)

    def fake_uv(self, exit_code=0):
        binary = self.root / "bin"
        binary.mkdir(exist_ok=True)
        uv = binary / "uv"
        uv.write_text(f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
                      "Path('uv-call.json').write_text(json.dumps({'args':sys.argv[1:], 'env':dict(os.environ)}))\n"
                      f"sys.exit({exit_code})\n")
        uv.chmod(0o755)
        return mock.patch.dict(os.environ, {"PATH": str(binary) + os.pathsep + os.environ.get("PATH", "")})

    def test_locked_policy_and_failed_bootstrap(self):
        (self.cwd / "pyproject.toml").write_text("[project]\n")
        (self.cwd / "uv.lock").write_text("fixture")
        for policy in ("never", "allow"):
            with self.fake_uv():
                bootstrap.prepare({**self.spec, "dependencies": "uv", "download_policy": policy}, self.cwd)
            call = json.loads((self.cwd / "uv-call.json").read_text())
            self.assertIn("--locked", call["args"])
            self.assertIn("--no-python-downloads", call["args"])
            self.assertEqual(policy == "never", "--offline" in call["args"])
            self.assertEqual("true" if policy == "never" else "false", call["env"]["UV_OFFLINE"])
        with self.fake_uv(37), self.assertRaisesRegex(bootstrap.Error, "exit 37"):
            bootstrap.prepare({**self.spec, "dependencies": "uv"}, self.cwd)

    def test_missing_lock_and_timeout(self):
        with self.fake_uv(), self.assertRaisesRegex(bootstrap.Error, "commit the lockfile"):
            bootstrap.prepare({**self.spec, "dependencies": "uv"}, self.cwd)
        (self.cwd / "pyproject.toml").touch()
        (self.cwd / "uv.lock").touch()
        real_run = subprocess.run
        def run(command, **kwargs):
            if "sync" in command:
                raise subprocess.TimeoutExpired(command, 1)
            return real_run(command, **kwargs)
        with self.fake_uv(), mock.patch.object(subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(bootstrap.Error, "timed out"):
                bootstrap.prepare({**self.spec, "dependencies": "uv", "timeout_seconds": 1}, self.cwd)

    def test_setup_cli_records_and_preserves_without_executing_bootstrap(self):
        declaration = self.root / "bootstrap.json"
        declaration.write_text(json.dumps(self.spec))
        args = ["symphony", "setup", "--project-dir", str(self.cwd), "--repo-url", "synthetic",
                "--validation-command", "python -m unittest", "--bootstrap-file", str(declaration)]
        with mock.patch.object(bootstrap, "prepare", side_effect=AssertionError("setup ran bootstrap")), \
             mock.patch.object(bootstrap, "environment", side_effect=AssertionError("setup probed")), \
             mock.patch.object(os, "execv", side_effect=AssertionError("setup started service")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, skills_cli.main(args))
            symphony.setup(self.cwd, dashboard_enabled=False)
        self.assertEqual(self.spec, symphony.load(self.cwd)["bootstrap"])

    def test_launch_checks_declaration_and_passes_environment(self):
        config = symphony.setup(self.cwd, repo_url="fixture", bootstrap=self.spec)
        issue = Path(config["workspace_root"]) / "DIE-1"
        issue.mkdir(parents=True)
        marker = {"kind": "symphony", "project_dir": str(self.cwd), "bootstrap": self.spec}
        (issue / ".symphony-worker.json").write_text(json.dumps(marker))
        with mock.patch.object(Path, "cwd", return_value=issue), \
             mock.patch.object(symphony, "worker_overrides", return_value=[]), \
             mock.patch.object(symphony.symphony_worker, "run_server", return_value=0) as server:
            with self.assertRaises(SystemExit) as result:
                symphony.run_worker(self.cwd)
            self.assertEqual(0, result.exception.code)
            env = server.call_args.args[-1]
            self.assertEqual(sys.executable, env["UV_PYTHON"])
            self.assertEqual(str(issue / ".symphony-cache" / "uv"), env["UV_CACHE_DIR"])
            self.assertNotIn("LINEAR_API_KEY", env)
            symphony.setup(self.cwd, bootstrap={**self.spec, "download_policy": "allow"})
            server.reset_mock()
            with self.assertRaisesRegex(bootstrap.Error, "reprovision"):
                symphony.run_worker(self.cwd)
            server.assert_not_called()

    @unittest.skipUnless(shutil.which("uv"), "real uv bootstrap acceptance requires uv")
    def test_two_clean_clones_bootstrap_locked_offline_with_real_uv(self):
        source = self.root / "source"
        source.mkdir()
        (source / "pyproject.toml").write_text('[project]\nname = "worker-fixture"\nversion = "0.0.0"\nrequires-python = ">=3.9"\ndependencies = []\n')
        env = bootstrap.environment(self.spec, source)
        subprocess.run([shutil.which("uv"), "lock", "--offline", "--python", sys.executable], cwd=source, env=env, check=True, capture_output=True)
        for command in (["init", "--quiet", "--template=", "--initial-branch=main"],
                        ["add", "pyproject.toml", "uv.lock"],
                        ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture"]):
            subprocess.run(["git", *command], cwd=source, check=True, capture_output=True)
        spec = {**self.spec, "dependencies": "uv", "download_policy": "never"}
        config = symphony.setup(self.cwd, repo_url=str(source), validation_command='uv run --no-sync python -c "import sys; print(sys.version)"', bootstrap=spec)
        locks = []
        for number in (1, 2):
            issue = Path(config["workspace_root"]) / f"DIE-{number}"
            issue.mkdir(parents=True)
            with mock.patch.object(Path, "cwd", return_value=issue):
                symphony.prepare_workspace(self.cwd)
            marker = json.loads((issue / ".symphony-worker.json").read_text())
            self.assertEqual(spec, marker["bootstrap"])
            locks.append((issue / "uv.lock").read_bytes())
            result = subprocess.run(config["validation_command"], shell=True, cwd=issue,
                                    env=bootstrap.environment(spec, issue), capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", subprocess.check_output(["git", "status", "--porcelain"], cwd=issue, text=True))
        self.assertEqual(locks[0], locks[1])
        # A stale lock must fail in a new clone and must not publish readiness.
        (source / "pyproject.toml").write_text((source / "pyproject.toml").read_text().replace('"0.0.0"', '"0.0.1"'))
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qam", "stale lock fixture"], cwd=source, check=True)
        issue = Path(config["workspace_root"]) / "DIE-3"
        issue.mkdir()
        with mock.patch.object(Path, "cwd", return_value=issue), self.assertRaisesRegex(bootstrap.Error, "uv sync failed"):
            symphony.prepare_workspace(self.cwd)
        self.assertFalse((issue / ".symphony-worker.json").exists())
        self.assertEqual(locks[0], (issue / "uv.lock").read_bytes())
