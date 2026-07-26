#!/usr/bin/env python3
"""Wrap a PR explorer fragment in a self-contained standalone HTML page."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

OUTER_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "frame-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)
IFRAME_SANDBOX = (
    "allow-scripts allow-popups allow-popups-to-escape-sandbox"
)


def _standalone_html(fragment: str, title: str) -> str:
    """Return a standalone page containing the escaped explorer fragment."""
    escaped_title = html.escape(title, quote=True)
    escaped_fragment = html.escape(fragment, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{OUTER_CSP}">
<title>{escaped_title}</title>
<style>
:root {{ color-scheme: light dark; background: light-dark(#fff, #181818); }}
html, body {{ margin: 0; min-height: 100%; }}
body {{ box-sizing: border-box; padding: 1rem; background: inherit; }}
iframe {{ display: block; width: 100%; height: calc(100vh - 2rem); border: 0; }}
</style>
</head>
<body>
<iframe
  sandbox="{IFRAME_SANDBOX}"
  referrerpolicy="no-referrer"
  title="{escaped_title}"
  srcdoc="{escaped_fragment}"
></iframe>
</body>
</html>
"""


def main() -> int:
    """Render a standalone PR explorer without a host visualization tool."""
    parser = argparse.ArgumentParser(
        description="Wrap an explorer fragment in standalone HTML."
    )
    parser.add_argument("--fragment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--title",
        required=True,
        help="Document title, including the PR number",
    )
    args = parser.parse_args()

    rendered = _standalone_html(
        args.fragment.read_text(encoding="utf-8"),
        args.title,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
