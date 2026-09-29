#!/usr/bin/env python3
"""Validate an onboarding model, attach real source excerpts, render the page.

The model names *where* each excerpt lives (path + line range); this script
reads the lines from the repository itself, so the page can never show code
that is not in the checkout. The node/edge/group kinds are read from the
template's own `onb-kinds` block, so the validator and the rendered legend
cannot disagree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_ROOT / "assets" / "onboarding-template.html"
MAX_EXCERPT_LINES = 16
MAX_LINE_CHARS = 120
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
VIEW_KINDS = {"architecture", "flow"}
LANGUAGES = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".jsx": "jsx", ".ts": "typescript", ".mts": "typescript",
    ".tsx": "tsx", ".go": "go", ".rs": "rust", ".sh": "shell", ".bash": "shell",
    ".zsh": "shell", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
    ".sql": "sql", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".cs": "csharp", ".swift": "swift", ".css": "css",
}


class ModelError(Exception):
    """Every problem found in a model, reported together."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def load_kinds(template: Path = TEMPLATE) -> dict:
    """Return the kinds table embedded in the template."""
    text = template.read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="onb-kinds">(.*?)</script>', text, re.DOTALL
    )
    if match is None:
        raise RuntimeError(f"{template} has no onb-kinds block")
    return json.loads(match.group(1))


def language_for(path: str) -> str:
    """Guess the highlighter language from a file extension."""
    name = Path(path).name
    if name in {"Dockerfile", "Makefile"} or name.endswith(".env"):
        return "shell"
    return LANGUAGES.get(Path(path).suffix.lower(), "text")


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def web_base(remote: str | None, commit: str | None) -> str | None:
    """Return a blob URL prefix for GitHub/GitLab remotes, else None."""
    if not remote or not commit:
        return None
    match = re.match(r"^(?:git@|ssh://git@|https?://)([^/:]+)[/:](.+?)(?:\.git)?/?$", remote)
    if match is None:
        return None
    host, path = match.groups()
    if "github" in host:
        return f"https://{host}/{path}/blob/{commit}/"
    if "gitlab" in host:
        return f"https://{host}/{path}/-/blob/{commit}/"
    return None


def repo_info(repo: Path) -> dict:
    """Commit, repo name and web link base for the checkout (all optional)."""
    commit = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "remote", "get-url", "origin")
    dirty = _git(repo, "status", "--porcelain")
    name = remote.rstrip("/").removesuffix(".git").split("/")[-1].split(":")[-1] if remote else repo.name
    return {
        "repo": name,
        "commit": (commit[:10] + ("+dirty" if dirty else "")) if commit else None,
        "web": None if dirty else web_base(remote, commit),
    }


def _excerpt(repo: Path, source: dict, where: str, problems: list[str]) -> dict | None:
    path = source.get("path")
    start, end = source.get("start"), source.get("end", source.get("start"))
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        problems.append(f"{where}: source.path must be a relative path inside the repo")
        return None
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        problems.append(f"{where}: source needs integer start >= 1 and end >= start")
        return None
    if end - start + 1 > MAX_EXCERPT_LINES:
        problems.append(
            f"{where}: excerpt {path}:{start}-{end} is {end - start + 1} lines; "
            f"keep it to {MAX_EXCERPT_LINES} or fewer by choosing the lines that matter"
        )
        return None
    file = repo / path
    if not file.is_file():
        problems.append(f"{where}: {path} does not exist in {repo}")
        return None
    lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
    if end > len(lines):
        problems.append(f"{where}: {path} has {len(lines)} lines, excerpt ends at {end}")
        return None
    chosen = lines[start - 1 : end]
    long = [start + i for i, line in enumerate(chosen) if len(line) > MAX_LINE_CHARS]
    if long:
        problems.append(f"{where}: {path} line(s) {long} exceed {MAX_LINE_CHARS} characters; pick narrower lines")
    anchor = source.get("contains")
    if anchor is not None and anchor not in "\n".join(chosen):
        problems.append(f"{where}: {path}:{start}-{end} does not contain {anchor!r}; the line numbers have drifted")
    return {"path": path, "start": start, "end": end, "lang": language_for(path), "code": "\n".join(chosen)}


