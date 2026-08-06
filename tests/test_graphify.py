from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("skills_installer", ROOT / "install.py")
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class GraphifyTests(unittest.TestCase):
    def test_platform_mapping_preserves_explicit_agent_variants(self) -> None:
        for agent in ("codex", "cursor", "copilot", "claude"):
            with self.subTest(agent=agent):
                self.assertEqual(
                    [["graphify", "install", "--platform", agent]],
                    INSTALLER.graphify_install_commands([agent], "user"),
                )

    def test_default_covers_every_graphify_platform(self) -> None:
        self.assertEqual(["agents", "claude"], INSTALLER.graphify_platforms([]))

    def test_universal_and_all_use_shared_agents_platform(self) -> None:
        self.assertEqual(["agents"], INSTALLER.graphify_platforms(["universal"]))
        self.assertEqual(["agents", "claude"], INSTALLER.graphify_platforms(["all"]))
        self.assertEqual(
            ["agents"], INSTALLER.graphify_platforms(["codex", "cursor", "copilot"])
        )

    def test_project_commands_include_project_flag(self) -> None:
        self.assertEqual(
            [["graphify", "install", "--project", "--platform", "codex"]],
            INSTALLER.graphify_install_commands(["codex"], "project"),
        )

    def test_install_uses_uv_then_registers_each_platform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/uv"),
                mock.patch.object(INSTALLER, "_find_graphify", return_value="/tools/graphify"),
                mock.patch.object(INSTALLER, "_run") as run,
            ):
                INSTALLER.install_graphify(
                    ["codex", "claude"],
                    "project",
                    project,
                    dry_run=False,
                    home=project,
                )
            self.assertEqual(
                [
                    mock.call(
                        ["/tools/uv", "tool", "install", "--upgrade", "graphifyy"],
                        project,
                    ),
                    mock.call(
                        [
                            "/tools/graphify",
                            "install",
                            "--project",
                            "--platform",
                            "codex",
                        ],
                        project,
                    ),
                    mock.call(
                        [
                            "/tools/graphify",
                            "install",
                            "--project",
                            "--platform",
                            "claude",
                        ],
                        project,
                    ),
                ],
                run.call_args_list,
            )

    def test_missing_uv_is_actionable(self) -> None:
        with mock.patch.object(INSTALLER.shutil, "which", return_value=None):
            with self.assertRaisesRegex(INSTALLER.InstallError, "requires uv"):
                INSTALLER.install_graphify([], "user", ROOT, dry_run=False)

    def test_graphify_is_found_in_uv_tool_bin_when_not_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory)
            executable = bin_dir / "graphify"
            executable.write_text("placeholder", encoding="utf-8")
            result = subprocess.CompletedProcess(
                args=["uv", "tool", "dir", "--bin"],
                returncode=0,
                stdout=f"{bin_dir}\n",
                stderr="",
            )
            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value=None),
                mock.patch.object(INSTALLER.subprocess, "run", return_value=result),
            ):
                self.assertEqual(
                    str(executable), INSTALLER._find_graphify("uv", ROOT)
                )

    def test_dry_run_prints_exact_commands_without_requiring_uv(self) -> None:
        output = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                INSTALLER.shutil,
                "which",
                side_effect=AssertionError("dry run must not inspect installed tools"),
            ),
            contextlib.redirect_stdout(output),
        ):
            INSTALLER.install_graphify(
                ["all"], "user", ROOT, dry_run=True, home=Path(directory)
            )
        self.assertEqual(
            "would run  uv tool install --upgrade graphifyy\n"
            "would run  graphify install --platform agents\n"
            "would run  graphify install --platform claude\n",
            output.getvalue(),
        )


MANAGED_POINTER_HEADER = (
    f"{INSTALLER.MANAGED_MARKER}\n"
    "<!-- Generated by dm1681/skills. -->\n\n"
)
APPENDED_GRAPHIFY = (
    "# graphify\n"
    "- **graphify** - any input to knowledge graph. Trigger: /graphify\n"
    "When the user types /graphify, use the installed graphify skill first.\n"
)


class GraphifyDeduplicationTests(unittest.TestCase):
    def _claude_pointer(self, directory: Path, body: str) -> Path:
        home = directory / "home"
        pointer = home / ".claude" / "CLAUDE.md"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(body, encoding="utf-8")
        return home

    def test_strips_trailing_block_from_managed_link_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self._claude_pointer(
                Path(directory),
                MANAGED_POINTER_HEADER
                + "# Global instructions\n\n@/elsewhere/AGENTS.md\n"
                + APPENDED_GRAPHIFY,
            )
            messages = INSTALLER.strip_appended_graphify(home, dry_run=False)
            self.assertEqual(1, len(messages))
            text = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertNotIn("graphify", text)
            self.assertTrue(text.endswith("@/elsewhere/AGENTS.md\n"))
            backups = list((home / ".skills-backups" / ".claude").iterdir())
            self.assertEqual(1, len(backups))
            self.assertIn("# graphify", backups[0].read_text(encoding="utf-8"))

    def test_leaves_files_it_does_not_manage_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self._claude_pointer(
                Path(directory), "# hand written\n\n" + APPENDED_GRAPHIFY
            )
            self.assertEqual(
                [], INSTALLER.strip_appended_graphify(home, dry_run=False)
            )
            self.assertIn(
                "# graphify",
                (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"),
            )

    def test_keeps_the_block_when_the_chain_does_not_carry_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self._claude_pointer(
                Path(directory),
                MANAGED_POINTER_HEADER
                + "# Global instructions\n\n@/elsewhere/AGENTS.md\n"
                + APPENDED_GRAPHIFY,
            )
            absent = Path(directory) / "no-such-global.md"
            with mock.patch.object(INSTALLER, "GLOBAL_SOURCE", absent):
                self.assertEqual(
                    [], INSTALLER.strip_appended_graphify(home, dry_run=False)
                )

    def test_copy_mode_keeps_the_inlined_section_and_drops_the_trailing_copy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self._claude_pointer(
                Path(directory),
                MANAGED_POINTER_HEADER
                + "# Global agent instructions\n\n## graphify\ninlined registration\n\n"
                + "## Output shaping\nrules\n"
                + APPENDED_GRAPHIFY,
            )
            messages = INSTALLER.strip_appended_graphify(home, dry_run=False)
            self.assertEqual(1, len(messages))
            text = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("## graphify\ninlined registration", text)
            self.assertNotIn("# graphify\n- **graphify**", text)
            self.assertTrue(text.endswith("## Output shaping\nrules\n"))

    def test_install_graphify_dedupes_after_registration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self._claude_pointer(
                Path(directory),
                MANAGED_POINTER_HEADER
                + "# Global instructions\n\n@/elsewhere/AGENTS.md\n"
                + APPENDED_GRAPHIFY,
            )
            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/uv"),
                mock.patch.object(
                    INSTALLER, "_find_graphify", return_value="/tools/graphify"
                ),
                mock.patch.object(INSTALLER, "_run"),
            ):
                INSTALLER.install_graphify(
                    ["claude"],
                    "user",
                    ROOT,
                    dry_run=False,
                    emit=lambda _line: None,
                    home=home,
                )
            self.assertNotIn(
                "graphify",
                (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
