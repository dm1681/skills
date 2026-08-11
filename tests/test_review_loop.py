from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "review-loop"
ENTRYPOINT = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

# The outcomes a round can end in. Three of them show the same green check,
# so losing one from the entrypoint's table is the failure the whole skill
# exists to prevent; `failed` is the catch-all that keeps an unclassifiable
# round from silently landing in one of the others.
OUTCOMES = ("clean", "findings", "stalled", "skipped", "failed")


class ReviewLoopPackagingTests(unittest.TestCase):
    def test_entrypoint_routes_every_bundled_reference(self) -> None:
        """A reference the entrypoint never links is one the agent never
        reaches: progressive disclosure only works through a pointer."""
        references = sorted((SKILL_ROOT / "references").glob("*.md"))
        self.assertTrue(references, "the skill bundles no references")
        for reference in references:
            with self.subTest(reference=reference.name):
                self.assertIn(f"references/{reference.name}", ENTRYPOINT)

    def test_every_round_outcome_stays_distinguishable(self) -> None:
        for outcome in OUTCOMES:
            with self.subTest(outcome=outcome):
                self.assertIn(f"**{outcome}**", ENTRYPOINT)

    def test_the_loop_stays_bounded_and_hands_merging_to_a_human(self) -> None:
        """Two constraints the issue states outright. A round cap keeps a
        reviewer and a fixer from ping-ponging forever; merging is a human's
        call, so the entrypoint must never reach for the merge command."""
        self.assertIn("round cap", ENTRYPOINT.lower())
        self.assertIn("never merges", ENTRYPOINT)
        self.assertNotIn("gh pr merge", ENTRYPOINT)
