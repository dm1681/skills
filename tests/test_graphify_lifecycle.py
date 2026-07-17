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
        self.assertIn("`GRAPHIFY_NOT_REQUIRED` with the verified reason", normalized)

    def test_worker_runs_one_refresh_after_source_clean(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Run exactly one synchronous refresh", normalized)
        self.assertIn("after ordinary tests and source Standards/Spec CLEAN", normalized)
        self.assertIn("A source repair that changes indexed files", normalized)
        self.assertIn("targeted exact-head artifact verification", normalized)
        self.assertIn("push the exact head", normalized)

    def test_code_only_fast_path_skips_clustering(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Use the structural fast path only when every indexed change is code", normalized)
        self.assertIn("graphify update . --no-cluster", normalized)
        self.assertIn("`GRAPHIFY_STRUCTURAL_CURRENT`", normalized)
        self.assertIn("`GRAPHIFY_PRESENTATION_DEFERRED`", normalized)
        self.assertIn("Never claim these artifacts are current", normalized)

    def test_semantic_and_architecture_changes_require_full_refresh(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("module, service, package, schema, public-interface", normalized)
        self.assertIn("Use a full public refresh for any semantic document", normalized)
        self.assertIn("For code-only changes run `graphify update .`", normalized)
        self.assertIn("For semantic inputs use `$graphify . --update`", normalized)

    def test_commit_hooks_are_suppressed_without_disabling_them(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("`GRAPHIFY_SKIP_HOOK=1`", normalized)
        self.assertIn("final generated-artifact commit", normalized)
        self.assertIn("Do not disable or uninstall the repository hook", normalized)
        self.assertIn("PowerShell", normalized)

    def test_cache_seed_is_exact_base_and_never_shares_outputs(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("same repository, exact starting SHA, and Graphify version", normalized)
        self.assertIn("only those two paths", normalized)
        self.assertIn("Never seed or share mutable `graph.json`", normalized)
        self.assertIn("Skip seeding when provenance is uncertain", normalized)

    def test_worker_parallelism_requires_local_timing_evidence(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("Respect Graphify's platform-safe worker default", normalized)
        self.assertIn("`GRAPHIFY_MAX_WORKERS`", normalized)
        self.assertIn("repository-local timing check", normalized)
        self.assertIn("never encode an unverified global override", normalized)

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
        self.assertIn("Block CLEAN", normalized)
        self.assertIn("structural freshness", normalized)
        self.assertIn("health, privacy, reproducibility", normalized)
        self.assertIn("presentation artifacts are either current or explicitly deferred", normalized)
        self.assertIn("unmodified upstream styling or interaction remains advisory", normalized)

    def test_repair_and_base_drift_repeat_the_gate(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("A source repair that changes indexed files", normalized)
        self.assertIn("current base added no indexed-file changes", normalized)
        self.assertIn("one final refresh, push, and exact-head review", normalized)

    def test_autonomous_batch_closes_deferred_presentation_in_pr(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("autonomous dispatch reaches an empty eligible issue frontier", normalized)
        self.assertIn("one Graphify presentation maintenance lane", normalized)
        self.assertIn("`graphify cluster-only .`", normalized)
        self.assertIn("review and merge its PR under the existing merge authority", normalized)
        self.assertIn("Any later full refresh", normalized)
        self.assertIn("do not create a redundant maintenance lane", normalized)
        self.assertIn("Never regenerate or commit directly on `main`", normalized)

    def test_reviewer_allows_only_truthful_nonblocking_deferral(self) -> None:
        policy = (
            SKILL_ROOT / "references" / "graphify-lifecycle.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.split())
        self.assertIn("`GRAPHIFY_PRESENTATION_DEFERRED` is non-blocking only", normalized)
        self.assertIn("no PR claim or acceptance check depends on those views", normalized)
        self.assertIn("an incorrectly deferred full-refresh trigger blocks CLEAN", normalized)


if __name__ == "__main__":
    unittest.main()
