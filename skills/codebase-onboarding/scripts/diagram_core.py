"""Shared core for Catppuccin Mocha flow and block diagrams.

Validates the graph structure every diagram shares (views, groups, nodes,
edges, steps, drills) and renders the self-contained page. The core knows the
visual language and nothing else. A skill built on it adds its own meaning in
two places: the `check_group`, `check_node` and `check_edge` hooks receive
each raw entry and its render-ready copy, and may fill the copy in (any extra
field rides through to the page untouched) or report problems; and `render`
injects the skill's own CSS and JS, whose hooks draw those extra fields.

This file is shared byte-for-byte by every skill that renders this look. Edit
it in skills/flow-diagrams and run scripts/sync_shared_diagram.py; a test
fails while the copies differ. It keeps no paths of its own, so whichever
copy Python imports first serves every caller identically.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Callable, Optional

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_SNIPPET_LINES = 16
MAX_LINE_CHARS = 120

GroupHook = Callable[[str, dict, dict, list], None]
NodeHook = Callable[[str, dict, dict, Optional[dict], list], None]
EdgeHook = Callable[[str, dict, dict, list], None]


class ModelError(Exception):
    """Every problem found in a model, reported together."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def load_kinds(path: Path) -> dict:
    """Return the node, edge and group kinds table."""
    return json.loads(path.read_text(encoding="utf-8"))


def build(
    model: dict,
    kinds: dict,
    *,
    view_kinds: set[str],
    default_group: str,
    check_group: GroupHook | None = None,
    check_node: NodeHook | None = None,
    check_edge: EdgeHook | None = None,
    meta: dict | None = None,
) -> dict:
    """Validate `model` and return the render-ready copy, or raise ModelError.

    `meta` lands in the built model's `source`; its `label`, if any, is the
    byline beside the page title (a repository and commit, an owner, ...).
    """
    problems: list[str] = []
    if not isinstance(model.get("title"), str) or not model["title"].strip():
        problems.append("model: title is required")
    views = model.get("views")
    if not isinstance(views, list) or not views:
        raise ModelError(problems + ["model: views must be a non-empty list"])
    view_ids = [v.get("id") for v in views if isinstance(v, dict)]
    group_kinds = [k for k in kinds["groups"] if k != "outside"]
    out_views = []
    for vi, view in enumerate(views):
        where = f"views[{vi}]"
        if not isinstance(view, dict):
            problems.append(f"{where}: must be an object")
            continue
        vid = view.get("id")
        if not isinstance(vid, str) or not ID_PATTERN.match(vid):
            problems.append(f"{where}: id must match {ID_PATTERN.pattern}")
        elif view_ids.count(vid) > 1:
            problems.append(f"{where}: duplicate view id {vid!r}")
        where = f"view {vid}"
        if view.get("kind") not in view_kinds:
            problems.append(f"{where}: kind must be one of {sorted(view_kinds)}")
        if not view.get("title"):
            problems.append(f"{where}: title is required")

        groups: dict[str, dict] = {}
        for gi, group in enumerate(view.get("groups", [])):
            gid = group.get("id")
            gw = f"{where} groups[{gi}]"
            if not isinstance(gid, str) or not ID_PATTERN.match(gid):
                problems.append(f"{gw}: id must match {ID_PATTERN.pattern}")
                continue
            if gid in groups:
                problems.append(f"{gw}: duplicate group id {gid!r}")
            gkind = group.get("kind", default_group)
            if gkind not in group_kinds:
                problems.append(f"{gw}: kind must be one of {group_kinds}")
            out = {"id": gid, "kind": gkind, "summary": group.get("summary", "")}
            if check_group:
                check_group(gw, group, out, problems)
            groups[gid] = out

        nodes, node_ids, steps = [], set(), {}
        for ni, node in enumerate(view.get("nodes", [])):
            nid = node.get("id")
            nw = f"{where} node {nid or ni}"
            if not isinstance(nid, str) or not ID_PATTERN.match(nid):
                problems.append(f"{nw}: id must match {ID_PATTERN.pattern}")
                continue
            if nid in node_ids:
                problems.append(f"{nw}: duplicate node id")
            node_ids.add(nid)
            if node.get("kind") not in kinds["nodes"]:
                problems.append(f"{nw}: kind {node.get('kind')!r} is not one of {list(kinds['nodes'])}")
            if not node.get("label"):
                problems.append(f"{nw}: label is required")
            gid = node.get("group")
            if gid is not None and gid not in groups:
                problems.append(f"{nw}: group {gid!r} is not defined in this view")
            step = node.get("step")
            if step is not None:
                if not isinstance(step, int) or step < 1:
                    problems.append(f"{nw}: step must be a positive integer")
                elif step in steps:
                    problems.append(f"{nw}: step {step} is also used by {steps[step]}")
                else:
                    steps[step] = nid
            drill = node.get("drill")
            if drill is not None and (drill not in view_ids or drill == vid):
                problems.append(f"{nw}: drill must name another view id")
            out = {
                "id": nid, "kind": node.get("kind"), "label": node.get("label", ""),
                "summary": node.get("summary", ""), "group": gid, "step": step,
                "drill": drill, "source": None,
            }
            if check_node:
                check_node(nw, node, out, groups.get(gid) if gid else None, problems)
            nodes.append(out)

        edges = []
        for ei, edge in enumerate(view.get("edges", [])):
            ew = f"{where} edges[{ei}] {edge.get('from')}->{edge.get('to')}"
            kind = edge.get("kind", "call")
            if kind not in kinds["edges"]:
                problems.append(f"{ew}: kind {kind!r} is not one of {list(kinds['edges'])}")
            for end in ("from", "to"):
                if edge.get(end) not in node_ids:
                    problems.append(f"{ew}: {end} {edge.get(end)!r} is not a node in this view")
            if kind == "branch" and not edge.get("label"):
                problems.append(f"{ew}: branch edges need a label naming the condition")
            out = {"from": edge.get("from"), "to": edge.get("to"), "kind": kind, "label": edge.get("label", "")}
            if check_edge:
                check_edge(ew, edge, out, problems)
            edges.append(out)

        if view.get("kind") == "flow" and not any(n["kind"] == "entry" for n in nodes):
            problems.append(f"{where}: a flow needs at least one entry node")
        out_view = {
            "id": vid, "title": view.get("title", ""), "kind": view.get("kind"),
            "summary": view.get("summary", ""), "groups": list(groups.values()),
            "nodes": nodes, "edges": edges,
        }
        if view.get("tag"):
            out_view["tag"] = str(view["tag"])
        out_views.append(out_view)

    if problems:
        raise ModelError(problems)
    return {
        "title": model["title"],
        "summary": model.get("summary", ""),
        "source": {**(meta or {}), "generated": dt.date.today().isoformat()},
        "views": out_views,
    }


