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


if __name__ == "__main__":
    unittest.main()
