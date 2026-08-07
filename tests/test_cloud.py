"""The cloud path: bootstrap a hook, then let the session ask what to install."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.py"
HOOK = ROOT / "scripts" / "cloud-session-start.sh"
SETUP = ROOT / "scripts" / "cloud-setup-script.sh"

sys.path.insert(0, str(ROOT))
import install  # noqa: E402


def run_installer(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, str(INSTALLER), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return result


class OfferTests(unittest.TestCase):
    def test_it_names_every_bundled_skill_with_a_real_description(self) -> None:
        """A skill with no agents/openai.yaml still has a SKILL.md description,
        and a menu entry reading "Bundled in this collection." is not one a user
        could choose on."""
        with tempfile.TemporaryDirectory() as directory:
            offer = install.cloud_offer(Path(directory))
            self.assertIsNotNone(offer)
            for name in install.available_skills():
                self.assertIn(name, offer)
            self.assertNotIn("Bundled in this collection.", offer)

    def test_the_suggested_command_omits_narrow_skills(self) -> None:
        """The one command the agent is most likely to run must not machine-wide
        install a skill whose `global_default: false` says it does not want that.
        --non-interactive would, which is why the offer spells the set out."""
        narrow = [
            name
            for name in install.available_skills()
            if not install.skill_global_default(name)
        ]
        self.assertTrue(narrow, "no narrow skill left to guard the behaviour")
        with tempfile.TemporaryDirectory() as directory:
            offer = install.cloud_offer(Path(directory))
        suggested = next(
            line for line in offer.splitlines() if "everything suggested" in line
        )
        for name in narrow:
            self.assertNotIn(name, suggested)
        for name in install.available_skills():
            if install.skill_global_default(name):
                self.assertIn(f"--skill {name}", suggested)

    def test_a_narrow_skill_is_still_listed_and_labelled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            offer = install.cloud_offer(Path(directory))
        for name in install.available_skills():
            if not install.skill_global_default(name):
                self.assertIn(name, offer)
                self.assertIn("project scope on request", offer)

    def test_it_tells_the_agent_to_ask_first(self) -> None:
        """The decision belongs to the user; the hook exists to surface it, not
        to hand the agent a licence to install."""
        with tempfile.TemporaryDirectory() as directory:
            offer = install.cloud_offer(Path(directory))
        self.assertIn("Ask the user", offer)
        self.assertIn("Install nothing before they answer", offer)

    def test_silence_once_any_bundled_skill_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            name = install.available_skills()[0]
            (home / ".claude" / "skills" / name).mkdir(parents=True)
            self.assertIsNone(install.cloud_offer(home))

    def test_silence_once_declined(self) -> None:
        """Declining has to outlive the session that declined, so it is a file
        and not an answer."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            sentinel = home / install.CLOUD_DECLINED
            sentinel.parent.mkdir(parents=True)
            sentinel.touch()
            self.assertIsNone(install.cloud_offer(home))

    def test_the_offer_reaches_the_command_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_installer("--cloud-offer", "--home", directory)
            self.assertIn("[skills]", result.stdout)

    def test_an_offer_installs_nothing_by_printing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_installer("--cloud-offer", "--home", directory)
            self.assertFalse((Path(directory) / ".claude" / "skills").exists())
            self.assertFalse((Path(directory) / ".agents").exists())


