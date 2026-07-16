from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"


class GraphifyLifecycleTests(unittest.TestCase):
    def test_entrypoint_routes_graphify_lifecycle(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/graphify-lifecycle.md", entrypoint)
        self.assertTrue(
            (SKILL_ROOT / "references" / "graphify-lifecycle.md").exists()
        )

    def test_trigger_is_tracked_graph_and_indexed_change(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("when `graphify-out/` is tracked", normalized)
        self.assertIn("changes a file inside Graphify's indexed corpus", normalized)
        self.assertIn("treat the refresh as required", normalized)
        self.assertIn("`GRAPHIFY_NOT_REQUIRED` with the reason", normalized)

    def test_worker_refreshes_after_tests_before_final_push(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Complete the implementation, documentation", normalized)
        self.assertIn("ordinary focused and aggregate tests", normalized)
        self.assertIn("Run `$graphify . --update`", normalized)
        self.assertIn("final pre-push Standards and Spec check", normalized)
        self.assertIn("push the exact head", normalized)

    def test_worker_does_not_hand_edit_or_bypass_failed_refresh(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Never hand-edit generated graph output", normalized)
        self.assertIn("A required refresh failure", normalized)
        self.assertIn("blocks handoff", normalized)
        self.assertIn("escalate rather than bypassing the gate", normalized)

    def test_reviewer_blocks_stale_or_unsafe_graphify_output(self) -> None:
        reviewer = (
            SKILL_ROOT / "references" / "reviewer-prompt.md"
        ).read_text(encoding="utf-8")
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join((reviewer + " " + policy).split())
        self.assertIn("block CLEAN", normalized)
        self.assertIn("tracked artifact freshness", normalized)
        self.assertIn("health results, privacy, reproducibility", normalized)
        self.assertIn("unmodified upstream styling or interaction remains advisory", normalized)

    def test_repair_and_base_drift_repeat_the_gate(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Repeat the gate during a repair round", normalized)
        self.assertIn("current base has not added indexed-file changes", normalized)
        self.assertIn("Graphify refresh, push, and exact-head review", normalized)

    def test_post_merge_is_verification_only(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Do not regenerate or commit directly on `main`", normalized)
        self.assertIn("separately authorized maintenance lane", normalized)


if __name__ == "__main__":
    unittest.main()
