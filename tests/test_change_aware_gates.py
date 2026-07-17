from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class ChangeAwareGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = (
            SKILL_ROOT / "references" / "change-aware-gates.md"
        ).read_text(encoding="utf-8")
        cls.normalized = " ".join(cls.policy.split())

    def test_entrypoint_routes_change_aware_contract(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/change-aware-gates.md", entrypoint)

    def test_source_review_precedes_evidence_and_graphify(self) -> None:
        self.assertIn("Do not capture required screenshots or run the final Graphify refresh until both source axes are CLEAN", self.normalized)
        contract = (SKILL_ROOT / "references" / "orchestration-contract.md").read_text(encoding="utf-8")
        normalized_contract = " ".join(contract.split())
        self.assertIn("WORKING -> SOURCE_REVIEWING", normalized_contract)
        self.assertIn("EVIDENCE_BUILDING -> ARTIFACT_VERIFYING -> REVIEWING", normalized_contract)

    def test_artifact_commit_reuses_only_matching_source_evidence(self) -> None:
        self.assertIn("does not necessarily invalidate source evidence", self.normalized)
        self.assertIn("when source hash and runtime fingerprint match", self.normalized)
        self.assertIn("final reusable Reviewer must still issue one exact-head CLEAN", self.normalized)

    def test_test_selector_change_is_source(self) -> None:
        self.assertIn("A changed test, fixture, selector", self.normalized)
        self.assertIn("is `SOURCE`", self.normalized)

    def test_runtime_and_test_evidence_are_fingerprinted(self) -> None:
        self.assertIn("`RUNTIME_FINGERPRINT`", self.normalized)
        self.assertIn("required=<true|false> source_tree_hash=<hash> runtime_fingerprint=<hash> result=PASS", self.normalized)
        self.assertIn("serialize that suite", self.normalized)

    def test_graphify_refresh_marker_prevents_duplicate_work(self) -> None:
        self.assertIn("`GRAPHIFY_REFRESH_MARKER`", self.normalized)
        self.assertIn("never run a second public refresh for the same source tree", self.normalized)

    def test_metadata_only_and_semantic_incrementality_have_safe_boundaries(self) -> None:
        self.assertIn("only when the path is excluded from Graphify's semantic corpus", self.normalized)
        self.assertIn("upstream Graphify engine improvement", self.normalized)
        self.assertIn("Do not hand-edit Graphify output", self.normalized)

    def test_actions_degradation_never_reaches_clean_or_merge(self) -> None:
        self.assertIn("continue only through one initial branch push and its corresponding WIP PR creation or update", self.normalized)
        self.assertIn("mandatory before final Reviewer CLEAN, readiness, or merge", self.normalized)
        self.assertIn("This fallback never means green", self.normalized)

    def test_required_review_axes_take_priority_over_watcher(self) -> None:
        lifecycle = (SKILL_ROOT / "references" / "subagent-lifecycle.md").read_text(encoding="utf-8")
        normalized = " ".join(lifecycle.split())
        self.assertIn("Reviewer, active Worker, required Standards and Spec source axes, optional Watcher", normalized)
        self.assertIn("run Standards and Spec sequentially", normalized)
        axis_prompt = (SKILL_ROOT / "references" / "source-review-axis-prompt.md").read_text(encoding="utf-8")
        normalized_prompt = " ".join(axis_prompt.split())
        self.assertIn("one-shot, read-only Olympus {STANDARDS_OR_SPEC} source-review axis", normalized_prompt)
        self.assertIn("Do not edit files, commit, push, write to GitHub", normalized_prompt)


if __name__ == "__main__":
    unittest.main()
