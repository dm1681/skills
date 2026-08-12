#!/usr/bin/env python3
"""Mechanical health checks for an llm-wiki.

Reports only what needs no judgment: broken links, orphan pages, index drift,
un-ingested sources, malformed log entries. Contradictions and stale claims
are the agent's half of a lint pass and are deliberately not attempted here.

Usage:
    python3 wiki_lint.py <wiki-root> [--strict] [--no-links] [--no-orphans]
                         [--no-index] [--no-sources] [--no-log]

<wiki-root> is the directory holding `wiki/` and `raw/`, or the `wiki/`
directory itself.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


FENCE = re.compile(r"^\s*(```|~~~)")
WIKILINK = re.compile(r"\[\[([^\]\n]+)\]\]")
MDLINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)")
LOG_HEADING = re.compile(r"^##\s+\[\d{4}-\d{2}-\d{2}\]\s+(ingest|query|lint)\s+\|\s+\S")
FRONTMATTER_SOURCE = re.compile(r"^source:\s*(.+?)\s*$", re.MULTILINE)

CHECKS = ("links", "orphans", "index", "sources", "log")


def strip_code(text: str) -> str:
    """Blank out fenced code blocks so examples do not read as real links."""
    out: List[str] = []
    fence: Optional[str] = None
    for line in text.splitlines():
        match = FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
                out.append("")
                continue
            out.append(line)
        else:
            if match and match.group(1) == fence:
                fence = None
            out.append("")
    return "\n".join(out)


def link_targets(text: str) -> List[str]:
    """Every link target in a page, wikilink and markdown alike."""
    body = strip_code(text)
    targets: List[str] = []
    for raw in WIKILINK.findall(body):
        targets.append(raw.split("|", 1)[0])
    for raw in MDLINK.findall(body):
        targets.append(raw)
    cleaned: List[str] = []
    for target in targets:
        target = target.split("#", 1)[0].strip().strip("<>")
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        cleaned.append(target)
    return cleaned


def page_keys(page: Path, wiki_dir: Path) -> Tuple[str, str]:
    relative = page.relative_to(wiki_dir).as_posix()
    return relative[: -len(".md")].lower(), page.stem.lower()


def build_index(pages: Iterable[Path], wiki_dir: Path) -> Dict[str, Path]:
    """Map both the relative path and the bare slug to their page."""
    table: Dict[str, Path] = {}
    for page in pages:
        by_path, by_stem = page_keys(page, wiki_dir)
        table[by_path] = page
        table.setdefault(by_stem, page)
    return table


def resolve(target: str, source: Path, wiki_dir: Path, table: Dict[str, Path]) -> Optional[Path]:
    key = target.lower()
    if key.endswith(".md"):
        key = key[: -len(".md")]
    key = key.strip("/")
    if key in table:
        return table[key]
    # Relative to the linking page, for links like ../concepts/foo.md
    candidate = (source.parent / target).resolve()
    if candidate.suffix != ".md":
        candidate = candidate.with_suffix(".md")
    if candidate.is_file():
        return candidate
    return None


def check_links(pages: List[Path], wiki_dir: Path, table: Dict[str, Path]) -> List[str]:
    findings: List[str] = []
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        for target in link_targets(text):
            if resolve(target, page, wiki_dir, table) is None:
                findings.append(
                    f"{page.relative_to(wiki_dir).as_posix()} links to missing page: {target}"
                )
    return findings


def linked_pages(
    pages: List[Path], wiki_dir: Path, table: Dict[str, Path], skip: Set[str]
) -> Set[Path]:
    linked: Set[Path] = set()
    for page in pages:
        if page.relative_to(wiki_dir).as_posix() in skip:
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        for target in link_targets(text):
            found = resolve(target, page, wiki_dir, table)
            if found is not None:
                linked.add(found)
    return linked


def check_orphans(pages: List[Path], wiki_dir: Path, table: Dict[str, Path]) -> List[str]:
    """A page nothing links to, ignoring the index and log as link sources."""
    linked = linked_pages(pages, wiki_dir, table, skip={"index.md", "log.md"})
    findings = []
    for page in pages:
        relative = page.relative_to(wiki_dir).as_posix()
        if relative in ("index.md", "log.md") or page in linked:
            continue
        findings.append(f"orphan page, nothing links to it: {relative}")
    return findings


def check_index(pages: List[Path], wiki_dir: Path, table: Dict[str, Path]) -> List[str]:
    index = wiki_dir / "index.md"
    if not index.is_file():
        return [f"missing {index.relative_to(wiki_dir).as_posix()}"]
    listed = linked_pages([index], wiki_dir, table, skip=set())
    findings = []
    for page in pages:
        relative = page.relative_to(wiki_dir).as_posix()
        if relative in ("index.md", "log.md") or page in listed:
            continue
        findings.append(f"not listed in index.md: {relative}")
    return findings


def check_sources(pages: List[Path], wiki_dir: Path, raw_dir: Optional[Path]) -> List[str]:
    if raw_dir is None or not raw_dir.is_dir():
        return []
    corpus = "\n".join(
        page.read_text(encoding="utf-8", errors="replace") for page in pages
    )
    findings = []
    for item in sorted(raw_dir.rglob("*")):
        if not item.is_file() or item.name.startswith("."):
            continue
        relative = item.relative_to(raw_dir.parent).as_posix()
        if relative in corpus or item.name in corpus:
            continue
        findings.append(f"source in raw/ with no wiki page referencing it: {relative}")
    return findings


def check_log(wiki_dir: Path) -> List[str]:
    log = wiki_dir / "log.md"
    if not log.is_file():
        return ["missing log.md"]
    findings = []
    text = strip_code(log.read_text(encoding="utf-8", errors="replace"))
    entries = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("## "):
            continue
        entries += 1
        if not LOG_HEADING.match(line):
            findings.append(
                f"log.md:{number} entry does not match"
                f' "## [YYYY-MM-DD] <ingest|query|lint> | <title>": {line.strip()}'
            )
    if entries == 0:
        findings.append("log.md has no entries; operations are not being logged")
    return findings


def locate(root: Path) -> Tuple[Path, Optional[Path]]:
    if (root / "wiki").is_dir():
        raw = root / "raw"
        return root / "wiki", raw if raw.is_dir() else None
    sibling = root.parent / "raw"
    return root, sibling if sibling.is_dir() else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="wiki root, or the wiki/ directory")
    parser.add_argument("--strict", action="store_true", help="exit 1 when anything is found")
    for check in CHECKS:
        parser.add_argument(f"--no-{check}", action="store_true", help=f"skip the {check} check")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2
    # Absolute throughout, so paths resolved relative to a linking page compare
    # equal to the ones rglob yields.
    wiki_dir, raw_dir = locate(args.root.resolve())
    pages = sorted(page for page in wiki_dir.rglob("*.md") if page.is_file())
    if not pages:
        print(f"no markdown pages under {wiki_dir}", file=sys.stderr)
        return 2
    table = build_index(pages, wiki_dir)

    groups: List[Tuple[str, List[str]]] = []
    if not args.no_links:
        groups.append(("broken links", check_links(pages, wiki_dir, table)))
    if not args.no_orphans:
        groups.append(("orphan pages", check_orphans(pages, wiki_dir, table)))
    if not args.no_index:
        groups.append(("index drift", check_index(pages, wiki_dir, table)))
    if not args.no_sources:
        groups.append(("un-ingested sources", check_sources(pages, wiki_dir, raw_dir)))
    if not args.no_log:
        groups.append(("log format", check_log(wiki_dir)))

    total = 0
    for title, findings in groups:
        if not findings:
            continue
        total += len(findings)
        print(f"\n{title} ({len(findings)}):")
        for finding in findings:
            print(f"  - {finding}")

    print(f"\nchecked {len(pages)} page(s) under {wiki_dir}: {total} finding(s)")
    if total:
        print("semantic checks (contradictions, stale claims, gaps) are not covered here")
    return 1 if (total and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
