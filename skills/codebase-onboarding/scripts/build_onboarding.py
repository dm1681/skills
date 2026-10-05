#!/usr/bin/env python3
"""Validate an onboarding model, attach real source excerpts, render the page.

The model names *where* each excerpt lives (path + line range); this script
reads the lines from the repository itself, so the page can never show code
that is not in the checkout. The graph rules, the kinds table and the page
come from the shared diagram core (`diagram_core.py`, `assets/diagram-*`);
this script adds what is specific to code: file and module containers,
excerpts, drift anchors and links back to the host.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diagram_core as core  # noqa: E402

SKILL_ROOT = HERE.parent
TEMPLATE = SKILL_ROOT / "assets" / "diagram-template.html"
KINDS_FILE = SKILL_ROOT / "assets" / "diagram-kinds.json"
MAX_EXCERPT_LINES = core.MAX_SNIPPET_LINES
MAX_LINE_CHARS = core.MAX_LINE_CHARS
VIEW_KINDS = {"architecture", "flow"}
# Onboarding names the shared container borders after what they hold.
GROUPS = {
    "file":    {"label": "File", "border": "solid", "definition": "Every step inside comes from this one file."},
    "module":  {"label": "Module", "border": "dashed", "definition": "A directory or package; steps may come from any file in it."},
    "outside": {"label": "Outside repo", "border": "dotted", "heading": "Outside the repo",
                "definition": "Callers and services with no source in this repo."},
}
LANGUAGES = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".jsx": "jsx", ".ts": "typescript", ".mts": "typescript",
    ".tsx": "tsx", ".go": "go", ".rs": "rust", ".sh": "shell", ".bash": "shell",
    ".zsh": "shell", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
    ".sql": "sql", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".cs": "csharp", ".swift": "swift", ".css": "css",
}
ModelError = core.ModelError


def load_kinds() -> dict:
    """Return the shared kinds table with onboarding's container names."""
    return {**core.load_kinds(KINDS_FILE), "groups": GROUPS}


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
    info = repo_info(repo)

    def check_group(where: str, raw: dict, out: dict, problems: list[str]) -> None:
        path = raw.get("path")
        if out["kind"] == "file" and not (repo / str(path or "")).is_file():
            problems.append(f"{where}: file group path {path!r} is not a file in the repo")
        if out["kind"] == "module" and not (repo / str(path or "")).is_dir():
            problems.append(f"{where}: module group path {path!r} is not a directory in the repo")
        out["path"] = path
        lang = raw.get("lang") or (language_for(path) if out["kind"] == "file" and path else None)
        if lang and lang != "text":
            out["tag"] = lang

    def check_node(where: str, raw: dict, out: dict, group: dict | None, problems: list[str]) -> None:
        if raw.get("source") is None:
            if group and group["kind"] == "file":
                problems.append(f"{where}: nodes in a file group need a source excerpt")
            return
        source = _excerpt(repo, raw["source"], where, problems)
        if not source:
            return
        if group and group["kind"] == "file" and source["path"] != group["path"]:
            problems.append(
                f"{where}: excerpt is from {source['path']} but its file group is {group['path']}; "
                "a file container holds only that file's steps"
            )
        if group and group["kind"] == "module" and not source["path"].startswith(str(group["path"]).rstrip("/") + "/"):
            problems.append(f"{where}: excerpt {source['path']} is outside module {group['path']}")
        if editor_links:
            source["href"] = f"vscode://file/{(repo / source['path']).resolve()}:{source['start']}"
        elif info["web"]:
            source["href"] = f"{info['web']}{source['path']}#L{source['start']}-L{source['end']}"
        out["source"] = source

    return core.build(
        model, kinds or load_kinds(), view_kinds=VIEW_KINDS, default_group="file",
        check_group=check_group, check_node=check_node,
        meta={"label": " @ ".join(filter(None, [info["repo"], info["commit"]]))},
    )


def render(built: dict, kinds: dict | None = None) -> str:
    """Inject the built model into the shared template as inert JSON."""
    return core.render(built, kinds or load_kinds(), TEMPLATE)


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
        built = build_model(core.load_model(args.model), repo, editor_links=args.editor_links)
    except ModelError as exc:
        return core.report(args.model, exc)

    if args.check:
        print(f"ok: {core.counts(built)}")
        return 0
    out = args.out or repo / "docs" / "onboarding" / f"{args.model.stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(built), encoding="utf-8")
    print(f"wrote {out} ({core.counts(built)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
