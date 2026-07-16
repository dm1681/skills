from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class OrchestrationStartupTests(unittest.TestCase):
    def test_contract_requires_orchestrator_only_cold_start(self) -> None:
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("create the persistent Orchestrator as the only role task", contract)
        self.assertIn("Never batch or parallel-create", contract)

    def test_orchestrator_has_bootstrap_and_identity_handshake(self) -> None:
        prompt = (SKILL_ROOT / "references" / "orchestrator-prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Bootstrap task prompt", prompt)
        self.assertIn("## Identity handshake", prompt)
        self.assertIn("Do not create any other role task during this bootstrap turn", prompt)

    def test_planner_identity_is_sent_immediately_after_creation(self) -> None:
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(contract.split())
        self.assertIn(
            "send `PLANNER_TASK_ID` immediately after the creation call returns",
            normalized,
        )
        self.assertIn("Do not wait for `READY_FOR_IDENTITY`", normalized)
        self.assertIn(
            "pending client-thread identifier", normalized
        )
        self.assertIn(
            "Never send a pending client ID as `PLANNER_TASK_ID`", normalized
        )

    def test_planner_does_not_pause_read_only_planning_for_identity(self) -> None:
        prompt = (SKILL_ROOT / "references" / "planner-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(prompt.split())
        self.assertIn("Begin read-only planning immediately", normalized)
        self.assertIn("Do not stop at or emit `READY_FOR_IDENTITY`", normalized)
        self.assertIn(
            "Both the base and eligibility gates must pass before any GitHub write",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
