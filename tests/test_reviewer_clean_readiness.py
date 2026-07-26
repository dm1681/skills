from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class ReviewerCleanReadinessTests(unittest.TestCase):
    def test_cloud_review_reference_is_removed(self) -> None:
        self.assertFalse(
            (SKILL_ROOT / "references" / "codex-github-review.md").exists()
        )

    def test_active_skill_contract_has_no_github_codex_review_trigger(self) -> None:
        checked = [
            SKILL_ROOT / "SKILL.md",
            *(SKILL_ROOT / "references").glob("*.md"),
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in checked)
        for removed in ("@codex review", "CODEX_REVIEWING", "CODEX_REVIEW_ACCEPTED"):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, combined)

    def test_presentation_flows_directly_to_readiness(self) -> None:
        contract = (
            SKILL_ROOT / "references" / "orchestration-contract.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(contract.split())
        self.assertIn(
            "PRESENTING --audit complete, CLEAN still valid--> READY_FOR_HUMAN_MERGE",
            normalized,
        )
        self.assertIn(
            "reusable-Reviewer CLEAN signal approving all work at the exact full head SHA",
            normalized,
        )

    def test_orchestrator_never_requests_cloud_review(self) -> None:
        prompt = (
            SKILL_ROOT / "references" / "orchestrator-prompt.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(prompt.split())
        self.assertIn("Never request a hosted cloud review by GitHub comment", normalized)
        self.assertIn("move directly to the final readiness or merge audit", normalized)


if __name__ == "__main__":
    unittest.main()
