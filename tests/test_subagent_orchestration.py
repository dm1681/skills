from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class SubagentOrchestrationTests(unittest.TestCase):
    def test_scheduled_automation_contract_is_removed(self) -> None:
        self.assertFalse(
            (SKILL_ROOT / "references" / "scheduled-automations.md").exists()
        )
        checked = [
            SKILL_ROOT / "SKILL.md",
            *(SKILL_ROOT / "references").glob("*.md"),
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in checked)
        for removed in (
            "olympus-work-orchestrator",
            "olympus-pr-review-watcher",
            "scheduled heartbeat",
            "every 10 minutes",
        ):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, combined)

    def test_subagent_roles_have_explicit_lifecycles(self) -> None:
        lifecycle = (
            SKILL_ROOT / "references" / "subagent-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(lifecycle.split())
        lowered = normalized.lower()
        self.assertIn("Reviewer: reusable", normalized)
        self.assertIn("Planner: one-shot", normalized)
        self.assertIn("Worker: reusable for the active lane", normalized)
        self.assertIn("Watcher: optional, bounded, and read-only", normalized)
        self.assertIn("spawn or recover the reviewer before", lowered)

    def test_parent_uses_event_driven_waits_and_stays_resident(self) -> None:
        lifecycle = (
            SKILL_ROOT / "references" / "subagent-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(lifecycle.split())
        self.assertIn("Use subagent messages and waits as the event loop", normalized)
        self.assertIn("Do not poll on a fixed schedule", normalized)
        self.assertIn("must not send its final response", normalized)
        self.assertIn("eligible autonomous queue remains", normalized)
        self.assertIn("CI or another external condition", normalized)

    def test_worker_and_reviewer_are_reused_across_repair_rounds(self) -> None:
        contract = (
            SKILL_ROOT / "references" / "orchestration-contract.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(contract.split())
        lowered = normalized.lower()
        self.assertIn("reuse the same active-lane worker", lowered)
        self.assertIn("reuse the same reviewer", lowered)
        self.assertIn("send a follow-up turn", normalized)


if __name__ == "__main__":
    unittest.main()
