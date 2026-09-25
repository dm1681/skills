"""Explicit, bounded fresh-clone proofs. Never called by setup or service start."""
from __future__ import annotations

import json
import functools
import os
import re
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import uuid

from install import InstallError as Error
import symphony_bootstrap
import symphony_identity
import symphony_worker


def deadline_for(timeout):
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise Error("Rehearsal/validation timeout must be 1–3600 seconds")
    if sys.platform != "linux":
        raise Error("Fresh-clone validation and rehearsal require Linux/WSL")
    return time.monotonic() + timeout


def bounded(action):
    @functools.wraps(action)
    def invoke(*args, timeout=300, **kwargs):
        deadline_for(timeout)
        def expired(_signum, _frame):
            raise Error("Rehearsal/validation deadline exceeded")
        previous = signal.signal(signal.SIGALRM, expired)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            return action(*args, timeout=timeout, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous)
    return invoke


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise Error("Rehearsal/validation deadline exceeded; inspect retained evidence")
    return value


def stop(proc):
    # Terminate descendants even if their immediate parent has already exited.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run(command, cwd, env, deadline, *, strip=True):
    """Bound process groups and suppress potentially secret-bearing tool output."""
    with tempfile.TemporaryFile() as output:
        try:
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            raise Error("Rehearsal command unavailable; verify configured tools") from None
        try:
            try:
                code = proc.wait(timeout=remaining(deadline))
            except subprocess.TimeoutExpired:
                raise Error("Rehearsal/validation deadline exceeded") from None
            if code:
                raise Error(f"Rehearsal command failed (exit {code}); verify tools, bootstrap and declared validation")
            output.seek(0)
            result = output.read(1024 * 1024).decode(errors="replace")
            return result.strip() if strip else result
        finally:
            stop(proc)


def save(path, record):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def new_evidence(config, kind):
    root = Path(config["project_dir"]) / ".symphony" / "evidence"
    workspace_root = Path(config["workspace_root"]).resolve()
    if root.is_symlink() or root.resolve() == workspace_root or workspace_root in root.resolve().parents:
        raise Error("Evidence must be outside disposable worker workspaces and not symlinked")
    root.mkdir(parents=True, exist_ok=True)
    run_id = kind + "-" + uuid.uuid4().hex
    folder = root / run_id
    folder.mkdir(mode=0o700)
    path = folder / "evidence.json"
    record = {"schema": 1, "kind": kind, "run_id": run_id, "status": "running",
              "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checks": [],
              "service_changed": False, "merged": False}
    names = (["identity", "bootstrap", "validation"] if kind == "bootstrap" else
             ["account_repository_access", "bootstrap", "worker_turn", "synthetic_commit",
              "validation", "push", "draft_pr", "pr_readback"])
    record["checks"] = [{"name": name, "status": "skipped", "remediation": "Complete preceding stages first"}
                        for name in names]
    save(path, record)
    return path, record


def stage(path, record, name, action):
    row = next(row for row in record["checks"] if row["name"] == name)
    row.update(status="running", remediation="Wait for completion or inspect an interrupted run")
    save(path, record)
    try:
        result = action()
    except BaseException as exc:
        row.update(status="fail", remediation="Correct the failing prerequisite and explicitly invoke a new isolated run")
        record.update(status="fail", failure=type(exc).__name__)
        save(path, record)
        raise
    row.update(status="pass", remediation="None required")
    save(path, record)
    return result


def provision(project, config, cwd, env, deadline):
    import symphony_project as s
    run([sys.executable, str(Path(s.__file__).resolve()), "prepare-workspace", "--project-dir", str(project)],
        cwd, env, deadline)
    symphony_worker.writable_roots(project, Path(config["workspace_root"]).resolve(), cwd)
    # Even projects without declared bootstrap need a writable cache in the clone.
    return symphony_bootstrap.environment(config.get("bootstrap") or {"cache_dir": ".symphony-cache"},
                                          cwd, base_env=env)


