"""The plugin half of the drift report.

Skills are files in this checkout, so their state is a byte comparison. Claude
Code plugins are installed by Claude Code's own CLI into a place this project
does not own, so the only honest reading is to ask that CLI. Everything here
therefore splits in two: `plugins_status` is pure and reconciles a manifest
against a fabricated probe, and the thin layer that actually shells out is
tested for how it *declines* -- because declining is what it does on a machine
without Claude Code, and answering "nothing to update" there would be a lie.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import install  # noqa: E402

INSTALLER = ROOT / "install.py"
MARKET = "claude-plugins-official"


def _manifest(directory: Path, plugins, marketplaces=None) -> Path:
    path = directory / "plugins.json"
    path.write_text(
        json.dumps(
            {
                "schema": install.PLUGINS_MANIFEST_SCHEMA,
                "marketplaces": (
                    {MARKET: "anthropics/claude-plugins-official"}
                    if marketplaces is None
                    else marketplaces
                ),
                "plugins": list(plugins),
            }
        ),
        encoding="utf-8",
    )
    return path


def _probe(installed=(), marketplaces=(MARKET,)) -> install.PluginProbe:
    """A machine, described the way `claude plugin list --json` describes one."""
    return install.PluginProbe(
        {entry["id"]: entry for entry in installed}, frozenset(marketplaces)
    )


def _entry(name, enabled=True, scope="user", version="1.0.0") -> dict:
    return {
        "id": f"{name}@{MARKET}",
        "version": version,
        "scope": scope,
        "enabled": enabled,
    }


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self.directory, ignore_errors=True)
        )

    def test_it_reads_ids_into_their_two_halves(self) -> None:
        path = _manifest(self.directory, [f"github@{MARKET}"])
        manifest = install.read_plugin_manifest(path)
        self.assertEqual(
            (install.PluginSpec("github", MARKET),), manifest.plugins
        )
        self.assertEqual(f"github@{MARKET}", manifest.plugins[0].identifier)

    def test_a_checkout_without_one_is_not_an_error(self) -> None:
        """An archive from before this release has no manifest and still works."""
        self.assertIsNone(
            install.read_plugin_manifest(self.directory / "absent.json")
        )

    def test_a_future_schema_is_refused_rather_than_guessed_at(self) -> None:
        path = self.directory / "plugins.json"
        path.write_text(json.dumps({"schema": 99, "plugins": []}), encoding="utf-8")
        with self.assertRaises(install.InstallError) as caught:
            install.read_plugin_manifest(path)
        self.assertIn("99", str(caught.exception))

    def test_an_id_without_a_marketplace_is_refused(self) -> None:
        path = _manifest(self.directory, ["github"])
        with self.assertRaises(install.InstallError) as caught:
            install.read_plugin_manifest(path)
        self.assertIn("name@marketplace", str(caught.exception))

    def test_a_plugin_from_an_undeclared_marketplace_is_refused(self) -> None:
        """Caught here, or caught on a fresh machine by a CLI error about a
        catalogue nobody mentioned, a long way from the typo that caused it."""
        path = _manifest(self.directory, ["github@nowhere"])
        with self.assertRaises(install.InstallError) as caught:
            install.read_plugin_manifest(path)
        self.assertIn("nowhere", str(caught.exception))

    def test_a_duplicate_is_refused(self) -> None:
        path = _manifest(self.directory, [f"github@{MARKET}", f"github@{MARKET}"])
        with self.assertRaises(install.InstallError) as caught:
            install.read_plugin_manifest(path)
        self.assertIn("more than once", str(caught.exception))

    def test_the_shipped_manifest_parses(self) -> None:
        """The file this repository actually ships, not a fixture of it."""
        manifest = install.read_plugin_manifest()
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest.plugins)
        for spec in manifest.plugins:
            self.assertIn(spec.marketplace, manifest.marketplaces)


class ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self.directory, ignore_errors=True)
        )

    def state_of(self, name, probe, declared=None):
        manifest = install.read_plugin_manifest(
            _manifest(self.directory, declared if declared is not None else [name])
        )
        report = install.plugins_status(manifest, probe)
        return {item.name: item for item in report.entries}

    def test_installed_and_enabled_is_current(self) -> None:
        rows = self.state_of(f"github@{MARKET}", _probe([_entry("github")]))
        self.assertEqual(install.CURRENT, rows[f"github@{MARKET}"].state)

    def test_declared_but_absent_is_missing(self) -> None:
        rows = self.state_of(f"github@{MARKET}", _probe())
        row = rows[f"github@{MARKET}"]
        self.assertEqual(install.MISSING, row.state)
        self.assertIn("claude plugin install", row.detail)

    def test_installed_but_switched_off_is_its_own_state(self) -> None:
        """Distinct from missing: the remedy is `enable`, not a reinstall."""
        rows = self.state_of(
            f"github@{MARKET}", _probe([_entry("github", enabled=False)])
        )
        row = rows[f"github@{MARKET}"]
        self.assertEqual(install.DISABLED, row.state)
        self.assertIn("claude plugin enable", row.detail)

    def test_installed_but_undeclared_is_untracked(self) -> None:
        rows = self.state_of(
            f"github@{MARKET}",
            _probe([_entry("github"), _entry("linear")]),
        )
        self.assertEqual(install.UNTRACKED, rows[f"linear@{MARKET}"].state)

    def test_a_project_scope_install_is_not_this_manifest_s_business(self) -> None:
        """It belongs to the repository that asked for it, not to the machine.

        Counting one as untracked would report every collaborator's repo-level
        choice as drift on every machine that opened that repo.
        """
        rows = self.state_of(
            f"github@{MARKET}",
            _probe([_entry("github"), _entry("linear", scope="project")]),
        )
        self.assertNotIn(f"linear@{MARKET}", rows)

    def test_an_unregistered_marketplace_is_reported_before_its_plugins(self) -> None:
        manifest = install.read_plugin_manifest(
            _manifest(self.directory, [f"github@{MARKET}"])
        )
        report = install.plugins_status(manifest, _probe(marketplaces=()))
        self.assertEqual("marketplace", report.entries[0].kind)
        self.assertEqual(install.MISSING, report.entries[0].state)
        self.assertIn("marketplace add", report.entries[0].detail)

    def test_every_off_baseline_state_counts_as_work(self) -> None:
        manifest = install.read_plugin_manifest(
            _manifest(self.directory, [f"github@{MARKET}", f"figma@{MARKET}"])
        )
        report = install.plugins_status(
            manifest,
            _probe([_entry("figma", enabled=False), _entry("linear")]),
        )
        self.assertEqual(
            {install.MISSING, install.DISABLED, install.UNTRACKED},
            {item.state for item in report.actionable()},
        )

    def test_a_machine_that_could_not_be_asked_says_so_and_counts_nothing(self) -> None:
        report = install.plugins_status(
            install.read_plugin_manifest(_manifest(self.directory, [])), None
        )
        self.assertEqual((), report.entries)
        self.assertIn("could not be asked", report.note)
        self.assertEqual([], report.actionable())


class ActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self.directory, ignore_errors=True)
        )

    def actions(self, declared, probe):
        manifest = install.read_plugin_manifest(_manifest(self.directory, declared))
        return install.plugin_actions(
            manifest, install.plugins_status(manifest, probe)
        )

    def test_the_marketplace_is_registered_before_anything_installs_from_it(
        self,
    ) -> None:
        actions = self.actions([f"github@{MARKET}"], _probe(marketplaces=()))
        self.assertEqual(["plugin", "marketplace", "add"], actions[0][:3])
        self.assertEqual("install", actions[1][1])

    def test_a_missing_plugin_installs_at_the_scope_the_manifest_governs(self) -> None:
        actions = self.actions([f"github@{MARKET}"], _probe())
        self.assertEqual(
            [
                "plugin",
                "install",
                f"github@{MARKET}",
                "--scope",
                install.PLUGIN_SCOPE,
                "--yes",
            ],
            actions[0],
        )

    def test_a_disabled_plugin_is_enabled_rather_than_reinstalled(self) -> None:
        actions = self.actions(
            [f"github@{MARKET}"], _probe([_entry("github", enabled=False)])
        )
        self.assertEqual(["plugin", "enable", f"github@{MARKET}"], actions[0])

    def test_an_undeclared_plugin_is_never_removed(self) -> None:
        """The manifest is a floor for what every machine has, not a warrant to
        delete what someone installed on one of them on purpose."""
        actions = self.actions(
            [f"github@{MARKET}"], _probe([_entry("github"), _entry("linear")])
        )
        self.assertEqual([], actions)

    def test_a_matching_machine_asks_for_nothing(self) -> None:
        self.assertEqual(
            [], self.actions([f"github@{MARKET}"], _probe([_entry("github")]))
        )


class CommandTests(unittest.TestCase):
    def test_a_batch_shim_is_routed_through_cmd(self) -> None:
        """An npm-global install on Windows puts a `claude.cmd` on PATH, and
        CreateProcess cannot launch a batch file."""
        self.assertEqual(
            ["cmd", "/c", r"C:\bin\claude.CMD", "plugin", "list"],
            install._claude_command(r"C:\bin\claude.CMD", ["plugin", "list"]),
        )

    def test_a_real_executable_is_run_directly(self) -> None:
        self.assertEqual(
            ["/usr/bin/claude", "plugin", "list"],
            install._claude_command("/usr/bin/claude", ["plugin", "list"]),
        )

    def test_a_cli_that_is_not_there_declines_rather_than_raising(self) -> None:
        """A status check must not die because Claude Code is absent."""
        self.assertIsNone(install.probe_plugins("definitely-not-a-command"))

    def test_install_refuses_when_the_cli_is_not_on_path(self) -> None:
        """Refusing beats installing nothing and reporting success."""
        with unittest.mock.patch.object(install, "claude_cli", return_value=None):
            with self.assertRaises(install.InstallError) as caught:
                install.install_plugins(emit=lambda _: None)
        self.assertIn("PATH", str(caught.exception))

    def test_install_refuses_when_the_cli_will_not_answer(self) -> None:
        """A CLI that is present but unreadable is its own refusal, not a
        silent "nothing to do": acting on an unknown machine is how a machine
        ends up with none of the plugins and no complaint about it."""
        with self.assertRaises(install.InstallError) as caught:
            install.install_plugins(
                claude="definitely-not-a-command", emit=lambda _: None
            )
        self.assertIn("could not read", str(caught.exception))


class ReportGateTests(unittest.TestCase):
    def test_off_drops_the_section_entirely(self) -> None:
        self.assertIsNone(
            install.plugins_report(environ={install.PLUGIN_STATUS_ENV: "off"})
        )

    def test_the_default_is_on(self) -> None:
        """Not behind a flag: plugins are the half of the drift this collection
        could not previously see."""
        self.assertNotEqual("off", os.environ.get(install.PLUGIN_STATUS_ENV, "on"))


class StatusRenderingTests(unittest.TestCase):
    def render(self, report):
        return install.status_lines([], False, None, report)

    def test_healthy_rows_collapse_to_a_count(self) -> None:
        """Two dozen `current` lines is what a matching machine produces, and
        printing each buries the rows that need a decision."""
        entries = tuple(
            install.PluginReport("plugin", install.CURRENT, f"p{index}@{MARKET}", "v1")
            for index in range(20)
        )
        lines, pending = self.render(install.PluginsReport(entries, None))
        self.assertFalse(pending)
        rendered = "\n".join(lines)
        self.assertIn("20 declared item(s)", rendered)
        self.assertNotIn(f"p7@{MARKET}", rendered)

    def test_an_actionable_row_is_named_and_counted(self) -> None:
        entries = (
            install.PluginReport("plugin", install.CURRENT, f"a@{MARKET}", "v1"),
            install.PluginReport(
                "plugin", install.MISSING, f"b@{MARKET}", "declared, not installed"
            ),
        )
        lines, pending = self.render(install.PluginsReport(entries, None))
        self.assertTrue(pending)
        rendered = "\n".join(lines)
        self.assertIn(f"b@{MARKET}", rendered)
        self.assertIn("1 item(s) need attention", rendered)

    def test_unknown_is_shown_and_not_counted(self) -> None:
        """A question this machine could not ask is not a finding; a box with
        no Claude Code would otherwise never report clean."""
        lines, pending = self.render(install.PluginsReport((), "could not ask"))
        self.assertFalse(pending)
        self.assertIn("could not ask", "\n".join(lines))

    def test_no_report_renders_no_section(self) -> None:
        # Matched as a whole line, not a substring: the word turns up in paths
        # (this checkout can live in one) and in other sections' prose.
        lines, _ = install.status_lines([], False, None, None)
        self.assertNotIn("plugins", lines)
        self.assertIn("plugins", self.render(install.PluginsReport((), None))[0])


class EndToEndTests(unittest.TestCase):
    """The wiring, not the reconciliation: that the flags reach the code."""

    def run_installer(self, *arguments, expected=0):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, install.PLUGIN_STATUS_ENV: "off"},
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def test_the_flag_is_documented_in_help(self) -> None:
        self.assertIn("--plugins", self.run_installer("--help").stdout)

    def test_mixing_it_with_a_skill_install_is_refused_not_dropped(self) -> None:
        """This is the flag a fresh machine runs, so asking for both halves at
        once is plausible, and doing one silently is the short-change."""
        result = self.run_installer("--plugins", "--skill", "tdd", expected=2)
        self.assertIn("two commands", result.stdout + result.stderr)

    def test_the_cli_exposes_the_same_command(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "skills_cli.py"), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertIn("plugins", result.stdout)


if __name__ == "__main__":
    unittest.main()
