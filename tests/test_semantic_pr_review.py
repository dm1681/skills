from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "semantic-pr-review"
SCRIPTS = SKILL_ROOT / "scripts"
REFERENCES = (
    "semantic-layers",
    "explorer-data-model",
    "interactive-flowchart",
    "build-and-verify",
    "visual-language",
)
SOURCE = """def dispatch(request):
    backend = resolve(request.mode)
    return backend.run(request)


def resolve(mode):
    return REGISTRY[mode]
"""
CONSUMER = """def consume(result):
    return result.value
"""


def _load_script(name: str):
    """Import one bundled script so its helpers can be unit tested."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _materialized(model: dict) -> dict:
    """Fill what the scaffold derives from Git, for tests that skip Git."""
    model = json.loads(json.dumps(model))
    for node in model["nodes"]:
        node["code_preview"]["code"] = "pass"
        for source in node["sources"]:
            source["github_url"] = f"https://github.com/o/r/blob/sha/{source['path']}#L1-L2"
    return model


class NodeChangeNoteTests(unittest.TestCase):
    """The optional per-node sentence describing what the PR did."""

    def scaffold(self):
        spec = importlib.util.spec_from_file_location(
            "scaffold_pr_explorer", SCRIPTS / "scaffold_pr_explorer.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def errors_for(self, value) -> list:
        module = self.scaffold()
        model = json.loads(json.dumps(_model("0" * 40)))
        model["nodes"][0]["change_note"] = value
        return [e for e in module._validate_model(model) if "change_note" in e]

    def test_it_is_optional(self) -> None:
        module = self.scaffold()
        model = json.loads(json.dumps(_model("0" * 40)))
        self.assertEqual(
            [], [e for e in module._validate_model(model) if "change_note" in e]
        )

    def test_a_sentence_is_accepted(self) -> None:
        self.assertEqual([], self.errors_for("Split the branch into a lookup."))

    def test_empty_or_non_string_is_rejected(self) -> None:
        """An empty note renders as a blank line, a non-string as [object Object]."""
        for value in ("", "   ", 123, None, ["a"]):
            with self.subTest(value=value):
                self.assertTrue(self.errors_for(value))

    def test_the_extension_falls_back_to_a_sentence_per_status(self) -> None:
        """Every status maps to a sentence, so the line is never a bare word."""
        extension = (SKILL_ROOT / "assets" / "pr-extension.js").read_text(encoding="utf-8")
        for status in ("added", "modified", "removed", "context"):
            self.assertIn(f"{status}: {{ mark:", extension)
        self.assertIn("changeSentence", extension)
        self.assertIn("item.change_note", extension)


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
        for asset in ("diagram-template.html", "diagram-kinds.json", "pr-extension.js", "pr-extension.css"):
            self.assertTrue((SKILL_ROOT / "assets" / asset).is_file(), asset)

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
                    if root == "diagram_core":
                        # The shared core ships beside the scripts, itself stdlib-only.
                        continue
                    with self.subTest(script=script.name, module=module):
                        self.assertIn(root, standard_library)

    def test_editor_links_survive_a_windows_path_on_any_host(self) -> None:
        """Cover the drive-letter case a POSIX-only run can never reach."""
        scaffold = _load_script("scaffold_pr_explorer")
        verify = _load_script("verify_pr_explorer")
        windows_file = PureWindowsPath(r"C:\repo\api.py")
        posix_file = PurePosixPath("/repo/api.py")

        self.assertEqual(
            "cursor://file/C:/repo/api.py:12",
            scaffold._cursor_url(windows_file, 12),
        )
        self.assertEqual(
            "cursor://file/repo/api.py:12",
            scaffold._cursor_url(posix_file, 12),
        )
        self.assertEqual(
            "C:/repo/api.py",
            verify._cursor_target("/C:/repo/api.py").as_posix(),
        )
        self.assertEqual(
            "/repo/api.py",
            verify._cursor_target("/repo/api.py").as_posix(),
        )

    def test_template_keeps_the_placeholders_the_scaffold_replaces(self) -> None:
        template = (SKILL_ROOT / "assets" / "diagram-template.html").read_text(encoding="utf-8")
        for marker in ("__DIAGRAM_MODEL__", "__DIAGRAM_KINDS__", "__DIAGRAM_EXTENSION_JS__",
                       "/* __DIAGRAM_EXTENSION_CSS__ */"):
            self.assertIn(marker, template)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_extension_script_parses_and_defines_every_hook_the_verifier_needs(self) -> None:
        verify = _load_script("verify_pr_explorer")
        path = SKILL_ROOT / "assets" / "pr-extension.js"
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = path.read_text(encoding="utf-8")
        for hook in verify.EXTENSION_HOOKS:
            self.assertRegex(text, rf"\n    {hook}\(")

    def test_kinds_follow_the_runtime_role(self) -> None:
        """Entry, fan-out decision, exit and branch edges come from the paths."""
        scaffold = _load_script("scaffold_pr_explorer")
        model = json.loads(json.dumps(_model("0" * 40)))
        model["nodes"].append(_node("legacy", "legacy()", "removed", "selection.py", 6, 7))
        model["branches"].append({"id": "mode-b", "label": "Mode B", "system": "shared", "path": ["legacy", "engine"]})
        model["edges"].append(_edge("dispatch", "legacy", "removed"))
        full = scaffold._diagram_model(_materialized(model))["views"][0]
        kinds = {n["id"]: n["kind"] for n in full["nodes"]}
        self.assertEqual((kinds["caller"], kinds["dispatch"], kinds["consumer"]), ("entry", "decision", "exit"))
        edges = {(e["from"], e["to"]): e for e in full["edges"]}
        self.assertEqual((edges["dispatch", "adapter"]["kind"], edges["dispatch", "adapter"]["label"]), ("branch", "Mode A"))
        self.assertEqual((edges["caller", "dispatch"]["kind"], edges["caller", "dispatch"]["label"]), ("call", "hands off"))
        self.assertEqual([n["step"] for n in full["nodes"]], list(range(1, len(full["nodes"]) + 1)))

    def test_an_authored_kind_wins_and_the_delta_view_appears_only_when_it_hides_something(self) -> None:
        scaffold = _load_script("scaffold_pr_explorer")
        model = json.loads(json.dumps(_model("0" * 40)))
        model["nodes"][4]["kind"] = "store"
        views = scaffold._diagram_model(_materialized(model))["views"]
        self.assertEqual([v["id"] for v in views], ["full"], "every node neighbours a change")
        self.assertEqual(views[0]["nodes"][4]["kind"], "store")
        for node in model["nodes"]:
            node["change_status"] = "context"
        model["nodes"][0]["change_status"] = "modified"
        views = scaffold._diagram_model(_materialized(model))["views"]
        self.assertEqual([v["id"] for v in views], ["full", "delta"])
        self.assertEqual([n["id"] for n in views[1]["nodes"]], ["caller", "dispatch"])


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

    def build(self, directory: str) -> tuple[Path, Path, str]:
        """Scaffold one explorer page from a fresh fixture snapshot."""
        repository, head_sha = self.fixture(directory)
        data = Path(directory) / "pr-model.json"
        data.write_text(json.dumps(_model(head_sha)), encoding="utf-8")
        page = Path(directory) / "page.html"
        self.run_script(
            "scaffold_pr_explorer.py",
            "--data",
            str(data),
            "--output",
            str(page),
            "--repo-root",
            str(repository),
            "--source-ref",
            head_sha,
        )
        return repository, page, head_sha

    def test_scaffold_render_and_strict_verification_agree_on_one_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, page, head_sha = self.build(directory)
            result = self.run_script(
                "verify_pr_explorer.py",
                str(page),
                "--source-repo",
                str(repository),
                "--source-ref",
                head_sha,
                "--strict",
            )
            self.assertIn("OK", result.stdout)
            rendered = page.read_text(encoding="utf-8")
            self.assertNotIn("__DIAGRAM_", rendered)
            self.assertIn("<title>PR 1: ", rendered)
            self.assertIn(head_sha, rendered)
            self.assertIn(
                f"https://github.com/owner/repository/blob/{head_sha}/selection.py",
                rendered,
            )

    def test_strict_verification_rejects_a_hand_edited_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, page, head_sha = self.build(directory)
            tampered = page.read_text(encoding="utf-8").replace(
                "backend.run(request)", "backend.run(other)"
            )
            page.write_text(tampered, encoding="utf-8")
            result = self.run_script(
                "verify_pr_explorer.py",
                str(page),
                "--source-repo",
                str(repository),
                "--source-ref",
                head_sha,
                "--strict",
                expected=1,
            )
            self.assertIn("code_preview bytes mismatch", result.stdout)

    def test_verification_rejects_a_page_that_polls_a_live_feed(self) -> None:
        """The shared page can poll; an explorer is a snapshot and must not."""
        verify = _load_script("verify_pr_explorer")
        with tempfile.TemporaryDirectory() as directory:
            _, page, _ = self.build(directory)
            text = page.read_text(encoding="utf-8")
            built = verify._embedded(text)
            self.assertEqual([], verify._check_page(text, built))
            built["live"] = {"url": "state.json", "every": 2}
            self.assertTrue(any("live feed" in e for e in verify._check_page(text, built)))

    def test_strict_verification_keeps_the_explorer_on_mocha(self) -> None:
        verify = _load_script("verify_pr_explorer")
        with tempfile.TemporaryDirectory() as directory:
            _, page, _ = self.build(directory)
            text = page.read_text(encoding="utf-8")
            built = verify._embedded(text)
            self.assertNotIn("themes", built, "the scaffold offers no themes")
            built["themes"] = {"mocha": {}, "latte": {}}
            errors = verify._check_quality_contract(text, built)
            self.assertTrue(any("locked to Catppuccin Mocha" in e for e in errors), errors)

    def test_strict_verification_rejects_a_displayed_copy_that_differs(self) -> None:
        """The drawn excerpt is checked against the verified record, not trusted."""
        verify = _load_script("verify_pr_explorer")
        with tempfile.TemporaryDirectory() as directory:
            _, page, _ = self.build(directory)
            text = page.read_text(encoding="utf-8")
            built = verify._embedded(text)
            built["views"][0]["nodes"][0]["source"]["code"] = "print('other')"
            errors = verify._check_quality_contract(text, built)
            self.assertTrue(any("displays a different code" in e for e in errors), errors)

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
                str(Path(directory) / "page.html"),
                "--repo-root",
                str(repository),
                "--source-ref",
                head_sha,
                expected=1,
            )
            self.assertIn("model analysis sha does not match source ref", result.stdout)

    def test_editor_links_address_absolute_paths_as_parseable_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, head_sha = self.fixture(directory)
            data = Path(directory) / "pr-model.json"
            data.write_text(json.dumps(_model(head_sha)), encoding="utf-8")
            page = Path(directory) / "page.html"
            self.run_script(
                "scaffold_pr_explorer.py",
                "--data",
                str(data),
                "--output",
                str(page),
                "--repo-root",
                str(repository),
                "--source-ref",
                head_sha,
                "--cursor-root",
                str(repository),
            )
            urls = set(
                re.findall(r'"cursor_url": "([^"]+)"', page.read_text(encoding="utf-8"))
            )
            self.assertTrue(urls, "scaffold emitted no editor deep links")
            for url in urls:
                with self.subTest(url=url):
                    # A Windows path starts at its drive letter, so only an
                    # explicit separator keeps this parseable as a URL.
                    self.assertRegex(url, r"^cursor://file/")
                    self.assertNotIn("\\", url)
                    parsed = urlparse(url)
                    self.assertEqual("cursor", parsed.scheme)
                    self.assertEqual("file", parsed.netloc)
            result = self.run_script(
                "verify_pr_explorer.py",
                str(page),
                "--source-repo",
                str(repository),
                "--source-ref",
                head_sha,
                "--strict",
            )
            self.assertIn("OK", result.stdout)

    def test_a_drifted_worktree_warns_and_omits_editor_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, head_sha = self.fixture(directory)
            _write(repository / "selection.py", SOURCE.replace("REGISTRY", "BACKENDS"))
            _commit(repository, "later work")
            data = Path(directory) / "pr-model.json"
            data.write_text(json.dumps(_model(head_sha)), encoding="utf-8")
            page = Path(directory) / "page.html"
            result = self.run_script(
                "scaffold_pr_explorer.py",
                "--data",
                str(data),
                "--output",
                str(page),
                "--repo-root",
                str(repository),
                "--source-ref",
                head_sha,
                "--cursor-root",
                str(repository),
            )
            self.assertIn("editor links omitted", result.stderr)
            self.assertIn("not the analyzed snapshot", result.stderr)
            # The explorer still builds, just without links it cannot verify.
            rendered = page.read_text(encoding="utf-8")
            self.assertNotIn("cursor://", rendered)
            # The reader never sees stderr, so the page carries the reason
            # and still offers the immutable GitHub link.
            self.assertIn('"notices": ["editor links omitted', rendered)
            self.assertIn('"data-role": "notices"', rendered)
            self.assertIn("https://github.com/owner/repository/blob/", rendered)

    def test_a_remote_worktree_warns_and_omits_editor_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, head_sha = self.fixture(directory)
            data = Path(directory) / "pr-model.json"
            data.write_text(json.dumps(_model(head_sha)), encoding="utf-8")
            page = Path(directory) / "page.html"
            result = self.run_script(
                "scaffold_pr_explorer.py",
                "--data",
                str(data),
                "--output",
                str(page),
                "--repo-root",
                str(repository),
                "--source-ref",
                head_sha,
                "--cursor-root",
                r"\\fileserver\share\checkout",
            )
            self.assertIn("is a remote path", result.stderr)
            self.assertNotIn("cursor://", page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