def build_model(model: dict, repo: Path, kinds: dict | None = None, editor_links: bool = False) -> dict:
    """Validate `model` and return the render-ready copy, or raise ModelError."""
    kinds = kinds or load_kinds()
    problems: list[str] = []
    info = repo_info(repo)
    if not isinstance(model.get("title"), str) or not model["title"].strip():
        problems.append("model: title is required")
    views = model.get("views")
    if not isinstance(views, list) or not views:
        raise ModelError(problems + ["model: views must be a non-empty list"])
    view_ids = [v.get("id") for v in views if isinstance(v, dict)]
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
        if view.get("kind") not in VIEW_KINDS:
            problems.append(f"{where}: kind must be one of {sorted(VIEW_KINDS)}")
        if not view.get("title"):
            problems.append(f"{where}: title is required")

        groups = {}
        for gi, group in enumerate(view.get("groups", [])):
            gid = group.get("id")
            gw = f"{where} groups[{gi}]"
            if not isinstance(gid, str) or not ID_PATTERN.match(gid):
                problems.append(f"{gw}: id must match {ID_PATTERN.pattern}")
                continue
            if gid in groups:
                problems.append(f"{gw}: duplicate group id {gid!r}")
            gkind = group.get("kind", "file")
            if gkind not in kinds["groups"] or gkind == "outside":
                problems.append(f"{gw}: kind must be 'file' or 'module'")
            if gkind == "file" and not (repo / str(group.get("path", ""))).is_file():
                problems.append(f"{gw}: file group path {group.get('path')!r} is not a file in the repo")
            if gkind == "module" and not (repo / str(group.get("path", ""))).is_dir():
                problems.append(f"{gw}: module group path {group.get('path')!r} is not a directory in the repo")
            groups[gid] = {
                "id": gid, "kind": gkind, "path": group.get("path"), "summary": group.get("summary", ""),
                "lang": group.get("lang") or (language_for(group["path"]) if gkind == "file" and group.get("path") else None),
            }
            if groups[gid]["lang"] == "text":
                groups[gid]["lang"] = None

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
            source = None
            if node.get("source") is not None:
                source = _excerpt(repo, node["source"], nw, problems)
                group = groups.get(gid) if gid else None
                if source and group:
                    if group["kind"] == "file" and source["path"] != group["path"]:
                        problems.append(
                            f"{nw}: excerpt is from {source['path']} but its file group is {group['path']}; "
                            "a file container holds only that file's steps"
                        )
                    if group["kind"] == "module" and not source["path"].startswith(str(group["path"]).rstrip("/") + "/"):
                        problems.append(f"{nw}: excerpt {source['path']} is outside module {group['path']}")
                if source:
                    if editor_links:
                        source["href"] = f"vscode://file/{(repo / source['path']).resolve()}:{source['start']}"
                    elif info["web"]:
                        source["href"] = f"{info['web']}{source['path']}#L{source['start']}-L{source['end']}"
            elif gid and groups.get(gid, {}).get("kind") == "file":
                problems.append(f"{nw}: nodes in a file group need a source excerpt")
            nodes.append({
                "id": nid, "kind": node.get("kind"), "label": node.get("label", ""),
                "summary": node.get("summary", ""), "group": gid, "step": step,
                "drill": drill, "source": source,
            })

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
            edges.append({"from": edge.get("from"), "to": edge.get("to"), "kind": kind, "label": edge.get("label", "")})

        if view.get("kind") == "flow" and not any(n["kind"] == "entry" for n in nodes):
            problems.append(f"{where}: a flow needs at least one entry node")
        out_views.append({
            "id": vid, "title": view.get("title", ""), "kind": view.get("kind"),
            "summary": view.get("summary", ""), "groups": list(groups.values()),
            "nodes": nodes, "edges": edges,
        })

    if problems:
        raise ModelError(problems)
    return {
        "title": model["title"],
        "summary": model.get("summary", ""),
        "source": {"repo": info["repo"], "commit": info["commit"], "generated": dt.date.today().isoformat()},
        "views": out_views,
    }


def render(built: dict, template: Path = TEMPLATE) -> str:
    """Inject the built model into the template as inert JSON."""
    payload = json.dumps(built, ensure_ascii=False, indent=None)
    # A literal `<` could close the <script> element (`</script>`) or open an
    # HTML comment (`<!--`); `\u003c` is the same character to JSON.parse.
    payload = payload.replace("<", "\\u003c")
    title = built["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = template.read_text(encoding="utf-8")
    return html.replace("__ONB_TITLE__", title, 1).replace("__ONB_MODEL__", payload, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("model", type=Path, help="onboarding model JSON")
    parser.add_argument("--repo", type=Path, default=Path("."), help="repository root the excerpts come from")
    parser.add_argument("--out", type=Path, help="HTML file to write (default: docs/onboarding/<model name>.html in --repo)")
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    parser.add_argument("--editor-links", action="store_true",
                        help="link excerpts to vscode:// on this machine instead of the web host (do not commit)")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    try:
        model = json.loads(args.model.read_text(encoding="utf-8"))
        built = build_model(model, repo, editor_links=args.editor_links)
    except json.JSONDecodeError as exc:
        print(f"error: {args.model} is not valid JSON: {exc}", file=sys.stderr)
        return 1
    except ModelError as exc:
        print(f"error: {len(exc.problems)} problem(s) in {args.model}:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    counts = ", ".join(f"{v['id']}: {len(v['nodes'])} nodes/{len(v['edges'])} edges" for v in built["views"])
    if args.check:
        print(f"ok: {counts}")
        return 0
    out = args.out or repo / "docs" / "onboarding" / f"{args.model.stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(built), encoding="utf-8")
    print(f"wrote {out} ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
