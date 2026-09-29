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
SKILL_ROOT = ROOT / "skills" / "codebase-onboarding"
SCRIPT = SKILL_ROOT / "scripts" / "build_onboarding.py"
TEMPLATE = SKILL_ROOT / "assets" / "onboarding-template.html"

ROUTES = """from app.service import place


def create_order(request):
    order = place(request.json)
    if order is None:
        return 422, "invalid"
    return 201, order
"""
SERVICE = """def place(payload):
    if not payload.get("sku"):
        return None
    return {"sku": payload["sku"], "note": "</script><!--"}
"""


def _load():
    spec = importlib.util.spec_from_file_location("build_onboarding", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load()


def _model() -> dict:
    return {
        "title": "Onboarding: shop",
        "summary": "What happens to a `POST /orders`.",
        "views": [
            {
                "id": "map",
                "title": "Architecture",
                "kind": "architecture",
                "groups": [{"id": "app", "kind": "module", "path": "app"}],
                "nodes": [
                    {"id": "api", "kind": "component", "label": "HTTP routes", "group": "app",
                     "source": {"path": "app/routes.py", "start": 4, "end": 5}, "drill": "order"},
                    {"id": "svc", "kind": "component", "label": "Order service", "group": "app",
                     "source": {"path": "app/service.py", "start": 1, "end": 2}},
                ],
                "edges": [{"from": "api", "to": "svc", "kind": "depends"}],
            },
            {
                "id": "order",
                "title": "Create an order",
                "kind": "flow",
                "groups": [
                    {"id": "routes", "path": "app/routes.py"},
                    {"id": "service", "path": "app/service.py"},
                ],
                "nodes": [
                    {"id": "post", "kind": "entry", "step": 1, "label": "POST /orders", "group": "routes",
                     "source": {"path": "app/routes.py", "start": 4, "end": 5, "contains": "def create_order"}},
                    {"id": "check", "kind": "decision", "step": 2, "label": "SKU present?", "group": "service",
                     "source": {"path": "app/service.py", "start": 1, "end": 4}},
                    {"id": "ok", "kind": "exit", "step": 3, "label": "201 Created", "group": "routes",
                     "source": {"path": "app/routes.py", "start": 8, "end": 8}},
                    {"id": "bad", "kind": "error", "step": 4, "label": "422", "group": "routes",
                     "source": {"path": "app/routes.py", "start": 6, "end": 7}},
                    {"id": "client", "kind": "external", "label": "Browser"},
                ],
                "edges": [
                    {"from": "client", "to": "post"},
                    {"from": "post", "to": "check", "label": "payload"},
                    {"from": "check", "to": "ok", "kind": "branch", "label": "yes"},
                    {"from": "check", "to": "bad", "kind": "branch", "label": "no"},
                ],
            },
        ],
    }


class OnboardingBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "app").mkdir()
        (self.tmp / "app" / "routes.py").write_text(ROUTES, encoding="utf-8")
        (self.tmp / "app" / "service.py").write_text(SERVICE, encoding="utf-8")

    def problems(self, model: dict) -> list[str]:
        with self.assertRaises(build.ModelError) as caught:
            build.build_model(model, self.tmp)
        return caught.exception.problems

    def test_excerpts_come_from_the_repository(self) -> None:
        built = build.build_model(_model(), self.tmp)
        post = built["views"][1]["nodes"][0]
        self.assertEqual(post["source"]["code"], "def create_order(request):\n    order = place(request.json)")
        self.assertEqual(post["source"]["lang"], "python")
        self.assertEqual(built["views"][1]["groups"][0]["lang"], "python")

    def test_render_leaves_no_placeholders_and_keeps_script_inert(self) -> None:
        html = build.render(build.build_model(_model(), self.tmp))
        self.assertNotIn("__ONB_", html)
        self.assertEqual(html.count("</script>"), 3, "excerpt text must not close a <script>")
        match = re.search(r'id="onb-model">(.*?)</script>', html, re.DOTALL)
        assert match is not None
        self.assertNotIn("<", match.group(1))
        self.assertEqual(json.loads(match.group(1))["views"][1]["nodes"][1]["source"]["code"].count("</script>"), 1)

    def test_file_group_holds_only_its_own_file(self) -> None:
        model = _model()
        model["views"][1]["nodes"][1]["group"] = "routes"
        self.assertTrue(any("a file container holds only that file's steps" in p for p in self.problems(model)))

    def test_drifted_anchor_fails(self) -> None:
        model = _model()
        model["views"][1]["nodes"][0]["source"]["start"] = 1
        model["views"][1]["nodes"][0]["source"]["end"] = 2
        self.assertTrue(any("drifted" in p for p in self.problems(model)))

    def test_every_problem_is_reported_together(self) -> None:
        model = _model()
        flow = model["views"][1]
        flow["nodes"][0]["kind"] = "entry-point"
        flow["nodes"][1]["source"]["end"] = 5
        flow["nodes"][2]["step"] = 2
        flow["edges"][2]["label"] = ""
        flow["edges"].append({"from": "post", "to": "ghost"})
        problems = self.problems(model)
        for expected in ("is not one of", "has 4 lines", "also used by", "need a label", "'ghost' is not a node"):
            self.assertTrue(any(expected in p for p in problems), f"missing {expected!r} in {problems}")

    def test_limits_and_paths(self) -> None:
        model = _model()
        model["views"][1]["nodes"][0]["source"] = {"path": "../etc/passwd", "start": 1, "end": 1}
        model["views"][1]["nodes"][1]["source"]["end"] = 1 + build.MAX_EXCERPT_LINES
        problems = self.problems(model)
        self.assertTrue(any("relative path inside the repo" in p for p in problems))
        self.assertTrue(any("keep it to" in p for p in problems))

    def test_flow_needs_an_entry_and_drill_needs_a_view(self) -> None:
        model = _model()
        model["views"][1]["nodes"][0]["kind"] = "step"
        model["views"][0]["nodes"][0]["drill"] = "nowhere"
        problems = self.problems(model)
        self.assertTrue(any("needs at least one entry" in p for p in problems))
        self.assertTrue(any("drill must name another view" in p for p in problems))

    def test_web_links_only_for_known_hosts(self) -> None:
        self.assertEqual(build.web_base("git@github.com:me/shop.git", "abc"), "https://github.com/me/shop/blob/abc/")
        self.assertEqual(build.web_base("https://gitlab.com/me/shop", "abc"), "https://gitlab.com/me/shop/-/blob/abc/")
        self.assertIsNone(build.web_base("https://example.com/me/shop.git", "abc"))
        self.assertIsNone(build.web_base(None, "abc"))

    def test_cli_check_writes_nothing_and_failures_exit_1(self) -> None:
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)
        model_path = self.tmp / "shop.json"
        model_path.write_text(json.dumps(_model()), encoding="utf-8")
        self.assertEqual(build.main([str(model_path), "--repo", str(self.tmp), "--check"]), 0)
        self.assertFalse((self.tmp / "docs").exists())
        self.assertEqual(build.main([str(model_path), "--repo", str(self.tmp)]), 0)
        self.assertTrue((self.tmp / "docs" / "onboarding" / "shop.html").is_file())
        broken = _model()
        broken["views"][1]["nodes"][0]["group"] = "service"
        model_path.write_text(json.dumps(broken), encoding="utf-8")
        self.assertEqual(build.main([str(model_path), "--repo", str(self.tmp), "--check"]), 1)


class OnboardingContractTests(unittest.TestCase):
    def test_every_kind_is_documented_in_the_visual_language(self) -> None:
        kinds = build.load_kinds()
        reference = (SKILL_ROOT / "references" / "visual-language.md").read_text(encoding="utf-8")
        for table in ("nodes", "edges"):
            for kind in kinds[table]:
                self.assertIn(f"| `{kind}` |", reference, f"{table} kind {kind} is undocumented")
        documented = set(re.findall(r"^\| `([a-z]+)` \|", reference, re.MULTILINE))
        self.assertEqual(documented, set(kinds["nodes"]) | set(kinds["edges"]))

    def test_skill_references_exist(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)#]+)\)", skill):
            self.assertTrue((SKILL_ROOT / link).exists(), link)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_template_script_parses(self) -> None:
        html = TEMPLATE.read_text(encoding="utf-8")
        script = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
        self.assertEqual(len(script), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(script[0], encoding="utf-8")
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
