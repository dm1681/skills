from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class AgenticDocumentationTests(unittest.TestCase):
    def test_agentic_documentation_contract_is_routed(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            "references/agentic-documentation.md",
            entrypoint,
        )
        self.assertTrue(
            (SKILL_ROOT / "references" / "agentic-documentation.md").exists()
        )

    def test_roles_have_separate_documentation_ownership(self) -> None:
        planner = (SKILL_ROOT / "references" / "planner-prompt.md").read_text(
            encoding="utf-8"
        )
        worker = (SKILL_ROOT / "references" / "worker-prompt.md").read_text(
            encoding="utf-8"
        )
        reviewer = (SKILL_ROOT / "references" / "reviewer-prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("documentation surfaces", planner)
        self.assertIn("Author or update", worker)
        self.assertIn("documentation comments", worker)
        self.assertIn("Enforce the agentic-documentation contract", reviewer)
        self.assertIn("Never author documentation", reviewer)

    def test_contract_prioritizes_signal_over_comment_coverage(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "agentic-documentation.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Documentation is a navigation layer for agents", normalized)
        self.assertIn("Do not impose a comment-coverage quota", normalized)
        self.assertIn("Do not restate the symbol name, signature, or type", normalized)
        self.assertIn("Use Olympus glossary terms from `CONTEXT.md`", normalized)
        self.assertIn("Prefer `/** ... */` documentation comments", normalized)
        self.assertIn("Tests prove behavior; they do not replace", normalized)
        self.assertIn(
            "ordering or lifecycle behavior is caller-visible and durable",
            normalized,
        )

    def test_reviewer_blocks_only_material_documentation_defects(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "agentic-documentation.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Blocking documentation finding", normalized)
        self.assertIn("material public contract", normalized)
        self.assertIn("non-obvious invariant", normalized)
        self.assertIn("Style-only preferences are advisory", normalized)
        self.assertIn("required actor is the Worker", normalized)
        self.assertIn("canonical brief explicitly requires", normalized)


if __name__ == "__main__":
    unittest.main()
