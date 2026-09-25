"""Project worker identity: public settings on disk, credentials only at runtime."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import install
import symphony_worker

Error = install.InstallError
FIELDS = (
    "git_author_name", "git_author_email", "ssh_host", "ssh_config",
    "ssh_executable", "github_repo", "github_account", "credential_provider",
)


def repository_path(url: str) -> str:
    """Extract owner/repository without resolving an SSH alias through DNS."""
    if "://" in url:
        parsed = urlsplit(url)
        if parsed.password or parsed.query or parsed.fragment or (parsed.scheme != "ssh" and parsed.username):
            raise Error("Repository URL must not contain credentials, query or fragment")
        path = parsed.path.lstrip("/")
    else:
        match = re.fullmatch(r"(?:git@)?[A-Za-z0-9.-]+:(.+)", url)
        path = match[1] if match else ""
    return path.removesuffix(".git")


def validate(config: dict) -> None:
    for key in FIELDS:
        value = config.get(key, "")
        if not isinstance(value, str) or any(c in value for c in "\x00\r\n"):
            raise Error(f"Invalid {key}: expected a single-line string")
    if bool(config.get("git_author_name")) != bool(config.get("git_author_email")):
        raise Error("Configure both git_author_name and git_author_email")
    for key in ("ssh_config", "credential_provider"):
        if config.get(key) and not Path(config[key]).is_absolute():
            raise Error(f"{key} must be an absolute path, with no command arguments or secrets")
    if config.get("ssh_host") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", config["ssh_host"]):
        raise Error("ssh_host must be a hostname or SSH alias")
    repo = config.get("github_repo", "")
    if repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise Error("github_repo must be owner/repository on github.com")
    account = config.get("github_account", "")
    if account and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", account):
        raise Error("github_account must be a GitHub login")
    if repo or account or config.get("credential_provider"):
        if not all(config.get(key) for key in ("github_repo", "github_account", "credential_provider")):
            raise Error("Explicit GitHub identity requires github_repo, github_account and credential_provider")
    url = config.get("repo_url", "")
    path = repository_path(url)
    if repo and path.casefold() != repo.casefold():
        raise Error("github_repo must match repo_url owner/repository")
    if repo and "://" in url:
        parsed = urlsplit(url)
        if parsed.scheme not in ("ssh", "https") or (parsed.scheme == "https" and parsed.hostname != "github.com"):
            raise Error("GitHub identity requires a github.com HTTPS URL or SSH transport")
    if config.get("ssh_host") and not path:
        raise Error("ssh_host requires a repository URL containing owner/repository")


def clone_url(config: dict) -> str:
    validate(config)
    if config.get("ssh_host"):
        return f"git@{config['ssh_host']}:{repository_path(config['repo_url'])}.git"
    if "://" in config["repo_url"]:
        return urlsplit(config["repo_url"]).geturl()
    return config["repo_url"]


def run(command: list[str], *, env: dict, cwd: Path, failure: str, timeout=30) -> subprocess.CompletedProcess:
    """Never relay subprocess output or exception details containing credentials."""
    try:
        result = subprocess.run(command, cwd=cwd, env=dict(env), capture_output=True, text=True, timeout=timeout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise Error(failure + " (unavailable or timed out)") from None
    if result.returncode:
        raise Error(failure) from None
    return result


def environment(config: dict, inherited=None, *, credentials=True) -> dict:
    """Return a fresh worker-only environment; never change global Git/gh state."""
    validate(config)
    env = symphony_worker.worker_environment(dict(os.environ if inherited is None else inherited))
    configured = any(config.get(key) for key in FIELDS)
    if not configured:
        return env
    # Ambient overrides could route another project's commands or leak diagnostics.
    for key in list(env):
        if key.startswith(("GIT_CONFIG_", "GIT_TRACE")) or key in {
            "GIT_CONFIG", "GIT_CURL_VERBOSE", "GH_DEBUG",
        }:
            env.pop(key)
    if config.get("github_repo"):
        for key in ("GH_HOST", "GH_REPO", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            env.pop(key, None)
    if config.get("git_author_name"):
        for role in ("AUTHOR", "COMMITTER"):
            env[f"GIT_{role}_NAME"] = config["git_author_name"]
            env[f"GIT_{role}_EMAIL"] = config["git_author_email"]
        env.pop("EMAIL", None)
    if any(config.get(key) for key in ("ssh_host", "ssh_config", "ssh_executable")):
        command = [config.get("ssh_executable") or "ssh"]
        if config.get("ssh_config"):
            if not Path(config["ssh_config"]).is_file():
                raise Error("Configured ssh_config is unavailable to this worker")
            command += ["-F", config["ssh_config"]]
        command += ["-o", "BatchMode=yes"]
        env.pop("GIT_SSH", None)
        env["GIT_SSH_COMMAND"] = shlex.join(command)
        env["GIT_SSH_VARIANT"] = "ssh"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if config.get("github_repo"):
        env.update(GH_HOST="github.com", GH_REPO=config["github_repo"], GH_PROMPT_DISABLED="1")
    if credentials and config.get("credential_provider"):
        cwd = Path(config["project_dir"])
        env["SYMPHONY_GITHUB_ACCOUNT"] = config["github_account"]
        result = run([config["credential_provider"]], env=env, cwd=cwd,
                     failure="Credential provider failed; verify its executable and runtime secret access")
        token = result.stdout.strip()
        if not token or len(token) > 16384 or any(c.isspace() or ord(c) < 32 for c in token):
            raise Error("Credential provider must return one nonempty token on stdout")
        env["GH_TOKEN"] = token
        login = run(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"],
                    env=env, cwd=cwd, failure="GitHub identity check failed; verify provider token and API access")
        if login.stdout.strip().casefold() != config["github_account"].casefold():
            raise Error("Credential provider account differs from github_account; refusing worker launch")
        # HTTPS Git uses the same runtime token through gh, without putting it in
        # arguments, remote URLs, config files or credential-store.
        env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0="",
                   GIT_CONFIG_KEY_1="credential.https://github.com.helper",
                   GIT_CONFIG_VALUE_1="!gh auth git-credential")
    return env


def check_access(config: dict, kind: str) -> list[str]:
    """Read-only checks: transport refs separately from GitHub PR API permissions."""
    try:
        if kind == "git":
            # SSH access does not depend on an API token. HTTPS does.
            url = clone_url(config)
            env = environment(config, credentials=urlsplit(url).scheme == "https")
            run(["git", "ls-remote", "--exit-code", "--", url, "HEAD"], env=env,
                cwd=Path(config["project_dir"]),
                failure="Git access failed; verify repo_url, SSH alias/config and key or HTTPS provider access")
        elif kind == "pr":
            if not config.get("github_repo"):
                raise Error("PR access check requires explicit github_repo (owner/repository)")
            env = environment(config)
            repo = config["github_repo"]
            result = run(["gh", "api", "--hostname", "github.com", f"repos/{repo}", "--jq", ".permissions.push"],
                         env=env, cwd=Path(config["project_dir"]),
                         failure="GitHub repository access failed; verify provider account and repository permissions")
            if result.stdout.strip() != "true":
                raise Error("GitHub account lacks repository push permission; PR writes are not ready")
            run(["gh", "api", "--hostname", "github.com", f"repos/{repo}/pulls?per_page=1"],
                env=env, cwd=Path(config["project_dir"]),
                failure="GitHub PR read access failed; verify provider pull-request permissions")
        else:
            raise Error("Unknown identity access check")
    except Error as exc:
        return [str(exc)]
    return []
