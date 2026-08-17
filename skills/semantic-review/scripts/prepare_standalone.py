#!/usr/bin/env python3
"""Prepare a host-rendered changeset explorer page for safe editor deep links."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REQUIRED_SANDBOX_PERMISSIONS = (
    "allow-scripts",
    "allow-popups",
    "allow-popups-to-escape-sandbox",
)
IFRAME_SANDBOX_PATTERN = re.compile(
    r"(?P<prefix><iframe\b[^>]*\bsandbox=)"
    r"(?P<quote>[\"'])(?P<permissions>.*?)(?P=quote)",
    re.IGNORECASE,
)
TITLE_PATTERN = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)


def _prepare_html(text: str, title: str | None) -> str:
    """Return a standalone page with safe popup permissions and title."""

    def replace_sandbox(match: re.Match[str]) -> str:
        """Add required permissions without disturbing existing permissions."""
        permissions = match.group("permissions").split()
        for permission in REQUIRED_SANDBOX_PERMISSIONS:
            if permission not in permissions:
                permissions.append(permission)
        quote = match.group("quote")
        return f"{match.group('prefix')}{quote}{' '.join(permissions)}{quote}"

    prepared, replacements = IFRAME_SANDBOX_PATTERN.subn(
        replace_sandbox,
        text,
        count=1,
    )
    if replacements != 1:
        raise ValueError("standalone page has no sandboxed iframe")

    if title is not None:
        escaped_title = (
            title.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        prepared, replacements = TITLE_PATTERN.subn(
            f"<title>{escaped_title}</title>",
            prepared,
            count=1,
        )
        if replacements != 1:
            raise ValueError("standalone page has no title element")

    return prepared


def main() -> int:
    """Prepare a rendered standalone page in place or at another path."""
    parser = argparse.ArgumentParser(
        description=(
            "Add the iframe permissions needed for local editor source links."
        )
    )
    parser.add_argument("page", type=Path, help="Rendered standalone HTML page")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path; defaults to replacing the input page",
    )
    parser.add_argument(
        "--title",
        help=(
            "Optional document title naming the changeset, such as "
            "'PR 54 Planning Explorer' or 'main...feature Planning Explorer'"
        ),
    )
    args = parser.parse_args()

    output = args.output or args.page
    prepared = _prepare_html(
        args.page.read_text(encoding="utf-8"),
        args.title,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prepared, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