class BootstrapTests(unittest.TestCase):
    def _settings(self, home: Path) -> dict:
        return json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_it_registers_the_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--cloud-bootstrap", "--home", directory)
            commands = [
                item["command"]
                for entry in self._settings(home)["hooks"]["SessionStart"]
                for item in entry["hooks"]
            ]
            self.assertEqual(1, len(commands))
            self.assertTrue(commands[0].endswith("scripts/cloud-session-start.sh"))

    def test_it_installs_no_skills(self) -> None:
        """The whole reason the flag exists: a setup script runs before anyone is
        there to choose, so it must not choose."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--cloud-bootstrap", "--home", directory)
            self.assertFalse((home / ".claude" / "skills").exists())
            self.assertFalse((home / ".agents").exists())
            self.assertFalse((home / ".claude" / "CLAUDE.md").exists())

    def test_a_second_run_changes_nothing(self) -> None:
        """Cloud setup scripts re-run on every environment rebuild. Comparing
        serialized JSON instead of parsed commands appended a duplicate every
        time, because json.dumps escapes the separators in the path it wrote."""
        with tempfile.TemporaryDirectory() as directory:
            run_installer("--cloud-bootstrap", "--home", directory)
            result = run_installer("--cloud-bootstrap", "--home", directory)
            self.assertIn("unchanged", result.stdout)
            entries = self._settings(Path(directory))["hooks"]["SessionStart"]
            self.assertEqual(1, len(entries))

    def test_it_keeps_settings_it_did_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude").mkdir()
            (home / ".claude" / "settings.json").write_text(
                json.dumps(
                    {
                        "model": "opus",
                        "hooks": {
                            "SessionStart": [
                                {"hooks": [{"type": "command", "command": "mine.sh"}]}
                            ],
                            "PreToolUse": [
                                {"hooks": [{"type": "command", "command": "guard.sh"}]}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            run_installer("--cloud-bootstrap", "--home", directory)
            settings = self._settings(home)
            self.assertEqual("opus", settings["model"])
            self.assertIn("PreToolUse", settings["hooks"])
            commands = [
                item["command"]
                for entry in settings["hooks"]["SessionStart"]
                for item in entry["hooks"]
            ]
            self.assertIn("mine.sh", commands)
            self.assertEqual(2, len(commands))

    def test_unreadable_settings_are_left_alone(self) -> None:
        """A syntax error in the user's settings is not permission to discard
        their hooks, so say what to do instead of salvaging by overwriting."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude").mkdir()
            broken = home / ".claude" / "settings.json"
            broken.write_text("{not json", encoding="utf-8")
            result = run_installer("--cloud-bootstrap", "--home", directory)
            self.assertEqual("{not json", broken.read_text(encoding="utf-8"))
            self.assertIn("not valid JSON", result.stdout)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_installer("--cloud-bootstrap", "--dry-run", "--home", directory)
            self.assertIn("would write", result.stdout)
            self.assertFalse((Path(directory) / ".claude" / "settings.json").exists())


class ScriptTests(unittest.TestCase):
    def test_the_hook_is_executable_in_the_index(self) -> None:
        """A fresh clone runs it directly, so the mode git records is the mode
        that matters -- not whatever this working tree happens to have."""
        if not shutil.which("git"):
            self.skipTest("git not available")
        listing = subprocess.run(
            ["git", "ls-files", "-s", "scripts/cloud-session-start.sh"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if listing.returncode != 0 or not listing.stdout.strip():
            self.skipTest("hook not tracked yet")
        self.assertTrue(listing.stdout.startswith("100755"), listing.stdout)

    def test_the_hook_only_runs_in_a_remote_session(self) -> None:
        """A local machine chose its skills in the dashboard and must not be
        asked again every session."""
        body = HOOK.read_text(encoding="utf-8")
        self.assertIn("CLAUDE_CODE_REMOTE", body)
        self.assertIn("--cloud-offer", body)

    def test_the_hook_can_be_switched_off_for_an_environment(self) -> None:
        self.assertIn("AGENT_SKILLS_CLOUD_OFFER", HOOK.read_text(encoding="utf-8"))

    def test_the_setup_script_decides_nothing(self) -> None:
        """It runs before anyone is present, so every skill choice it makes is
        one the user has to come back here to change."""
        body = SETUP.read_text(encoding="utf-8")
        self.assertIn("--cloud-bootstrap", body)
        for decided in ("--skill", "--matt-skills", "--graphify", "AGENT_GLOBAL_INSTRUCTIONS"):
            self.assertNotIn(decided, body)


class SummaryTests(unittest.TestCase):
    def test_a_skill_without_an_interface_file_still_describes_itself(self) -> None:
        for name in install.available_skills():
            interface = install.SOURCE_ROOT / name / "agents" / "openai.yaml"
            if interface.is_file():
                continue
            summary = install.skill_summary(name)
            self.assertNotEqual("Bundled in this collection.", summary)
            self.assertTrue(summary)

    def test_a_summary_stays_one_short_line(self) -> None:
        for name in install.available_skills():
            summary = install.skill_summary(name)
            self.assertNotIn("\n", summary)
            self.assertLessEqual(len(summary), 97, name)

    def test_the_gist_is_cut_at_the_first_clause(self) -> None:
        self.assertEqual(
            "Do the thing",
            install.first_clause("Do the thing - and all the details. Use when ..."),
        )
        self.assertEqual(
            "Do the thing.",
            install.first_clause("Do the thing. Then all the details."),
        )

    def test_a_long_unbroken_gist_is_truncated_on_a_word(self) -> None:
        clause = install.first_clause("word " * 40)
        self.assertLessEqual(len(clause), 97)
        self.assertTrue(clause.endswith("…"))


if __name__ == "__main__":
    unittest.main()
