#!/usr/bin/env python3
"""Validate and render compact Olympus orchestration checkpoints."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TASK_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

DISPATCH_MODES = {"human-controlled", "autonomous"}
MERGE_MODES = {"owner-only", "autonomous"}
PAUSE_MODES = {"running", "owner-paused", "escalated"}
LANE_KINDS = {"none", "issue", "repair", "maintenance"}
PHASES = {
    "IDLE",
    "RECOMMENDED",
    "PLANNING",
    "WORKING",
    "MAINTENANCE_WORKING",
    "REVIEWING",
    "REPAIRING",
    "PRESENTING",
    "CODEX_REVIEWING",
    "READY_FOR_HUMAN_MERGE",
    "READY_TO_AUTOMERGE",
    "MERGING",
    "MERGED_ARCHIVE",
    "PAUSED",
    "ESCALATED",
}
PROVENANCE = {"olympus-authored", "generated-artifact", "upstream"}
SEVERITIES = {"P0", "P1", "P2", "P3"}
FINDING_SCOPES = {
    "correctness",
    "security",
    "privacy",
    "migration",
    "integration",
    "packaging",
    "integrity",
    "documentation-claim",
    "access-path",
    "presentation",
    "upstream-quality",
    "accessibility",
    "testing",
    "other",
}
GENERATED_BLOCKING_SCOPES = {
    "security",
    "privacy",
    "integration",
    "packaging",
    "integrity",
    "documentation-claim",
    "access-path",
}
ACTORS = {"worker", "orchestrator", "owner", "upstream"}
DISPOSITIONS = {
    "open",
    "fixed-pending-review",
    "accepted-fixed",
    "no-change-pending",
    "accepted-no-change",
    "advisory",
    "disputed",
}
PROMOTERS = {"none", "orchestrator", "owner"}
ARTIFACT_STATUSES = {"planned", "active", "verified", "stale", "failed"}
CODEX_REVIEW_STATUSES = {"pending", "in-progress", "findings", "accepted", "stale", "blocked"}
ACCEPTED_BLOCKING = {"accepted-fixed", "accepted-no-change"}

REQUIRED_FIELDS = {
    "schema_version",
    "repository",
    "dispatch_mode",
    "merge_mode",
    "pause_mode",
    "lane_kind",
    "phase",
    "scope_version",
    "issue",
    "pr",
    "branch",
    "base",
    "head",
    "orchestrator_task",
    "planner_task",
    "worker_task",
    "reviewer_task",
    "worker_worktree",
    "worker_dirty",
    "dirty_paths",
    "findings",
    "checks",
    "clean_signal",
    "artifacts",
    "escalation",
    "next",
}


def _enum(errors: list[str], field: str, value: Any, allowed: set[str]) -> None:
    if value not in allowed:
        errors.append(f"{field} must be one of {sorted(allowed)}")


def _nullable_sha(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not SHA_RE.fullmatch(value)):
        errors.append(f"{field} must be null or a lowercase 40-character SHA")


def _sha(errors: list[str], field: str, value: Any) -> None:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        errors.append(f"{field} must be a lowercase 40-character SHA")


def _nullable_nonempty_string(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        errors.append(f"{field} must be null or a non-empty string")


def _nullable_task(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not TASK_RE.fullmatch(value)):
        errors.append(f"{field} must be null or a Codex task UUID")


def _nullable_positive_int(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
        errors.append(f"{field} must be null or a positive integer")


def _validate_lane_snapshot(errors: list[str], value: Any, prefix: str) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return
    required = {
        "lane_kind",
        "scope_version",
        "issue",
        "pr",
        "branch",
        "base",
        "head",
        "worker_task",
        "worker_worktree",
        "worker_dirty",
        "dirty_paths",
        "next",
    }
    missing = sorted(required - value.keys())
    if missing:
        errors.append(f"{prefix} missing fields: {', '.join(missing)}")
        return
    _enum(errors, f"{prefix}.lane_kind", value["lane_kind"], {"issue", "repair"})
    if not isinstance(value["scope_version"], int) or isinstance(value["scope_version"], bool) or value["scope_version"] < 1:
        errors.append(f"{prefix}.scope_version must be a positive integer")
    _nullable_positive_int(errors, f"{prefix}.issue", value["issue"])
    _nullable_positive_int(errors, f"{prefix}.pr", value["pr"])
    _nullable_nonempty_string(errors, f"{prefix}.branch", value["branch"])
    _nullable_sha(errors, f"{prefix}.base", value["base"])
    _nullable_sha(errors, f"{prefix}.head", value["head"])
    _nullable_task(errors, f"{prefix}.worker_task", value["worker_task"])
    _nullable_nonempty_string(errors, f"{prefix}.worker_worktree", value["worker_worktree"])
    if value["lane_kind"] == "issue" and value["issue"] is None:
        errors.append(f"{prefix}.issue is required for an issue lane")
    if value["lane_kind"] == "repair" and value["pr"] is None:
        errors.append(f"{prefix}.pr is required for a repair lane")
    if not isinstance(value["worker_dirty"], bool):
        errors.append(f"{prefix}.worker_dirty must be boolean")
    if not isinstance(value["dirty_paths"], list) or not all(isinstance(p, str) for p in value["dirty_paths"]):
        errors.append(f"{prefix}.dirty_paths must be a string array")
    if value["worker_dirty"] and not value["worker_worktree"]:
        errors.append(f"{prefix}.worker_worktree is required when dirty")
    if not isinstance(value["next"], str) or not value["next"].strip():
        errors.append(f"{prefix}.next must be a non-empty string")


def _validate_codex_review(errors: list[str], value: Any, current_head: Any) -> None:
    prefix = "codex_review"
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return
    required = {"head", "request_comment_id", "request_url", "review_id", "status", "accepted_head"}
    missing = sorted(required - value.keys())
    if missing:
        errors.append(f"{prefix} missing fields: {', '.join(missing)}")
        return
    _sha(errors, f"{prefix}.head", value["head"])
    if not isinstance(value["request_comment_id"], int) or isinstance(value["request_comment_id"], bool) or value["request_comment_id"] <= 0:
        errors.append(f"{prefix}.request_comment_id must be a positive integer")
    if not isinstance(value["request_url"], str) or not value["request_url"].strip():
        errors.append(f"{prefix}.request_url must be a non-empty string")
    _nullable_nonempty_string(errors, f"{prefix}.review_id", value["review_id"])
    _enum(errors, f"{prefix}.status", value["status"], CODEX_REVIEW_STATUSES)
    _nullable_sha(errors, f"{prefix}.accepted_head", value["accepted_head"])
    if value["status"] == "accepted":
        if value["review_id"] is None:
            errors.append(f"{prefix}.accepted requires review_id")
        if value["accepted_head"] != value["head"]:
            errors.append(f"{prefix}.accepted_head must equal codex_review.head when accepted")
    elif value["accepted_head"] is not None:
        errors.append(f"{prefix}.accepted_head must be null unless status=accepted")
    if value["status"] != "stale" and current_head is not None and value["head"] != current_head:
        errors.append(f"{prefix}.head must equal current head unless status=stale")


def validate_data(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["checkpoint must be a JSON object"]

    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
        return errors

    if data["schema_version"] != 2:
        errors.append("schema_version must be 2")
    if data["repository"] != "dm1681/Olympus":
        errors.append("repository must be dm1681/Olympus")
    _enum(errors, "dispatch_mode", data["dispatch_mode"], DISPATCH_MODES)
    _enum(errors, "merge_mode", data["merge_mode"], MERGE_MODES)
    _enum(errors, "pause_mode", data["pause_mode"], PAUSE_MODES)
    _enum(errors, "lane_kind", data["lane_kind"], LANE_KINDS)
    _enum(errors, "phase", data["phase"], PHASES)

    if not isinstance(data["scope_version"], int) or isinstance(data["scope_version"], bool) or data["scope_version"] < 1:
        errors.append("scope_version must be a positive integer")
    _nullable_positive_int(errors, "issue", data["issue"])
    _nullable_positive_int(errors, "pr", data["pr"])
    _nullable_sha(errors, "base", data["base"])
    _nullable_sha(errors, "head", data["head"])
    _nullable_sha(errors, "clean_signal", data["clean_signal"])
    for field in ("orchestrator_task", "planner_task", "worker_task", "reviewer_task"):
        _nullable_task(errors, field, data[field])
    for field in ("reviewer_task", "planner_task", "worker_task"):
        if data[field] is not None and data["orchestrator_task"] is None:
            errors.append(f"{field} requires orchestrator_task")

    _nullable_nonempty_string(errors, "branch", data["branch"])
    _nullable_nonempty_string(errors, "worker_worktree", data["worker_worktree"])
    if data["lane_kind"] == "none" and data["phase"] not in {"IDLE", "MERGED_ARCHIVE", "PAUSED", "ESCALATED"}:
        errors.append("lane_kind=none requires phase IDLE, MERGED_ARCHIVE, PAUSED, or ESCALATED")
    if data["lane_kind"] == "issue" and data["issue"] is None:
        errors.append("issue is required for lane_kind=issue")
    if data["lane_kind"] == "repair" and data["pr"] is None:
        errors.append("pr is required for lane_kind=repair")
    if data["phase"] in {"PRESENTING", "CODEX_REVIEWING", "READY_FOR_HUMAN_MERGE", "READY_TO_AUTOMERGE", "MERGING"} and data["pr"] is None:
        errors.append(f"pr is required in phase {data['phase']}")
    if data["phase"] == "MAINTENANCE_WORKING" and data["lane_kind"] != "maintenance":
        errors.append("MAINTENANCE_WORKING requires lane_kind=maintenance")

    if data["pause_mode"] == "owner-paused" and data["phase"] != "PAUSED":
        errors.append("pause_mode=owner-paused requires phase PAUSED")
    if data["pause_mode"] == "escalated" and data["phase"] != "ESCALATED":
        errors.append("pause_mode=escalated requires phase ESCALATED")
    if data["pause_mode"] == "running" and data["phase"] in {"PAUSED", "ESCALATED"}:
        errors.append("running pause_mode cannot use PAUSED or ESCALATED phase")
    if data["phase"] == "ESCALATED" and not data["escalation"]:
        errors.append("ESCALATED phase requires escalation text")
    if data["merge_mode"] == "owner-only" and data["phase"] in {"READY_TO_AUTOMERGE", "MERGING"}:
        errors.append("owner-only merge_mode cannot enter autonomous merge phases")

    if not isinstance(data["worker_dirty"], bool):
        errors.append("worker_dirty must be boolean")
    if not isinstance(data["dirty_paths"], list) or not all(isinstance(path, str) for path in data["dirty_paths"]):
        errors.append("dirty_paths must be a string array")
    if data["worker_dirty"] and not data["worker_worktree"]:
        errors.append("worker_worktree is required when worker_dirty=true")

    findings = data["findings"]
    if not isinstance(findings, list):
        errors.append("findings must be an array")
        findings = []
    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        required = {"id", "head", "severity", "provenance", "scope", "blocking", "required_actor", "disposition", "promoted_by"}
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing_finding = sorted(required - finding.keys())
        if missing_finding:
            errors.append(f"{prefix} missing fields: {', '.join(missing_finding)}")
            continue
        finding_id = finding["id"]
        if not isinstance(finding_id, str) or not finding_id.strip():
            errors.append(f"{prefix}.id must be non-empty")
        elif finding_id in seen_ids:
            errors.append(f"duplicate finding id: {finding_id}")
        else:
            seen_ids.add(finding_id)
        _sha(errors, f"{prefix}.head", finding["head"])
        _enum(errors, f"{prefix}.severity", finding["severity"], SEVERITIES)
        _enum(errors, f"{prefix}.provenance", finding["provenance"], PROVENANCE)
        _enum(errors, f"{prefix}.scope", finding["scope"], FINDING_SCOPES)
        _enum(errors, f"{prefix}.required_actor", finding["required_actor"], ACTORS)
        _enum(errors, f"{prefix}.disposition", finding["disposition"], DISPOSITIONS)
        _enum(errors, f"{prefix}.promoted_by", finding["promoted_by"], PROMOTERS)
        if not isinstance(finding["blocking"], bool):
            errors.append(f"{prefix}.blocking must be boolean")
            continue
        if finding["disposition"] == "advisory" and finding["blocking"]:
            errors.append(f"{prefix}: advisory findings cannot block")
        if finding["provenance"] == "upstream" and finding["blocking"] and finding["promoted_by"] == "none":
            errors.append(f"{prefix}: upstream blocking finding requires owner/orchestrator promotion")
        if (
            finding["provenance"] == "generated-artifact"
            and finding["blocking"]
            and finding["scope"] not in GENERATED_BLOCKING_SCOPES
            and finding["promoted_by"] == "none"
        ):
            errors.append(f"{prefix}: generated-artifact blocking scope requires explicit promotion")

    if data["clean_signal"] is not None:
        if data["head"] is None or data["clean_signal"] != data["head"]:
            errors.append("clean_signal must equal the current head")
        for finding in findings:
            if isinstance(finding, dict) and finding.get("blocking") and finding.get("disposition") not in ACCEPTED_BLOCKING:
                errors.append(f"clean_signal conflicts with unresolved blocking finding {finding.get('id', '?')}")

    artifacts = data["artifacts"]
    if not isinstance(artifacts, list):
        errors.append("artifacts must be an array")
    else:
        for index, artifact in enumerate(artifacts):
            prefix = f"artifacts[{index}]"
            if not isinstance(artifact, dict):
                errors.append(f"{prefix} must be an object")
                continue
            missing_artifact = {"label", "location", "head", "status"} - artifact.keys()
            if missing_artifact:
                errors.append(f"{prefix} missing fields: {', '.join(sorted(missing_artifact))}")
                continue
            if not isinstance(artifact["label"], str) or not artifact["label"].strip():
                errors.append(f"{prefix}.label must be non-empty")
            if not isinstance(artifact["location"], str) or not artifact["location"].strip():
                errors.append(f"{prefix}.location must be non-empty")
            _nullable_sha(errors, f"{prefix}.head", artifact["head"])
            _enum(errors, f"{prefix}.status", artifact["status"], ARTIFACT_STATUSES)

    paused_lane = data.get("paused_lane")
    if paused_lane is not None:
        if data["lane_kind"] != "maintenance" or data["pause_mode"] != "running":
            errors.append("paused_lane may coexist only with a running maintenance lane")
        _validate_lane_snapshot(errors, paused_lane, "paused_lane")
        if isinstance(paused_lane, dict) and data["pr"] is not None and paused_lane.get("pr") is not None:
            errors.append("running maintenance and paused lane cannot both have an open Worker PR")

    codex_review = data.get("codex_review")
    if codex_review is not None:
        _validate_codex_review(errors, codex_review, data["head"])
    if data["phase"] == "CODEX_REVIEWING":
        if data["clean_signal"] != data["head"]:
            errors.append("CODEX_REVIEWING requires Reviewer CLEAN at current head")
        if codex_review is None:
            errors.append("CODEX_REVIEWING requires codex_review state")
        elif isinstance(codex_review, dict) and codex_review.get("status") not in {"pending", "in-progress"}:
            errors.append("CODEX_REVIEWING requires pending or in-progress codex_review status")
    if data["phase"] in {"READY_FOR_HUMAN_MERGE", "READY_TO_AUTOMERGE", "MERGING"}:
        if not isinstance(codex_review, dict) or codex_review.get("status") != "accepted":
            errors.append(f"{data['phase']} requires accepted codex_review state")
        elif codex_review.get("accepted_head") != data["head"]:
            errors.append(f"{data['phase']} requires codex_review accepted at current head")

    if not isinstance(data["checks"], str):
        errors.append("checks must be a string")
    if data["escalation"] is not None and not isinstance(data["escalation"], str):
        errors.append("escalation must be null or a string")
    if not isinstance(data["next"], str) or not data["next"].strip():
        errors.append("next must be a non-empty string")

    return errors


def load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"checkpoint not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    errors = validate_data(value)
    if errors:
        raise ValueError("\n".join(f"- {error}" for error in errors))
    return value


def _fmt(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_state(data: dict[str, Any]) -> str:
    lines = [
        f"schema_version={data['schema_version']} repository={data['repository']}",
        f"dispatch_mode={data['dispatch_mode']} merge_mode={data['merge_mode']} pause_mode={data['pause_mode']}",
        f"lane_kind={data['lane_kind']} phase={data['phase']} scope_version={data['scope_version']}",
        f"issue={_fmt(data['issue'])} pr={_fmt(data['pr'])} branch={_fmt(data['branch'])}",
        f"base={_fmt(data['base'])} head={_fmt(data['head'])}",
        "tasks="
        + ",".join(
            f"{role}:{_fmt(data[field])}"
            for role, field in (
                ("orchestrator", "orchestrator_task"),
                ("planner", "planner_task"),
                ("worker", "worker_task"),
                ("reviewer", "reviewer_task"),
            )
        ),
        f"worker_worktree={_fmt(data['worker_worktree'])} worker_dirty={_fmt(data['worker_dirty'])}",
        "dirty_paths=" + (",".join(data["dirty_paths"]) if data["dirty_paths"] else "none"),
    ]
    if data["findings"]:
        lines.append(
            "findings="
            + ",".join(
                f"{item['id']}[{item['provenance']};{'blocking' if item['blocking'] else 'advisory'};{item['disposition']}]"
                for item in data["findings"]
            )
        )
    else:
        lines.append("findings=none")
    lines.extend(
        [
            f"checks={data['checks'] or 'none'} clean_signal={_fmt(data['clean_signal'])}",
            f"artifacts={len(data['artifacts'])} escalation={_fmt(data['escalation'])}",
        ]
    )
    if data.get("paused_lane") is not None:
        paused = data["paused_lane"]
        lines.append(
            f"paused_lane={paused['lane_kind']} issue={_fmt(paused['issue'])} pr={_fmt(paused['pr'])} "
            f"worker={_fmt(paused['worker_task'])} dirty={_fmt(paused['worker_dirty'])}"
        )
    if data.get("codex_review") is not None:
        review = data["codex_review"]
        lines.append(
            f"codex_review={review['status']} head={review['head']} request={review['request_comment_id']} "
            f"review={_fmt(review['review_id'])} accepted_head={_fmt(review['accepted_head'])}"
        )
    lines.append(f"next={data['next']}")
    return "\n".join(lines)


def render_heartbeat(data: dict[str, Any]) -> str:
    state = render_state(data)
    return f"""Use $orchestrate-olympus as the persistent Olympus Orchestrator for dm1681/Olympus.

