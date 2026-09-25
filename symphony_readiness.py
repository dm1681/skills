"""Evidence layers for readiness; expensive validation is explicitly invoked."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import symphony_bootstrap
import symphony_identity
from install import InstallError as Error


def report(project: Path, *, remote=True, bootstrap=False, timeout=300) -> dict:
    import symphony_project as s
    config = s.load(project)
    rows = []

    def check(name, probe, remediation, *, skipped=None, required=True):
        if skipped:
            rows.append(dict(name=name, status="skipped", detail=skipped,
                             remediation=remediation, required=required))
            return
        try:
            problems = probe() or []
        except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
            # Only our own errors are safe to display; subprocess exceptions may
            # contain credential-bearing commands or output.
            problems = [str(exc) if isinstance(exc, Error) else type(exc).__name__]
        rows.append(dict(name=name, status="fail" if problems else "pass",
                         detail="; ".join(problems) if problems else "Verified",
                         remediation=remediation if problems else "None required", required=required))

    def prerequisites():
        problems = []
        if sys.platform != "linux":
            problems.append("Only Linux/WSL is supported by this integration")
        for key in ("repo_url", "validation_command"):
            if not config.get(key):
                problems.append(f"Missing {key}")
        for binary in ("git", "bash", "sh", "gh", config["codex"]):
            if not shutil.which(binary):
                problems.append(f"Required executable is unavailable: {binary}")
        return problems

    def runtime():
        source = s.verify_runtime(config)
        if not (source / "package.json").is_file() and not shutil.which("erl"):
            return ["Erlang is required for the source-built escript"]
        if not s.runtime_binary(config).is_file():
            return ["Symphony executable is missing"]

    def workflow():
        path = project.resolve() / ".symphony/WORKFLOW.md"
        if not path.is_file() or path.is_symlink() or path.read_text() != s.render_workflow(config):
            return ["Generated WORKFLOW.md does not match project configuration"]

    def bootstrap_prerequisites():
        root = Path(config["workspace_root"])
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root, prefix="prerequisites-") as raw:
            env = symphony_identity.environment(config, credentials=False)
            symphony_bootstrap.environment(config.get("bootstrap", {}), Path(raw), base_env=env)

    check("tools", prerequisites, "Install the missing service-environment tools and configure repository/validation.")
    check("runtime", runtime, "Run symphony install-runtime or build-runtime for the pinned runtime.")
    check("workflow", workflow, "Reconcile managed files, then rerun symphony setup.")
    check("worker_sandbox", lambda: s.probe_worker(config),
          "Verify Codex discovery, native Git writes and denied parent/sibling writes in the service environment.",
          skipped=None if shutil.which(config["codex"]) and shutil.which("git") else "Missing Codex or Git")
    check("bootstrap_prerequisites", bootstrap_prerequisites,
          "Preinstall declared tools/interpreter and choose a writable workspace-local cache.")
    check("authentication", lambda: s.authentication_problems(config),
          "Authenticate the configured Codex and GitHub account in the service environment.",
          skipped=None if remote else "Authentication not checked offline")
    check("git_access", lambda: symphony_identity.check_access(config, "git"),
          "Run symphony check-git; verify configured transport and repository access.",
          skipped=None if remote else "Repository access not checked offline")
    check("pr_access", lambda: symphony_identity.check_access(config, "pr"),
          "Configure github_repo, github_account and credential_provider; run symphony check-pr. A rehearsal proves writes.",
          skipped="PR account not declared" if not config.get("github_repo") else
                  (None if remote else "PR access not checked offline"),
          required=bool(config.get("github_repo")))
    def gate():
        s.linear_gate(config)
    check("linear_gate", gate, "Verify the exact setup issue is Done and required lifecycle states exist.",
          skipped=None if remote else "Linear setup-issue gate not checked offline; startup readiness is unverified")
    evidence = []
    def validate_clone():
        from symphony_rehearsal import validate_fresh_clone
        evidence.append(str(validate_fresh_clone(project, timeout=timeout)))
    check("bootstrap_validation", validate_clone,
          "Run symphony check --bootstrap explicitly for trusted declared dependencies and validation.",
          skipped=None if bootstrap and remote else "Fresh-clone bootstrap and validation were not invoked",
          required=bootstrap)
    if evidence:
        rows[-1]["detail"] = "Verified; evidence: " + evidence[0]
        rows[-1]["evidence"] = evidence[0]
    check("process_startup", lambda: None, "Use explicit start only when dispatch is authorized.",
          skipped="No service was started or inspected; process presence cannot prove delivery", required=False)
    check("worker_delivery", lambda: None, "Invoke symphony rehearse --accept-rehearsal separately and inspect its durable evidence.",
          skipped="No model turn or PR write was attempted", required=False)
    return {"schema": 1, "checks": rows,
            "startup_ready": all(row["status"] == "pass" for row in rows if row["required"]),
            "delivery_ready": False}


def problems(report: dict) -> list[str]:
    return [f"{row['name']}: {row['detail']}; {row['remediation']}" for row in report["checks"]
            if row["status"] == "fail" or (row["required"] and row["status"] == "skipped")]


def render(report: dict) -> str:
    lines = [f"{row['status']}: {row['name']}: {row['detail']} | {row['remediation']}" for row in report["checks"]]
    lines.append("Startup prerequisites passed." if report["startup_ready"] else "Startup prerequisites incomplete.")
    lines.append("Worker delivery unverified; no workers started by this check.")
    return "\n".join(lines)
