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
            "schema_version": 2,
            "repository": "dm1681/Olympus",
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
        rendered = self.run_checkpoint(data, "render-heartbeat")
        self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
        self.assertIn("lane_kind=none phase=IDLE", rendered.stdout)

    def test_dependent_role_tasks_require_orchestrator_task(self) -> None:
        task_id = "11111111-1111-1111-1111-111111111111"
        for field in ("reviewer_task", "planner_task", "worker_task"):
            with self.subTest(field=field):
                data = self.idle_checkpoint()
                data[field] = task_id
                validated = self.run_checkpoint(data)
                self.assertNotEqual(0, validated.returncode)
                self.assertIn(
                    f"{field} requires orchestrator_task",
                    validated.stderr,
                )

    def test_orchestrator_can_be_recorded_before_reviewer(self) -> None:
        data = self.idle_checkpoint()
        data["orchestrator_task"] = "11111111-1111-1111-1111-111111111111"
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)

    def test_codex_reviewing_requires_reviewer_clean_at_current_head(self) -> None:
        head = "a" * 40
        data = self.idle_checkpoint()
        data.update(
            {
                "lane_kind": "repair",
                "phase": "CODEX_REVIEWING",
                "pr": 35,
                "head": head,
                "orchestrator_task": "11111111-1111-1111-1111-111111111111",
                "reviewer_task": "22222222-2222-2222-2222-222222222222",
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
        missing_clean = self.run_checkpoint(data)
        self.assertNotEqual(0, missing_clean.returncode)
        self.assertIn(
            "CODEX_REVIEWING requires Reviewer CLEAN at current head",
            missing_clean.stderr,
        )

        data["clean_signal"] = head
        validated = self.run_checkpoint(data)
        self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)


if __name__ == "__main__":
    unittest.main()
