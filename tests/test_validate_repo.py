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


# The one shipped skill allowed to warn. `olympus-report-progress` is vendored
# from the Olympus repository, and the sessions that load it run in unrelated
# repositories where Olympus's own docs do not exist -- so it states its whole
# spec inline and cannot be split into references/ the way the warning
# suggests. Splitting it would break the case it exists for. Everything else
# must stay clean, including that skill's description phrasing.
SELF_CONTAINED_BY_DESIGN = "olympus-report-progress"


class ShippedSkillTests(unittest.TestCase):
    def test_only_the_off_repo_skill_may_exceed_the_entrypoint_budget(self) -> None:
        budget_warning = f"skills/{SELF_CONTAINED_BY_DESIGN}/SKILL.md is"
        unexpected = [
            warning
            for warning in VALIDATOR.collect_warnings()
            if not (warning.startswith(budget_warning) and "budget" in warning)
        ]
        self.assertEqual([], unexpected)


if __name__ == "__main__":
    unittest.main()
