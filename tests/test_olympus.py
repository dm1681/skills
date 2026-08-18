"""The Olympus integration: a registration in ~/.claude.json, and a skill.

Everything runs against a fake home and a fake Olympus checkout, so no test
reads the machine it happens to run on or the real ~/.claude.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

INSTALLER = ROOT / "install.py"
TOKEN = "olympus-secret-token"
# One bundled skill, so an end-to-end run installs something small rather than
# the whole collection.
BUNDLED = sorted(
    path.name
    for path in (ROOT / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)[0]


class Fixture(unittest.TestCase):
    """A throwaway home and a checkout that looks like Olympus."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.checkout = self.make_checkout(self.base / "projects" / "Olympus")
        self.root = self.home / ".claude" / "skills"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def make_checkout(
        self,
        path: Path,
        *,
        built: bool = True,
        skill: bool = True,
        base_url: str = "http://hades.nord:4317",
        token: str = "",
    ) -> Path:
        (path / "apps" / "mcp" / "dist").mkdir(parents=True)
        if built:
            (path / "apps" / "mcp" / "dist" / "index.js").write_text(
                "// adapter\n", encoding="utf-8"
            )
        (path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "olympus": {
                            "command": "node",
                            "args": ["apps/mcp/dist/index.js"],
                            "env": {"OLYMPUS_BASE_URL": base_url},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        if skill:
            source = path / ".claude" / "skills" / install.OLYMPUS_SKILL
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(
                "---\nname: %s\ndescription: Report progress. Use when asked.\n---\n"
                % install.OLYMPUS_SKILL,
                encoding="utf-8",
            )
        if token:
            settings = path / ".claude" / "settings.local.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(
                json.dumps(
                    {
                        "permissions": {"allow": []},
                        "mcpServers": {"olympus": {"env": {"OLYMPUS_AGENT_TOKEN": token}}},
                    }
                ),
                encoding="utf-8",
            )
        return path

    # -- helpers ---------------------------------------------------------

    def config_path(self) -> Path:
        return self.home / ".claude.json"

    def config(self) -> dict:
        return json.loads(self.config_path().read_text(encoding="utf-8"))

    def install(self, **kwargs):
        lines: list = []
        install.install_olympus(
            kwargs.pop("roots", [self.root]),
            self.home,
            checkout=kwargs.pop("checkout", self.checkout),
            env=kwargs.pop("env", {}),
            emit=lines.append,
            **kwargs,
        )
        return lines

    def run_installer(self, *arguments: str, expected: int = 0):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            expected, result.returncode, f"{result.stdout}\n{result.stderr}"
        )
        return result


class RegistrationTests(Fixture):
    def test_a_fresh_config_gets_the_absolute_adapter_path_and_env(self) -> None:
        self.install(token=TOKEN)
        entry = self.config()["mcpServers"]["olympus"]
        self.assertEqual("node", entry["command"])
        self.assertEqual(
            [(self.checkout / "apps" / "mcp" / "dist" / "index.js").as_posix()],
            entry["args"],
        )
        self.assertTrue(Path(entry["args"][0]).is_absolute())
        self.assertEqual(
            {
                "OLYMPUS_BASE_URL": "http://hades.nord:4317",
                "OLYMPUS_AGENT_TOKEN": TOKEN,
            },
            entry["env"],
        )

    def test_the_merge_preserves_other_servers_and_other_keys(self) -> None:
        self.config_path().write_text(
            json.dumps(
                {
                    "numStartups": 12,
                    "mcpServers": {
                        "github": {"command": "gh-mcp", "args": ["--stdio"]}
                    },
                    "projects": {"/somewhere": {"allowedTools": []}},
                }
            ),
            encoding="utf-8",
        )
        self.install()
        after = self.config()
        self.assertEqual(12, after["numStartups"])
        self.assertEqual({"/somewhere": {"allowedTools": []}}, after["projects"])
        self.assertEqual(
            {"command": "gh-mcp", "args": ["--stdio"]}, after["mcpServers"]["github"]
        )
        self.assertIn("olympus", after["mcpServers"])

    def test_a_config_that_will_not_parse_is_refused_byte_for_byte(self) -> None:
        broken = '{"mcpServers": {"github": }\n'
        self.config_path().write_text(broken, encoding="utf-8")
        with self.assertRaises(install.InstallError) as caught:
            self.install()
        self.assertIn("not valid JSON", str(caught.exception))
        self.assertIn("nothing was changed", str(caught.exception))
        self.assertEqual(broken, self.config_path().read_text(encoding="utf-8"))

    def test_a_rerun_replaces_the_entry_after_backing_the_config_up(self) -> None:
        self.install(token="first-token")
        self.install(token="second-token")
        self.assertEqual(
            "second-token",
            self.config()["mcpServers"]["olympus"]["env"]["OLYMPUS_AGENT_TOKEN"],
        )
        backups = sorted(
            (self.home / ".skills-backups" / "claude-config").glob(".claude.json-*")
        )
        self.assertEqual(1, len(backups))
        kept = json.loads(backups[0].read_text(encoding="utf-8"))
        self.assertEqual(
            "first-token", kept["mcpServers"]["olympus"]["env"]["OLYMPUS_AGENT_TOKEN"]
        )

    def test_an_identical_rerun_reports_unchanged_and_writes_no_backup(self) -> None:
        self.install(token=TOKEN)
        lines = self.install(token=TOKEN)
        self.assertTrue(any(line.startswith("unchanged") for line in lines))
        self.assertFalse((self.home / ".skills-backups").exists())

    def test_a_dry_run_writes_nothing(self) -> None:
        lines = self.install(dry_run=True)
        self.assertTrue(any(line.startswith("would register") for line in lines))
        self.assertFalse(self.config_path().exists())
        self.assertFalse((self.root / install.OLYMPUS_SKILL).exists())

    def test_a_non_object_mcpservers_key_is_refused(self) -> None:
        self.config_path().write_text('{"mcpServers": []}', encoding="utf-8")
        with self.assertRaises(install.InstallError) as caught:
            self.install()
        self.assertIn("non-object 'mcpServers'", str(caught.exception))


