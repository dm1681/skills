"""Tests for the council skill's convening script.

No test here calls a real model: every seat runs through a fake runner, so the
suite is free, offline, and independent of which CLIs a machine has.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "council" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("council", SCRIPTS / "council.py")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their annotations through sys.modules.
    sys.modules["council"] = module
    spec.loader.exec_module(module)
    return module


council = _load()


def _fake_run(stdout="", returncode=0, stderr="", write=None):
    """A stand-in for subprocess.run that records the call it received."""
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if write is not None:
            path = Path(argv[argv.index("-o") + 1])
            path.write_text(write, encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    run.calls = calls
    return run


class SeatCommandTests(unittest.TestCase):
    def test_each_seat_pins_the_requested_model_and_effort(self):
        out = Path("answer.md")
        codex = council.SEATS["codex"].command(out, Path("repo"))
        self.assertIn("gpt-6.2-astra", codex)
        self.assertIn('model_reasoning_effort="xhigh"', codex)
        claude = council.SEATS["claude"].command(out, Path("repo"))
        self.assertEqual(claude[claude.index("--model") + 1], "claude-fable-5-2")
        self.assertEqual(claude[claude.index("--effort") + 1], "xhigh")
        gemini = council.SEATS["gemini"].command(out, Path("repo"))
        self.assertEqual(gemini[gemini.index("--model") + 1], "gemini-4-neon-xhigh")

    def test_every_seat_is_read_only(self):
        out = Path("answer.md")
        codex = council.SEATS["codex"].command(out, Path("repo"))
        self.assertEqual(codex[codex.index("-s") + 1], "read-only")
        claude = council.SEATS["claude"].command(out, Path("repo"))
        self.assertEqual(claude[claude.index("--tools") + 1], "Read,Grep,Glob")
        rules = _gemini_rules(Path("repo"))
        self.assertIn("write_file(*)", rules["deny"])
        self.assertIn("mcp(*)", rules["deny"])

    def test_repository_is_granted_for_reading_without_its_config(self):
        repo = Path("repo")
        claude = council.SEATS["claude"].command(Path("a.md"), repo)
        self.assertEqual(claude[claude.index("--add-dir") + 1], str(repo))
        self.assertEqual(claude[claude.index("--setting-sources") + 1], "user")
        settings = Path(claude[claude.index("--settings") + 1])
        self.assertTrue(json.loads(settings.read_text(encoding="utf-8"))["disableAllHooks"])
        gemini = council.SEATS["gemini"].command(Path("a.md"), repo)
        # An --add-dir folder joins agy's workspace, which starts its MCP servers.
        self.assertNotIn("--add-dir", gemini)
        self.assertIn(f"read_file({repo})", _gemini_rules(repo)["allow"])

    def test_gemini_runs_only_commands_that_cannot_write(self):
        rules = _gemini_rules(Path("/r"))
        allowed = [re.fullmatch(r"command\(regex:(.*)\)", r) for r in rules["allow"]]
        allowed = [m.group(1) for m in allowed if m]
        denied = [re.fullmatch(r"command\(regex:(.*)\)", r) for r in rules["deny"]]
        denied = [m.group(1) for m in denied if m]

        def runs(cmd):
            return (any(re.fullmatch(a, cmd) for a in allowed)
                    and not any(re.fullmatch(d, cmd) for d in denied))

        for cmd in ("grep -rn needle /r", "ls -R /r", "cat /r/a.py", "head -n 5 /r/a.py", "wc -l /r/a.py"):
            self.assertTrue(runs(cmd), cmd)
        for cmd in ("find /r -name x -delete", "rg --pre sh x /r", "rm /r/a.py", "ls /r > /r/out",
                    "cat $(echo /r/a)", "cat `echo /r/a`", "grep x /r; rm /r/a.py", "git log"):
            self.assertFalse(runs(cmd), cmd)

    def test_gemini_signs_in_with_google_and_never_uses_an_api_key(self):
        gemini = council.SEATS["gemini"]
        self.assertEqual(gemini.binary, "agy")
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "AGY_ADC_AUTH"):
            self.assertIn(key, gemini.drop_env)


def _gemini_rules(repo):
    argv = council.SEATS["gemini"].command(Path("a.md"), repo)
    return json.loads(argv[argv.index("--settings") + 1])["permissions"]


def _agy_stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


class GeminiStreamTests(unittest.TestCase):
    def test_brief_is_one_stream_json_user_message(self):
        line = council.SEATS["gemini"].encode("the brief")
        self.assertEqual(json.loads(line), {"event": "user", "message": {"role": "user", "content": "the brief"}})

    def test_answer_and_model_come_from_the_result_events(self):
        out = _agy_stream({"event": "init", "init": {"model": "gemini-4-neon-xhigh"}},
                          {"event": "step_update", "step_update": {}},
                          {"event": "result", "result": {"status": "SUCCESS", "response": "Do it.\n"}})
        self.assertEqual(council.SEATS["gemini"].decode(out), ("Do it.\n", "", "gemini-4-neon-xhigh"))

    def test_a_failed_run_returns_its_error(self):
        out = _agy_stream({"event": "result", "result": {"status": "ERROR", "response": "",
                                                          "error": "429 RESOURCE_EXHAUSTED"}})
        self.assertEqual(council.SEATS["gemini"].decode(out)[1], "429 RESOURCE_EXHAUSTED")

    def test_an_empty_answer_after_a_denial_says_so(self):
        out = _agy_stream({"event": "result", "result": {"status": "SUCCESS", "response": "",
                                                          "denied_actions": [{"action": "command"}]}})
        self.assertIn("denied it: command", council.SEATS["gemini"].decode(out)[1])


class ConsultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.which = lambda name: f"/bin/{name}"

    def test_answer_on_stdout_is_saved_and_returned(self):
        run = _fake_run(stdout="## Recommendation\nDo it.\n")
        verdict = council.consult(council.SEATS["claude"], "brief", self.tmp, self.tmp, 5, run, self.which)
        self.assertTrue(verdict.ok)
        self.assertIn("Do it.", verdict.text)
        self.assertIn("Do it.", (self.tmp / "claude.md").read_text(encoding="utf-8"))

    def test_brief_goes_on_stdin_and_the_seat_is_marked(self):
        run = _fake_run(stdout="ok")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}):
            council.consult(council.SEATS["gemini"], "the brief", self.tmp, self.tmp, 5, run, self.which)
        _, kwargs = run.calls[0]
        self.assertEqual(json.loads(kwargs["input"])["message"]["content"], "the brief")
        self.assertEqual(kwargs["env"][council.SEAT_MARKER], "1")
        self.assertNotIn("GEMINI_API_KEY", kwargs["env"])

    def test_seats_never_run_inside_the_repository(self):
        # A working directory is where each CLI loads project config and hooks.
        repo = self.tmp / "repo"
        (repo / ".claude").mkdir(parents=True)
        for name in council.SEATS:
            run = _fake_run(stdout="ok", write="ok" if name == "codex" else None)
            council.consult(council.SEATS[name], "b", repo, self.tmp, 5, run, self.which)
            workdir = Path(run.calls[0][1]["cwd"])
            self.assertNotEqual(workdir.resolve(), repo.resolve())
            self.assertNotIn(repo.resolve(), workdir.resolve().parents)
            self.assertEqual(list(workdir.iterdir()), [])

    def test_codex_answer_is_read_from_its_last_message_file(self):
        run = _fake_run(stdout="noisy progress log", write="## Recommendation\nWait.\n")
        verdict = council.consult(council.SEATS["codex"], "brief", self.tmp, self.tmp, 5, run, self.which)
        self.assertTrue(verdict.ok)
        self.assertNotIn("noisy", verdict.text)
        self.assertIn("Wait.", verdict.text)

    def test_refused_codex_model_falls_back_to_gpt_6_astra(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            model = argv[argv.index("-m") + 1]
            if model == "gpt-6.2-astra":
                return subprocess.CompletedProcess(argv, 1, "", '"code":"model_not_found"')
            Path(argv[argv.index("-o") + 1]).write_text("## Recommendation\nFallback.\n", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")

        verdict = council.consult(council.SEATS["codex"], "b", self.tmp, self.tmp, 5, run, self.which)
        self.assertEqual([a[a.index("-m") + 1] for a in calls], ["gpt-6.2-astra", "gpt-6-astra"])
        self.assertTrue(verdict.ok)
        self.assertIn("gpt-6-astra (xhigh, fallback)", verdict.seat.label)
        self.assertIn("`gpt-6.2-astra` was refused", verdict.text)
        self.assertIn("Fallback.", verdict.text)

    def test_other_codex_failures_do_not_spend_a_second_run(self):
        run = _fake_run(returncode=1, stderr="401 Unauthorized")
        verdict = council.consult(council.SEATS["codex"], "b", self.tmp, self.tmp, 5, run, self.which)
        self.assertEqual(len(run.calls), 1)
        self.assertFalse(verdict.ok)

    def test_missing_cli_is_an_empty_seat_not_a_crash(self):
        verdict = council.consult(council.SEATS["gemini"], "b", self.tmp, self.tmp, 5, _fake_run(), lambda *a, **k: None)
        self.assertFalse(verdict.ok)
        self.assertIn("not on PATH", verdict.text)

    def test_cli_outside_path_is_found_in_a_per_user_folder(self):
        def which(name, path=None):
            return f"{path}/{name}" if path == os.path.expanduser("~/.npm-global/bin") else None

        self.assertEqual(council.find_cli("agy", which), os.path.expanduser("~/.npm-global/bin/agy"))

    def test_report_shows_the_error_line_not_the_help_after_it(self):
        help_text = "\n".join(f"  --flag{i}   Some help text." for i in range(30))
        run = _fake_run(returncode=1, stderr=f"Usage: agy [options]\n{help_text}\nUnknown arguments: skip-trust")
        verdict = council.consult(council.SEATS["claude"], "b", self.tmp, self.tmp, 5, run, self.which)
        first = verdict.text.splitlines()[0]
        self.assertIn("Unknown arguments: skip-trust", first)

    def test_a_cli_too_old_for_the_flags_is_told_to_update(self):
        run = _fake_run(returncode=2, stderr="flag provided but not defined: -input-format\nUsage of agy:")
        verdict = council.consult(council.SEATS["gemini"], "b", self.tmp, self.tmp, 5, run, self.which)
        self.assertIn(f"at least version {council.GEMINI_MIN_VERSION}", verdict.text)
        self.assertIn("flag provided but not defined", verdict.text.splitlines()[0])

    def test_missing_sign_in_says_how_to_sign_in(self):
        run = _fake_run(returncode=1, stderr="Error: authentication required. Run 'agy' to log in, then retry.")
        verdict = council.consult(council.SEATS["gemini"], "b", self.tmp, self.tmp, 5, run, self.which)
        self.assertIn("authentication required", verdict.text.splitlines()[0])
        self.assertIn("Sign in with Google", verdict.text)

    def test_quota_and_billing_errors_are_named(self):
        quota = _agy_stream({"event": "result", "result": {"status": "ERROR", "error": "429 RESOURCE_EXHAUSTED"}})
        verdict = council.consult(council.SEATS["gemini"], "b", self.tmp, self.tmp, 5,
                                  _fake_run(stdout=quota, returncode=1), self.which)
        self.assertIn("quota is used up", verdict.text)
        billing = council.explain_failure(council.SEATS["codex"], 1, "402 credits depleted")
        self.assertIn("run out of paid credits", billing)

    def test_failed_run_reports_the_error_tail(self):
        run = _fake_run(returncode=1, stderr="402 credits depleted")
        verdict = council.consult(council.SEATS["gemini"], "b", self.tmp, self.tmp, 5, run, self.which)
        self.assertFalse(verdict.ok)
        self.assertIn("402 credits depleted", verdict.text)

    def test_timeout_is_reported(self):
        def run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 5)

        verdict = council.consult(council.SEATS["claude"], "b", self.tmp, self.tmp, 5, run, self.which)
        self.assertFalse(verdict.ok)
        self.assertIn("within 5 s", verdict.text)


class MainTests(unittest.TestCase):
    def _main(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        environ = {k: v for k, v in os.environ.items() if k != council.SEAT_MARKER}
        environ.update(env or {})
        with mock.patch.dict(os.environ, environ, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = council.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_prints_one_command_per_seat(self):
        code, out, _ = self._main("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 4)
        self.assertIn("codex (if refused): codex exec -m gpt-6-astra", out)

    def test_a_seat_cannot_convene_its_own_council(self):
        code, _, err = self._main("--dry-run", env={council.SEAT_MARKER: "1"})
        self.assertEqual(code, 2)
        self.assertIn("already a council seat", err)

    def test_unknown_seat_is_a_usage_error(self):
        code, _, err = self._main("--seats", "codex,grok", "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("grok", err)

    def test_report_counts_answered_seats(self):
        seats = council.SEATS
        text = council.report(
            [council.Verdict(seats["codex"], True, "yes"), council.Verdict(seats["gemini"], False, "402")],
            Path("out"),
        )
        self.assertIn("1 of 2 seats answered", text)
        self.assertIn("gemini: gemini-4-neon-xhigh (Antigravity CLI), NO ANSWER", text)


if __name__ == "__main__":
    unittest.main()
