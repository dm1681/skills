"""Optional fresh-clone prerequisites; no service or application startup."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from install import InstallError as Error


def validate(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise Error("bootstrap must be a JSON object")
    unknown = spec.keys() - {"python", "python_version", "dependencies", "download_policy",
                             "cache_dir", "required_tools", "timeout_seconds"}
    if unknown:
        raise Error("Unknown bootstrap fields: " + ", ".join(sorted(unknown)))
    for key in ("python", "python_version", "dependencies", "download_policy", "cache_dir"):
        if key in spec and (not isinstance(spec[key], str) or not spec[key] or
                            any(c in spec[key] for c in "\x00\n\r")):
            raise Error(f"bootstrap.{key} must be a nonempty string without control characters")
    if "python_version" in spec and not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", spec["python_version"]):
        raise Error("bootstrap.python_version must be major.minor or major.minor.patch")
    if spec.get("dependencies", "none") not in ("none", "uv"):
        raise Error("bootstrap.dependencies must be none or uv (locked sync)")
    if ("python_version" in spec or spec.get("dependencies") == "uv") and "python" not in spec:
        raise Error("Declare bootstrap.python as a preinstalled executable for version checks or uv sync")
    if spec.get("download_policy", "never") not in ("never", "allow"):
        raise Error("bootstrap.download_policy must be never or allow")
    cache = Path(spec.get("cache_dir", ".symphony-cache"))
    if (cache.is_absolute() or ".." in cache.parts or cache == Path(".") or
            cache.parts[0] in (".git", ".agents", ".venv") or
            any(c in str(cache) for c in "*?[]!\\")):
        raise Error("bootstrap.cache_dir must be a workspace-relative directory outside .git and .agents")
    tools = spec.get("required_tools", [])
    if not isinstance(tools, list) or any(not isinstance(t, str) or not t or any(c in t for c in "\x00\n\r") for t in tools):
        raise Error("bootstrap.required_tools must be a list of executable names or absolute paths")
    for executable in [*tools, *([spec["python"]] if "python" in spec else [])]:
        if not Path(executable).is_absolute() and ("/" in executable or "\\" in executable):
            raise Error("Bootstrap executables must be PATH names or absolute preinstalled paths")
    if type(spec.get("timeout_seconds", 300)) is not int or not 1 <= spec.get("timeout_seconds", 300) <= 3600:
        raise Error("bootstrap.timeout_seconds must be an integer from 1 to 3600")


def executable(name: str, env: dict) -> str:
    found = shutil.which(name, path=env.get("PATH", os.defpath))
    if not found:
        raise Error(f"Bootstrap executable unavailable: {name}; preinstall it in the service environment or configure an absolute path")
    return str(Path(found).absolute())


def environment(spec: dict, cwd: Path, *, base_env=None) -> dict:
    """Check local prerequisites and return the same environment for hook/worker."""
    validate(spec)
    env = dict(os.environ if base_env is None else base_env)
    if not spec:
        return env
    # An interactive venv must not select the worker's interpreter/dependencies.
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    for tool in spec.get("required_tools", []):
        executable(tool, env)
    if "python" in spec:
        python = executable(spec["python"], env)
        try:
            probe = subprocess.run([python, "-I", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                                   cwd=cwd, env=env, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Error(f"Bootstrap Python probe failed: {python}; check the preinstalled interpreter") from exc
        actual = probe.stdout.strip()
        expected = spec.get("python_version")
        if probe.returncode or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", actual):
            raise Error(f"Bootstrap Python probe failed: {python}; expected a runnable Python interpreter")
        if expected and actual.split(".")[:len(expected.split("."))] != expected.split("."):
            raise Error(f"Bootstrap Python version mismatch: expected {expected}, found {actual}; select a matching preinstalled interpreter")
        env["SYMPHONY_PYTHON"] = env["UV_PYTHON"] = python
    cache = cwd / spec.get("cache_dir", ".symphony-cache")
    if cwd.resolve() not in cache.resolve().parents:
        raise Error("Bootstrap cache resolves outside the worker workspace")
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=cache):
            pass
    except OSError as exc:
        raise Error(f"Bootstrap cache is not writable: {cache}; choose a writable workspace-relative cache_dir") from exc
    env.update({"XDG_CACHE_HOME": str(cache), "UV_CACHE_DIR": str(cache / "uv"),
                "PIP_CACHE_DIR": str(cache / "pip"), "UV_PYTHON_DOWNLOADS": "never",
                "UV_OFFLINE": "true" if spec.get("download_policy", "never") == "never" else "false",
                "UV_PROJECT_ENVIRONMENT": str(cwd / ".venv")})
    if spec.get("dependencies") == "uv":
        executable("uv", env)
        if cwd.resolve() not in (cwd / ".venv").resolve().parents:
            raise Error("Bootstrap .venv resolves outside the worker workspace")
    return env


def prepare(spec: dict, cwd: Path, *, base_env=None) -> None:
    env = environment(spec, cwd, base_env=base_env)
    if spec.get("dependencies") != "uv":
        return
    if not (cwd / "uv.lock").is_file() or not (cwd / "pyproject.toml").is_file():
        raise Error("Bootstrap uv sync requires committed pyproject.toml and uv.lock; generate and commit the lockfile first")
    command = [executable("uv", env), "sync", "--locked", "--project", str(cwd),
               "--python", env["SYMPHONY_PYTHON"], "--no-python-downloads"]
    if spec.get("download_policy", "never") == "never":
        command.append("--offline")
    try:
        result = subprocess.run(command, cwd=cwd, env=env, timeout=spec.get("timeout_seconds", 300))
    except subprocess.TimeoutExpired as exc:
        raise Error("Bootstrap uv sync timed out; check dependency availability or increase timeout_seconds") from exc
    except OSError as exc:
        raise Error("Bootstrap could not launch uv; check its installation and permissions") from exc
    if result.returncode:
        raise Error(f"Bootstrap uv sync failed (exit {result.returncode}); check uv.lock and cached dependencies; "
                    "download_policy=never requires dependencies already cached")
