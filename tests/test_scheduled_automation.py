from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class ScheduledAutomationTests(unittest.TestCase):
    def test_cold_start_requires_codex_heartbeat_automations(self) -> None:
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(contract.split())
        self.assertIn("create a Codex scheduled heartbeat automation", normalized)
        self.assertIn("olympus-work-orchestrator", contract)
        self.assertIn("olympus-pr-review-watcher", contract)
        self.assertIn("10 minutes", contract)

    def test_automation_creation_waits_for_actual_task_identity(self) -> None:
        prompt = (SKILL_ROOT / "references" / "orchestrator-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(prompt.split())
        self.assertIn("only after its actual task ID is known", normalized)
        self.assertIn("native Codex automation tool", normalized)
        self.assertIn("Never substitute cron", normalized)

    def test_entrypoint_makes_automation_creation_a_startup_gate(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(entrypoint.split()).lower()
        self.assertIn(
            "create or recover its codex scheduled heartbeat automation", normalized
        )
        self.assertIn(
            "before creating a planner, worker, recovery, or maintenance task",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
