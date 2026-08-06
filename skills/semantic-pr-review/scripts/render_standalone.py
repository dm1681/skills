#!/usr/bin/env python3
"""Render a PR explorer fragment in a self-contained standalone wrapper."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

OUTER_CSP = (
    "default-src 'none'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; "
    "frame-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)
INNER_CSP = (
    "default-src 'none'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)
IFRAME_SANDBOX = (
    "allow-scripts allow-popups allow-popups-to-escape-sandbox"
)


def _standalone_html(fragment: str, base_css: str, title: str) -> str:
    """Return a sandboxed standalone document with local base styles."""
    escaped_title = html.escape(title, quote=True)
    inner_document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{INNER_CSP}">
<title>{escaped_title}</title>
<style data-pr-explorer-base>
{base_css}
</style>
</head>
<body>
<main data-pr-explorer-standalone>
{fragment}
</main>
</body>
</html>
"""
    escaped_document = html.escape(inner_document, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{OUTER_CSP}">
<title>{escaped_title}</title>
<style>
:root {{ color-scheme: dark; background: #1e1e2e; }}
html, body {{ min-height: 100%; margin: 0; }}
body {{ box-sizing: border-box; padding: 1rem; background: inherit; }}
iframe {{ display: block; width: 100%; height: calc(100vh - 2rem); border: 0; }}
</style>
</head>
<body>
<iframe
  sandbox="{IFRAME_SANDBOX}"
  referrerpolicy="no-referrer"
  title="{escaped_title}"
  srcdoc="{escaped_document}"
></iframe>
</body>
</html>
"""


def main() -> int:
    """Render standalone HTML without a host visualization dependency."""
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Render an explorer fragment as standalone HTML."
    )
    parser.add_argument("--fragment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--title",
        required=True,
        help="Document title, including the PR number",
    )
    parser.add_argument(
        "--stylesheet",
        type=Path,
        default=skill_root / "assets" / "pr-explorer-base.css",
        help="Base stylesheet embedded before the explorer fragment",
    )
    args = parser.parse_args()

    rendered = _standalone_html(
        args.fragment.read_text(encoding="utf-8"),
        args.stylesheet.read_text(encoding="utf-8"),
        args.title,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
