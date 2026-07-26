from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "orchestrate-olympus"
CHECKPOINT = SKILL_ROOT / "scripts" / "checkpoint.py"

sys.path.insert(0, str(CHECKPOINT.parent))
import checkpoint  # noqa: E402


def _read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


def _normalized(relative: str) -> str:
    return " ".join(_read(relative).split())


class HostNeutralContractTests(unittest.TestCase):
    def test_host_adaptation_reference_exists_and_is_routed(self) -> None:
        self.assertTrue(
            (SKILL_ROOT / "references" / "host-adaptation.md").exists()
        )
        entrypoint = _read("SKILL.md")
        self.assertIn("references/host-adaptation.md", entrypoint)

    def test_host_adaptation_defines_required_capabilities_and_fallbacks(self) -> None:
        adaptation = _normalized("references/host-adaptation.md")
        for required in (
            "Required host capabilities",
            "stable identifier",
            "Capability fallbacks",
            "pinning",
            "ESCALATED",
        ):
            self.assertIn(required, adaptation)

    def test_contract_documents_are_host_neutral(self) -> None:
        # The normative contract must not assume the Codex host. Codex may
        # appear only as a named example in the host-adaptation reference,
        # legacy checkpoint-schema history, and the OpenAI interface file.
        host_neutral = (
            "SKILL.md",
            "references/subagent-lifecycle.md",
            "references/review-boundaries.md",
            "references/change-aware-gates.md",
            "references/pause-and-recovery.md",
            "references/visual-evidence.md",
            "references/follow-up-issues.md",
            "references/agentic-documentation.md",
            "references/matt-triage-labels.md",
            "references/planner-prompt.md",
            "references/worker-prompt.md",
            "references/reviewer-prompt.md",
            "references/source-review-axis-prompt.md",
        )
        for relative in host_neutral:
            self.assertNotIn(
                "Codex",
                _read(relative),
                msg=f"{relative} must not hard-code the Codex host",
            )

    def test_core_contract_limits_codex_to_schema_history(self) -> None:
        contract = _read("references/orchestration-contract.md")
        for line in contract.splitlines():
            if "codex" in line.lower():
                self.assertIn(
                    "codex_review",
                    line,
                    msg="orchestration-contract.md may mention Codex only for "
                    f"legacy codex_review schema history: {line!r}",
                )

    def test_prompts_use_host_neutral_signatures(self) -> None:
        for relative in (
            "references/orchestrator-prompt.md",
            "references/planner-prompt.md",
            "references/worker-prompt.md",
            "references/reviewer-prompt.md",
        ):
            content = _read(relative)
            self.assertNotIn("Codex subagent", content)
            self.assertNotIn("parent Codex session", content)

    def test_cloud_review_prohibition_is_generalized(self) -> None:
        entrypoint = _normalized("SKILL.md")
        self.assertIn(
            "Never request a hosted cloud review (for example, Codex Cloud)"
            " by GitHub comment",
            _normalized("references/host-adaptation.md"),
        )
        self.assertIn("hosted cloud review", entrypoint)

    def test_invocation_is_not_codex_dollar_syntax_in_prompts(self) -> None:
        for relative in (
            "references/orchestrator-prompt.md",
            "references/reviewer-prompt.md",
        ):
            self.assertNotIn(
                "$orchestrate-olympus",
                _read(relative),
                msg=f"{relative} must invoke the skill host-neutrally",
            )


class HostNeutralTaskIdTests(unittest.TestCase):
    def _base_checkpoint(self) -> dict:
        data = json.loads(json.dumps(checkpoint.sample_checkpoint()))
        return data

    def test_uuid_task_ids_remain_valid(self) -> None:
        errors = checkpoint.validate_data(self._base_checkpoint())
        self.assertEqual([], errors)

    def test_non_uuid_host_task_ids_are_valid(self) -> None:
        data = self._base_checkpoint()
        data["reviewer_task"] = "agent-a1b2c3"
        data["worker_task"] = "task_01HZXW9K"
        errors = checkpoint.validate_data(data)
        self.assertEqual([], errors)

    def test_blank_and_whitespace_task_ids_are_rejected(self) -> None:
        data = self._base_checkpoint()
        data["reviewer_task"] = "   "
        errors = checkpoint.validate_data(data)
        self.assertTrue(
            any("reviewer_task" in error for error in errors),
            msg=f"expected reviewer_task error, got {errors}",
        )
        data["reviewer_task"] = "has embedded space"
        errors = checkpoint.validate_data(data)
        self.assertTrue(any("reviewer_task" in error for error in errors))

    def test_cli_accepts_non_uuid_task_ids(self) -> None:
        data = self._base_checkpoint()
        data["worker_task"] = "claude-code/session-42"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(CHECKPOINT), "validate", str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
