from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "llm-wiki"
ENTRYPOINT = SKILL_ROOT / "SKILL.md"
LINTER = SKILL_ROOT / "scripts" / "wiki_lint.py"


def _load_linter():
    spec = importlib.util.spec_from_file_location("wiki_lint", LINTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wiki_lint = _load_linter()


PAGES = {
    "sources/analytical-engine-memoir.md": """---
type: source
title: The Analytical Engine, a memoir
source: raw/analytical-engine-memoir.md
updated: 2026-04-02
---

Summary that names [[entities/ada-lovelace]].
""",
    "entities/ada-lovelace.md": """---
type: entity
title: Ada Lovelace
sources: [analytical-engine-memoir]
updated: 2026-04-02
---

First published algorithm [[sources/analytical-engine-memoir]], working on
[[concepts/stored-program]].
""",
    "concepts/stored-program.md": """---
type: concept
title: Stored program
updated: 2026-04-02
---

Instructions held as data [[sources/analytical-engine-memoir]].
""",
    "index.md": """# Index

## Sources

- [[sources/analytical-engine-memoir]] — the 1843 memoir

## Entities

- [[entities/ada-lovelace]] — mathematician, first published algorithm

## Concepts

- [[concepts/stored-program]] — instructions held as data
""",
    "log.md": """# Log

## [2026-04-02] ingest | The Analytical Engine, a memoir

Touched [[sources/analytical-engine-memoir]] and [[entities/ada-lovelace]].
""",
}

RAW = {"analytical-engine-memoir.md": "The memoir itself.\n"}


class WikiFixture:
    """A healthy wiki on disk that each test bends in exactly one way."""

    def __init__(self, directory: Path) -> None:
        self.root = directory
        for name, text in RAW.items():
            self._write(self.root / "raw" / name, text)
        for name, text in PAGES.items():
            self._write(self.root / "wiki" / name, text)

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def page(self, name: str) -> Path:
        return self.root / "wiki" / name

    def add_page(self, name: str, text: str) -> None:
        self._write(self.page(name), text)

    def append(self, name: str, text: str) -> None:
        path = self.page(name)
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def add_source(self, name: str, text: str) -> None:
        self._write(self.root / "raw" / name, text)


class LinterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.wiki = WikiFixture(Path(self._temporary.name))

    def findings(self, check: str, *arguments: str) -> list:
        """Run one check over the fixture and return only its findings."""
        skipped = [f"--no-{name}" for name in wiki_lint.CHECKS if name != check]
        collected: list = []
        real_print = print

        root = str(self.wiki.root)
        lines: list = []
        import builtins

        def capture(*args, **kwargs):  # noqa: ANN001 - test shim
            lines.append(" ".join(str(arg) for arg in args))

        builtins.print = capture
        try:
            code = wiki_lint.main([root, *skipped, *arguments])
        finally:
            builtins.print = real_print
        collected = [line.strip()[2:] for line in lines if line.strip().startswith("- ")]
        self.exit_code = code
        return collected

    def test_healthy_wiki_is_clean(self) -> None:
        for check in wiki_lint.CHECKS:
            with self.subTest(check=check):
                self.assertEqual([], self.findings(check))
                self.assertEqual(0, self.exit_code)

    def test_broken_link_is_reported(self) -> None:
        self.wiki.append("entities/ada-lovelace.md", "\nSee [[concepts/missing-page]].\n")
        findings = self.findings("links")
        self.assertEqual(1, len(findings), findings)
        self.assertIn("concepts/missing-page", findings[0])

    def test_links_inside_code_fences_are_ignored(self) -> None:
        self.wiki.append(
            "entities/ada-lovelace.md",
            "\n```markdown\n[[concepts/an-example-that-does-not-exist]]\n```\n",
        )
        self.assertEqual([], self.findings("links"))

    def test_bare_slug_and_alias_links_resolve(self) -> None:
        self.wiki.append(
            "entities/ada-lovelace.md",
            "\nAlso [[stored-program|the concept]] and [[../concepts/stored-program.md]].\n",
        )
        self.assertEqual([], self.findings("links"))

    def test_orphan_page_is_reported(self) -> None:
        self.wiki.add_page(
            "concepts/punch-cards.md",
            "---\ntype: concept\n---\n\nNothing links here.\n",
        )
        self.wiki.append("index.md", "\n- [[concepts/punch-cards]] — cards\n")
        findings = self.findings("orphans")
        self.assertEqual(1, len(findings), findings)
        self.assertIn("punch-cards", findings[0])

    def test_index_listing_alone_does_not_rescue_an_orphan(self) -> None:
        """The index links everything, so it cannot count as an inbound link."""
        self.wiki.add_page("concepts/looms.md", "---\ntype: concept\n---\n\nText.\n")
        self.wiki.append("index.md", "\n- [[concepts/looms]] — looms\n")
        self.assertTrue(any("looms" in finding for finding in self.findings("orphans")))

    def test_page_missing_from_index_is_reported(self) -> None:
        self.wiki.add_page("concepts/looms.md", "---\ntype: concept\n---\n\nText.\n")
        self.wiki.append("entities/ada-lovelace.md", "\nSee [[concepts/looms]].\n")
        findings = self.findings("index")
        self.assertEqual(1, len(findings), findings)
        self.assertIn("concepts/looms.md", findings[0])

    def test_un_ingested_source_is_reported(self) -> None:
        self.wiki.add_source("babbage-letters.md", "Letters.\n")
        findings = self.findings("sources")
        self.assertEqual(1, len(findings), findings)
        self.assertIn("babbage-letters", findings[0])

    def test_malformed_log_entry_is_reported(self) -> None:
        self.wiki.append("log.md", "\n## 2026-04-03 ingested something\n")
        findings = self.findings("log")
        self.assertEqual(1, len(findings), findings)
        self.assertIn("log.md:", findings[0])

    def test_strict_changes_only_the_exit_code(self) -> None:
        self.wiki.add_source("babbage-letters.md", "Letters.\n")
        self.findings("sources")
        self.assertEqual(0, self.exit_code)
        self.findings("sources", "--strict")
        self.assertEqual(1, self.exit_code)

    def test_wiki_directory_can_be_passed_directly(self) -> None:
        code = wiki_lint.main([str(self.wiki.root / "wiki"), "--strict"])
        self.assertEqual(0, code)


class SkillLayoutTests(unittest.TestCase):
    """Pin what the repo validator cannot see."""

    def test_every_reference_is_linked_from_the_entrypoint(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        references = sorted((SKILL_ROOT / "references").glob("*.md"))
        self.assertTrue(references, "the skill ships no references")
        for reference in references:
            with self.subTest(reference=reference.name):
                relative = reference.relative_to(SKILL_ROOT).as_posix()
                self.assertIn(
                    relative,
                    text,
                    f"{relative} is unreachable: nothing in SKILL.md links to it",
                )

    def test_entrypoint_documents_the_linter(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("scripts/wiki_lint.py", text)

    def test_conventions_and_linter_agree_on_the_log_prefix(self) -> None:
        conventions = (SKILL_ROOT / "references" / "conventions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## [YYYY-MM-DD] <ingest|query|lint> | <title>", conventions)
        for operation in ("ingest", "query", "lint"):
            with self.subTest(operation=operation):
                self.assertTrue(
                    wiki_lint.LOG_HEADING.match(f"## [2026-04-02] {operation} | Title")
                )


if __name__ == "__main__":
    unittest.main()