class PreflightTests(Fixture):
    def test_an_unbuilt_adapter_names_pnpm_build_and_the_checkout(self) -> None:
        unbuilt = self.make_checkout(self.base / "unbuilt", built=False)
        with self.assertRaises(install.InstallError) as caught:
            self.install(checkout=unbuilt)
        message = str(caught.exception)
        self.assertIn("pnpm build", message)
        self.assertIn(str(unbuilt), message)
        self.assertIn("gitignored", message)
        self.assertFalse(self.config_path().exists())

    def test_a_checkout_without_the_skill_is_refused(self) -> None:
        bare = self.make_checkout(self.base / "bare", skill=False)
        with self.assertRaises(install.InstallError) as caught:
            self.install(checkout=bare)
        self.assertIn(install.OLYMPUS_SKILL, str(caught.exception))
        self.assertFalse(self.config_path().exists())

    def test_the_base_url_is_reported_with_the_off_network_caveat(self) -> None:
        lines = self.install(token=TOKEN)
        joined = "\n".join(lines)
        self.assertIn("http://hades.nord:4317", joined)
        self.assertIn(install.OLYMPUS_LAN_URL, joined)
        self.assertIn("#69", joined)


class CheckoutDiscoveryTests(Fixture):
    def test_an_explicit_path_outranks_the_environment(self) -> None:
        other = self.make_checkout(self.base / "other")
        self.assertEqual(
            other.resolve(),
            install.olympus_checkout(
                other, {"OLYMPUS_CHECKOUT": str(self.checkout)}, self.home
            ),
        )

    def test_the_environment_outranks_the_conventional_locations(self) -> None:
        conventional = self.make_checkout(self.home / "projects" / "olympus")
        self.assertTrue(conventional.is_dir())
        self.assertEqual(
            self.checkout.resolve(),
            install.olympus_checkout(
                None, {"OLYMPUS_CHECKOUT": str(self.checkout)}, self.home
            ),
        )

    def test_the_conventional_locations_are_probed_in_order(self) -> None:
        self.make_checkout(self.home / "Olympus")
        self.assertEqual(
            (self.home / "Olympus").resolve(),
            install.olympus_checkout(None, {}, self.home),
        )
        preferred = self.make_checkout(self.home / "projects" / "olympus")
        self.assertEqual(
            preferred.resolve(), install.olympus_checkout(None, {}, self.home)
        )

    def test_a_named_path_that_is_not_a_checkout_fails_rather_than_probing(self) -> None:
        self.make_checkout(self.home / "projects" / "olympus")
        stray = self.base / "not-olympus"
        stray.mkdir()
        with self.assertRaises(install.InstallError) as caught:
            install.olympus_checkout(stray, {}, self.home)
        self.assertIn("apps/mcp", str(caught.exception))

    def test_a_named_path_that_does_not_exist_says_so(self) -> None:
        with self.assertRaises(install.InstallError) as caught:
            install.olympus_checkout(self.base / "missing", {}, self.home)
        self.assertIn("does not exist", str(caught.exception))

    def test_finding_nothing_names_the_flag_and_the_variable(self) -> None:
        with self.assertRaises(install.InstallError) as caught:
            install.olympus_checkout(None, {}, self.home)
        message = str(caught.exception)
        self.assertIn("--olympus-path", message)
        self.assertIn("OLYMPUS_CHECKOUT", message)
        self.assertIn(str(self.home / "projects" / "olympus"), message)


