#!/usr/bin/env python3
"""Copy the shared diagram look from flow-diagrams into the skills built on it.

Skills install one at a time and cannot depend on each other, so every skill
that renders the Catppuccin flow-diagram look carries its own copy of the
shared files. `skills/flow-diagrams` owns them: edit there, then run this
script. `--check` writes nothing and exits 1 while any copy differs, which is
what the test suite runs.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / "skills" / "flow-diagrams"
SHARED = (
    "assets/diagram-template.html",
    "assets/diagram-kinds.json",
    "assets/diagram-themes.json",
    "scripts/diagram_core.py",
    "references/visual-language.md",
)
CONSUMERS = ("codebase-onboarding", "semantic-pr-review")


def drift() -> list[tuple[Path, str]]:
    """Return (copy, shared path) for every copy that is missing or differs."""
    stale = []
    for consumer in CONSUMERS:
        for rel in SHARED:
            copy = ROOT / "skills" / consumer / rel
            if not copy.is_file() or copy.read_bytes() != (OWNER / rel).read_bytes():
                stale.append((copy, rel))
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift; write nothing")
    args = parser.parse_args(argv)

    stale = drift()
    if args.check:
        for path, _ in stale:
            print(f"drift: {path.relative_to(ROOT)} differs from skills/flow-diagrams", file=sys.stderr)
        if stale:
            print("run: python3 scripts/sync_shared_diagram.py", file=sys.stderr)
        return 1 if stale else 0
    for path, rel in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OWNER / rel, path)
        print(f"synced {path.relative_to(ROOT)}")
    if not stale:
        print("ok: every shared diagram file matches skills/flow-diagrams")
    return 0


if __name__ == "__main__":
    sys.exit(main())
