import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import install
import symphony_project


class AsdSte100Tests(unittest.TestCase):
    def test_pinned_upstream_files_and_version_are_preserved(self):
        hashes = json.loads((install.REPO_ROOT / 'docs/asd-ste100-files.json').read_text(encoding='utf-8'))
        source = install.SOURCE_ROOT / 'asd-ste100'
        for name, expected in hashes.items():
            with self.subTest(file=name):
                value = install.vendored_upstream_text(source/name) if name == 'SKILL.md' else (source/name).read_text(encoding='utf-8')
                self.assertEqual(expected,hashlib.sha256(value.encode()).hexdigest())
        self.assertEqual('0.4.0', install.skill_version(source))
        self.assertEqual([], install.vendored_status())

    def test_installer_copies_references_and_linter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'skills'
            install.install_one(install.SOURCE_ROOT/'asd-ste100',root,'copy',False,False)
            self.assertTrue((root/'asd-ste100/references/writing-rules.md').is_file())
            self.assertTrue((root/'asd-ste100/scripts/ste-lint.py').is_file())

    def test_worker_allows_skill_and_prompt_requires_flavored_mode(self):
        self.assertIn('asd-ste100',symphony_project.WORKER_SKILLS)
        prompt=(symphony_project.RESOURCES/'WORKFLOW.md').read_text(encoding='utf-8')
        self.assertIn('.agents/skills/asd-ste100/SKILL.md',prompt)
        self.assertIn('STE-flavored mode',prompt)