class TokenTests(Fixture):
    def test_the_flag_outranks_the_environment_and_the_settings_file(self) -> None:
        checkout = self.make_checkout(self.base / "with-token", token="from-settings")
        token, source = install.olympus_token(
            "from-flag", checkout, {"OLYMPUS_AGENT_TOKEN": "from-env"}
        )
        self.assertEqual(("from-flag", "--olympus-token"), (token, source))

    def test_the_environment_outranks_the_settings_file(self) -> None:
        checkout = self.make_checkout(self.base / "with-token", token="from-settings")
        token, source = install.olympus_token(
            None, checkout, {"OLYMPUS_AGENT_TOKEN": "from-env"}
        )
        self.assertEqual("from-env", token)
        self.assertIn("environment variable", source)

    def test_the_settings_file_is_the_last_resort(self) -> None:
        checkout = self.make_checkout(self.base / "with-token", token="from-settings")
        token, source = install.olympus_token(None, checkout, {})
        self.assertEqual("from-settings", token)
        self.assertIn("settings.local.json", source)

    def test_a_top_level_env_block_is_read_too(self) -> None:
        checkout = self.make_checkout(self.base / "top-level")
        settings = checkout / ".claude" / "settings.local.json"
        settings.write_text(
            json.dumps({"env": {"OLYMPUS_AGENT_TOKEN": "top-level-token"}}),
            encoding="utf-8",
        )
        self.assertEqual("top-level-token", install.olympus_token_from_settings(checkout))

    def test_an_unreadable_settings_file_means_no_token_not_an_error(self) -> None:
        checkout = self.make_checkout(self.base / "broken-settings")
        settings = checkout / ".claude" / "settings.local.json"
        settings.write_text("{not json", encoding="utf-8")
        self.assertIsNone(install.olympus_token_from_settings(checkout))

    def test_no_token_still_installs_and_warns_about_401(self) -> None:
        lines = self.install()
        self.assertNotIn("OLYMPUS_AGENT_TOKEN", self.config()["mcpServers"]["olympus"]["env"])
        warning = next(line for line in lines if line.startswith("WARNING"))
        self.assertIn("401 UNAUTHORIZED", warning)
        self.assertIn("2026-08-13", warning)
        self.assertIn("--olympus-token", warning)

    def test_the_token_reaches_the_config_and_nothing_else(self) -> None:
        lines = self.install(token=TOKEN)
        self.assertNotIn(TOKEN, "\n".join(lines))
        self.assertIn(
            TOKEN, self.config_path().read_text(encoding="utf-8")
        )
        self.assertNotIn(
            TOKEN, install.receipt_path(self.home).read_text(encoding="utf-8")
        )
        self.assertNotIn(
            TOKEN, install.registry_path(self.home).read_text(encoding="utf-8")
        )
        # Nowhere in this version-controlled collection either — this file's own
        # fixture value is the one legitimate occurrence.
        mine = Path(__file__).resolve()
        for path in ROOT.rglob("*"):
            if not path.is_file() or path == mine:
                continue
            if any(part in (".git", "__pycache__") for part in path.parts):
                continue
            self.assertNotIn(
                TOKEN, path.read_text(encoding="utf-8", errors="ignore"), str(path)
            )


class SkillTests(Fixture):
    def test_the_skill_is_installed_and_recorded_with_origin_olympus(self) -> None:
        self.install(token=TOKEN)
        self.assertTrue((self.root / install.OLYMPUS_SKILL / "SKILL.md").is_file())
        entries = install.receipt_entries(self.root, kind="skill", origin="olympus")
        self.assertIn(install.OLYMPUS_SKILL, entries)

    def test_the_generic_uninstall_removes_it(self) -> None:
        self.install()
        message = install.uninstall_one(install.OLYMPUS_SKILL, self.root, False)
        self.assertTrue(message.startswith("removed"))
        self.assertFalse((self.root / install.OLYMPUS_SKILL).exists())
        self.assertEqual({}, install.receipt_entries(self.root, kind="skill"))

    def test_the_install_is_visible_to_status(self) -> None:
        self.install()
        found = [
            item
            for item in install.discover_skills([self.root])
            if item.name == install.OLYMPUS_SKILL
        ]
        self.assertEqual(1, len(found))
        self.assertEqual("olympus", found[0].origin)
        self.assertTrue(found[0].recorded)

    def test_the_root_is_recorded_so_status_finds_it_again(self) -> None:
        self.install()
        self.assertIn(self.root.resolve(), install.known_roots(self.home))


