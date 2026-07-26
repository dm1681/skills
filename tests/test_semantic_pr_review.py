from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "semantic-pr-review"
SCRIPTS = SKILL_ROOT / "scripts"
REFERENCES = ("semantic-layers", "explorer-data-model", "interactive-flowchart")
SOURCE = """def dispatch(request):
    backend = resolve(request.mode)
    return backend.run(request)


def resolve(mode):
    return REGISTRY[mode]
"""
CONSUMER = """def consume(result):
    return result.value
"""


def _git(repository: Path, *arguments: str) -> str:
    """Return output from one Git command run inside a fixture repository."""
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write(path: Path, text: str) -> None:
    """Write fixture source with newlines that survive every platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _commit(repository: Path, message: str) -> str:
    """Commit the fixture worktree and return the immutable head SHA."""
    _git(repository, "add", "-A")
    _git(
        repository,
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "user.name=Fixture",
        "commit",
        "-m",
        message,
    )
    return _git(repository, "rev-parse", "HEAD")


def _node(
    identifier: str,
    label: str,
    change_status: str,
    path: str,
    start_line: int,
    end_line: int,
) -> dict[str, object]:
    """Return one source-backed explorer node."""
    return {
        "id": identifier,
        "label": label,
        "code_label": True,
        "system": "shared",
        "change_status": change_status,
        "purpose": f"{label} owns one step of the request path.",
        "receives": "`PlanningRequest`",
        "sends": "`PlanningResult`",
        "role": "Request path",
        "connection": "Receives from upstream and hands off downstream.",
        "tradeoff": "Explicit routing is auditable but needs a registration.",
        "sources": [
            {
                "label": f"{label} · {path} lines {start_line}–{end_line}",
                "path": path,
                "start_line": start_line,
                "end_line": end_line,
            }
        ],
        "code_preview": {"language": "python", "source_index": 0},
    }


def _edge(source: str, destination: str, change_status: str) -> dict[str, object]:
    """Return one evidence-backed runtime handoff."""
    return {
        "from": source,
        "to": destination,
        "change_status": change_status,
        "verb": "hands off",
        "transfer": ["`PlanningRequest`"],
        "optional": [],
        "containers": [],
        "transformation": "Normalizes the request for the next owner.",
        "evidence": "selection.py lines 1–3",
    }


def _model(head_sha: str) -> dict[str, object]:
    """Return a minimal but complete explorer model for the fixture PR."""
    return {
        "pr": {"number": 1, "repository": "owner/repository", "head_sha": head_sha},
        "summary": {
            "goal": "One stable boundary for every strategy",
            "old_to_new": "Caller-selected implementation to subsystem dispatch",
            "ownership_chain": ["Caller owns when", "Subsystem owns how"],
            "payoff": "Implementations change behind one contract.",
            "residual_debt": "One legacy branch remains isolated.",
        },
        "systems": [
            {
                "id": "shared",
                "label": "Shared contract",
                "color_token": "var(--viz-series-1)",
            }
        ],
        "shared_before": ["caller", "dispatch"],
        "branches": [
            {
                "id": "mode-a",
                "label": "Mode A",
                "system": "shared",
                "path": ["adapter", "engine"],
            }
        ],
        "convergence_node": "normalized",
        "shared_after": ["consumer"],
        "nodes": [
            _node("caller", "caller()", "context", "selection.py", 1, 3),
            _node("dispatch", "dispatch()", "added", "selection.py", 1, 3),
            _node("adapter", "resolve()", "added", "selection.py", 6, 7),
            _node("engine", "backend.run()", "modified", "selection.py", 2, 3),
            _node("normalized", "PlanningResult", "added", "consumer.py", 1, 2),
            _node("consumer", "consume()", "context", "consumer.py", 1, 2),
        ],
        "edges": [
            _edge("caller", "dispatch", "added"),
            _edge("dispatch", "adapter", "added"),
            _edge("adapter", "engine", "context"),
            _edge("engine", "normalized", "context"),
            _edge("normalized", "consumer", "context"),
        ],
    }


class SemanticPrReviewPackagingTests(unittest.TestCase):
    def test_skill_metadata_matches_its_directory_and_agent_interface(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: semantic-pr-review", entrypoint)
        self.assertIn("description:", entrypoint)
        interface = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("display_name:", interface)
        self.assertIn("short_description:", interface)
        self.assertIn("$semantic-pr-review", interface)

    def test_entrypoint_routes_every_bundled_reference_and_script(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for name in REFERENCES:
            with self.subTest(reference=name):
                self.assertIn(f"references/{name}.md", entrypoint)
                self.assertTrue((SKILL_ROOT / "references" / f"{name}.md").is_file())
        for script in sorted(SCRIPTS.glob("*.py")):
            with self.subTest(script=script.name):
                self.assertIn(f"scripts/{script.name}", entrypoint)
        self.assertTrue((SKILL_ROOT / "assets" / "pr-explorer-template.html").is_file())

    def test_commands_stay_portable_across_install_locations(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("<skill-root>", entrypoint)
        for assumption in ("~/.agents/skills", "~/.claude/skills", ".cursor/skills"):
            with self.subTest(assumption=assumption):
                self.assertNotIn(assumption, entrypoint)

    def test_bundled_scripts_import_only_the_standard_library(self) -> None:
        standard_library = set(sys.stdlib_module_names)
        for script in sorted(SCRIPTS.glob("*.py")):
            tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
            for statement in ast.walk(tree):
                if isinstance(statement, ast.Import):
                    modules = [alias.name for alias in statement.names]
                elif isinstance(statement, ast.ImportFrom):
                    modules = [statement.module or ""]
                else:
                    continue
                for module in modules:
                    root = module.split(".")[0]
                    with self.subTest(script=script.name, module=module):
                        self.assertIn(root, standard_library)

    def test_template_keeps_the_placeholders_the_scaffold_replaces(self) -> None:
        template = (SKILL_ROOT / "assets" / "pr-explorer-template.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("__PR_EXPLORER_ROOT_ID__", template)
        self.assertIn("__PR_EXPLORER_DATA__", template)


@unittest.skipIf(shutil.which("git") is None, "requires Git for snapshot fixtures")
class SemanticPrReviewPipelineTests(unittest.TestCase):
    def fixture(self, directory: str) -> tuple[Path, str]:
        """Create a one-commit repository and return its path and head SHA."""
        repository = Path(directory) / "repository"
        _write(repository / "selection.py", SOURCE)
        _write(repository / "consumer.py", CONSUMER)
        _git(repository, "init", "-q", ".")
        return repository, _commit(repository, "fixture snapshot")

    def run_script(
        self, name: str, *arguments: str, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / name), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def build(self, directory: str) -> tuple[Path, Path, Path, str]:
        """Scaffold and render one explorer from a fresh fixture snapshot."""
        repository, head_sha = self.fixture(directory)
        data = Path(directory) / "pr-model.json"
        data.write_text(json.dumps(_model(head_sha)), encoding="utf-8")
        fragment = Path(directory) / "fragment.html"
        page = Path(directory) / "page.html"
        self.run_script(
            "scaffold_pr_explorer.py",
            "--data",
            str(data),
            "--output",
            str(fragment),
            "--repo-root",
            str(repository),
            "--source-ref",
            head_sha,
        )
        self.run_script(
            "render_standalone.py",
            "--fragment",
            str(fragment),
            "--output",
            str(page),
            "--title",
            "PR 1 Dispatch Explorer",
        )
        return repository, fragment, page, head_sha

    def test_scaffold_render_and_strict_verification_agree_on_one_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, fragment, page, head_sha = self.build(directory)
            result = self.run_script(
                "verify_pr_explorer.py",
                str(fragment),
                "--standalone",
                str(page),
                "--source-repo",
                str(repository),
                "--source-ref",
                head_sha,
                "--strict",
            )
            self.assertIn("OK", result.stdout)
            rendered = fragment.read_text(encoding="utf-8")
            self.assertNotIn("__PR_EXPLORER_", rendered)
            self.assertIn(head_sha, rendered)
            self.assertIn(
                f"https://github.com/owner/repository/blob/{head_sha}/selection.py",
                rendered,
            )

    def test_strict_verification_rejects_a_hand_edited_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, fragment, _, head_sha = self.build(directory)
            tampered = fragment.read_text(encoding="utf-8").replace(
                "backend.run(request)", "backend.run(other)"
            )
            fragment.write_text(tampered, encoding="utf-8")
            result = self.run_script(
                "verify_pr_explorer.py",
                str(fragment),
                "--source-repo",
                str(repository),
                "--source-ref",
                head_sha,
                "--strict",
                expected=1,
            )
            self.assertIn("code_preview bytes mismatch", result.stdout)

    def test_scaffold_refuses_a_model_that_does_not_match_the_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, head_sha = self.fixture(directory)
            model = _model("0" * 40)
            data = Path(directory) / "pr-model.json"
            data.write_text(json.dumps(model), encoding="utf-8")
            result = self.run_script(
                "scaffold_pr_explorer.py",
                "--data",
                str(data),
                "--output",
                str(Path(directory) / "fragment.html"),
                "--repo-root",
                str(repository),
                "--source-ref",
                head_sha,
                expected=1,
            )
            self.assertIn("head_sha does not match source ref", result.stdout)

    def test_editor_links_require_a_worktree_on_the_analyzed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, head_sha = self.fixture(directory)
            _write(repository / "selection.py", SOURCE.replace("REGISTRY", "BACKENDS"))
            _commit(repository, "later work")
            data = Path(directory) / "pr-model.json"
            data.write_text(json.dumps(_model(head_sha)), encoding="utf-8")
            result = self.run_script(
                "scaffold_pr_explorer.py",
                "--data",
                str(data),
                "--output",
                str(Path(directory) / "fragment.html"),
                "--repo-root",
                str(repository),
                "--source-ref",
                head_sha,
                "--cursor-root",
                str(repository),
                expected=1,
            )
            self.assertIn("does not match analyzed snapshot", result.stdout)


if __name__ == "__main__":
    unittest.main()
