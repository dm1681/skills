"""Project-scoped Symphony setup, readiness and launch; upstream owns dispatch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import install
import symphony_bootstrap
import symphony_worker

REVISION = "be10a1b79df723d6d7612b5651c8522704dafb2e"
UPSTREAM = "https://github.com/openai/symphony.git"
RESOURCES = Path(__file__).resolve().parent / "templates" / "symphony"
WORKER_SKILLS = ("codebase-design", "diagnosing-bugs", "tdd", "research", "writing-for-agents", "claude-handoff")
DELIVERY_SKILLS = ("linear", "commit", "pull", "push", "land")
RUNTIME_ASSETS = {
    "x86_64": ("linux_x86_64", "08d7aac26747fdc14022ade870cf7e530a6343ab92a040f39a4294b27a0cd5af"),
    "aarch64": ("linux_arm64", "d98a9c91b34b0f48897cff228b4f31f3551c0359db35777a669a95fc9a2f75f0"),
}
PREVIEW_FLAG = "--i-understand-that-this-will-be-running-without-the-usual-guardrails"
Error = install.InstallError


def config_path(project: Path) -> Path:
    return project.resolve() / ".symphony" / "project.json"


def load(project: Path) -> dict:
    path = config_path(project)
    if path.parent.is_symlink() or path.is_symlink():
        raise Error("Symphony configuration must be project-local, not a symlink")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Error("Run skills symphony setup for this project first") from exc
    if not isinstance(data, dict) or data.get("schema") != 1 or data.get("project_dir") != str(project.resolve()):
        raise Error("Invalid or relocated Symphony configuration; rerun setup explicitly")
    validate_config(data)
    return data


def validate_config(config: dict) -> None:
    """Recheck editable configuration before setup writes or runtime actions."""
    symphony_bootstrap.validate(config.get("bootstrap", {}))
    for key in ("project_dir", "runtime_source", "workspace_root", "codex", "revision",
                "repo_url", "base_branch", "project_id", "project_slug", "setup_issue",
                "validation_command"):
        value = config.get(key)
        if not isinstance(value, str) or "\x00" in value:
            raise Error(f"Invalid {key}: expected a string without NUL characters")
        if key != "validation_command" and any(c in value for c in ("\n", "\r")):
            raise Error(f"Invalid newline in {key}")
    for key in ("project_dir", "runtime_source", "workspace_root"):
        if not Path(config[key]).is_absolute():
            raise Error(f"Invalid {key}: expected an absolute path")
    if not config["codex"] or not config["base_branch"]:
        raise Error("Codex executable and base branch must not be empty")
    if config.get("dashboard_port") is not None and (type(config["dashboard_port"]) is not int or not 1 <= config["dashboard_port"] <= 65535):
        raise Error("Dashboard port must be between 1 and 65535")
    if "dashboard_port" not in config:
        raise Error("Missing dashboard_port in Symphony configuration")
    generated = config.get("generated")
    if not isinstance(generated, dict) or any(not isinstance(value, str) for value in generated.values()):
        raise Error("Invalid generated-file hashes in Symphony configuration")
    project = Path(config["project_dir"]).resolve()
    root = Path(config["workspace_root"]).resolve()
    if root == project or root in project.parents:
        raise Error("Workspace root must not be the interactive project or its ancestor")
    if config["revision"] != REVISION:
        raise Error("Runtime revision differs from the supported pin")


def write_managed(path: Path, text: str, old_hash: str = "") -> str:
    if path.is_symlink():
        raise Error(f"Refusing managed-file symlink: {path}")
    if path.exists():
        before = path.read_bytes()
        if before == text.encode():
            return hashlib.sha256(before).hexdigest()
        if hashlib.sha256(before).hexdigest() != old_hash:
            raise Error(f"Preserving edited file: {path}; reconcile it before setup")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    # Hash and persist the same bytes on every host; text-mode newline
    # translation would otherwise make our own output look like a user edit.
    with temporary.open("xb") as stream:
        stream.write(text.encode("utf-8"))
    temporary.replace(path)
    return hashlib.sha256(text.encode()).hexdigest()


def setup(project: Path, **options) -> dict:
    project = project.resolve()
    if not project.is_dir():
        raise Error(f"Project does not exist: {project}")
    if (project / ".symphony").is_symlink():
        raise Error(".symphony must be a project-local directory")
    path = config_path(project)
    if path.is_symlink():
        raise Error("Project configuration must not be a symlink")
    previous = load(project) if path.exists() else {}
    config = dict(previous) if previous else {
        "schema": 1, "project_dir": str(project), "project_id": "", "project_slug": "",
        "setup_issue": "", "runtime_source": str(project / ".symphony" / "runtime"),
        "codex": shutil.which("codex") or "codex", "dashboard_port": 8788,
        "workspace_root": str(project / ".symphony" / "workspaces"),
        "revision": REVISION, "repo_url": "", "base_branch": "main",
        "validation_command": "", "generated": {},
    }
    dashboard_enabled = options.pop("dashboard_enabled", None)
    for key, value in options.items():
        if value is not None:
            config[key] = str(value) if isinstance(value, Path) else value
    if dashboard_enabled is False:
        config["dashboard_port"] = None
    if not config["repo_url"]:
        result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=project, capture_output=True, text=True)
        config["repo_url"] = result.stdout.strip() if result.returncode == 0 else ""
    for key in ("runtime_source", "workspace_root"):
        if not isinstance(config[key], str) or not config[key]:
            raise Error(f"Invalid {key}: expected a nonempty path")
        config[key] = str(Path(config[key]).expanduser().resolve())
    # Apply the same checks when creating and loading machine-local settings.
    validate_config(config)
    workflow = render_workflow(config)
    target = project / ".symphony" / "WORKFLOW.md"
    digest = write_managed(target, workflow, previous.get("generated", {}).get("WORKFLOW.md", ""))
    config["generated"] = {"WORKFLOW.md": digest}
    # Configuration is intentionally editable; setup merges provided fields only.
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def command_string(config: dict, action: str) -> str:
    return shlex.join([sys.executable, str(Path(__file__).resolve()), action, "--project-dir", config["project_dir"]])


def render_workflow(config: dict) -> str:
    # JSON is a YAML subset; use it for unambiguous quoting without a YAML dependency.
    document = {
        "tracker": {"kind": "linear", "provider": {"project_slug": config["project_slug"]},
                    "active_states": ["Todo", "In Progress", "Merging", "Rework"],
                    "terminal_states": ["Closed", "Cancelled", "Canceled", "Duplicate", "Done"]},
        "polling": {"interval_ms": 30000}, "workspace": {"root": config["workspace_root"]},
        "hooks": {"after_create": command_string(config, "prepare-workspace")},
        "agent": {"max_concurrent_agents": 1, "max_turns": 20},
        "codex": {"command": command_string(config, "worker"), "approval_policy": "never", "read_timeout_ms": 30000,
                  "thread_sandbox": "workspace-write", "turn_sandbox_policy": {"type": "workspaceWrite", "networkAccess": True}},
        "server": {"host": "127.0.0.1", "port": config["dashboard_port"]},
    }
    if config.get("bootstrap", {}).get("dependencies") == "uv":
        document["hooks"]["timeout_ms"] = (config["bootstrap"].get("timeout_seconds", 300) + 60) * 1000
    prompt = (RESOURCES / "WORKFLOW.md").read_text(encoding="utf-8").replace("<base_branch>", config["base_branch"])
    return "---\n" + json.dumps(document, indent=2) + "\n---\n\n" + prompt


def linear_gate(config: dict, query=None) -> dict:
    for key in ("project_id", "project_slug", "setup_issue"):
        if not config.get(key):
            raise Error(f"Missing {key}; record the exact pilot project and setup issue")
    if query is None:
        token = os.environ.get("LINEAR_API_KEY")
        if not token:
            raise Error("LINEAR_API_KEY is unavailable; setup issue cannot be verified")
        def query(document, variables):
            request = urllib.request.Request("https://api.linear.app/graphql", data=json.dumps({"query": document, "variables": variables}).encode(), headers={"Content-Type": "application/json", "Authorization": token})
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    value = json.load(response)
            except (OSError, ValueError) as exc:
                raise Error("Linear readiness lookup failed; no workers started") from exc
            if value.get("errors") or not isinstance(value.get("data"), dict):
                raise Error("Linear did not return verifiable readiness data")
            return value["data"]
    try:
        data = query("query Setup($id: String!) { issue(id: $id) { id identifier state { name type } project { id slugId } team { states { nodes { name } } } } }", {"id": config["setup_issue"]})
        issue = data["issue"]
        if config["setup_issue"] not in (issue["id"], issue["identifier"]):
            raise Error("Linear returned a different setup issue")
        if issue["project"]["id"] != config["project_id"] or issue["project"]["slugId"] != config["project_slug"]:
            raise Error("Setup issue does not belong to the configured Symphony project")
        if issue["state"]["name"] != "Done" or issue["state"]["type"] != "completed":
            raise Error("Setup issue must be Done after human review of setup evidence")
        states = {row["name"] for row in issue["team"]["states"]["nodes"]}
        required = {"Backlog", "Todo", "In Progress", "Human Review", "Merging", "Rework", "Done"}
        if required - states:
            raise Error("Linear team is missing Symphony states: " + ", ".join(sorted(required - states)))
    except (KeyError, TypeError) as exc:
        raise Error("Setup issue is missing, inaccessible or unverifiable") from exc
    return issue


def runtime_binary(config: dict) -> Path:
    source = Path(config["runtime_source"])
    return source / "bin/symphony" if (source / "package.json").is_file() else source / "elixir/bin/symphony"


def install_runtime(project: Path) -> None:
    """Install the digest-pinned official binary; never execute it during setup."""
    config = load(project)
    if sys.platform != "linux" or platform.machine() not in RUNTIME_ASSETS:
        raise Error("No pinned binary for this platform; use the documented source build")
    target = Path(config["runtime_source"])
    if target.exists():
        verify_runtime(config)
        print(f"Verified existing runtime: {target}")
        return
    name, digest = RUNTIME_ASSETS[platform.machine()]
    url = f"https://github.com/openai/symphony/releases/download/nightly/symphony-nightly-{name}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except OSError as exc:
        raise Error("Pinned runtime download failed; build-runtime is the source alternative") from exc
    if hashlib.sha256(data).hexdigest() != digest:
        raise Error("Rolling nightly no longer matches the reviewed pin; use build-runtime, not the newer binary")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix="symphony-package-") as raw:
        staging = Path(raw) / "runtime"
        (staging / "bin").mkdir(parents=True)
        binary = staging / "bin/symphony"
        binary.write_bytes(data); binary.chmod(0o755)
        (staging / "package.json").write_text(json.dumps({"revision": REVISION, "target": name, "sha256": digest, "url": url}, indent=2) + "\n")
        staging.rename(target)
    print(f"Installed verified upstream runtime at {target}; no workers started")


def verify_runtime(config: dict) -> Path:
    source = Path(config["runtime_source"])
    if (source / "package.json").is_file():
        try:
            record = json.loads((source / "package.json").read_text())
            name, digest = RUNTIME_ASSETS[platform.machine()]
            binary = source / "bin/symphony"
            if record["revision"] != REVISION or record["target"] != name or record["sha256"] != digest or binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest() != digest:
                raise Error("Packaged Symphony runtime failed integrity verification")
        except (KeyError, ValueError, OSError) as exc:
            raise Error("Packaged Symphony runtime is invalid or incomplete") from exc
        return source
    if not (source / ".git").exists():
        raise Error("Runtime source is missing; run skills symphony build-runtime")
    if install.checkout_head(source) != REVISION:
        raise Error("Symphony source is not at the supported revision")
    if install.checkout_worktree_changes(source) != "" or install.checkout_content_mismatches(source, prefix="") != []:
        raise Error("Symphony source differs from the verified revision")
    return source


def build_runtime(project: Path) -> None:
    config = load(project)
    if sys.platform != "linux":
        raise Error("This integration targets Linux/WSL; the native Windows port is separate")
    for binary in ("git", "mix", "erl"):
        if not shutil.which(binary):
            raise Error(f"{binary} is required; install upstream's Erlang 28 / Elixir 1.19.5-otp-28 toolchain first")
    source = Path(config["runtime_source"])
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=source.parent, prefix="runtime-fetch-") as raw:
            staging = Path(raw) / "source"
            staging.mkdir()
            for command in install.upstream_fetch_commands(UPSTREAM, REVISION):
                subprocess.run(command, cwd=staging, check=True, env={**os.environ, **install.UPSTREAM_GIT_ENV})
            verify_runtime({**config, "runtime_source": str(staging)})
            staging.rename(source)
    verify_runtime(config)
    for command in (["mix", "deps.get"], ["mix", "build"]):
        subprocess.run(command, cwd=source / "elixir", check=True)


def probe_worker(config: dict) -> list[str]:
    """Exercise discovery and the configured Linux sandbox without a model turn."""
    problems = []
    probe_parent = Path(config["workspace_root"])
    probe_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=probe_parent, prefix="readiness-") as raw:
        root = Path(raw)
        cwd = root / "worker"
        cwd.mkdir()
        try:
            symphony_bootstrap.environment(config.get("bootstrap", {}), cwd)
        except Error as exc:
            problems.append(str(exc))
        subprocess.run(["git", "init", "--quiet", "--template="], cwd=cwd, check=True)
        (cwd / ".symphony-worker.json").write_text(json.dumps({"kind": "symphony", "project_dir": config["project_dir"]}))
        for name in WORKER_SKILLS:
            install.install_one(install.SOURCE_ROOT / name, cwd / ".agents/skills", "copy", False, False)
        for name in DELIVERY_SKILLS:
            install.install_one(RESOURCES / "skills" / name, cwd / ".agents/skills", "copy", False, False)
        try:
            worker_overrides(config, cwd)
        except (Error, OSError) as exc:
            problems.append("Worker discovery failed: " + str(exc))
        try:
            symphony_worker.probe_git(config["codex"], Path(config["project_dir"]), root, cwd)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            problems.append("Worker Git/isolation probe failed: " + str(exc))
    return problems


def authentication_problems(config: dict) -> list[str]:
    """Check CLI login without exposing credential-bearing diagnostic output."""
    problems = []
    probes = (
        ("gh", ["auth", "status", "--hostname", "github.com"],
         "GitHub CLI is not authenticated; run gh auth login in the service environment"),
        (config["codex"], ["login", "status"],
         "Codex is not authenticated; log in with the configured executable"),
    )
    for executable, args, message in probes:
        if not shutil.which(executable):
            continue  # The executable check already reports this prerequisite.
        try:
            result = subprocess.run([executable, *args], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            problems.append(f"Authentication check failed or timed out: {Path(executable).name}")
        else:
            if result.returncode != 0:
                problems.append(message)
    return problems


def check(project: Path, *, remote=True) -> list[str]:
    config = load(project)
    problems = []
    for key in ("repo_url", "validation_command"):
        if not config.get(key):
            problems.append(f"Missing {key}; supply the project's repository and validation command")
    if sys.platform != "linux":
        problems.append("Only Linux/WSL is supported by this integration")
    for binary in ("git", "bash", "sh", "gh", config["codex"]):
        if not shutil.which(binary):
            problems.append(f"Required executable is unavailable: {binary}")
    try:
        source = verify_runtime(config)
        if not (source / "package.json").is_file() and not shutil.which("erl"):
            problems.append("Erlang is required for the source-built escript")
        if not runtime_binary(config).is_file():
            problems.append("Symphony executable is missing; run skills symphony build-runtime")
    except Error as exc:
        problems.append(str(exc))
    workflow = project.resolve() / ".symphony" / "WORKFLOW.md"
    if not workflow.is_file() or workflow.is_symlink() or workflow.read_text() != render_workflow(config):
        problems.append("Generated WORKFLOW.md does not match project configuration; rerun setup")
    if shutil.which(config["codex"]) and shutil.which("git"):
        problems.extend(probe_worker(config))
    if remote:
        problems.extend(authentication_problems(config))
        try:
            linear_gate(config)
        except Error as exc:
            problems.append(str(exc))
    else:
        problems.append("Linear setup-issue gate not checked offline; startup readiness is unverified")
    return problems


def workspace(config: dict) -> Path:
    cwd = Path.cwd().resolve()
    root = Path(config["workspace_root"]).resolve()
    if cwd.parent != root or cwd == Path(config["project_dir"]).resolve():
        raise Error("Worker hook must run in a direct issue workspace under its configured root")
    return cwd


def prepare_workspace(project: Path) -> None:
    config = load(project)
    cwd = workspace(config)
    if any(cwd.iterdir()):
        raise Error("New issue workspace is not empty; preserving its contents")
    if not config["repo_url"] or not config["validation_command"]:
        raise Error("Repository URL and validation command must be configured")
    branch = f"codex/{cwd.name}"
    for ref in (branch, config["base_branch"]):
        subprocess.run(["git", "check-ref-format", "--branch", ref], cwd=cwd, check=True, capture_output=True)
    subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout", "--", config["repo_url"], "."], cwd=cwd, check=True)
    # Recover a published issue branch after workspace cleanup, otherwise branch
    # from the configured base (which need not be the remote's default branch).
    remote_branch = f"refs/remotes/origin/{branch}"
    exists = subprocess.run(["git", "show-ref", "--verify", "--quiet", remote_branch], cwd=cwd)
    if exists.returncode not in (0, 1):
        raise Error("Could not verify the remote issue branch")
    source = remote_branch if exists.returncode == 0 else f"refs/remotes/origin/{config['base_branch']}"
    subprocess.run(["git", "checkout", "--no-track", "-b", branch, source], cwd=cwd, check=True)
    # Preserve project instructions. Only the worker's skill roots are provisioned.
    root = cwd / ".agents" / "skills"
    if cwd not in root.resolve().parents:
        raise Error("Project skill root resolves outside the issue workspace")
    for name in WORKER_SKILLS:
        install.install_one(install.SOURCE_ROOT / name, root, "copy", False, False)
    for name in DELIVERY_SKILLS:
        install.install_one(RESOURCES / "skills" / name, root, "copy", False, False)
    install.write_receipt(root, list(WORKER_SKILLS + DELIVERY_SKILLS), "copy", False)
    bootstrap = config.get("bootstrap", {})
    symphony_bootstrap.prepare(bootstrap, cwd)
    context = {"kind": "symphony", "project_dir": config["project_dir"], "base_branch": config["base_branch"], "validation_command": config["validation_command"], "bootstrap": bootstrap}
    (cwd / ".symphony-worker.json").write_text(json.dumps(context, indent=2) + "\n")
    # Worker provisioning must never become part of the feature PR.
    with (cwd / ".git" / "info" / "exclude").open("a") as stream:
        stream.write("\n/.agents/skills/\n/.symphony-worker.json\n")
        if bootstrap:
            stream.write("/" + bootstrap.get("cache_dir", ".symphony-cache") + "/\n/.venv/\n")


def skills_list(codex: str, cwd: Path, overrides=(), timeout=20) -> list[dict]:
    """Protocol-only discovery: no thread or model turn, bounded process lifetime."""
    command = [codex, *overrides, "app-server"]
    env = dict(os.environ)
    env.pop("LINEAR_API_KEY", None)
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        buffer = b""
        def send(value):
            proc.stdin.write((json.dumps(value) + "\n").encode()); proc.stdin.flush()
        try:
            send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "skills-symphony-check", "version": "1.0"}, "capabilities": {"experimentalApi": True}}})
            while time.monotonic() < deadline:
                if not selector.select(max(0, deadline-time.monotonic())):
                    break
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    raise Error("Codex app-server exited during skill discovery")
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if message.get("id") not in (1, 2):
                        continue
                    if "error" in message:
                        raise Error("Codex rejected the worker skill-discovery request")
                    if message.get("id") == 1:
                        send({"method": "initialized", "params": {}})
                        send({"id": 2, "method": "skills/list", "params": {"cwds": [str(cwd)], "forceReload": True}})
                    elif message.get("id") == 2:
                        entries = message.get("result", {}).get("data", [])
                        if len(entries) != 1 or entries[0].get("errors"):
                            raise Error("Codex returned incomplete or invalid skill discovery")
                        return entries[0]["skills"]
            raise Error("Codex skill discovery timed out")
        finally:
            selector.close()
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            proc.stdin.close(); proc.stdout.close()


def worker_overrides(config: dict, cwd: Path) -> list[str]:
    allowed = {str((cwd / ".agents" / "skills" / name / "SKILL.md").resolve()) for name in WORKER_SKILLS + DELIVERY_SKILLS}
    discovered = skills_list(config["codex"], cwd)
    paths = {str(Path(row["path"]).resolve()) for row in discovered}
    if not allowed <= paths:
        raise Error("Worker skills were not all discovered by this Codex build")
    entries = ["{path=" + json.dumps(path) + ",enabled=" + ("true" if path in allowed else "false") + "}" for path in sorted(paths)]
    overrides = ["-c", "skills.config=[" + ",".join(entries) + "]"]
    verified = skills_list(config["codex"], cwd, overrides)
    enabled = {str(Path(row["path"]).resolve()) for row in verified if row["enabled"]}
    if enabled != allowed:
        raise Error("Codex did not enforce the selected worker skill set; refusing worker launch")
    return overrides


def run_worker(project: Path) -> None:
    config = load(project)
    cwd = workspace(config)
    marker = json.loads((cwd / ".symphony-worker.json").read_text())
    if marker.get("kind") != "symphony" or marker.get("project_dir") != config["project_dir"]:
        raise Error("Missing explicit Symphony worker launch context")
    if marker.get("bootstrap", {}) != config.get("bootstrap", {}):
        raise Error("Worker bootstrap declaration changed; reprovision the issue workspace before launching")
    overrides = worker_overrides(config, cwd)
    env = symphony_bootstrap.environment(config.get("bootstrap", {}), cwd)
    env["SKILLS_SESSION_KIND"] = "symphony"
    env.pop("LINEAR_API_KEY", None)
    try:
        code = symphony_worker.run_server([config["codex"], *overrides, "app-server"],
                                         project.resolve(), Path(config["workspace_root"]), cwd, env)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise Error("Worker Git adapter refused launch/request: " + type(exc).__name__) from exc
    raise SystemExit(code if code >= 0 else 128 - code)


def start(project: Path, *, accept_preview=False) -> None:
    if not accept_preview:
        raise Error("Explicit start requires --accept-preview to acknowledge upstream's engineering preview")
    problems = check(project)
    if problems:
        raise Error("Not ready:\n- " + "\n- ".join(problems))
    config = load(project)
    binary = runtime_binary(config)
    # Exec preserves upstream signal/cancellation handling; no second scheduler.
    os.execv(str(binary), [str(binary), PREVIEW_FLAG, str(project.resolve() / ".symphony" / "WORKFLOW.md")])


def add_parser(subcommands):
    parser = subcommands.add_parser("symphony", help="project-only Symphony setup, checks and explicit start")
    actions = parser.add_subparsers(dest="symphony_action", required=True)
    for action in ("setup", "check", "install-runtime", "build-runtime", "start"):
        child = actions.add_parser(action)
        child.add_argument("--project-dir", type=Path, default=Path.cwd())
        child.set_defaults(handler=dispatch)
        if action == "setup":
            for flag in ("project-id", "project-slug", "setup-issue", "repo-url", "runtime-source", "workspace-root", "codex", "base-branch", "validation-command"):
                child.add_argument("--" + flag)
            child.add_argument("--port", type=int, dest="dashboard_port")
            child.add_argument("--no-dashboard", action="store_true")
            child.add_argument("--bootstrap-file", type=Path, help="JSON worker prerequisites; {} disables bootstrap")
        if action == "check":
            child.add_argument("--offline", action="store_true")
        if action == "start":
            child.add_argument("--accept-preview", action="store_true")
    return parser


def dispatch(args) -> int:
    project = args.project_dir.resolve()
    action = args.symphony_action
    if action == "setup":
        options = {key: getattr(args, key, None) for key in ("project_id", "project_slug", "setup_issue", "repo_url", "runtime_source", "workspace_root", "codex", "base_branch", "validation_command", "dashboard_port")}
        if getattr(args, "no_dashboard", False):
            options["dashboard_enabled"] = False
        if getattr(args, "bootstrap_file", None) is not None:
            try:
                options["bootstrap"] = json.loads(args.bootstrap_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise Error("Cannot read bootstrap JSON; supply a readable JSON object") from exc
        setup(project, **options)
        print(f"Configured {config_path(project)}; no workers started. Run skills symphony check.")
    elif action == "install-runtime":
        install_runtime(project)
    elif action == "build-runtime":
        build_runtime(project)
    elif action == "check":
        problems = check(project, remote=not args.offline)
        print("\n".join("not ready: " + problem for problem in problems) if problems else "Ready to start explicitly; no workers started.")
        return 3 if problems else 0
    elif action == "start":
        start(project, accept_preview=args.accept_preview)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare-workspace", "worker"))
    parser.add_argument("--project-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        (prepare_workspace if args.action == "prepare-workspace" else run_worker)(args.project_dir)
    except (Error, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