def validate(config, project, cwd, env, deadline):
    roots = symphony_worker.writable_roots(project, Path(config["workspace_root"]).resolve(), cwd)
    run([config["codex"], "-c", 'sandbox_mode="workspace-write"', "-c",
         "sandbox_workspace_write.writable_roots=" + json.dumps(roots), "sandbox", "--",
         "bash", "-lc", config["validation_command"]], cwd, env, deadline)


def validate_commit(config, project, cwd, env, deadline, base, head, marker, expected):
    """Reprovision trusted base; never copy the worker's index or ignored files."""
    with tempfile.TemporaryDirectory(dir=cwd.parent, prefix="validation-") as raw:
        clean = Path(raw).resolve()
        clean_env = provision(project, config, clean, env, deadline)
        def git(*args):
            return run(["git", "-c", "core.hooksPath=/dev/null", *args], clean, clean_env, deadline)
        if git("rev-parse", "HEAD") != base:
            raise Error("Repository base moved during rehearsal; explicitly start a new run")
        # Fetch objects over Git transport, without copying worker metadata.
        git("fetch", "--no-tags", str(cwd), head)
        git("checkout", "--detach", head)
        committed = run(["git", "-c", "core.hooksPath=/dev/null", "show", f"{head}:{marker}"],
                        clean, clean_env, deadline, strip=False)
        if committed != expected:
            raise Error("Committed rehearsal marker differs from the requested content")
        validate(config, project, clean, clean_env, deadline)
        if git("rev-parse", "HEAD") != head:
            raise Error("Validation changed the recorded commit")
        if git("status", "--porcelain", "--untracked-files=no"):
            raise Error("Validation changed tracked files in the recorded commit")


def push_validated(config, cwd, env, deadline, head, branch):
    """Publish from fresh controller-owned Git metadata, never the worker's origin."""
    with tempfile.TemporaryDirectory(dir=cwd.parent, prefix="publication-") as raw:
        clean = Path(raw).resolve()
        run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-hardlinks", "--no-checkout",
             "--", symphony_identity.clone_url(config), str(clean)], cwd.parent, env, deadline)
        def git(*args):
            return run(["git", "-c", "core.hooksPath=/dev/null", *args], clean, env, deadline)
        git("fetch", "--no-tags", str(cwd), head)
        git("push", "origin", head + ":refs/heads/" + branch)


@bounded
def validate_fresh_clone(project: Path, *, timeout=300):
    import symphony_project as s
    project = project.resolve()
    deadline = deadline_for(timeout)
    config = s.load(project)
    path, record = new_evidence(config, "bootstrap")
    try:
        env = stage(path, record, "identity", lambda: symphony_identity.environment(config))
        root = Path(config["workspace_root"])
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root, prefix=record["run_id"] + "-") as raw:
            cwd = Path(raw).resolve()
            record["workspace"] = str(cwd)
            env = stage(path, record, "bootstrap", lambda: provision(project, config, cwd, env, deadline))
            stage(path, record, "validation", lambda: validate(config, project, cwd, env, deadline))
        record.update(status="pass", local_cleanup="complete")
        save(path, record)
        return path
    except (Error, OSError, ValueError, subprocess.SubprocessError):
        record.update(status="fail", local_cleanup="temporary clone removed")
        save(path, record)
        raise Error(f"Fresh-clone validation failed; evidence: {path}") from None


