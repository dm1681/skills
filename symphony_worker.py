"""Scoped Git access and bounded stdio relay for Linux Symphony workers."""
from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import sys
from pathlib import Path


def worker_environment(env: dict) -> dict:
    """Clear repository routing overrides while preserving transport authentication."""
    blocked = {
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_NAMESPACE", "GIT_SHALLOW_FILE", "LINEAR_API_KEY",
    }
    return {key: value for key, value in env.items() if key not in blocked}


def writable_roots(project: Path, root: Path, cwd: Path) -> list[str]:
    """Accept only a marked, standalone clone directly under the configured root."""
    for path in (project, root, cwd):
        if not path.is_absolute() or path != path.resolve():
            raise ValueError("Worker paths must be absolute and canonical")
    if cwd.parent != root or cwd == project or root == project or root in project.parents:
        raise ValueError("Worker must be inside its configured workspace root")
    marker_path = cwd / ".symphony-worker.json"
    if marker_path.is_symlink():
        raise ValueError("Worker marker must not be a symlink")
    marker = json.loads(marker_path.read_text())
    if not isinstance(marker, dict) or marker.get("kind") != "symphony" or marker.get("project_dir") != str(project):
        raise ValueError("Missing or mismatched Symphony worker identity")
    git = cwd / ".git"
    if git.is_symlink() or not git.is_dir() or (git / "commondir").exists():
        raise ValueError("Worker requires its own real .git directory, not a linked worktree")
    # Do not grant a Git subtree containing redirected metadata.
    def unreadable(error):
        raise error

    for directory, dirs, files in os.walk(git, onerror=unreadable):
        if any((Path(directory) / name).is_symlink() for name in dirs + files):
            raise ValueError("Worker Git metadata must not contain symlinks")
        if any((Path(directory) / name).stat().st_nlink > 1 for name in files):
            raise ValueError("Worker Git metadata must not contain shared hard links")
    return [str(cwd), str(git)]


def prepare_request(line: bytes, project: Path, root: Path, cwd: Path) -> bytes:
    request = json.loads(line)
    if not isinstance(request, dict):
        raise ValueError("Expected a JSON-RPC object")
    if request.get("method") != "turn/start":
        return line
    params = request.get("params")
    if not isinstance(params, dict) or params.get("cwd") != str(cwd):
        raise ValueError("Turn cwd must match the canonical worker directory")
    policy = params.get("sandboxPolicy")
    if not isinstance(policy, dict) or policy.get("type") != "workspaceWrite":
        raise ValueError("Worker turn must retain workspaceWrite sandbox")
    allowed = writable_roots(project, root, cwd)
    existing = policy.get("writableRoots", [])
    if not isinstance(existing, list) or any(path not in allowed for path in existing):
        raise ValueError("Unexpected writable roots outside the worker clone")
    # All other fields, including network and approval policy, pass through intact.
    policy["writableRoots"] = allowed
    return json.dumps(request).encode() + b"\n"


def run_server(command: list[str], project: Path, root: Path, cwd: Path, env: dict) -> int:
    """Relay requests only; native stdout/stderr go directly to Symphony."""
    writable_roots(project, root, cwd)
    child = subprocess.Popen(command, cwd=cwd, env=worker_environment(env), stdin=subprocess.PIPE, start_new_session=True)
    previous = {}

    def interrupt(signum, _frame):
        raise SystemExit(128 + signum)

    try:
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous[signum] = signal.signal(signum, interrupt)
        pending = b""
        while child.poll() is None:
            if not select.select([sys.stdin.fileno()], [], [], 0.2)[0]:
                continue
            block = os.read(sys.stdin.fileno(), 65536)
            if not block:
                if pending:
                    child.stdin.write(prepare_request(pending, project, root, cwd))
                child.stdin.close()
                return child.wait(timeout=10)
            pending += block
            if len(pending) > 16 * 1024 * 1024:
                raise ValueError("Worker request exceeds 16 MiB")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                child.stdin.write(prepare_request(line + b"\n", project, root, cwd))
                child.stdin.flush()
        return child.returncode
    except BrokenPipeError:
        return child.wait(timeout=10)
    finally:
        # Include descendants even when the direct child has already exited.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if not child.stdin.closed:
            child.stdin.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def probe_git(codex: str, project: Path, root: Path, cwd: Path, *, env=None) -> None:
    """A real synthetic commit plus denied parent/sibling writes; no model turn."""
    request = {"method": "turn/start", "params": {"cwd": str(cwd), "sandboxPolicy": {"type": "workspaceWrite"}}}
    policy = json.loads(prepare_request(json.dumps(request).encode(), project, root, cwd))["params"]["sandboxPolicy"]
    sibling = root / "sibling"
    sibling.mkdir()
    program = '''import errno, pathlib, subprocess, sys
subprocess.run(["git", "-c", "user.name=Sandbox Probe", "-c", "user.email=probe@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "sandbox readiness"], check=True, stdout=subprocess.DEVNULL)
for target in sys.argv[1:]:
    try:
        pathlib.Path(target).write_text("unexpected access")
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            continue
        raise
    raise SystemExit("sandbox allowed a write outside the worker clone")
print("git-isolation-ok")
'''
    env = worker_environment(os.environ if env is None else env)
    result = subprocess.run([
        codex, "-c", 'sandbox_mode="workspace-write"', "-c",
        "sandbox_workspace_write.writable_roots=" + json.dumps(policy["writableRoots"]),
        "sandbox", "--", sys.executable, "-c", program,
        str(root / "outside-worker"), str(sibling / "outside-worker"),
    ], cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
    if result.returncode or result.stdout.strip() != "git-isolation-ok":
        raise ValueError("Worker sandbox must allow a Git commit and deny parent/sibling writes")
