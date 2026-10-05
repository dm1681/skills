from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "flow-diagrams"
SCRIPT = SKILL_ROOT / "scripts" / "build_diagram.py"
TEMPLATE = SKILL_ROOT / "assets" / "diagram-template.html"
SYNC = ROOT / "scripts" / "sync_shared_diagram.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("build_diagram", SCRIPT)
sync = _load("sync_shared_diagram", SYNC)


def _model() -> dict:
    return {
        "title": "Refund requests",
        "summary": "From a customer's ask to money back.",
        "views": [
            {
                "id": "system",
                "title": "Systems",
                "kind": "map",
                "groups": [{"id": "core", "label": "Core platform", "kind": "area", "tag": "AWS"}],
                "nodes": [
                    {"id": "billing", "kind": "component", "label": "Billing", "group": "core", "drill": "refund"},
                    {"id": "ledger", "kind": "store", "label": "Ledger", "group": "core"},
                ],
                "edges": [{"from": "billing", "to": "ledger", "kind": "data", "label": "writes"}],
            },
            {
                "id": "refund",
                "title": "Refund a charge",
                "kind": "flow",
                "groups": [{"id": "desk", "label": "Support desk"}],
                "nodes": [
                    {"id": "ask", "kind": "entry", "step": 1, "label": "Customer asks", "group": "desk"},
                    {"id": "big", "kind": "decision", "step": 2, "label": "Over $500?", "group": "desk",
                     "snippet": {"lang": "python", "title": "rules.py", "code": "if amount > LIMIT:\n    return '</script><!--'\n"}},
                    {"id": "done", "kind": "exit", "step": 3, "label": "Refund issued", "group": "desk"},
                    {"id": "mgr", "kind": "external", "step": 4, "label": "Finance approval"},
                ],
                "edges": [
                    {"from": "ask", "to": "big"},
                    {"from": "big", "to": "done", "kind": "branch", "label": "no"},
                    {"from": "big", "to": "mgr", "kind": "branch", "label": "yes"},
                ],
            },
        ],
    }


class DiagramBuildTests(unittest.TestCase):
    def problems(self, model: dict) -> list[str]:
        with self.assertRaises(build.ModelError) as caught:
            build.build_model(model)
        return caught.exception.problems

    def test_groups_and_snippets_become_render_ready(self) -> None:
        built = build.build_model(_model())
        core = built["views"][0]["groups"][0]
        self.assertEqual((core["label"], core["kind"], core["tag"]), ("Core platform", "area", "AWS"))
        self.assertEqual(built["views"][1]["groups"][0]["kind"], "unit")
        source = built["views"][1]["nodes"][1]["source"]
        self.assertEqual(source["code"], "if amount > LIMIT:\n    return '</script><!--'")
        self.assertEqual((source["lang"], source["start"], source["title"]), ("python", 1, "rules.py"))
        self.assertNotIn("label", built["source"])

    def test_render_leaves_no_placeholders_and_keeps_script_inert(self) -> None:
        html = build.render(build.build_model(_model()))
        self.assertNotIn("__DIAGRAM_", html)
        self.assertEqual(html.count("</script>"), 4, "snippet text must not close a <script>")
        kinds = re.search(r'id="diagram-kinds">(.*?)</script>', html, re.DOTALL)
        payload = re.search(r'id="diagram-model">(.*?)</script>', html, re.DOTALL)
        assert kinds is not None and payload is not None
        self.assertEqual(json.loads(kinds.group(1)), build.load_kinds())
        self.assertNotIn("<", payload.group(1))

    def test_every_problem_is_reported_together(self) -> None:
        model = _model()
        flow = model["views"][1]
        model["views"][0]["kind"] = "architecture"
        flow["groups"][0]["label"] = ""
        flow["groups"].append({"id": "x", "label": "X", "kind": "file"})
        flow["nodes"][0]["kind"] = "start"
        flow["nodes"][1]["snippet"]["code"] = "\n".join(["x"] * 17)
        flow["nodes"][2]["step"] = 2
        flow["edges"][1]["label"] = ""
        flow["edges"].append({"from": "ask", "to": "ghost"})
        problems = self.problems(model)
        for expected in ("kind must be one of ['flow', 'map']", "label is required", "kind must be one of ['unit', 'area']",
                         "is not one of", "snippet is 17 lines", "also used by", "need a label", "'ghost' is not a node",
                         "needs at least one entry"):
            self.assertTrue(any(expected in p for p in problems), f"missing {expected!r} in {problems}")

    def test_snippet_lines_must_be_narrow_and_present(self) -> None:
        model = _model()
        model["views"][1]["nodes"][1]["snippet"] = {"code": "x" * 121}
        model["views"][1]["nodes"][2]["snippet"] = {"code": "  "}
        problems = self.problems(model)
        self.assertTrue(any("exceed 120 characters" in p for p in problems))
        self.assertTrue(any("non-empty code string" in p for p in problems))

    def test_cli_check_writes_nothing_and_failures_exit_1(self) -> None:
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "refunds.json"
            model_path.write_text(json.dumps(_model()), encoding="utf-8")
            self.assertEqual(build.main([str(model_path), "--check"]), 0)
            self.assertFalse(model_path.with_suffix(".html").exists())
            self.assertEqual(build.main([str(model_path)]), 0)
            self.assertTrue(model_path.with_suffix(".html").is_file())
            model_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(build.main([str(model_path), "--check"]), 1)


