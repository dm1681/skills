from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class ExternalPrFeedbackTests(unittest.TestCase):
    def test_reviewer_owns_assessment_and_dispatch_reply(self) -> None:
        prompt = (SKILL_ROOT / "references" / "reviewer-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(prompt.split())
        self.assertIn("external PR comment or review item", normalized)
        self.assertIn("AGREE or DISAGREE", normalized)
        self.assertIn("concise evidence-based reasoning", normalized)
        self.assertIn(
            "Worker SENT with a finding ID or NOT SENT with a reason",
            normalized,
        )
        self.assertIn("reply in its original thread", normalized)

    def test_external_feedback_protocol_is_explicit_and_deduplicated(self) -> None:
        boundaries = (
            SKILL_ROOT / "references" / "review-boundaries.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(boundaries.split())
        self.assertIn("sole conversational owner", normalized)
        self.assertIn("people, apps, or bots", normalized)
        self.assertIn("**Olympus Reviewer assessment:** AGREE|DISAGREE", normalized)
        self.assertIn("**Reason:** <concise evidence-based reasoning>", normalized)
        self.assertIn(
            "**Worker:** SENT as `<FINDING_ID>`|NOT SENT — <concise reason>",
            normalized,
        )
        self.assertIn("olympus-review-assessment source=", normalized)
        self.assertIn("source activity ID to prevent duplicate assessments", normalized)

    def test_only_promoted_worker_owned_findings_are_dispatched(self) -> None:
        boundaries = (
            SKILL_ROOT / "references" / "review-boundaries.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(boundaries.split())
        self.assertIn("agreeing with an in-scope Worker-owned defect", normalized)
        self.assertIn("send it to the reusable Worker", normalized)
        self.assertIn("Report `NOT SENT` for every disagreement", normalized)
        self.assertIn("advisory, duplicates, already assigned", normalized)
        self.assertIn("require the Orchestrator, owner, or upstream actor", normalized)

    def test_worker_never_acts_on_or_replies_to_external_comment_directly(self) -> None:
        prompt = (SKILL_ROOT / "references" / "worker-prompt.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(prompt.split())
        self.assertIn("Never act directly on a PR comment or review item", normalized)
        self.assertIn("Repair only a Reviewer-promoted finding", normalized)
        self.assertIn("Do not reply to the external commenter", normalized)

    def test_readiness_waits_for_assessment_but_clean_is_head_keyed(self) -> None:
        boundaries = (
            SKILL_ROOT / "references" / "review-boundaries.md"
        ).read_text(encoding="utf-8")
        contract = (
            SKILL_ROOT / "references" / "orchestration-contract.md"
        ).read_text(encoding="utf-8")
        normalized_boundaries = " ".join(boundaries.split())
        normalized_contract = " ".join(contract.split())
        self.assertIn(
            "pauses presentation, readiness, and merge until its assessment",
            normalized_boundaries,
        )
        self.assertIn(
            "comment alone does not automatically invalidate exact-head code evidence or CLEAN",
            normalized_boundaries,
        )
        self.assertIn("blocking `AGREE` supersedes CLEAN immediately", normalized_boundaries)
        self.assertIn("returns the lane to `REPAIRING`", normalized_boundaries)
        self.assertIn(
            "every substantive external PR feedback item",
            normalized_contract,
        )

    def test_reviewer_reports_verified_resolution_without_resolving_foreign_thread(
        self,
    ) -> None:
        boundaries = (
            SKILL_ROOT / "references" / "review-boundaries.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(boundaries.split())
        self.assertIn("reply in the same source thread", normalized)
        self.assertIn("finding ID, verified head, and outcome", normalized)
        self.assertIn("do not resolve a thread authored by someone else", normalized)


if __name__ == "__main__":
    unittest.main()
