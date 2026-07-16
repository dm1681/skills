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
            "schema_version": 4,
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
        data["automations"] = {
            "orchestrator": None,
            "reviewer": None,
        }

        strict = self.run_checkpoint(data)
        self.assertNotEqual(0, strict.returncode)
        self.assertIn("orchestrator_mode", strict.stderr)

        rendered = self.run_checkpoint(data, "render-resume")
        self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
        self.assertIn("schema_version=4", rendered.stdout)
        self.assertIn("orchestrator_mode=parent-resident", rendered.stdout)

        migrated = self.run_checkpoint(data, "migrate")
        self.assertEqual(0, migrated.returncode, migrated.stdout + migrated.stderr)
        normalized = json.loads(migrated.stdout)
        self.assertEqual(4, normalized["schema_version"])
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


if __name__ == "__main__":
    unittest.main()