class LibraryExtensionTests(unittest.TestCase):
    """The hooks a consumer skill builds on, without any domain in the library."""

    def setUp(self) -> None:
        self.core = build.core
        self.kinds = build.load_kinds()

    def test_hooks_attach_fields_that_ride_through_to_the_page(self) -> None:
        def check_edge(where, raw, out, problems):
            out["weight"] = raw.get("weight", 0)
            if out["weight"] < 0:
                problems.append(f"{where}: weight must not be negative")

        model = _model()
        model["views"][1]["edges"][0]["weight"] = 3
        built = self.core.build(model, self.kinds, view_kinds={"flow", "map"}, default_group="unit", check_edge=check_edge)
        self.assertEqual(built["views"][1]["edges"][0]["weight"], 3)
        model["views"][1]["edges"][0]["weight"] = -1
        with self.assertRaises(self.core.ModelError) as caught:
            self.core.build(model, self.kinds, view_kinds={"flow", "map"}, default_group="unit", check_edge=check_edge)
        self.assertTrue(any("weight must not be negative" in p for p in caught.exception.problems))

    def test_render_injects_the_extension_and_refuses_one_that_breaks_out(self) -> None:
        built = build.build_model(_model())
        css, js = ".x { color: var(--rosewater); }", "window.diagramExtension = { header() {} };"
        html = self.core.render(built, self.kinds, TEMPLATE, {"css": css, "js": js})
        self.assertIn(css, html)
        self.assertIn(f'<script id="diagram-extension">{js}</script>', html)
        plain = self.core.render(built, self.kinds, TEMPLATE)
        self.assertIn('<script id="diagram-extension"></script>', plain)
        self.assertNotIn("__DIAGRAM_", plain)
        for extension in ({"js": "x = '</script>'"}, {"css": "/* </style> */"}):
            with self.subTest(extension=extension), self.assertRaises(ValueError):
                self.core.render(built, self.kinds, TEMPLATE, extension)

    def test_template_calls_every_documented_hook(self) -> None:
        template = TEMPLATE.read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "extending.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `(\w+)\(", reference, re.MULTILINE))
        called = set(re.findall(r'call\("(\w+)"', template))
        self.assertEqual(documented, called)


class DiagramContractTests(unittest.TestCase):
    def test_every_kind_is_documented_in_the_visual_language(self) -> None:
        kinds = build.load_kinds()
        reference = (SKILL_ROOT / "references" / "visual-language.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `([a-z]+)` \|", reference, re.MULTILINE))
        self.assertEqual(documented, set(kinds["nodes"]) | set(kinds["edges"]))
        for spec in kinds["groups"].values():
            self.assertIn(spec["border"], {"solid", "dashed", "dotted"})

    def test_skill_references_exist(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)#]+)\)", skill):
            self.assertTrue((SKILL_ROOT / link).exists(), link)

    def test_shared_copies_match_the_owner(self) -> None:
        stale = [str(path.relative_to(ROOT)) for path, _ in sync.drift()]
        self.assertEqual(stale, [], "run: python3 scripts/sync_shared_diagram.py")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_template_script_parses(self) -> None:
        script = re.findall(r"<script>(.*?)</script>", TEMPLATE.read_text(encoding="utf-8"), re.DOTALL)
        self.assertEqual(len(script), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(script[0], encoding="utf-8")
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
