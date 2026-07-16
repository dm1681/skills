from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class FollowUpIssueTests(unittest.TestCase):
    def test_entrypoint_routes_follow_up_issue_contract(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/follow-up-issues.md", entrypoint)
        self.assertTrue(
            (SKILL_ROOT / "references" / "follow-up-issues.md").exists()
        )

    def test_only_agreed_deferred_feedback_is_considered(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "follow-up-issues.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("assesses `AGREE`", normalized)
        self.assertIn("`Worker: NOT SENT`", normalized)
        self.assertIn("non-blocking or outside the current scope", normalized)
        self.assertIn("Do not propose an issue for a disagreement", normalized)

    def test_candidate_quality_and_safety_gates_are_explicit(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "follow-up-issues.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("durable Olympus-relevant problem", normalized)
        self.assertIn("there is enough evidence", normalized)
        self.assertIn("no existing issue, PR, roadmap item", normalized)
        self.assertIn("without exposing a vulnerability", normalized)
        self.assertIn(
            "pure upstream behavior with no concrete Olympus-owned",
            normalized,
        )

    def test_reviewer_proposes_and_orchestrator_creates(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "follow-up-issues.md"
        ).read_text(encoding="utf-8")
        reviewer = (
            SKILL_ROOT / "references" / "reviewer-prompt.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join((policy + " " + reviewer).split())
        self.assertIn("Reviewer owns the technical judgment", normalized)
        self.assertIn(
            "does not create, label, assign, close, or dispatch",
            normalized,
        )
        self.assertIn("FOLLOW_UP_ISSUE_CANDIDATE", normalized)
        self.assertIn("parent Orchestrator standing authority", normalized)

    def test_issue_is_self_contained_and_needs_triage_only(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "follow-up-issues.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        for section in (
            "## Origin",
            "## Problem",
            "## Evidence",
            "## Desired outcome",
            "## Likely surfaces",
            "## Acceptance notes",
        ):
            with self.subTest(section=section):
                self.assertIn(section, policy)
        self.assertIn("configured Matt Pocock `needs-triage`", normalized)
        self.assertIn("does not authorize implementation", normalized)
        self.assertIn("`ready-for-agent`", normalized)

    def test_deduplication_and_recovery_use_stable_markers(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "follow-up-issues.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("search by source activity ID", normalized)
        self.assertIn("olympus-follow-up source=", normalized)
        self.assertIn("never creates a second issue", normalized)
        self.assertIn("FOLLOW_UP: CAPTURE PENDING", normalized)

    def test_capture_does_not_change_current_lane_readiness(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "follow-up-issues.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("never sends work to the current Worker", normalized)
        self.assertIn("changes the current scope version", normalized)
        self.assertIn("invalidates CLEAN", normalized)
        self.assertIn("withholds readiness or merge", normalized)


if __name__ == "__main__":
    unittest.main()