def _inert(value: object) -> str:
    # A literal `<` could close the <script> element (`</script>`) or open an
    # HTML comment (`<!--`); `<` is the same character to JSON.parse.
    return json.dumps(value, ensure_ascii=False, indent=None).replace("<", "\\u003c")


def render(built: dict, kinds: dict, template: Path, extension: dict | None = None) -> str:
    """Inject the kinds table, the built model and an optional extension.

    `extension` is `{"css": str, "js": str}`, both optional. The JS runs
    before the page and sets `window.diagramExtension`; see the hooks in the
    template's "extension hooks" section.
    """
    css = (extension or {}).get("css", "")
    js = (extension or {}).get("js", "")
    if re.search(r"</style", css, re.IGNORECASE) or re.search(r"</script", js, re.IGNORECASE):
        raise ValueError("extension CSS/JS must not contain a closing </style> or </script> tag")
    title = built["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = template.read_text(encoding="utf-8")
    # The JSON payloads go in last, so text inside them is never scanned for a
    # marker; every real marker precedes the extension script in the page, so
    # a count-1 replace cannot land inside the extension's own text either.
    return (
        html.replace("__DIAGRAM_TITLE__", title, 1)
        .replace("/* __DIAGRAM_EXTENSION_CSS__ */", css, 1)
        .replace("__DIAGRAM_EXTENSION_JS__", js, 1)
        .replace("__DIAGRAM_KINDS__", _inert(kinds), 1)
        .replace("__DIAGRAM_MODEL__", _inert(built), 1)
    )


def load_model(path: Path) -> dict:
    """Read a model file; a JSON error becomes a ModelError naming the file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelError([f"{path} is not valid JSON: {exc}"]) from exc


def report(path: Path, error: ModelError) -> int:
    """Print every problem in one block and return the CLI exit code."""
    print(f"error: {len(error.problems)} problem(s) in {path}:", file=sys.stderr)
    for problem in error.problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def counts(built: dict) -> str:
    """One-line node/edge summary per view, for the CLI's success message."""
    return ", ".join(f"{v['id']}: {len(v['nodes'])} nodes/{len(v['edges'])} edges" for v in built["views"])
