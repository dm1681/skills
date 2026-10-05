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
state = _load("update_state", SKILL_ROOT / "scripts" / "update_state.py")
EXAMPLE = SKILL_ROOT / "examples" / "status-tracker"


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


class LiveUpdateTests(unittest.TestCase):
    """A drawn page whose node and edge data can change while it is open."""

    def setUp(self) -> None:
        quiet = contextlib.ExitStack()
        self.err = io.StringIO()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(self.err))
        self.addCleanup(quiet.close)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_live_feed_is_validated_and_carried_to_the_page(self) -> None:
        model = _model()
        model["live"] = {"url": " state.json ", "every": 1}
        self.assertEqual(build.build_model(model)["live"], {"url": "state.json", "every": 1})
        self.assertNotIn("live", build.build_model(_model()))
        for live, expected in (({"every": 2}, "live.url"), ({"url": "s.json", "every": 0.1}, "live.every"),
                               ({"url": "s.json", "every": True}, "live.every"), ("s.json", "live.url")):
            model["live"] = live
            with self.subTest(live=live), self.assertRaises(build.ModelError) as caught:
                build.build_model(model)
            self.assertTrue(any(expected in p for p in caught.exception.problems))

    def test_page_and_writer_agree_on_the_fields_that_place_an_element(self) -> None:
        template = TEMPLATE.read_text(encoding="utf-8")
        match = re.search(r'const FIXED = \{ nodes: (\[[^\]]*\]), edges: (\[[^\]]*\]) \};', template)
        assert match is not None
        self.assertEqual(set(json.loads(match.group(1))), state.FIXED["nodes"])
        self.assertEqual(set(json.loads(match.group(2))), state.FIXED["edges"])
        for marker in ("window.diagram = { update", "api.update = update", "if (MODEL.live) startLive(MODEL.live)"):
            self.assertIn(marker, template)

    def test_header_minimises_to_the_tab_row_and_keeps_the_live_status(self) -> None:
        template = TEMPLATE.read_text(encoding="utf-8")
        detail = re.search(r'<div class="header-detail" id="header-detail">(.*?)\n    </div>\n    <div class="toolbar">', template, re.DOTALL)
        assert detail is not None, "the title, summary and extension header share one collapsible block"
        for part in ('id="title"', 'id="summary"', 'id="ext-header"'):
            self.assertIn(part, detail.group(1))
        self.assertNotIn('id="tabs"', detail.group(1))
        self.assertIn("header.top.minimised .header-detail { display: none; }", template)
        self.assertIn('else if (e.key === "h") setHeader(!collapsed.header);', template)
        self.assertIn('$("search").before(status);', template)

    def test_writer_merges_parses_values_and_replaces_the_file(self) -> None:
        path = self.tmp / "state.json"
        self.assertEqual(state.main([str(path), "--node", "a", "status=running", "pct=40", "--edge", "a>b", "label=retrying"]), 0)
        self.assertEqual(state.main([str(path), "--node", "a", "status=done", "--node", "b", 'tags=["x"]', "note=null"]), 0)
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["nodes"], {"a": {"status": "done", "pct": 40}, "b": {"tags": ["x"], "note": None}})
        self.assertEqual(written["edges"], {"a>b": {"label": "retrying"}})
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["state.json"], "no temporary file is left behind")
        self.assertEqual(state.main([str(path), "--reset", "--node", "c", "status=pending"]), 0)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["nodes"], {"c": {"status": "pending"}})

    def test_writer_refuses_layout_fields_unknown_ids_and_broken_files(self) -> None:
        path = self.tmp / "state.json"
        model = self.tmp / "model.json"
        model.write_text(json.dumps(_model()), encoding="utf-8")
        for argv, expected in (
            (["--node", "ask", "step=9"], "cannot change live"),
            (["--edge", "ask>big", "from=x"], "cannot change live"),
            (["--edge", "ask", "label=x"], "FROM>TO"),
            (["--node", "ask", "status"], "KEY=VALUE"),
            (["--node", "ghost", "status=done", "--model", str(model)], "no node 'ghost'"),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(state.main([str(path), *argv]), 1)
                self.assertIn(expected, self.err.getvalue())
        self.assertFalse(path.exists(), "a refused change writes nothing")
        path.write_text("{oops", encoding="utf-8")
        self.assertEqual(state.main([str(path), "--node", "ask", "status=done"]), 1)
        self.assertIn("--reset", self.err.getvalue())

    def test_status_tracker_example_builds_with_its_extension(self) -> None:
        out = self.tmp / "page.html"
        argv = [str(EXAMPLE / "pipeline.json"), "--out", str(out),
                "--css", str(EXAMPLE / "status.css"), "--js", str(EXAMPLE / "status.js")]
        self.assertEqual(build.main(argv), 0)
        html = out.read_text(encoding="utf-8")
        self.assertIn("window.diagramExtension", html)
        self.assertIn('"live": {"url": "state.json"', html)
        bad = self.tmp / "bad.js"
        bad.write_text("x = '</script>'", encoding="utf-8")
        self.assertEqual(build.main([*argv[:3], "--js", str(bad)]), 1)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_status_tracker_example_script_parses(self) -> None:
        result = subprocess.run(["node", "--check", str(EXAMPLE / "status.js")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ThemeTests(unittest.TestCase):
    """Themes re-assign the palette's roles; meanings never change."""

    def setUp(self) -> None:
        self.core = build.core
        self.kinds = build.load_kinds()
        self.themes = self.core.load_themes(build.THEMES_FILE)
        quiet = contextlib.ExitStack()
        self.err = io.StringIO()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(self.err))
        self.addCleanup(quiet.close)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_built_in_themes_carry_the_language_and_mocha_is_the_template_default(self) -> None:
        self.assertEqual(list(self.themes), ["mocha", "macchiato", "frappe", "latte"])
        for name, theme in self.themes.items():
            with self.subTest(theme=name):
                self.assertEqual(self.core.theme_problems(name, theme, self.kinds), [])
                self.assertEqual(theme["dark"], name != "latte")
        root = dict(re.findall(r"--([a-z0-9]+): (#[0-9a-f]{6})", TEMPLATE.read_text(encoding="utf-8")[:3000]))
        self.assertEqual({k: root[k] for k in self.core.PALETTE}, self.themes["mocha"]["colors"])

    def test_custom_theme_extends_a_built_in_and_is_checked(self) -> None:
        raw = json.loads((SKILL_ROOT / "examples" / "themes" / "paper.json").read_text(encoding="utf-8"))
        name, theme = self.core.custom_theme(raw, self.themes, self.kinds)
        self.assertEqual((name, theme["dark"], theme["colors"]["green"]), ("paper", False, self.themes["latte"]["colors"]["green"]))
        for raw, expected in (
            ({"name": "x", "colors": {"base": "#000000"}}, "missing text"),
            ({"name": "x", "extends": "mocha", "colors": {"base": "black"}}, "must be #rrggbb"),
            ({"name": "x", "extends": "mocha", "colors": {"accent": "#ffffff"}}, "not a palette role"),
            ({"name": "x", "extends": "mocha", "colors": {"text": "#2a2a3a"}}, "text on base"),
            ({"name": "x", "extends": "mocha", "colors": {"teal": "#74c7ec"}}, "sapphire and teal"),
            ({"name": "x", "extends": "latte", "colors": {"yellow": "#e6e9ef"}}, "yellow on mantle"),
            ({"name": "mocha", "extends": "mocha", "colors": {}}, "taken by a built-in"),
            ({"name": "x", "extends": "dracula", "colors": {}}, "not one of"),
            ({"name": "has space", "colors": {}}, "name must match"),
        ):
            with self.subTest(expected=expected), self.assertRaises(self.core.ModelError) as caught:
                self.core.custom_theme(raw, self.themes, self.kinds)
            self.assertTrue(any(expected in p for p in caught.exception.problems), caught.exception.problems)

    def test_offer_and_default_decide_picker_and_lock(self) -> None:
        built = self.core.apply_themes(build.build_model(_model()), self.themes, default="latte")
        self.assertEqual((list(built["themes"]), built["theme"]), (list(self.themes), "latte"))
        locked = self.core.apply_themes(build.build_model(_model()), self.themes, offer=["frappe"])
        self.assertEqual((list(locked["themes"]), locked["theme"]), (["frappe"], "frappe"))
        with self.assertRaises(self.core.ModelError):
            self.core.apply_themes(build.build_model(_model()), self.themes, default="latte", offer=["mocha"])

    def test_builder_flags(self) -> None:
        model = self.tmp / "m.json"
        model.write_text(json.dumps(_model()), encoding="utf-8")
        page = lambda: json.loads(re.search(r'id="diagram-model">(.*?)</script>', (self.tmp / "m.html").read_text(encoding="utf-8"), re.S).group(1))
        self.assertEqual(build.main([str(model)]), 0)
        self.assertEqual((len(page()["themes"]), page()["theme"]), (4, "mocha"))
        self.assertEqual(build.main([str(model), "--themes", "latte"]), 0)
        self.assertEqual(list(page()["themes"]), ["latte"])
        paper = SKILL_ROOT / "examples" / "themes" / "paper.json"
        self.assertEqual(build.main([str(model), "--theme-file", str(paper)]), 0)
        self.assertEqual((len(page()["themes"]), page()["theme"]), (5, "paper"))
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"name": "bad", "extends": "mocha", "colors": {"teal": "#74c7ec"}}), encoding="utf-8")
        self.assertEqual(build.main([str(model), "--theme-file", str(bad), "--check"]), 1)
        self.assertIn("sapphire and teal", self.err.getvalue())

    def test_template_applies_a_theme_through_the_palette_variables(self) -> None:
        template = TEMPLATE.read_text(encoding="utf-8")
        for marker in ('root.style.setProperty(`--${role}`, value)', 'root.style.colorScheme = theme.dark ? "dark" : "light"',
                       'picker.hidden = Object.keys(THEMES).length < 2', 'id="theme"'):
            self.assertIn(marker, template)


