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
    def test_idle_checkpoint_validates_and_renders(self) -> None:
        data = {
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
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            validated = subprocess.run(
                [sys.executable, str(CHECKPOINT), "validate", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, validated.returncode, validated.stdout + validated.stderr)
            rendered = subprocess.run(
                [sys.executable, str(CHECKPOINT), "render-heartbeat", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
            self.assertIn("lane_kind=none phase=IDLE", rendered.stdout)


if __name__ == "__main__":
    unittest.main()
