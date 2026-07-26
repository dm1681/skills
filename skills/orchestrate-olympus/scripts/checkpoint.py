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
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
# Host-neutral task/subagent identifier: whatever stable token the agent host
# exposes (Codex UUID, Claude Code session slug, path-like ID, ...). It must be
# a single whitespace-free token so signatures and hidden markers stay parseable.
TASK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{3,127}$")

DISPATCH_MODES = {"human-controlled", "autonomous"}
MERGE_MODES = {"owner-only", "autonomous"}
PAUSE_MODES = {"running", "owner-paused", "escalated"}
ORCHESTRATOR_MODES = {"parent-resident"}
LANE_KINDS = {"none", "issue", "repair", "maintenance"}
PHASES = {
    "IDLE",
    "RECOMMENDED",
    "PLANNING",
    "WORKING",
    "MAINTENANCE_WORKING",
    "SOURCE_REVIEWING",
    "EVIDENCE_BUILDING",
    "ARTIFACT_VERIFYING",
    "REVIEWING",
    "REPAIRING",
    "PRESENTING",
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
ACCEPTED_BLOCKING = {"accepted-fixed", "accepted-no-change"}
HEAD_CHANGE_CLASSES = {
    "none",
    "source",
    "deterministic-artifact",
    "provenance-metadata-only",
    "mixed-or-unknown",
}
GATE_STATUSES = {"not-run", "clean", "stale", "failed"}
ACTIONS_STATES = {
    "not-checked",
    "pending",
    "green",
    "failed",
    "unknown-degraded",
}
TEST_RESULTS = {"pass", "fail"}

REQUIRED_FIELDS = {
    "schema_version",
    "repository",
    "orchestrator_mode",
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
    "gate_evidence",
    "clean_signal",
    "artifacts",
    "escalation",
    "next",
}


def empty_gate_evidence() -> dict[str, Any]:
    """Return conservative defaults that never imply reusable validation."""
    return {
        "head_change_class": "mixed-or-unknown",
        "source_tree_hash": None,
        "runtime_fingerprint": None,
        "standards_status": "not-run",
        "standards_head": None,
        "standards_scope_version": None,
        "spec_status": "not-run",
        "spec_head": None,
        "spec_scope_version": None,
        "artifact_review": "not-run",
        "artifact_review_head": None,
        "test_evidence": [],
        "actions_state": "not-checked",
        "actions_head": None,
        "actions_degraded_evidence": None,
    }


def _enum(errors: list[str], field: str, value: Any, allowed: set[str]) -> None:
    if value not in allowed:
        errors.append(f"{field} must be one of {sorted(allowed)}")


def _nullable_sha(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not SHA_RE.fullmatch(value)):
        errors.append(f"{field} must be null or a lowercase 40-character SHA")


def _nullable_hash(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not HASH_RE.fullmatch(value)):
        errors.append(f"{field} must be null or a lowercase 64-character hash")


def _hash(errors: list[str], field: str, value: Any) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        errors.append(f"{field} must be a lowercase 64-character hash")


def _sha(errors: list[str], field: str, value: Any) -> None:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        errors.append(f"{field} must be a lowercase 40-character SHA")


def _nullable_nonempty_string(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        errors.append(f"{field} must be null or a non-empty string")


def _nullable_task(errors: list[str], field: str, value: Any) -> None:
    if value is not None and (not isinstance(value, str) or not TASK_RE.fullmatch(value)):
        errors.append(
            f"{field} must be null or a stable whitespace-free host task identifier"
        )


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


def _validate_gate_evidence(
    errors: list[str], value: Any, current_head: Any, scope_version: Any
) -> None:
    prefix = "gate_evidence"
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return
    required = set(empty_gate_evidence())
    missing = sorted(required - value.keys())
    if missing:
        errors.append(f"{prefix} missing fields: {', '.join(missing)}")
        return

    _enum(errors, f"{prefix}.head_change_class", value["head_change_class"], HEAD_CHANGE_CLASSES)
    _nullable_hash(errors, f"{prefix}.source_tree_hash", value["source_tree_hash"])
    _nullable_hash(errors, f"{prefix}.runtime_fingerprint", value["runtime_fingerprint"])
    for axis in ("standards", "spec"):
        _enum(errors, f"{prefix}.{axis}_status", value[f"{axis}_status"], GATE_STATUSES)
        _nullable_sha(errors, f"{prefix}.{axis}_head", value[f"{axis}_head"])
        _nullable_positive_int(errors, f"{prefix}.{axis}_scope_version", value[f"{axis}_scope_version"])
    _enum(errors, f"{prefix}.artifact_review", value["artifact_review"], GATE_STATUSES)
    _nullable_sha(errors, f"{prefix}.artifact_review_head", value["artifact_review_head"])
    _enum(errors, f"{prefix}.actions_state", value["actions_state"], ACTIONS_STATES)
    _nullable_sha(errors, f"{prefix}.actions_head", value["actions_head"])

    clean_axes = value["standards_status"] == "clean" and value["spec_status"] == "clean"
    for axis in ("standards", "spec"):
        if value[f"{axis}_status"] == "clean":
            for field in ("source_tree_hash", "runtime_fingerprint"):
                if value[field] is None:
                    errors.append(f"{prefix}.{field} is required when {axis}_status=clean")
            if value[f"{axis}_head"] is None:
                errors.append(f"{prefix}.{axis}_head is required when {axis}_status=clean")
            if value[f"{axis}_scope_version"] != scope_version:
                errors.append(f"clean {axis} certificate must match the current scope_version")
            if (
                value["head_change_class"] in {"source", "mixed-or-unknown"}
                and current_head is not None
                and value[f"{axis}_head"] != current_head
            ):
                errors.append(f"clean {axis} certificate for a source or unknown head must match the current head")
    if clean_axes and value["standards_head"] != value["spec_head"]:
        errors.append("clean Standards and Spec certificates must review the same source head")

    if value["artifact_review"] == "clean":
        if value["artifact_review_head"] is None:
            errors.append(f"{prefix}.artifact_review_head is required when artifact_review=clean")
        elif current_head is None or value["artifact_review_head"] != current_head:
            errors.append("clean artifact review must match the current head")

    test_evidence = value["test_evidence"]
    if not isinstance(test_evidence, list):
        errors.append(f"{prefix}.test_evidence must be an array")
    else:
        for index, item in enumerate(test_evidence):
            item_prefix = f"{prefix}.test_evidence[{index}]"
            required_test = {"command", "scope", "required", "source_tree_hash", "runtime_fingerprint", "result"}
            if not isinstance(item, dict):
                errors.append(f"{item_prefix} must be an object")
                continue
            missing_test = sorted(required_test - item.keys())
            if missing_test:
                errors.append(f"{item_prefix} missing fields: {', '.join(missing_test)}")
                continue
            for field in ("command", "scope"):
                if not isinstance(item[field], str) or not item[field].strip():
                    errors.append(f"{item_prefix}.{field} must be a non-empty string")
            if not isinstance(item["required"], bool):
                errors.append(f"{item_prefix}.required must be boolean")
            _hash(errors, f"{item_prefix}.source_tree_hash", item["source_tree_hash"])
            _hash(errors, f"{item_prefix}.runtime_fingerprint", item["runtime_fingerprint"])
            _enum(errors, f"{item_prefix}.result", item["result"], TEST_RESULTS)

        matching_required = [
            item
            for item in test_evidence
            if isinstance(item, dict)
            and item.get("required") is True
            and item.get("scope") == "aggregate"
            and item.get("source_tree_hash") == value["source_tree_hash"]
            and item.get("runtime_fingerprint") == value["runtime_fingerprint"]
        ]
        if clean_axes and not matching_required:
            errors.append("clean source certificates require matching required aggregate test evidence")
        if clean_axes and any(item.get("result") != "pass" for item in matching_required):
            errors.append("clean source certificates require all matching required aggregate tests to pass")

    degraded = value["actions_degraded_evidence"]
    if degraded is not None:
        degraded_prefix = f"{prefix}.actions_degraded_evidence"
        required_degraded = {"attempts", "last_error", "corroboration"}
        if not isinstance(degraded, dict):
            errors.append(f"{degraded_prefix} must be null or an object")
        else:
            missing_degraded = sorted(required_degraded - degraded.keys())
            if missing_degraded:
                errors.append(f"{degraded_prefix} missing fields: {', '.join(missing_degraded)}")
            else:
                if not isinstance(degraded["attempts"], int) or isinstance(degraded["attempts"], bool) or degraded["attempts"] < 2:
                    errors.append(f"{degraded_prefix}.attempts must be an integer of at least 2")
                if not isinstance(degraded["last_error"], str) or not degraded["last_error"].strip():
                    errors.append(f"{degraded_prefix}.last_error must be a non-empty string")
                if not isinstance(degraded["corroboration"], list) or not degraded["corroboration"] or not all(isinstance(item, str) and item.strip() for item in degraded["corroboration"]):
                    errors.append(f"{degraded_prefix}.corroboration must be a non-empty string array")
    if value["actions_state"] == "unknown-degraded" and degraded is None:
        errors.append("actions_state=unknown-degraded requires actions_degraded_evidence")
    if value["actions_state"] == "green":
        if current_head is None or value["actions_head"] != current_head:
            errors.append("green Actions evidence must match the current head")
    elif value["actions_head"] is not None:
        errors.append("actions_head must be null unless actions_state=green")


def validate_data(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["checkpoint must be a JSON object"]

    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
        return errors

    if data["schema_version"] != 5:
        errors.append("schema_version must be 5")
    if data["repository"] != "dm1681/Olympus":
        errors.append("repository must be dm1681/Olympus")
    _enum(
        errors,
        "orchestrator_mode",
        data["orchestrator_mode"],
        ORCHESTRATOR_MODES,
    )
    _enum(errors, "dispatch_mode", data["dispatch_mode"], DISPATCH_MODES)
    _enum(errors, "merge_mode", data["merge_mode"], MERGE_MODES)
    _enum(errors, "pause_mode", data["pause_mode"], PAUSE_MODES)
    _enum(errors, "lane_kind", data["lane_kind"], LANE_KINDS)
    if data["phase"] == "CODEX_REVIEWING":
        errors.append(
            "CODEX_REVIEWING was removed; migrate the checkpoint to PRESENTING "
            "and repeat the exact-head readiness audit"
        )
    else:
        _enum(errors, "phase", data["phase"], PHASES)
    if "codex_review" in data:
        errors.append("codex_review was removed from checkpoint schema version 3")
    if "automations" in data:
        errors.append(
            "automations was removed from checkpoint schema version 4; "
            "use parent-resident subagents"
        )

    if not isinstance(data["scope_version"], int) or isinstance(data["scope_version"], bool) or data["scope_version"] < 1:
        errors.append("scope_version must be a positive integer")
    _nullable_positive_int(errors, "issue", data["issue"])
    _nullable_positive_int(errors, "pr", data["pr"])
    _nullable_sha(errors, "base", data["base"])
    _nullable_sha(errors, "head", data["head"])
    _nullable_sha(errors, "clean_signal", data["clean_signal"])
    for field in ("orchestrator_task", "planner_task", "worker_task", "reviewer_task"):
        _nullable_task(errors, field, data[field])
    for field in ("planner_task", "worker_task"):
        if data[field] is not None and data["reviewer_task"] is None:
            errors.append(f"{field} requires reviewer_task")

    _nullable_nonempty_string(errors, "branch", data["branch"])
    _nullable_nonempty_string(errors, "worker_worktree", data["worker_worktree"])
    if data["lane_kind"] == "none" and data["phase"] not in {"IDLE", "MERGED_ARCHIVE", "PAUSED", "ESCALATED"}:
        errors.append("lane_kind=none requires phase IDLE, MERGED_ARCHIVE, PAUSED, or ESCALATED")
    if data["lane_kind"] == "issue" and data["issue"] is None:
        errors.append("issue is required for lane_kind=issue")
    if data["lane_kind"] == "repair" and data["pr"] is None:
        errors.append("pr is required for lane_kind=repair")
    if data["phase"] in {"PRESENTING", "READY_FOR_HUMAN_MERGE", "READY_TO_AUTOMERGE", "MERGING"} and data["pr"] is None:
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
        gate_evidence = data["gate_evidence"]
        if isinstance(gate_evidence, dict):
            if gate_evidence.get("standards_status") != "clean" or gate_evidence.get("spec_status") != "clean":
                errors.append("clean_signal requires clean Standards and Spec certificates")
            if gate_evidence.get("artifact_review") != "clean" or gate_evidence.get("artifact_review_head") != data["head"]:
                errors.append("clean_signal requires clean artifact review at current head")
            if gate_evidence.get("actions_state") != "green" or gate_evidence.get("actions_head") != data["head"]:
                errors.append("clean_signal requires successful Actions evidence at current head")

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

    if data["phase"] in {"READY_FOR_HUMAN_MERGE", "READY_TO_AUTOMERGE", "MERGING"}:
        if data["clean_signal"] != data["head"]:
            errors.append(f"{data['phase']} requires Reviewer CLEAN at current head")
        gate_evidence = data["gate_evidence"]
        if isinstance(gate_evidence, dict):
            if gate_evidence.get("standards_status") != "clean" or gate_evidence.get("spec_status") != "clean":
                errors.append(f"{data['phase']} requires clean Standards and Spec certificates")
            if gate_evidence.get("artifact_review") != "clean" or gate_evidence.get("artifact_review_head") != data["head"]:
                errors.append(f"{data['phase']} requires clean artifact review at current head")
            if gate_evidence.get("actions_state") != "green" or gate_evidence.get("actions_head") != data["head"]:
                errors.append(f"{data['phase']} requires successful Actions evidence at current head")

    if not isinstance(data["checks"], str):
        errors.append("checks must be a string")
    _validate_gate_evidence(errors, data["gate_evidence"], data["head"], data["scope_version"])
    if data["escalation"] is not None and not isinstance(data["escalation"], str):
        errors.append("escalation must be null or a string")
    if not isinstance(data["next"], str) or not data["next"].strip():
        errors.append("next must be a non-empty string")

    return errors


def load_checkpoint(path: Path) -> dict[str, Any]:
    value = read_checkpoint_json(path)
    errors = validate_data(value)
    if errors:
        raise ValueError("\n".join(f"- {error}" for error in errors))
    return value


def read_checkpoint_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"checkpoint not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def migrate_data(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("checkpoint must be a JSON object")

    migrated = copy.deepcopy(value)
    if migrated.get("schema_version") == 3:
        migrated["schema_version"] = 4
        migrated["orchestrator_mode"] = "parent-resident"
        migrated.pop("automations", None)
    if migrated.get("schema_version") == 4:
        migrated["schema_version"] = 5
        migrated["gate_evidence"] = empty_gate_evidence()
        if migrated.get("clean_signal") is not None:
            migrated["clean_signal"] = None
            if migrated.get("phase") in {
                "PRESENTING",
                "READY_FOR_HUMAN_MERGE",
                "READY_TO_AUTOMERGE",
                "MERGING",
            }:
                migrated["phase"] = "REVIEWING"
                migrated["next"] = (
                    "Rebuild schema v5 source, artifact, and Actions evidence "
                    "before requesting exact-head Reviewer CLEAN."
                )

    errors = validate_data(migrated)
    if errors:
        raise ValueError("\n".join(f"- {error}" for error in errors))
    return migrated


def load_resume_checkpoint(path: Path) -> dict[str, Any]:
    return migrate_data(read_checkpoint_json(path))


def _fmt(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_state(data: dict[str, Any]) -> str:
    lines = [
        f"schema_version={data['schema_version']} repository={data['repository']}",
        f"orchestrator_mode={data['orchestrator_mode']}",
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
            "gates="
            f"class:{data['gate_evidence']['head_change_class']},"
            f"standards:{data['gate_evidence']['standards_status']},"
            f"spec:{data['gate_evidence']['spec_status']},"
            f"artifact:{data['gate_evidence']['artifact_review']},"
            f"actions:{data['gate_evidence']['actions_state']}",
            f"artifacts={len(data['artifacts'])} escalation={_fmt(data['escalation'])}",
        ]
    )
    if data.get("paused_lane") is not None:
        paused = data["paused_lane"]
        lines.append(
            f"paused_lane={paused['lane_kind']} issue={_fmt(paused['issue'])} pr={_fmt(paused['pr'])} "
            f"worker={_fmt(paused['worker_task'])} dirty={_fmt(paused['worker_dirty'])}"
        )
    lines.append(f"next={data['next']}")
    return "\n".join(lines)


def render_resume(data: dict[str, Any]) -> str:
    state = render_state(data)
    return f"""Use the orchestrate-olympus skill in this parent task for dm1681/Olympus.

This parent task is the Olympus Orchestrator. Do not spawn an Orchestrator subagent. This checkpoint is a validated host-local cache, not authority. Recover live GitHub, child-subagent, and worktree state before every mutation; live evidence supersedes stale values.

CHECKPOINT
{state}

Follow the skill's core contract and subagent lifecycle. Recover or spawn the reusable Reviewer first, use one-shot Planners and a reusable active-lane Worker, and use messages plus waits as the event loop. Keep dispatch, merge, and pause authority independent. If pause_mode is not running, perform no implementation, review, presentation, merge, or GitHub write without an explicit owner command. Preserve dirty worktrees. Do not duplicate children or comments. Do not send a final response while active work or a bounded wait remains. Continue an eligible autonomous queue only after the current lane is merged and reconciled; READY_FOR_HUMAN_MERGE under owner-only merge authority is terminal even when later issues are eligible."""


def sample_checkpoint() -> dict[str, Any]:
    sha = "a" * 40
    return {
        "schema_version": 5,
        "repository": "dm1681/Olympus",
        "orchestrator_mode": "parent-resident",
        "dispatch_mode": "human-controlled",
        "merge_mode": "owner-only",
        "pause_mode": "running",
        "lane_kind": "issue",
        "phase": "WORKING",
        "scope_version": 1,
        "issue": 11,
        "pr": None,
        "branch": "agent/issue-11-example",
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
        "gate_evidence": empty_gate_evidence(),
        "clean_signal": None,
        "artifacts": [],
        "escalation": None,
        "next": "continue the current TDD slice",
    }


def self_test() -> None:
    valid = sample_checkpoint()
    assert validate_data(valid) == []
    assert "dispatch_mode=human-controlled" in render_state(valid)
    assert "live evidence supersedes stale values" in render_resume(valid)
    assert "parent task is the Olympus Orchestrator" in render_resume(valid)

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

    ready = copy.deepcopy(valid)
    ready.update(
        {
            "pr": 35,
            "phase": "READY_FOR_HUMAN_MERGE",
            "clean_signal": "a" * 40,
            "gate_evidence": {
                **empty_gate_evidence(),
                "head_change_class": "source",
                "source_tree_hash": "b" * 64,
                "runtime_fingerprint": "c" * 64,
                "standards_status": "clean",
                "standards_head": "a" * 40,
                "standards_scope_version": 1,
                "spec_status": "clean",
                "spec_head": "a" * 40,
                "spec_scope_version": 1,
                "artifact_review": "clean",
                "artifact_review_head": "a" * 40,
                "test_evidence": [
                    {
                        "command": "pnpm test",
                        "scope": "aggregate",
                        "required": True,
                        "source_tree_hash": "b" * 64,
                        "runtime_fingerprint": "c" * 64,
                        "result": "pass",
                    }
                ],
                "actions_state": "green",
                "actions_head": "a" * 40,
            },
        }
    )
    assert validate_data(ready) == []

    ready_without_clean = copy.deepcopy(ready)
    ready_without_clean["clean_signal"] = None
    assert any("requires Reviewer CLEAN" in error for error in validate_data(ready_without_clean))

    legacy_cloud_review = copy.deepcopy(ready)
    legacy_cloud_review["phase"] = "CODEX_REVIEWING"
    legacy_cloud_review["codex_review"] = {}
    legacy_errors = validate_data(legacy_cloud_review)
    assert any("CODEX_REVIEWING was removed" in error for error in legacy_errors)
    assert any("codex_review was removed" in error for error in legacy_errors)

    legacy_automations = copy.deepcopy(valid)
    legacy_automations["automations"] = {}
    assert any(
        "automations was removed" in error
        for error in validate_data(legacy_automations)
    )

    real_v3 = copy.deepcopy(valid)
    real_v3["schema_version"] = 3
    real_v3.pop("orchestrator_mode")
    real_v3["automations"] = {"orchestrator": None, "reviewer": None}
    migrated_v3 = migrate_data(real_v3)
    assert migrated_v3["schema_version"] == 5
    assert migrated_v3["orchestrator_mode"] == "parent-resident"
    assert "automations" not in migrated_v3
    assert migrated_v3["gate_evidence"]["standards_status"] == "not-run"

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
            "branch": "agent/setup-example",
            "paused_lane": {
                "lane_kind": "issue",
                "scope_version": 1,
                "issue": 11,
                "pr": None,
                "branch": "agent/issue-11-example",
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
    for name in ("validate", "render-state", "render-resume", "migrate"):
        command = subparsers.add_parser(name)
        command.add_argument("checkpoint", type=Path)
    subparsers.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        print("checkpoint self-test: PASS")
        return 0

    try:
        if args.command in {"render-resume", "migrate"}:
            data = load_resume_checkpoint(args.checkpoint)
        else:
            data = load_checkpoint(args.checkpoint)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "validate":
        print("checkpoint valid")
    elif args.command == "render-state":
        print(render_state(data))
    elif args.command == "migrate":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(render_resume(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
