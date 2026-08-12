from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "review-loop"
ENTRYPOINT = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
SCRIPTS = SKILL_ROOT / "scripts"

_SPEC = importlib.util.spec_from_file_location(
    "review_loop_round_status", SCRIPTS / "round_status.py"
)
assert _SPEC is not None and _SPEC.loader is not None
ROUND_STATUS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ROUND_STATUS)


def _review(review_id, head, login):
    return {"id": review_id, "commit_id": head, "user": {"login": login}}


def _comment(review_id, path="a.py"):
    return {"pull_request_review_id": review_id, "path": path}

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
        for script in sorted(SCRIPTS.glob("*.py")):
            with self.subTest(script=script.name):
                self.assertIn(f"scripts/{script.name}", ENTRYPOINT)

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


class RoundStatusTests(unittest.TestCase):
    """The correlation rules a hand-written variant of this script got wrong."""

    HEAD = "aaa111"
    BOT = "chatgpt-codex-connector[bot]"

    def test_a_stranger_reviewing_the_same_head_is_not_this_surface(self) -> None:
        """The bug that shipped in the ad-hoc script: filtering on commit_id
        alone lets a human's review — including the ones in-thread replies
        create — stand in as the bot's verdict."""
        reviews = [
            _review(1, self.HEAD, self.BOT),
            _review(2, self.HEAD, "a-human"),
        ]
        self.assertEqual(1, ROUND_STATUS.select_review(reviews, self.HEAD, self.BOT)["id"])

    def test_a_review_of_an_earlier_head_is_not_a_current_verdict(self) -> None:
        reviews = [_review(1, "older0", self.BOT)]
        self.assertEqual({}, ROUND_STATUS.select_review(reviews, self.HEAD, self.BOT))

    def test_the_newest_matching_review_wins(self) -> None:
        reviews = [_review(1, self.HEAD, self.BOT), _review(9, self.HEAD, self.BOT)]
        self.assertEqual(9, ROUND_STATUS.select_review(reviews, self.HEAD, self.BOT)["id"])

    def test_findings_exclude_earlier_rounds(self) -> None:
        comments = [_comment(1), _comment(9), _comment(9)]
        self.assertEqual(2, len(ROUND_STATUS.findings_for(comments, 9)))

    def test_no_review_means_no_findings_rather_than_all_of_them(self) -> None:
        self.assertEqual([], ROUND_STATUS.findings_for([_comment(1)], None))

    def test_an_empty_review_is_reported_but_not_declared_clean(self) -> None:
        """`surface_state` reports how far the surface got, never whether the
        verdict is acceptable — an empty review is not evidence of a clean one."""
        state = ROUND_STATUS.surface_state(_review(1, self.HEAD, self.BOT), [])
        self.assertEqual("reported-empty", state)
        self.assertNotIn("clean", state)

    def test_a_missing_review_is_awaiting_not_stalled(self) -> None:
        self.assertEqual("awaiting", ROUND_STATUS.surface_state({}, []))

    def test_gate_reports_every_failing_check_by_name(self) -> None:
        checks = [
            {"name": "ok", "conclusion": "SUCCESS"},
            {"name": "broken", "conclusion": "FAILURE"},
            {"context": "legacy", "state": "failure"},
            {"name": "running", "conclusion": None, "state": "IN_PROGRESS"},
        ]
        self.assertEqual(["broken", "legacy"], ROUND_STATUS.gate_failed(checks))

    def test_an_empty_check_list_is_not_a_passing_gate_by_accident(self) -> None:
        """No failing checks is reported as no failing checks; whether a gate
        exists at all is the caller's question, and the skill requires saying
        which it concluded."""
        self.assertEqual([], ROUND_STATUS.gate_failed([]))

    def test_the_script_imports_only_the_standard_library(self) -> None:
        source = (SCRIPTS / "round_status.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, set(sys.stdlib_module_names))