def model_turn(config, project, cwd, env, prompt, deadline):
    """One native app-server turn using production skill selection and Git policy."""
    import symphony_project as s
    allowed = {"HOME", "PATH", "LANG", "TERM", "USER", "LOGNAME", "CODEX_HOME", "CODEX_SQLITE_HOME",
               "XDG_RUNTIME_DIR", "XDG_CACHE_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR", "UV_OFFLINE",
               "UV_PYTHON_DOWNLOADS", "UV_PROJECT_ENVIRONMENT", "SYMPHONY_PYTHON"}
    env = {key: value for key, value in symphony_worker.worker_environment(env).items()
           if key in allowed or key.startswith("LC_")}
    overrides = s.worker_overrides(config, cwd, env=env)
    env["SKILLS_SESSION_KIND"] = "symphony"
    proc = subprocess.Popen([config["codex"], *overrides, "app-server"], cwd=cwd, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    buffer = b""
    turn_id = None

    def send(value):
        raw = json.dumps(value).encode() + b"\n"
        raw = symphony_worker.prepare_request(raw, project, Path(config["workspace_root"]).resolve(), cwd)
        proc.stdin.write(raw)
        proc.stdin.flush()
    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "skills-rehearsal", "version": "1"},
              "capabilities": {"experimentalApi": True}}})
        while True:
            if not selector.select(remaining(deadline)):
                raise Error("Rehearsal model turn timed out")
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                raise Error("Rehearsal worker exited before completing its turn")
            buffer += chunk
            if len(buffer) > 16 * 1024 * 1024:
                raise Error("Rehearsal protocol exceeded message limit")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if "error" in message:
                    raise Error("Rehearsal worker rejected a protocol request")
                if "method" in message and "id" in message:
                    # Never approve tools, prompts or privilege escalation.
                    raise Error("Rehearsal worker requested interactive approval; refused")
                if message.get("id") == 1:
                    send({"method": "initialized", "params": {}})
                    send({"id": 2, "method": "thread/start", "params": {
                        "cwd": str(cwd), "approvalPolicy": "never", "sandbox": "workspace-write", "ephemeral": True}})
                elif message.get("id") == 2:
                    thread_id = message["result"]["thread"]["id"]
                    send({"id": 3, "method": "turn/start", "params": {
                        "threadId": thread_id, "cwd": str(cwd), "approvalPolicy": "never",
                        "sandboxPolicy": {"type": "workspaceWrite", "networkAccess": False,
                                          "excludeTmpdirEnvVar": True, "excludeSlashTmp": True},
                        "input": [{"type": "text", "text": prompt}]}})
                elif message.get("id") == 3:
                    turn_id = message["result"]["turn"]["id"]
                elif message.get("method") == "turn/completed":
                    turn = message["params"]["turn"]
                    if not turn_id or turn["id"] != turn_id or turn["status"] != "completed":
                        raise Error("Rehearsal worker turn did not complete successfully")
                    return
    finally:
        selector.close()
        stop(proc)
        proc.stdin.close()
        proc.stdout.close()


