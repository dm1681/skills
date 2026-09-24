"""Core-only Ponytail packaging and real installer regression coverage."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import install

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "ponytail"
PIN = "356918eba965ee1eac64bd3a7f0dd02108350de5"


class PonytailTests(unittest.TestCase):
    def test_core_only_package_preserves_upstream_and_attribution(self):
        self.assertIn("ponytail", install.available_skills())
        entry = next(e for e in install.VENDORED_SKILLS if e.skill == "ponytail")
        self.assertEqual(PIN, entry.commit)
        self.assertEqual("DietrichGebert/ponytail skills/ponytail/SKILL.md", entry.upstream)
        upstream = install.vendored_upstream_text(SOURCE / "SKILL.md")
        self.assertEqual(entry.sha256, hashlib.sha256(upstream.encode()).hexdigest())
        self.assertEqual(
            {"SKILL.md", "LICENSE", "agents/openai.yaml"},
            {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()},
        )
        self.assertEqual(
            "fb1bc6909ac3ef82d5c22106e32ef682b0cff66788fa915fb9b53b15c9d2f3ab",
            hashlib.sha256((SOURCE / "LICENSE").read_text().encode()).hexdigest(),
        )

    def test_upstream_edits_are_detected_but_crlf_is_accepted(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            shutil.copytree(SOURCE, root / "ponytail")
            entry = next(e for e in install.VENDORED_SKILLS if e.skill == "ponytail")
            path = root / "ponytail" / "SKILL.md"
            original = path.read_text()
            with patch.object(install, "SOURCE_ROOT", root), patch.object(install, "VENDORED_SKILLS", (entry,)):
                path.write_bytes(original.replace("\n", "\r\n").encode())
                self.assertEqual([], install.vendored_status())
                path.write_text(original + "\nChanged upstream instructions.\n")
                self.assertIn("edited here instead of upstream", install.vendored_status()[0])

    def test_isolated_copy_and_link_install_and_repeat(self):
        for mode in ("copy", "link"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=ROOT) as directory:
                home = Path(directory)
                if mode == "link":
                    try:
                        (home / "probe").symlink_to(SOURCE, target_is_directory=True)
                        (home / "probe").unlink()
                    except OSError as error:
                        self.skipTest(f"Directory symlinks unavailable: {error}")
                command = [sys.executable, str(ROOT / "install.py"), "--home", str(home),
                           "--agent", "universal", "--skill", "ponytail", "--mode", mode]
                for attempt in range(2):
                    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                            env={**os.environ, "SKILLS_PLUGIN_STATUS": "off"})
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    if attempt:
                        self.assertIn("unchanged", result.stdout)
                destination = home / ".agents" / "skills" / "ponytail"
                self.assertEqual(mode == "link", destination.is_symlink())
                for relative in ("SKILL.md", "LICENSE", "agents/openai.yaml"):
                    self.assertEqual((SOURCE / relative).read_bytes(), (destination / relative).read_bytes())
                self.assertEqual({"ponytail"}, set(install.receipt_skills(destination.parent)))
