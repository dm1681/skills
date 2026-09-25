"""Boundary and transport regressions; native sandbox proof is explicitly opt-in."""
import copy
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import symphony_project
import symphony_worker as worker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.root = self.project / "workspaces"
        self.cwd = self.root / "DIE-123"
        self.cwd.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--template=", str(self.cwd)], check=True)
        self.marker = self.cwd / ".symphony-worker.json"
        self.marker.write_text(json.dumps({"kind": "symphony", "project_dir": str(self.project)}))
        self.request = {"id": 3, "method": "turn/start", "params": {
            "cwd": str(self.cwd), "approvalPolicy": {"reject": {"sandbox_approval": True}},
            "sandboxPolicy": {"type": "workspaceWrite", "networkAccess": True,
                              "excludeTmpdirEnvVar": True, "excludeSlashTmp": True},
            "input": [{"type": "text", "text": "task"}],
        }}

    def prepare(self, request=None):
        return json.loads(worker.prepare_request(json.dumps(request or self.request).encode(), self.project, self.root, self.cwd))

    def test_only_git_roots_change_and_other_protocol_messages_pass_through(self):
        expected = copy.deepcopy(self.request)
        expected["params"]["sandboxPolicy"]["writableRoots"] = [str(self.cwd), str(self.cwd / ".git")]
        self.assertEqual(expected, self.prepare())
        for message in [b'{"id":1,"method":"initialize"}\n', b'{"method":"thread/start","params":{}}\n', b'{"id":9,"result":{}}\n']:
            self.assertEqual(message, worker.prepare_request(message, self.project, self.root, self.cwd))

    def test_rejects_cwd_policy_and_writable_root_changes(self):
        for field, value in [("cwd", str(self.project)), ("cwd", str(self.cwd / "..")),
                             ("sandboxPolicy", {"type": "dangerFullAccess"}),
                             ("sandboxPolicy", {"type": "workspaceWrite", "writableRoots": [str(self.root)]}),
                             ("sandboxPolicy", {"type": "workspaceWrite", "writableRoots": "bad"})]:
            request = copy.deepcopy(self.request)
            request["params"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.prepare(request)

    def test_rejects_unmarked_wrong_project_and_marker_symlink(self):
        for marker in [{}, [], {"kind": "symphony", "project_dir": str(self.root)}]:
            self.marker.write_text(json.dumps(marker))
            with self.assertRaises(ValueError): self.prepare()
        self.marker.unlink()
        self.marker.symlink_to(self.project / "elsewhere")
        with self.assertRaises(ValueError): self.prepare()

    def test_rejects_linked_git_and_redirected_metadata(self):
        git = self.cwd / ".git"
        real = self.cwd / "original-git"
        git.rename(real)
        for is_link in (False, True):
            if is_link: git.symlink_to(real, target_is_directory=True)
            else: git.write_text("gitdir: " + str(real))
            with self.assertRaises(ValueError): self.prepare()
            git.unlink()
        real.rename(git)
        for name in ["commondir", "objects/redirect"]:
            path = git / name
            if name == "commondir": path.write_text(str(self.project))
            else: path.symlink_to(self.project, target_is_directory=True)
            with self.assertRaises(ValueError): self.prepare()
            path.unlink()
        outside = self.project / "shared"
        outside.write_text("outside")
        os.link(outside, git / "shared")
        with self.assertRaises(ValueError): self.prepare()

    def test_rejects_wrong_root_and_noncanonical_paths(self):
        for root, cwd in [(self.project, self.cwd), (self.root, self.root),
                          (self.root, self.cwd / ".."), (self.root, Path("relative"))]:
            with self.subTest(root=root, cwd=cwd), self.assertRaises(ValueError):
                worker.writable_roots(self.project, root, cwd)

    @unittest.skipIf(os.name == "nt", "Linux/WSL stdio relay")
    def test_relay_fragmented_lines_and_eof(self):
        process = self.relay('import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())')
        data = json.dumps(self.request).encode()
        process.stdin.write(data[:17]); process.stdin.flush()
        output, errors = process.communicate(data[17:] + b'\n{"id":4,"result":{}}', timeout=10)
        self.assertEqual(0, process.returncode, errors)
        first, second = output.splitlines()
        self.assertEqual(self.prepare(), json.loads(first))
        self.assertEqual({"id": 4, "result": {}}, json.loads(second))

    def relay(self, code):
        program = "import os,sys; from pathlib import Path; import symphony_worker as w; sys.exit(w.run_server([sys.executable,'-c',sys.argv[4]],Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),dict(os.environ)))"
        return subprocess.Popen([sys.executable, "-c", program, str(self.project), str(self.root), str(self.cwd), code],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @unittest.skipIf(os.name == "nt", "Linux/WSL process groups")
    def test_relay_exits_when_child_exits_with_stdin_still_open(self):
        process = self.relay('raise SystemExit(7)')
        try:
            self.assertEqual(7, process.wait(timeout=5))
        finally:
            process.communicate(timeout=5)

    @unittest.skipIf(os.name == "nt", "Linux/WSL process groups")
    def test_relay_signal_terminates_child(self):
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=signum):
                process = self.relay('import os,time; print(os.getpid(),flush=True); time.sleep(60)')
                try:
                    import select
                    self.assertTrue(select.select([process.stdout], [], [], 5)[0])
                    pid = int(process.stdout.readline())
                    process.send_signal(signum)
                    process.communicate(timeout=8)
                    self.assertEqual(128 + signum, process.returncode)
                    with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
                finally:
                    if process.poll() is None:
                        process.kill(); process.communicate()

    @unittest.skipIf(os.name == "nt", "Linux/WSL stdio relay")
    def test_real_child_does_not_inherit_git_routing_or_tracker_secret(self):
        routing = {key: "/wrong/path" for key in (
            "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
            "GIT_NAMESPACE", "GIT_SHALLOW_FILE",
        )}
        authentication = {"GIT_SSH_COMMAND": "ssh -i /synthetic/key",
                          "GIT_ASKPASS": "/synthetic/askpass", "GIT_CONFIG_COUNT": "1",
                          "GIT_CONFIG_KEY_0": "http.extraHeader",
                          "GIT_CONFIG_VALUE_0": "Authorization: synthetic"}
        with mock.patch.dict(os.environ, {**routing, **authentication, "LINEAR_API_KEY": "synthetic"}):
            process = self.relay('import os, json; print(json.dumps(dict(os.environ)))')
        output, errors = process.communicate(timeout=5)
        self.assertEqual(0, process.returncode, errors)
        inherited = json.loads(output)
        for key in (*routing, "LINEAR_API_KEY"):
            self.assertNotIn(key, inherited)
        for key, value in authentication.items():
            self.assertEqual(value, inherited[key])

    def test_worker_entrypoint_uses_adapter_and_keeps_native_codex_config(self):
        config = {"project_dir": str(self.project), "workspace_root": str(self.root), "codex": "/native/codex"}
        with mock.patch.object(symphony_project, "load", return_value=config), \
             mock.patch.object(symphony_project, "workspace", return_value=self.cwd), \
             mock.patch.object(symphony_project, "worker_overrides", return_value=["-c", "skills.config=[]"]), \
             mock.patch.object(worker, "run_server", return_value=0) as run, \
             mock.patch.dict(os.environ, {"LINEAR_API_KEY": "synthetic-test-token"}), self.assertRaises(SystemExit):
            symphony_project.run_worker(self.project)
        self.assertEqual(["/native/codex", "-c", "skills.config=[]", "app-server"], run.call_args.args[0])
        self.assertNotIn("LINEAR_API_KEY", run.call_args.args[-1])
        self.assertEqual("symphony", run.call_args.args[-1]["SKILLS_SESSION_KIND"])

    def test_readiness_fails_when_git_isolation_fails(self):
        config = {"project_dir": str(self.project), "workspace_root": str(self.root), "codex": "/native/codex"}
        (self.project / ".symphony").mkdir()
        with mock.patch.object(symphony_project, "worker_overrides", return_value=[]), \
             mock.patch.object(symphony_project.install, "install_one"), \
             mock.patch.object(worker, "probe_git", side_effect=ValueError("Git denied")):
            self.assertEqual(["Worker Git/isolation probe failed: Git denied"], symphony_project.probe_worker(config))

    def test_fresh_workflow_keeps_native_cli_and_shared_worker_defaults(self):
        config = symphony_project.setup(self.project, project_id="synthetic", project_slug="synthetic",
                                       setup_issue="TEST-1", repo_url="git@example.invalid:synthetic/repo.git",
                                       codex="/native/codex")
        workflow = json.loads((self.project / ".symphony/WORKFLOW.md").read_text().split("---", 2)[1])
        self.assertEqual("/native/codex", config["codex"])
        self.assertEqual(30000, workflow["polling"]["interval_ms"])
        self.assertEqual(30000, workflow["codex"]["read_timeout_ms"])
        command = shlex.split(workflow["codex"]["command"])
        self.assertEqual("symphony_project.py", Path(command[1]).name)
        self.assertEqual("worker", command[2])

    @unittest.skipUnless(os.environ.get("SYMPHONY_TEST_CODEX"), "Set SYMPHONY_TEST_CODEX to run native sandbox proof")
    def test_native_git_commit_and_parent_sibling_denials(self):
        # /tmp is writable by default; place the fixture beside the checkout.
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1], prefix=".git-proof-") as raw:
            project = Path(raw).resolve()
            root = project / "workspaces"
            cwd = root / "worker"
            cwd.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "--template=", str(cwd)], check=True)
            (cwd / ".symphony-worker.json").write_text(json.dumps({"kind": "symphony", "project_dir": str(project)}))
            worker.probe_git(os.environ["SYMPHONY_TEST_CODEX"], project, root, cwd)
            subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd, check=True, stdout=subprocess.DEVNULL)
            self.assertFalse((root / "outside-worker").exists())
            self.assertFalse((root / "sibling/outside-worker").exists())
