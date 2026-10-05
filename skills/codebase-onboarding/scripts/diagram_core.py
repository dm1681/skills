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

import argparse
import datetime as dt
import itertools
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

    live = _live(model.get("live"), problems)
    if problems:
        raise ModelError(problems)
    built = {
        "title": model["title"],
        "summary": model.get("summary", ""),
        "source": {**(meta or {}), "generated": dt.date.today().isoformat()},
        "views": out_views,
    }
    if live:
        built["live"] = live
    return built


def _live(live: object, problems: list[str]) -> dict | None:
    """Validate the optional live feed: a state file the page polls."""
    if live is None:
        return None
    if not isinstance(live, dict) or not isinstance(live.get("url"), str) or not live["url"].strip():
        problems.append("model: live.url must name the state file the page polls")
        return None
    every = live.get("every", 2)
    if isinstance(every, bool) or not isinstance(every, (int, float)) or every < 0.5:
        problems.append("model: live.every must be a number of seconds, at least 0.5")
        return None
    return {"url": live["url"].strip(), "every": every}


# ---------- themes ----------
# A theme assigns values to the palette's named roles; the kinds table names
# roles, never values, so every meaning survives a theme change. A custom
# theme is checked so it cannot break "one hue means one thing".
PALETTE = (
    "rosewater", "flamingo", "pink", "mauve", "red", "maroon", "peach", "yellow", "green", "teal",
    "sky", "sapphire", "blue", "lavender", "text", "subtext1", "subtext0", "overlay2", "overlay1",
    "overlay0", "surface2", "surface1", "surface0", "base", "mantle", "crust",
)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MIN_HUE_DISTANCE = 8.0   # CIE76 ΔE between any two kind colours; the built-ins keep ≥ 10
MIN_TEXT_CONTRAST = 4.5  # text on base (WCAG AA)
MIN_MUTED_CONTRAST = 3.0  # subtext0, the secondary text, on base
MIN_SHAPE_CONTRAST = 1.8  # a kind colour's outline against the container fill (mantle)


def load_themes(path: Path) -> dict:
    """Return the built-in themes: {name: {"label", "dark", "colors"}}."""
    return json.loads(path.read_text(encoding="utf-8"))


def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(value: str) -> list[float]:
    return [_linear(int(value[i:i + 2], 16)) for i in (1, 3, 5)]


def _luminance(value: str) -> float:
    r, g, b = _rgb(value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two #rrggbb colours."""
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _lab(value: str) -> tuple[float, float, float]:
    r, g, b = _rgb(value)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def distance(a: str, b: str) -> float:
    """CIE76 ΔE between two #rrggbb colours: about 2.3 is just noticeable."""
    return sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b))) ** 0.5


def theme_problems(name: str, theme: dict, kinds: dict) -> list[str]:
    """Every reason `theme` cannot carry the visual language, or []."""
    where = f"theme {name}"
    colors = theme.get("colors") if isinstance(theme, dict) else None
    if not isinstance(colors, dict):
        return [f"{where}: colors must be an object of palette roles"]
    problems = [f"{where}: {key!r} is not a palette role" for key in colors if key not in PALETTE]
    problems += [f"{where}: missing {key}" for key in PALETTE if key not in colors]
    problems += [f"{where}: {key} must be #rrggbb, not {value!r}"
                 for key, value in colors.items() if key in PALETTE and not (isinstance(value, str) and HEX.match(value))]
    if problems:
        return problems
    for role, floor in (("text", MIN_TEXT_CONTRAST), ("subtext0", MIN_MUTED_CONTRAST)):
        ratio = contrast(colors[role], colors["base"])
        if ratio < floor:
            problems.append(f"{where}: {role} on base is {ratio:.1f}:1; it needs at least {floor}:1 to stay readable")
    hues = sorted({spec["color"] for spec in kinds["nodes"].values()})
    for hue in hues:
        ratio = contrast(colors[hue], colors["mantle"])
        if ratio < MIN_SHAPE_CONTRAST:
            problems.append(f"{where}: {hue} on mantle is {ratio:.2f}:1; shapes in that colour would vanish (at least {MIN_SHAPE_CONTRAST}:1)")
    for a, b in itertools.combinations(hues, 2):
        gap = distance(colors[a], colors[b])
        if gap < MIN_HUE_DISTANCE:
            problems.append(f"{where}: {a} and {b} are ΔE {gap:.1f} apart; kinds need at least {MIN_HUE_DISTANCE} to stay distinct")
    return problems


def custom_theme(raw: dict, themes: dict, kinds: dict) -> tuple[str, dict]:
    """Resolve and validate one custom theme; raise ModelError on any problem.

    `{"name", "label"?, "dark"?, "extends"?, "colors"}`: with `extends`, only
    the roles that differ need listing. `dark` defaults from the base colour.
    """
    name = raw.get("name") if isinstance(raw, dict) else None
    if not isinstance(name, str) or not ID_PATTERN.match(name):
        raise ModelError([f"custom theme: name must match {ID_PATTERN.pattern}"])
    if name in themes:
        raise ModelError([f"custom theme {name}: the name is taken by a built-in theme"])
    parent = raw.get("extends")
    if parent is not None and parent not in themes:
        raise ModelError([f"custom theme {name}: extends {parent!r}, which is not one of {list(themes)}"])
    colors = {**(themes[parent]["colors"] if parent else {}), **(raw.get("colors") or {})}
    theme = {"label": str(raw.get("label") or name), "colors": colors}
    problems = theme_problems(name, theme, kinds)
    if problems:
        raise ModelError(problems)
    dark = raw.get("dark")
    theme["dark"] = dark if isinstance(dark, bool) else _luminance(colors["base"]) < 0.18
    return name, theme


def apply_themes(built: dict, themes: dict, *, default: str | None = None, offer: list[str] | None = None) -> dict:
    """Attach the themes a page offers and the one it opens in.

    One offered theme locks the page to it; two or more add a picker whose
    choice is remembered per viewer. Pages built without this keep the
    template's own palette (Catppuccin Mocha) and show no picker.
    """
    names = offer or list(themes)
    unknown = [n for n in names if n not in themes]
    default = default or names[0]
    if unknown or default not in names:
        raise ModelError([f"themes: {', '.join(unknown or [default])} not available; choose from {list(themes)}"])
    built["themes"] = {n: themes[n] for n in names}
    built["theme"] = default
    return built


def add_theme_arguments(parser: argparse.ArgumentParser) -> None:
    """The theme flags every builder shares."""
    parser.add_argument("--theme", help="theme the page opens in (default: the first offered)")
    parser.add_argument("--theme-file", type=Path, action="append", default=[],
                        help="custom theme JSON to add; repeatable (see references/themes.md)")
    parser.add_argument("--themes", default="all",
                        help="comma-separated themes the viewer may pick from, or 'all' (default); one locks the page")


def themes_from_args(args: argparse.Namespace, built: dict, themes: dict, kinds: dict) -> dict:
    """Apply the shared theme flags to `built`; raise ModelError on bad input."""
    themes = dict(themes)
    custom = []
    for path in args.theme_file:
        name, theme = custom_theme(load_model(path), themes, kinds)
        themes[name] = theme
        custom.append(name)
    offer = list(themes) if args.themes == "all" else [n.strip() for n in args.themes.split(",") if n.strip()]
    # A custom theme someone bothered to write opens by default.
    default = args.theme or (custom[0] if custom and custom[0] in offer else None)
    return apply_themes(built, themes, default=default, offer=offer)


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
