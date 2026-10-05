#!/usr/bin/env python3
"""Validate a diagram model and render it as one self-contained HTML page.

The model is plain JSON: views of nodes, edges and labelled groups, with
optional inline code snippets. The kinds a model may use come from
`assets/diagram-kinds.json`, the same table the page's legend is drawn from,
so the validator and the legend cannot disagree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diagram_core as core  # noqa: E402

SKILL_ROOT = HERE.parent
TEMPLATE = SKILL_ROOT / "assets" / "diagram-template.html"
KINDS_FILE = SKILL_ROOT / "assets" / "diagram-kinds.json"
VIEW_KINDS = {"flow", "map"}
ModelError = core.ModelError


def load_kinds() -> dict:
    return core.load_kinds(KINDS_FILE)


def _check_group(where: str, raw: dict, out: dict, problems: list[str]) -> None:
    label = raw.get("label")
    if not isinstance(label, str) or not label.strip():
        problems.append(f"{where}: label is required")
    out["label"] = label or out["id"]
    if raw.get("tag"):
        out["tag"] = str(raw["tag"])


def _check_node(where: str, raw: dict, out: dict, group: dict | None, problems: list[str]) -> None:
    snippet = raw.get("snippet")
    if snippet is None:
        return
    code = snippet.get("code") if isinstance(snippet, dict) else None
    if not isinstance(code, str) or not code.strip():
        problems.append(f"{where}: snippet needs a non-empty code string")
        return
    lines = code.rstrip("\n").split("\n")
    if len(lines) > core.MAX_SNIPPET_LINES:
        problems.append(f"{where}: snippet is {len(lines)} lines; keep it to {core.MAX_SNIPPET_LINES} or fewer")
    long = [i + 1 for i, line in enumerate(lines) if len(line) > core.MAX_LINE_CHARS]
    if long:
        problems.append(f"{where}: snippet line(s) {long} exceed {core.MAX_LINE_CHARS} characters")
    out["source"] = {"code": "\n".join(lines), "lang": snippet.get("lang") or "text",
                     "start": 1, "title": snippet.get("title", "")}


def build_model(model: dict, kinds: dict | None = None) -> dict:
    """Validate `model` and return the render-ready copy, or raise ModelError."""
    return core.build(
        model, kinds or load_kinds(), view_kinds=VIEW_KINDS, default_group="unit",
        check_group=_check_group, check_node=_check_node,
    )


def render(built: dict, kinds: dict | None = None) -> str:
    return core.render(built, kinds or load_kinds(), TEMPLATE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("model", type=Path, help="diagram model JSON")
    parser.add_argument("--out", type=Path, help="HTML file to write (default: the model path with .html)")
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = parser.parse_args(argv)

    try:
        built = build_model(core.load_model(args.model))
    except ModelError as exc:
        return core.report(args.model, exc)
    if args.check:
        print(f"ok: {core.counts(built)}")
        return 0
    out = args.out or args.model.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(built), encoding="utf-8")
    print(f"wrote {out} ({core.counts(built)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
