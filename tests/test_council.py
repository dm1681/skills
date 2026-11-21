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
        codex = council.SEATS["codex"].command(out)
        self.assertIn("gpt-6.2-astra", codex)
        self.assertIn('model_reasoning_effort="xhigh"', codex)
        claude = council.SEATS["claude"].command(out)
        self.assertEqual(claude[claude.index("--model") + 1], "claude-fable-5-2")
        self.assertEqual(claude[claude.index("--effort") + 1], "xhigh")
        gemini = council.SEATS["gemini"].command(out)
        self.assertEqual(gemini[gemini.index("-m") + 1], "council-neon")

    def test_every_seat_is_read_only(self):
        out = Path("answer.md")
        codex = council.SEATS["codex"].command(out)
        self.assertEqual(codex[codex.index("-s") + 1], "read-only")
        claude = council.SEATS["claude"].command(out)
        self.assertEqual(claude[claude.index("--tools") + 1], "Read,Grep,Glob")
        gemini = council.SEATS["gemini"].command(out)
        self.assertEqual(gemini[gemini.index("--approval-mode") + 1], "plan")

    def test_gemini_alias_is_neon_at_xhigh(self):
        settings = json.loads(council.GEMINI_SETTINGS.read_text(encoding="utf-8"))
        alias = settings["modelConfigs"]["customAliases"]["council-neon"]["modelConfig"]
        self.assertEqual(alias["model"], "gemini-4-neon")
        self.assertEqual(alias["generateContentConfig"]["thinkingConfig"]["thinkingLevel"], "XHIGH")
        self.assertEqual(
            council.SEATS["gemini"].env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"], str(council.GEMINI_SETTINGS)
        )


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
        council.consult(council.SEATS["gemini"], "the brief", self.tmp, self.tmp, 5, run, self.which)
        _, kwargs = run.calls[0]
        self.assertEqual(kwargs["input"], "the brief")
        self.assertEqual(kwargs["env"][council.SEAT_MARKER], "1")
        self.assertIn("GEMINI_CLI_SYSTEM_SETTINGS_PATH", kwargs["env"])

    def test_codex_answer_is_read_from_its_last_message_file(self):
        run = _fake_run(stdout="noisy progress log", write="## Recommendation\nWait.\n")
        verdict = council.consult(council.SEATS["codex"], "brief", self.tmp, self.tmp, 5, run, self.which)
        self.assertTrue(verdict.ok)
        self.assertNotIn("noisy", verdict.text)
        self.assertIn("Wait.", verdict.text)

    def test_missing_cli_is_an_empty_seat_not_a_crash(self):
        verdict = council.consult(council.SEATS["gemini"], "b", self.tmp, self.tmp, 5, _fake_run(), lambda _: None)
        self.assertFalse(verdict.ok)
        self.assertIn("not on PATH", verdict.text)

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
        self.assertEqual(len(out.strip().splitlines()), 3)

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
        self.assertIn("gemini: gemini-4-neon (XHIGH), NO ANSWER", text)


if __name__ == "__main__":
    unittest.main()
