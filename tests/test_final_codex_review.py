from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class FinalCodexReviewTests(unittest.TestCase):
    def test_gate_forbids_request_before_reviewer_approval(self) -> None:
        gate = (SKILL_ROOT / "references" / "codex-github-review.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(gate.split())
        self.assertIn("Reviewer CLEAN is the authorization event", normalized)
        self.assertIn("Do not post `@codex review`", normalized)

    def test_orchestrator_prompt_treats_request_as_last_review_trigger(self) -> None:
        prompt = (SKILL_ROOT / "references" / "orchestrator-prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("final review trigger", prompt)
        self.assertIn("Reviewer CLEAN", prompt)


if __name__ == "__main__":
    unittest.main()
