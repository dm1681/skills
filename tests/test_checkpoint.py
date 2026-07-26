from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "skills" / "orchestrate-olympus" / "scripts" / "checkpoint.py"


class CheckpointTests(unittest.TestCase):
    @staticmethod
    def idle_checkpoint() -> dict[str, object]:
        return {
            "schema_version": 5,
            "repository": "dm1681/Olympus",
            "orchestrator_mode": "parent-resident",
            "dispatch_mode": "human-controlled",
            "merge_mode": "owner-only",
            "pause_mode": "running",
            "lane_kind": "none",
            "phase": "IDLE",
            "scope_version": 1,
            "issue": None,
            "pr": None,
            "branch": None,
            "base": None,
            "head": None,
            "orchestrator_task": None,
            "planner_task": None,
            "worker_task": None,
            "reviewer_task": None,
            "worker_worktree": None,
            "worker_dirty": False,
            "dirty_paths": [],
            "findings": [],
            "checks": "none",
            "gate_evidence": {
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
            },
            "clean_signal": None,
            "artifacts": [],
            "escalation": None,
            "next": "Wait for owner approval.",
        }

    def run_checkpoint(
        self,
        data: dict[str, object],
        command: str = "validate",
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CHECKPOINT), command, str(path)],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_idle_checkpoint_validates_and_renders(self) -> None:
        data = self.idle_checkpoint()
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)
        rendered = self.run_checkpoint(data, "render-resume")
        self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
        self.assertIn("lane_kind=none phase=IDLE", rendered.stdout)
        self.assertIn("parent task is the Olympus Orchestrator", rendered.stdout)

    def test_planner_and_worker_require_reviewer_subagent(self) -> None:
        task_id = "11111111-1111-1111-1111-111111111111"
        for field in ("planner_task", "worker_task"):
            with self.subTest(field=field):
                data = self.idle_checkpoint()
                data[field] = task_id
                validated = self.run_checkpoint(data)
                self.assertNotEqual(0, validated.returncode)
                self.assertIn(
                    f"{field} requires reviewer_task",
                    validated.stderr,
                )

    def test_reviewer_can_be_recorded_without_parent_task_uuid(self) -> None:
        data = self.idle_checkpoint()
        data["reviewer_task"] = "11111111-1111-1111-1111-111111111111"
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

    def test_legacy_scheduled_automation_state_is_rejected(self) -> None:
        data = self.idle_checkpoint()
        data["automations"] = {}
        validated = self.run_checkpoint(data)
        self.assertNotEqual(0, validated.returncode)
        self.assertIn("automations was removed", validated.stderr)

    def test_real_v3_checkpoint_can_migrate_and_render_resume(self) -> None:
        data = self.idle_checkpoint()
        data["schema_version"] = 3
        data.pop("orchestrator_mode")
        data.pop("gate_evidence")
        data["automations"] = {
            "orchestrator": None,
            "reviewer": None,
        }

        strict = self.run_checkpoint(data)
        self.assertNotEqual(0, strict.returncode)
        self.assertIn("orchestrator_mode", strict.stderr)

        rendered = self.run_checkpoint(data, "render-resume")
        self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
        self.assertIn("schema_version=5", rendered.stdout)
        self.assertIn("orchestrator_mode=parent-resident", rendered.stdout)

        migrated = self.run_checkpoint(data, "migrate")
        self.assertEqual(0, migrated.returncode, migrated.stdout + migrated.stderr)
        normalized = json.loads(migrated.stdout)
        self.assertEqual(5, normalized["schema_version"])
        self.assertEqual("parent-resident", normalized["orchestrator_mode"])
        self.assertNotIn("automations", normalized)

    def test_ready_for_human_merge_requires_reviewer_clean_at_current_head(self) -> None:
        head = "a" * 40
        data = self.idle_checkpoint()
        data.update(
            {
                "lane_kind": "repair",
                "phase": "READY_FOR_HUMAN_MERGE",
                "pr": 35,
                "head": head,
                "reviewer_task": "22222222-2222-2222-2222-222222222222",
            }
        )
        missing_clean = self.run_checkpoint(data)
        self.assertNotEqual(0, missing_clean.returncode)
        self.assertIn(
            "READY_FOR_HUMAN_MERGE requires Reviewer CLEAN at current head",
            missing_clean.stderr,
        )

        data["clean_signal"] = head
        data["gate_evidence"] = {
            "head_change_class": "source",
            "source_tree_hash": "b" * 64,
            "runtime_fingerprint": "c" * 64,
            "standards_status": "clean",
            "standards_head": head,
            "standards_scope_version": 1,
            "spec_status": "clean",
            "spec_head": head,
            "spec_scope_version": 1,
            "artifact_review": "clean",
            "artifact_review_head": head,
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
            "actions_head": head,
            "actions_degraded_evidence": None,
        }
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

        data["dispatch_mode"] = "autonomous"
        rendered = self.run_checkpoint(data, "render-resume")
        self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
        self.assertIn(
            "READY_FOR_HUMAN_MERGE under owner-only merge authority is terminal",
            rendered.stdout,
        )

    def test_legacy_codex_cloud_review_state_is_rejected(self) -> None:
        head = "a" * 40
        data = self.idle_checkpoint()
        data.update(
            {
                "lane_kind": "repair",
                "phase": "CODEX_REVIEWING",
                "pr": 35,
                "head": head,
                "clean_signal": head,
                "codex_review": {
                    "head": head,
                    "request_comment_id": 123,
                    "request_url": "https://github.com/dm1681/Olympus/pull/35#issuecomment-123",
                    "review_id": None,
                    "status": "pending",
                    "accepted_head": None,
                },
            }
        )
        legacy = self.run_checkpoint(data)
        self.assertNotEqual(0, legacy.returncode)
        self.assertIn("CODEX_REVIEWING", legacy.stderr)
        self.assertIn("codex_review was removed", legacy.stderr)

    def test_artifact_only_head_can_reuse_source_axes_but_needs_exact_artifact_review(self) -> None:
        source_head = "a" * 40
        artifact_head = "d" * 40
        data = self.idle_checkpoint()
        data.update(
            {
                "lane_kind": "repair",
                "phase": "ARTIFACT_VERIFYING",
                "pr": 35,
                "head": artifact_head,
                "gate_evidence": {
                    "head_change_class": "deterministic-artifact",
                    "source_tree_hash": "b" * 64,
                    "runtime_fingerprint": "c" * 64,
                    "standards_status": "clean",
                    "standards_head": source_head,
                    "standards_scope_version": 1,
                    "spec_status": "clean",
                    "spec_head": source_head,
                    "spec_scope_version": 1,
                    "artifact_review": "not-run",
                    "artifact_review_head": None,
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
                    "actions_state": "pending",
                    "actions_head": None,
                    "actions_degraded_evidence": None,
                },
            }
        )
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

        data["phase"] = "READY_FOR_HUMAN_MERGE"
        data["clean_signal"] = artifact_head
        not_ready = self.run_checkpoint(data)
        self.assertNotEqual(0, not_ready.returncode)
        self.assertIn("requires clean artifact review", not_ready.stderr)
        self.assertIn("requires successful Actions evidence", not_ready.stderr)

    def test_v4_checkpoint_migrates_with_conservative_gate_defaults(self) -> None:
        data = self.idle_checkpoint()
        data["schema_version"] = 4
        data.pop("gate_evidence")
        migrated = self.run_checkpoint(data, "migrate")
        self.assertEqual(0, migrated.returncode, migrated.stdout + migrated.stderr)
        normalized = json.loads(migrated.stdout)
        self.assertEqual(5, normalized["schema_version"])
        self.assertEqual("mixed-or-unknown", normalized["gate_evidence"]["head_change_class"])
        self.assertEqual("not-run", normalized["gate_evidence"]["standards_status"])

    def test_clean_axes_require_both_certificates_and_matching_aggregate(self) -> None:
        head = "a" * 40
        data = self.idle_checkpoint()
        data.update({"lane_kind": "repair", "phase": "SOURCE_REVIEWING", "pr": 35, "head": head})
        data["gate_evidence"].update(
            {
                "head_change_class": "source",
                "source_tree_hash": "b" * 64,
                "runtime_fingerprint": "c" * 64,
                "standards_status": "clean",
                "standards_head": head,
                "standards_scope_version": 1,
                "spec_status": "clean",
                "spec_head": head,
                "spec_scope_version": 1,
            }
        )
        missing_tests = self.run_checkpoint(data)
        self.assertNotEqual(0, missing_tests.returncode)
        self.assertIn("matching required aggregate test evidence", missing_tests.stderr)

        data["gate_evidence"]["test_evidence"] = [
            {
                "command": "pnpm test",
                "scope": "aggregate",
                "required": True,
                "source_tree_hash": "b" * 64,
                "runtime_fingerprint": "c" * 64,
                "result": "pass",
            }
        ]
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

        data["scope_version"] = 2
        stale_scope = self.run_checkpoint(data)
        self.assertNotEqual(0, stale_scope.returncode)
        self.assertIn("must match the current scope_version", stale_scope.stderr)

    def test_green_actions_require_exact_head(self) -> None:
        head = "a" * 40
        data = self.idle_checkpoint()
        data.update({"lane_kind": "repair", "phase": "REVIEWING", "pr": 35, "head": head})
        data["gate_evidence"].update(
            {
                "actions_state": "green",
                "actions_head": "d" * 40,
            }
        )
        invalid = self.run_checkpoint(data)
        self.assertNotEqual(0, invalid.returncode)
        self.assertIn("green Actions evidence must match the current head", invalid.stderr)

    def test_degraded_actions_requires_bounded_retry_evidence(self) -> None:
        data = self.idle_checkpoint()
        data["gate_evidence"]["actions_state"] = "unknown-degraded"
        missing = self.run_checkpoint(data)
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("requires actions_degraded_evidence", missing.stderr)

        data["gate_evidence"]["actions_degraded_evidence"] = {
            "attempts": 3,
            "last_error": "authenticated Actions endpoint returned 503",
            "corroboration": ["viewer identity", "remote branch head"],
        }
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)


if __name__ == "__main__":
    unittest.main()
