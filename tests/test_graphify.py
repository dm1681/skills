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
                    ["codex", "claude"], "project", project, dry_run=False
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
            mock.patch.object(
                INSTALLER.shutil,
                "which",
                side_effect=AssertionError("dry run must not inspect installed tools"),
            ),
            contextlib.redirect_stdout(output),
        ):
            INSTALLER.install_graphify(["all"], "user", ROOT, dry_run=True)
        self.assertEqual(
            "would run  uv tool install --upgrade graphifyy\n"
            "would run  graphify install --platform agents\n"
            "would run  graphify install --platform claude\n",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
