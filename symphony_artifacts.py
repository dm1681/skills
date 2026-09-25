"""Project-scoped artifact publishing via an external, upload-only key file."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

import install

Error = install.InstallError
FIELD = "artifact_publish_token_file"


def validate(config: dict) -> None:
    value = config.get(FIELD, "")
    if not isinstance(value, str) or any(c in value for c in "\x00\n\r"):
        raise Error("artifact_publish_token_file must be a file path, never a token value")
    if not value:
        return
    path = Path(value)
    if not path.is_absolute():
        raise Error("Artifact publishing key path must be absolute and outside the repository")
    for root in (Path(config["project_dir"]).resolve(), Path(config["workspace_root"]).resolve()):
        if path.resolve() == root or root in path.resolve().parents:
            raise Error("Artifact publishing key must stay outside project and worker directories")


def environment(config: dict, env: dict) -> dict:
    validate(config)
    result = dict(env)
    if not config.get(FIELD):
        return result
    path = Path(config[FIELD])
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or
                (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
            raise ValueError("unsafe file")
        token = path.read_text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}\.[A-Za-z0-9_-]{43}", token):
            raise ValueError("invalid key")
    except (OSError, ValueError):
        raise Error("Artifact publishing key must be a readable owner-only regular file containing an upload-only publishing key") from None
    node = shutil.which("node", path=result.get("PATH", ""))
    try:
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10) if node else None
        if version is None or version.returncode or int(version.stdout.strip().lstrip("v").split(".")[0]) < 22:
            raise ValueError("Node unavailable")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise Error("Artifact publishing requires Node.js 22 or newer on the worker PATH") from None
    # The client prioritizes a raw token; remove it when a project selects a file.
    result.pop("ARTIFACT_PUBLISH_TOKEN", None)
    result["ARTIFACT_PUBLISH_TOKEN_FILE"] = str(path)
    return result


def probe(codex: str, cwd: Path, env: dict) -> None:
    """Verify sandbox access without uploading anything or printing the credential."""
    code = "const fs=require('node:fs'); const t=fs.readFileSync(process.env.ARTIFACT_PUBLISH_TOKEN_FILE,'utf8').trim(); if(!/^[A-Za-z0-9_-]{1,48}\\.[A-Za-z0-9_-]{43}$/.test(t)) process.exit(1); process.stdout.write('artifact-key-readable');"
    try:
        result = subprocess.run([codex, "-c", 'sandbox_mode="workspace-write"', "sandbox", "--", "node", "-e", code],
                                cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
        if result.returncode or result.stdout != "artifact-key-readable":
            raise ValueError("sandbox check failed")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise Error("Artifact publishing key or Node.js is unavailable inside the worker sandbox") from None
