from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class OrchestrationStartupTests(unittest.TestCase):
    def test_current_parent_becomes_orchestrator_before_spawning_children(self) -> None:
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(contract.split())
        lowered = normalized.lower()
        self.assertIn("the current parent task is the orchestrator", lowered)
        self.assertIn("do not spawn a separate orchestrator subagent", lowered)
        self.assertIn("spawn or recover the reusable reviewer first", lowered)

    def test_orchestrator_prompt_is_for_the_parent_task(self) -> None:
        prompt = (SKILL_ROOT / "references" / "orchestrator-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(prompt.split())
        self.assertIn("## Parent task prompt", prompt)
        self.assertIn("This current task is the Olympus Orchestrator", normalized)
        self.assertIn("Do not spawn an Orchestrator subagent", normalized)
        self.assertIn("Do not send a final response while", normalized)

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

    def test_worker_identity_is_sent_immediately_after_creation(self) -> None:
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(
            encoding="utf-8"
        )
        prompt = (SKILL_ROOT / "references" / "orchestrator-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized_contract = " ".join(contract.split())
        normalized_prompt = " ".join(prompt.split())
        self.assertIn("### Worker creation and identity order", contract)
        self.assertIn(
            "send `WORKER_TASK_ID` immediately after the creation call returns",
            normalized_contract,
        )
        self.assertIn(
            "immediately send WORKER_TASK_ID",
            normalized_prompt,
        )

    def test_matt_triage_label_gate_covers_issues_and_prs(self) -> None:
        policy = (SKILL_ROOT / "references" / "matt-triage-labels.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(policy.split())
        for label in (
            "needs-triage",
            "needs-info",
            "ready-for-agent",
            "ready-for-human",
            "wontfix",
        ):
            self.assertIn(f"`{label}`", policy)
        self.assertIn("GitHub labels are repository-wide", normalized)
        self.assertIn("both issues and pull requests", normalized)
        self.assertIn("`docs/agents/triage-labels.md`", normalized)
        self.assertIn(
            "gh label list --repo dm1681/Olympus --limit 1000 --json name",
            normalized,
        )
        self.assertIn("Create only missing mapped labels", normalized)
        self.assertIn("Never rename, delete, or overwrite", normalized)

    def test_label_gate_precedes_lane_dispatch(self) -> None:
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(
            encoding="utf-8"
        )
        prompt = (SKILL_ROOT / "references" / "orchestrator-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized_contract = " ".join(contract.split())
        normalized_prompt = " ".join(prompt.split())
        self.assertIn("### Matt Pocock triage-label gate", contract)
        self.assertIn("before dispatching any Planner or Worker", normalized_contract)
        self.assertIn("enter `ESCALATED`", normalized_contract)
        self.assertIn(
            "verify the matt pocock triage-label gate",
            normalized_prompt.lower(),
        )


if __name__ == "__main__":
    unittest.main()