This checkpoint is a validated host-local cache, not authority. Recover live GitHub, task, worktree, and automation state before every mutation; live evidence supersedes stale values.

CHECKPOINT
{state}

Follow the skill's core contract and load only the conditional references needed for this wake-up. Keep dispatch, merge, and pause authority independent. If pause_mode is not running, perform no implementation, review, presentation, merge, or GitHub write without an explicit owner command. Preserve dirty worktrees. Do not duplicate tasks or comments. On a transition, update the checkpoint and report one next action; otherwise make no GitHub write."""


def sample_checkpoint() -> dict[str, Any]:
    sha = "a" * 40
    return {
        "schema_version": 2,
        "repository": "dm1681/Olympus",
        "dispatch_mode": "human-controlled",
        "merge_mode": "owner-only",
        "pause_mode": "running",
        "lane_kind": "issue",
        "phase": "WORKING",
        "scope_version": 1,
        "issue": 11,
        "pr": None,
        "branch": "codex/issue-11-example",
        "base": sha,
        "head": sha,
        "orchestrator_task": "11111111-1111-1111-1111-111111111111",
        "planner_task": None,
        "worker_task": "22222222-2222-2222-2222-222222222222",
        "reviewer_task": "33333333-3333-3333-3333-333333333333",
        "worker_worktree": "/tmp/olympus-worker",
        "worker_dirty": False,
        "dirty_paths": [],
        "findings": [],
        "checks": "focused green",
        "clean_signal": None,
        "artifacts": [],
        "escalation": None,
        "next": "continue the current TDD slice",
    }