@bounded
def rehearse(project: Path, *, accept=False, timeout=300):
    """Opt-in local worker -> verified synthetic commit -> draft PR; never merge."""
    import symphony_project as s
    if not accept:
        raise Error("Rehearsal requires --accept-rehearsal: one model turn, declared validation, remote branch and draft PR")
    project = project.resolve()
    deadline = deadline_for(timeout)
    config = s.load(project)
    if not config.get("github_repo"):
        raise Error("Rehearsal requires explicit repository, GitHub account and credential provider")
    path, record = new_evidence(config, "rehearsal")
    record["timeout_seconds"] = timeout
    root = Path(config["workspace_root"])
    cwd = root / record["run_id"]
    branch = "codex/" + record["run_id"]
    record.update(workspace=str(cwd), branch=branch, repository=config["github_repo"],
                  cleanup="Retain evidence; after Human Review close the recorded draft PR, delete only its branch and remove this workspace. Never merge the synthetic PR.")
    save(path, record)
    try:
        def access():
            issues = symphony_identity.check_access(config, "git") + symphony_identity.check_access(config, "pr")
            if issues:
                raise Error("; ".join(issues))
            return symphony_identity.environment(config)
        env = stage(path, record, "account_repository_access", access)
        cwd.mkdir(parents=True)
        env = stage(path, record, "bootstrap", lambda: provision(project, config, cwd, env, deadline))
        git_config = (cwd / ".git/config").read_bytes()
        env = {**env, "GIT_NO_REPLACE_OBJECTS": "1"}
        def git(*args):
            symphony_worker.writable_roots(project, root.resolve(), cwd)
            if (cwd / ".git/config").read_bytes() != git_config or (cwd / ".git/info/grafts").exists():
                raise Error("Worker changed Git configuration; refusing controller Git commands")
            return run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd, env, deadline)
        base = git("rev-parse", "HEAD")
        record["base_sha"] = base
        marker = "symphony-rehearsal.txt"
        if (cwd / marker).exists():
            raise Error("Synthetic rehearsal file already exists; preserve repository content")
        expected = record["run_id"] + "\n"
        prompt = ("This is an explicitly authorized synthetic readiness rehearsal, not a Linear issue. "
                  "Do not contact Linear, publish, merge, start services or run application workloads. "
                  f"Create only {marker} containing exactly {expected!r}. Commit only this file on the existing branch. "
                  "Use the configured Git identity; do not change Git config. Then finish. "
                  "The controller will validate and publish a draft PR for Human Review.")
        stage(path, record, "worker_turn", lambda: model_turn(config, project, cwd, env, prompt, deadline))
        def verify():
            if git("branch", "--show-current") != branch:
                raise Error("Worker changed rehearsal branch")
            if git("diff", "--name-only", base, "HEAD") != marker or git("status", "--porcelain"):
                raise Error("Worker changed files outside the synthetic commit or left uncommitted work")
            target = cwd / marker
            if target.is_symlink() or not target.is_file() or target.read_text() != expected:
                raise Error("Worker synthetic artifact did not match the requested content")
            if git("rev-list", "--count", base + "..HEAD") != "1":
                raise Error("Worker must produce exactly one synthetic commit")
            head = git("rev-parse", "HEAD")
            if git("rev-list", "--parents", "-n", "1", "HEAD") != head + " " + base:
                raise Error("Worker synthetic commit must have the recorded base as its sole parent")
            if git("remote", "get-url", "origin") != symphony_identity.clone_url(config):
                raise Error("Worker changed origin; refusing publication")
            return head
        record["head_sha"] = stage(path, record, "synthetic_commit", verify)
        stage(path, record, "validation", lambda: validate_commit(
            config, project, cwd, env, deadline, base, record["head_sha"], marker, expected))
        if verify() != record["head_sha"]:
            raise Error("Validation changed the synthetic commit")
        stage(path, record, "push", lambda: push_validated(config, cwd, env, deadline, record["head_sha"], branch))
        def publish():
            body = path.parent / "pr-body.md"
            body.write_text("Synthetic Symphony readiness rehearsal. One worker-created marker commit and declared validation passed.\n\nHuman Review required. Close this PR after inspection; do not merge. No service was changed.\n")
            url = run(["gh", "pr", "create", "--repo", config["github_repo"], "--base", config["base_branch"],
                        "--head", branch, "--draft", "--title", "Symphony synthetic readiness rehearsal",
                        "--body-file", str(body)], cwd, env, deadline)
            if not re.fullmatch(r"https://github\.com/" + re.escape(config["github_repo"]) + r"/pull/[0-9]+", url):
                raise Error("PR creation returned an unexpected URL; inspect the recorded branch")
            return url
        record["pr_url"] = stage(path, record, "draft_pr", publish)
        def readback():
            result = json.loads(run(["gh", "pr", "view", branch, "--repo", config["github_repo"],
                       "--json", "url,state,isDraft,headRefOid,baseRefName,baseRefOid"], cwd, env, deadline))
            if (result.get("state") != "OPEN" or not result.get("isDraft") or
                    result.get("headRefOid") != record["head_sha"] or result.get("baseRefName") != config["base_branch"] or
                    result.get("baseRefOid") != record["base_sha"] or
                    result.get("url") != record["pr_url"]):
                raise Error("Rehearsal PR readback did not match the validated commit and review boundary")
            record["pr_url"] = result["url"]
        stage(path, record, "pr_readback", readback)
        record.update(status="pass", review_boundary="Human Review", delivery="one synthetic worker-to-draft-PR run")
        save(path, record)
        return path
    except BaseException as exc:
        record.update(status="fail", failure=type(exc).__name__)
        save(path, record)
        raise Error(f"Rehearsal failed; retained workspace and evidence: {path}") from None
