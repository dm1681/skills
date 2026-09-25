"""Bounded stdio relay for dynamic model selection in Symphony workers."""
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


def prepare_request(line: bytes, cwd: Path, routing=None) -> bytes:
    if routing is None:
        return line
    request = json.loads(line)
    if not isinstance(request, dict):
        raise ValueError("Expected a JSON-RPC object")
    if request.get("method") != "turn/start":
        return line
    params = request.get("params")
    if not isinstance(params, dict) or params.get("cwd") != str(cwd):
        raise ValueError("Turn cwd must match the canonical worker directory")
    routing.apply(params)
    return json.dumps(request).encode() + b"\n"


def run_server(command: list[str], cwd: Path, env: dict, routing=None) -> int:
    """Relay requests only; native stdout/stderr go directly to Symphony."""
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
                    child.stdin.write(prepare_request(pending, cwd, routing))
                child.stdin.close()
                return child.wait(timeout=10)
            pending += block
            if len(pending) > 16 * 1024 * 1024:
                raise ValueError("Worker request exceeds 16 MiB")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                child.stdin.write(prepare_request(line + b"\n", cwd, routing))
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
