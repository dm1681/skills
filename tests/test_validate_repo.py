"""Skill-convention warnings from scripts/validate_repo.py."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_validator", ROOT / "scripts" / "validate_repo.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def skill_text(description: str, body_lines: int) -> str:
    body = "\n".join(f"line {index}" for index in range(body_lines))
    return f"---\nname: demo\ndescription: {description}\n---\n\n{body}\n"


class SkillWarningTests(unittest.TestCase):
    def test_compact_skill_with_trigger_phrasing_is_clean(self) -> None:
        text = skill_text("Does a thing. Use when the user asks for it.", 40)
        self.assertEqual([], VALIDATOR.skill_warnings("demo", text))

    def test_trigger_phrasing_is_case_insensitive(self) -> None:
        text = skill_text("USE WHEN the user asks for it.", 10)
        self.assertEqual([], VALIDATOR.skill_warnings("demo", text))

    def test_long_entrypoint_suggests_references(self) -> None:
        text = skill_text("Use when testing.", VALIDATOR.SKILL_LINE_BUDGET + 10)
        warnings = VALIDATOR.skill_warnings("demo", text)
        self.assertEqual(1, len(warnings))
        self.assertIn("references/", warnings[0])

    def test_description_without_trigger_phrasing_is_flagged(self) -> None:
        warnings = VALIDATOR.skill_warnings("demo", skill_text("Renders charts.", 10))
        self.assertEqual(1, len(warnings))
        self.assertIn("Use when", warnings[0])

    def test_missing_description_is_the_error_check_problem_not_a_warning(self) -> None:
        text = "---\nname: demo\n---\n\nbody\n"
        self.assertEqual([], VALIDATOR.skill_warnings("demo", text))


# `ponytail` is vendored from DietrichGebert/ponytail, and its upstream
# description carries no "Use when" trigger phrasing. It is not ours to
# rephrase: the copy here is pinned to upstream by SHA256, so editing it is
# drift, not a fix.
UPSTREAM_PHRASED_BY_DESIGN = "ponytail"


class ShippedSkillTests(unittest.TestCase):
    def test_the_shipped_collection_warns_about_nothing(self) -> None:
        """A clean run must be genuinely clean, or nobody reads the warnings.

        This used to whitelist the vendored skill's over-budget entrypoint,
        which meant every green run still printed one line -- and a warning
        that is always there is a warning everyone learns to skip. The
        exemption now lives in `skill_warnings`, where the reason it can never
        be acted on is stated, so this asserts the honest thing instead.
        """
        self.assertEqual([], VALIDATOR.collect_warnings())

    def test_the_vendored_skill_is_the_one_that_would_otherwise_warn(self) -> None:
        """Pins *why* the exemption is load-bearing rather than decorative.

        If upstream ever adopts the trigger phrasing, this fails and the
        exemption can be reconsidered on purpose instead of quietly covering
        for a skill that no longer needs it.
        """
        entrypoint = VALIDATOR.ROOT / "skills" / UPSTREAM_PHRASED_BY_DESIGN / "SKILL.md"
        text = entrypoint.read_text(encoding="utf-8")
        self.assertIn(UPSTREAM_PHRASED_BY_DESIGN, VALIDATOR.VENDORED_SKILL_NAMES)
        # Same text under a non-vendored name still warns: the silence is the
        # exemption's doing, not a hole in the budget check itself.
        self.assertTrue(VALIDATOR.skill_warnings("not-vendored", text))
        self.assertEqual([], VALIDATOR.skill_warnings(UPSTREAM_PHRASED_BY_DESIGN, text))


if __name__ == "__main__":
    unittest.main()
