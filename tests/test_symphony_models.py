"""Task routing and durable escalation behavior at the request boundary."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import symphony_models as models
import symphony_worker as worker
import symphony_project as project


def prompt(title="Implement a filter", description="Add filtering and unit tests.", labels=""):
    return f"Issue context:\nIdentifier: DIE-123\nTitle: {title}\nCurrent status: Todo\nLabels: {labels}\nURL: https://example.invalid\n\nDescription:\n{description}\nInstructions:\nShared sandbox and security boilerplate"


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        (self.project / ".symphony").mkdir()
        self.root = self.project / "workers"
        self.cwd = self.root / "DIE-123"
        self.cwd.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--template=", str(self.cwd)], check=True)
        (self.cwd / ".symphony-worker.json").write_text(json.dumps({"kind": "symphony", "project_dir": str(self.project)}))

    def params(self, text=None):
        return {"cwd": str(self.cwd), "approvalPolicy": "never", "sandboxPolicy": {
            "type": "dangerFullAccess"},
            "input": [{"type": "text", "text": text or prompt()}]}

    def request_escalation(self, reason="Cross-module concurrency requires a deeper implementation design", category="complexity"):
        (self.cwd / ".git/symphony-model-escalation.json").write_text(json.dumps({"category": category, "reason": reason}))

    def test_classification_ignores_workflow_and_obeys_explicit_labels(self):
        for title, description, expected in [
            ("Fix typo in README", "Correct spelling", "simple"),
            ("Implement a filter", "Add filtering and tests", "standard"),
            ("Fix typo in authentication docs", "Explain credential handling", "complex"),
            ("Add durable output contracts", "Preserve data after cleanup", "complex"),
        ]:
            self.assertEqual(expected, models.assess(prompt(title, description))["profile"])
        self.assertEqual("simple", models.assess(prompt("Architecture", labels="['symphony:simple']"))["profile"])
        self.assertEqual("standard", models.assess("No issue block")["profile"])
        with self.assertRaises(ValueError): models.assess(prompt(labels="symphony:simple, symphony:complex"))
        self.assertEqual("standard", models.assess(prompt(labels="not-symphony:simple"))["profile"])

    def test_turn_profile_preserves_policy_and_records_reason(self):
        router = models.Router(self.project, self.cwd)
        original = self.params()
        request = {"method": "turn/start", "params": original}
        prepared = json.loads(worker.prepare_request(json.dumps(request).encode(), self.cwd, router))["params"]
        self.assertEqual(("gpt-6-sol", "medium"), (prepared["model"], prepared["effort"]))
        self.assertEqual("never", prepared["approvalPolicy"])
        self.assertEqual({"type": "dangerFullAccess"}, prepared["sandboxPolicy"])
        self.assertIn("Codex Workpad", prepared["input"][-1]["text"])
        self.assertEqual("standard", json.loads(router.path.read_text())["profile"])
        self.assertNotIn("Issue context", router.path.read_text())

    def test_escalation_cap_survives_worker_restart(self):
        router = models.Router(self.project, self.cwd)
        router.apply(self.params(prompt("Fix typo", "spelling")))
        self.request_escalation()
        params = self.params("Continue")
        router.apply(params)
        self.assertEqual("gpt-6-sol", params["model"])
        router = models.Router(self.project, self.cwd)
        self.request_escalation()
        params = self.params(prompt("Fix typo", "spelling"))
        router.apply(params)
        self.assertEqual("gpt-6-sol", params["model"])
        self.assertEqual(1, router.state["escalations"])

    def test_permission_quota_auth_and_wrong_category_do_not_escalate(self):
        router = models.Router(self.project, self.cwd)
        router.apply(self.params())
        for reason in ["Git permission denied during fetch", "Rate limit exhausted", "Authentication failed for Git", "Required network unavailable"]:
            self.request_escalation(reason)
            router.apply(self.params("Continue"))
            self.assertEqual(0, router.state["escalations"])
        self.request_escalation(category="retry")
        router.apply(self.params("Continue"))
        self.assertEqual(0, router.state["escalations"])

    def test_explicit_override_is_fixed_and_can_change_on_new_pickup(self):
        router = models.Router(self.project, self.cwd)
        router.apply(self.params(prompt(labels="symphony:simple")))
        self.request_escalation()
        router.apply(self.params("Continue"))
        self.assertEqual("simple", router.state["profile"])
        router = models.Router(self.project, self.cwd)
        router.apply(self.params(prompt(labels="symphony:complex")))
        self.assertEqual("complex", router.state["profile"])
        router = models.Router(self.project, self.cwd)
        router.apply(self.params(prompt()))
        self.assertEqual("standard", router.state["profile"])
        self.assertFalse(router.state["override"])

    def test_missing_model_or_unsupported_effort_is_actionable(self):
        rows = [{"model": m, "supportedReasoningEfforts": [{"reasoningEffort": e}]} for m, e in models.PROFILES.values()]
        models.validate_catalog(rows)
        rows[0]["supportedReasoningEfforts"] = []
        with self.assertRaisesRegex(ValueError, "gpt-6-luna/low"):
            models.validate_catalog(rows)

    @unittest.skipIf(__import__('os').name == 'nt', 'Symlink privilege varies on Windows')
    def test_symlinked_escalation_request_is_rejected(self):
        router = models.Router(self.project, self.cwd)
        router.request_path.symlink_to(self.project / "outside")
        with self.assertRaises(ValueError): router.apply(self.params())

    def test_default_configuration_and_catalog_preflight(self):
        config = project.setup(self.project, project_id="test", project_slug="test", setup_issue="TEST-1", repo_url="git@example.invalid:test.git", codex="codex")
        self.assertEqual("auto", project.load(self.project)["model_routing"])
        config["model_routing"] = "typo"
        with self.assertRaises(ValueError): models.validate_catalog([])
        with self.assertRaises(project.Error): project.validate_config(config)