def self_test() -> None:
    valid = sample_checkpoint()
    assert validate_data(valid) == []
    assert "dispatch_mode=human-controlled" in render_state(valid)
    assert "live evidence supersedes stale values" in render_heartbeat(valid)

    paused = copy.deepcopy(valid)
    paused["pause_mode"] = "owner-paused"
    paused["phase"] = "PAUSED"
    paused["worker_dirty"] = True
    paused["dirty_paths"] = ["tests/example.test.ts"]
    assert validate_data(paused) == []

    idle_paused = copy.deepcopy(valid)
    idle_paused.update(
        {
            "lane_kind": "none",
            "phase": "PAUSED",
            "pause_mode": "owner-paused",
            "issue": None,
            "branch": None,
            "base": None,
            "head": None,
            "worker_task": None,
            "worker_worktree": None,
        }
    )
    assert validate_data(idle_paused) == []

    bad_merge = copy.deepcopy(valid)
    bad_merge["pr"] = 35
    bad_merge["phase"] = "READY_TO_AUTOMERGE"
    assert any("owner-only" in error for error in validate_data(bad_merge))

    codex_pending = copy.deepcopy(valid)
    codex_pending.update(
        {
            "pr": 35,
            "phase": "CODEX_REVIEWING",
            "clean_signal": "a" * 40,
            "codex_review": {
                "head": "a" * 40,
                "request_comment_id": 123,
                "request_url": "https://github.com/dm1681/Olympus/pull/35#issuecomment-123",
                "review_id": None,
                "status": "pending",
                "accepted_head": None,
            },
        }
    )
    assert validate_data(codex_pending) == []

    codex_missing = copy.deepcopy(valid)
    codex_missing.update({"pr": 35, "phase": "CODEX_REVIEWING"})
    assert any("requires codex_review" in error for error in validate_data(codex_missing))

    ready = copy.deepcopy(valid)
    ready.update(
        {
            "pr": 35,
            "phase": "READY_FOR_HUMAN_MERGE",
            "clean_signal": "a" * 40,
            "codex_review": {
                "head": "a" * 40,
                "request_comment_id": 123,
                "request_url": "https://github.com/dm1681/Olympus/pull/35#issuecomment-123",
                "review_id": "PRR_example",
                "status": "accepted",
                "accepted_head": "a" * 40,
            },
        }
    )
    assert validate_data(ready) == []

    ready_without_codex = copy.deepcopy(ready)
    del ready_without_codex["codex_review"]
    assert any("requires accepted codex_review" in error for error in validate_data(ready_without_codex))

    bad_upstream = copy.deepcopy(valid)
    bad_upstream["findings"] = [
        {
            "id": "UPSTREAM-001",
            "head": "a" * 40,
            "severity": "P2",
            "provenance": "upstream",
            "scope": "upstream-quality",
            "blocking": True,
            "required_actor": "worker",
            "disposition": "open",
            "promoted_by": "none",
        }
    ]
    assert any("requires owner/orchestrator promotion" in error for error in validate_data(bad_upstream))

    clean_with_blocker = copy.deepcopy(valid)
    clean_with_blocker["pr"] = 35
    clean_with_blocker["phase"] = "PRESENTING"
    clean_with_blocker["clean_signal"] = "a" * 40
    clean_with_blocker["findings"] = [
        {
            "id": "OLY-001",
            "head": "a" * 40,
            "severity": "P1",
            "provenance": "olympus-authored",
            "scope": "correctness",
            "blocking": True,
            "required_actor": "worker",
            "disposition": "open",
            "promoted_by": "none",
        }
    ]
    assert any("conflicts with unresolved blocking finding" in error for error in validate_data(clean_with_blocker))

    maintenance = copy.deepcopy(valid)
    maintenance.update(
        {
            "lane_kind": "maintenance",
            "phase": "MAINTENANCE_WORKING",
            "issue": None,
            "pr": 35,
            "branch": "codex/setup-example",
            "paused_lane": {
                "lane_kind": "issue",
                "scope_version": 1,
                "issue": 11,
                "pr": None,
                "branch": "codex/issue-11-example",
                "base": "a" * 40,
                "head": "a" * 40,
                "worker_task": "22222222-2222-2222-2222-222222222222",
                "worker_worktree": "/tmp/paused-worker",
                "worker_dirty": True,
                "dirty_paths": ["tests/example.test.ts"],
                "next": "resume only after owner authorization",
            },
        }
    )
    assert validate_data(maintenance) == []

    maintenance["paused_lane"]["pr"] = 34
    assert any("cannot both have an open Worker PR" in error for error in validate_data(maintenance))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render-state", "render-heartbeat"):
        command = subparsers.add_parser(name)
        command.add_argument("checkpoint", type=Path)
    subparsers.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        print("checkpoint self-test: PASS")
        return 0

    try:
        data = load_checkpoint(args.checkpoint)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "validate":
        print("checkpoint valid")
    elif args.command == "render-state":
        print(render_state(data))
    else:
        print(render_heartbeat(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