class RemovalTests(Fixture):
    def test_only_the_olympus_entry_goes_and_the_config_is_backed_up(self) -> None:
        self.config_path().write_text(
            json.dumps({"numStartups": 3, "mcpServers": {"github": {"command": "gh"}}}),
            encoding="utf-8",
        )
        self.install(token=TOKEN)
        messages = install.uninstall_olympus(self.home, False)
        after = self.config()
        self.assertNotIn("olympus", after["mcpServers"])
        self.assertEqual({"command": "gh"}, after["mcpServers"]["github"])
        self.assertEqual(3, after["numStartups"])
        self.assertTrue(messages[0].startswith("removed"))
        self.assertIn(install.OLYMPUS_SKILL, messages[1])
        backups = sorted(
            (self.home / ".skills-backups" / "claude-config").glob(".claude.json-*")
        )
        # One from the install (the pre-Olympus config), one from the removal.
        self.assertEqual(2, len(backups))
        self.assertIn(
            "olympus",
            json.loads(backups[-1].read_text(encoding="utf-8"))["mcpServers"],
        )

    def test_removing_twice_is_not_an_error(self) -> None:
        self.install()
        install.uninstall_olympus(self.home, False)
        again = install.uninstall_olympus(self.home, False)
        self.assertTrue(again[0].startswith("absent"))

    def test_removal_with_no_config_at_all_is_absent(self) -> None:
        messages = install.uninstall_olympus(self.home, False)
        self.assertTrue(messages[0].startswith("absent"))

    def test_a_config_that_will_not_parse_is_refused_on_removal_too(self) -> None:
        broken = '{"mcpServers": '
        self.config_path().write_text(broken, encoding="utf-8")
        with self.assertRaises(install.InstallError):
            install.uninstall_olympus(self.home, False)
        self.assertEqual(broken, self.config_path().read_text(encoding="utf-8"))

    def test_a_dry_run_removal_changes_nothing(self) -> None:
        self.install(token=TOKEN)
        before = self.config_path().read_text(encoding="utf-8")
        messages = install.uninstall_olympus(self.home, True)
        self.assertTrue(messages[0].startswith("would remove"))
        self.assertEqual(before, self.config_path().read_text(encoding="utf-8"))


class CommandLineTests(Fixture):
    def test_the_flag_registers_and_installs_end_to_end(self) -> None:
        self.run_installer(
            "--home",
            str(self.home),
            "--agent",
            "claude",
            "--skill",
            BUNDLED,
            "--olympus",
            "--olympus-path",
            str(self.checkout),
            "--olympus-token",
            TOKEN,
            "--non-interactive",
        )
        self.assertIn("olympus", self.config()["mcpServers"])
        self.assertTrue((self.root / install.OLYMPUS_SKILL / "SKILL.md").is_file())

    def test_uninstall_removes_the_registration(self) -> None:
        self.run_installer(
            "--home",
            str(self.home),
            "--agent",
            "claude",
            "--skill",
            BUNDLED,
            "--olympus",
            "--olympus-path",
            str(self.checkout),
            "--non-interactive",
        )
        self.run_installer(
            "--home", str(self.home), "--agent", "claude", "--uninstall", "--olympus"
        )
        self.assertEqual({}, self.config()["mcpServers"])
        self.assertTrue((self.root / install.OLYMPUS_SKILL).is_dir())

    def test_the_configuring_flags_require_olympus(self) -> None:
        result = self.run_installer(
            "--home",
            str(self.home),
            "--olympus-path",
            str(self.checkout),
            "--non-interactive",
            expected=2,
        )
        self.assertIn("only applies to --olympus", result.stderr)

    def test_the_configuring_flags_are_refused_on_an_uninstall(self) -> None:
        result = self.run_installer(
            "--home",
            str(self.home),
            "--uninstall",
            "--olympus",
            "--olympus-token",
            TOKEN,
            expected=2,
        )
        self.assertIn("removes whichever one is there", result.stderr)

    def test_the_dashboard_refuses_a_scripted_flag(self) -> None:
        result = self.run_installer(
            "--home", str(self.home), "--olympus", "--interactive", expected=2
        )
        self.assertIn("--olympus is a scripted option", result.stderr)


class CliSurfaceTests(unittest.TestCase):
    def test_the_uninstall_subcommand_forwards_the_flag(self) -> None:
        import skills_cli

        argv = skills_cli.uninstall_argv(
            [], "user", Path.cwd(), [], olympus=True
        )
        self.assertIn("--olympus", argv)
        self.assertIn("--uninstall", argv)

    def test_the_uninstall_subcommand_accepts_it_as_a_selector(self) -> None:
        import skills_cli

        arguments = skills_cli.parser().parse_args(["uninstall", "--olympus"])
        self.assertTrue(arguments.olympus)


if __name__ == "__main__":
    unittest.main()