class MovableContainerTests(unittest.TestCase):
    """Containers drag by their header; arrows re-route from real positions."""

    def setUp(self) -> None:
        self.template = TEMPLATE.read_text(encoding="utf-8")

    def test_headers_are_handles_and_offsets_are_remembered_and_resettable(self) -> None:
        for marker in ('"data-grip": lane.id', 'class: "group-grip"', "tabindex: 0", 'const grip = e.target.closest("[data-grip]")',
                       "`diagram-layout:${MODEL.title}:${view.id}`", 'id="layout-reset"', 'else if (e.key === "r") resetLayout();',
                       "if (offset) shiftLane(box, offset[0], offset[1]);"):
            self.assertIn(marker, self.template)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_routing_follows_positions(self) -> None:
        start = self.template.index("  function edgeGeometry(")
        end = self.template.index("  const bezier = ")
        script = (
            'const KINDS = { nodes: { step: { shape: "rounded" } } };\n'
            + self.template[start:end]
            + """
const box = (x, y) => ({ x, y, w: 200, h: 60, kind: "step" });
const a = box(100, 300);
const cases = {
  below: edgeGeometry(a, box(400, 500), false, 0),
  level: edgeGeometry(a, box(400, 310), false, 0),
  aboveApart: edgeGeometry(a, box(400, 100), false, 0),
  aboveStacked: edgeGeometry(a, box(120, 100), false, 0),
  cycle: edgeGeometry(a, box(400, 500), true, 0),
};
console.log(JSON.stringify(cases));
""")
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        c = json.loads(result.stdout)
        self.assertEqual(c["below"][:2], [200, 360], "leaves the bottom when the target is below")
        self.assertEqual(c["level"][:2], [300, 330], "leaves the side facing a level target")
        self.assertEqual(c["aboveApart"][:2], [200, 300], "leaves the top when the target is above and off to one side")
        self.assertEqual(c["aboveStacked"][:2], [300, 330], "loops round the right rather than cut through a column")
        self.assertGreater(c["cycle"][2], 300, "a cycle bulges out to the right")


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
