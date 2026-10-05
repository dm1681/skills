#!/usr/bin/env python3
"""Build a PR explorer page from a source-verified JSON model.

The PR model names where each excerpt lives; this script reads the bytes from
one immutable Git snapshot, validates the semantic contract, maps the model
onto the shared flow-diagram page (`diagram_core.py`, `assets/diagram-*`) and
injects this skill's extension (`assets/pr-extension.*`), which draws
everything PR-specific: orientation, change status, handoffs and notices.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import diagram_core as core  # noqa: E402

SKILL_ROOT = HERE.parent
TEMPLATE = SKILL_ROOT / "assets" / "diagram-template.html"
KINDS_FILE = SKILL_ROOT / "assets" / "diagram-kinds.json"
EXTENSION = {
    "css": SKILL_ROOT / "assets" / "pr-extension.css",
    "js": SKILL_ROOT / "assets" / "pr-extension.js",
}
# Systems own nodes, so they are the page's containers.
GROUPS = {
    "system": {"label": "System", "border": "solid",
               "definition": "One owner: every node inside belongs to this system."},
    "outside": {"label": "Outside", "border": "dotted", "heading": "Outside the PR's systems",
                "definition": "Nodes that name no system."},
}
VIEW_KINDS = {"flow", "delta"}

REQUIRED_TOP_LEVEL = {
    "pr",
    "summary",
    "systems",
    "nodes",
    "edges",
    "branches",
    "shared_before",
    "convergence_node",
    "shared_after",
}
REQUIRED_SUMMARY = {
    "goal",
    "old_to_new",
    "ownership_chain",
    "payoff",
    "residual_debt",
}
REQUIRED_NODE = {
    "id",
    "label",
    "code_label",
    "system",
    "change_status",
    "purpose",
    "receives",
    "sends",
    "role",
    "connection",
    "tradeoff",
    "sources",
    "code_preview",
}
REQUIRED_EDGE = {
    "from",
    "to",
    "change_status",
    "verb",
    "transfer",
    "optional",
    "containers",
    "transformation",
    "evidence",
}
REQUIRED_BRANCH = {"id", "label", "system", "path"}
CHANGE_STATUSES = {"added", "modified", "removed", "context"}
REQUIRED_SOURCE = {
    "label",
    "path",
    "start_line",
    "end_line",
    "snapshot_sha",
    "github_url",
}
REQUIRED_CODE_PREVIEW = {
    "language",
    "source_label",
    "source_index",
    "source_sha",
    "code",
}
PREVIEW_LANGUAGES = {
    "javascript",
    "json",
    "markdown",
    "python",
    "shell",
    "text",
    "toml",
    "typescript",
    "yaml",
}


def _missing(record: dict[str, Any], required: set[str]) -> list[str]:
    """Return required keys missing from a record."""
    return sorted(required.difference(record))


def _git(repo_root: Path, *args: str) -> str:
    """Return UTF-8 output from one read-only Git command."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _blob_text(repo_root: Path, source_sha: str, source_path: str) -> str:
    """Return one UTF-8 source file from an immutable Git snapshot."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{source_sha}:{source_path}"],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8")


def _source_label(source_path: str, start_line: int, end_line: int) -> str:
    """Return the compact visible label for one exact source excerpt."""
    return f"{Path(source_path).name} · {start_line}–{end_line}"


def _cursor_url(cursor_file: Path, start_line: int) -> str:
    """Return one editor deep link addressing an absolute path as a URL.

    A POSIX path already opens with the separator the URL needs, but a
    Windows path starts at its drive letter, so the same concatenation
    yields `cursor://fileC:\\...`, which browsers refuse to parse.
    """
    url_path = cursor_file.as_posix()
    if not url_path.startswith("/"):
        url_path = f"/{url_path}"
    return f"cursor://file{url_path}:{start_line}"


def _is_remote_path(candidate: Path) -> bool:
    """Return whether a path is written as a share on another host.

    An editor deep link names a path on the machine running the browser,
    so a share served from elsewhere cannot be opened by clicking it.

    Only UNC-style spellings are detectable this way. A mapped drive or a
    mounted share reads as local, so this narrows the failure rather than
    removing it. Inspect the path as given: resolving it first would
    rewrite a UNC spelling into a local absolute path on POSIX and hide
    exactly the case being tested.
    """
    text = str(candidate)
    return text.startswith("\\\\") or text.startswith("//")


def _editor_link_refusal(cursor_root: Path, source_sha: str) -> str | None:
    """Return why editor links cannot be offered, or None when they can."""
    if _is_remote_path(cursor_root):
        return f"{cursor_root} is a remote path"
    try:
        cursor_sha = _git(cursor_root, "rev-parse", "HEAD^{commit}")
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"{cursor_root} is not a readable Git worktree ({exc})"
    if cursor_sha != source_sha:
        return (
            f"{cursor_root} is at {cursor_sha[:12]}, "
            f"not the analyzed snapshot {source_sha[:12]}"
        )
    return None


def _analysis_sha(model: dict[str, Any]) -> str | None:
    """Return the commit every excerpt and link must resolve against.

    This is normally the PR head. A deletion-only PR has no evidence at its
    head, so ``pr.evidence_sha`` may name the pre-image instead; the page
    still reports both, so the anchor is never silently swapped.
    """
    pr = model.get("pr", {})
    return pr.get("evidence_sha") or pr.get("head_sha")


def _materialize_sources(
    model: dict[str, Any],
    repo_root: Path,
    source_ref: str,
    cursor_root: Path | None,
    warn: Callable[[str], None] = lambda message: None,
) -> dict[str, Any]:
    """Derive source links and preview bytes from one immutable Git snapshot."""
    materialized = copy.deepcopy(model)
    # Notices travel with the model so the page can explain a degraded
    # build to its reader, not only the operator who ran the scaffold.
    notices: list[str] = []
    materialized["notices"] = notices
    report = warn

    def note(message: str) -> None:
        """Record one notice for both the operator and the rendered page."""
        notices.append(message)
        report(message)

    warn = note
    source_sha = _git(repo_root, "rev-parse", f"{source_ref}^{{commit}}")
    expected_sha = _analysis_sha(materialized)
    if expected_sha != source_sha:
        raise ValueError(
            "model analysis sha does not match source ref: "
            f"{expected_sha!r} != {source_sha!r}"
        )
    # A pre-image anchor is a deliberate, visible choice, never a silent one.
    if materialized["pr"].get("evidence_sha"):
        note(
            "evidence anchored at "
            f"{materialized['pr']['evidence_sha'][:12]}, not PR head "
            f"{materialized['pr']['head_sha'][:12]}"
        )

    repository = materialized["pr"]["repository"]
    # Editor links are a convenience, so an unusable worktree drops them
    # and warns rather than failing the whole explorer.
    if cursor_root is not None:
        refusal = _editor_link_refusal(cursor_root, source_sha)
        if refusal is not None:
            warn(f"editor links omitted: {refusal}")
            cursor_root = None

    for node in materialized.get("nodes", []):
        node_id = node.get("id", "<unknown>")
        sources = node.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"node {node_id} has no source records")

        for source_index, source in enumerate(sources):
            if not isinstance(source, dict):
                raise ValueError(
                    f"node {node_id} source {source_index} is not an object"
                )
            missing = [
                field
                for field in ("label", "path", "start_line", "end_line")
                if field not in source
            ]
            if missing:
                raise ValueError(
                    f"node {node_id} source {source_index} is missing: "
                    + ", ".join(missing)
                )

            source_path = source["path"]
            start_line = source["start_line"]
            end_line = source["end_line"]
            if (
                not isinstance(start_line, int)
                or not isinstance(end_line, int)
                or start_line < 1
                or end_line < start_line
            ):
                raise ValueError(
                    f"node {node_id} source {source_index} has invalid line range"
                )

            blob = _blob_text(repo_root, source_sha, source_path)
            blob_lines = blob.splitlines()
            if end_line > len(blob_lines):
                raise ValueError(
                    f"node {node_id} source {source_index} ends after "
                    f"{source_path}:{len(blob_lines)}"
                )

            encoded_path = quote(source_path, safe="/")
            source["snapshot_sha"] = source_sha
            source["github_url"] = (
                f"https://github.com/{repository}/blob/{source_sha}/"
                f"{encoded_path}#L{start_line}-L{end_line}"
            )
            source.pop("cursor_url", None)
            source.pop("local_path", None)

            if cursor_root is not None:
                cursor_file = (cursor_root / source_path).resolve()
                if not cursor_file.is_file():
                    warn(
                        f"editor link omitted for {source_path}: "
                        f"{cursor_file} does not exist"
                    )
                elif cursor_file.read_text(encoding="utf-8") != blob:
                    warn(
                        f"editor link omitted for {source_path}: "
                        "working copy differs from the analyzed snapshot"
                    )
                else:
                    source["cursor_url"] = _cursor_url(cursor_file, start_line)

        preview = node.get("code_preview")
        if not isinstance(preview, dict):
            raise ValueError(f"node {node_id} has no code_preview object")
        source_index = preview.get("source_index")
        if (
            not isinstance(source_index, int)
            or source_index < 0
            or source_index >= len(sources)
        ):
            raise ValueError(
                f"node {node_id} code_preview source_index does not resolve"
            )
        source = sources[source_index]
        blob = _blob_text(repo_root, source_sha, source["path"])
        lines = blob.splitlines()
        preview["source_label"] = _source_label(
            source["path"],
            source["start_line"],
            source["end_line"],
        )
        preview["source_sha"] = source_sha
        preview["code"] = "\n".join(
            lines[source["start_line"] - 1 : source["end_line"]]
        )

    return materialized


def _validate_model(model: dict[str, Any]) -> list[str]:
    """Return semantic errors found in an explorer model."""
    errors: list[str] = []

    missing_top = _missing(model, REQUIRED_TOP_LEVEL)
    if missing_top:
        return [f"model is missing top-level fields: {', '.join(missing_top)}"]

    missing_summary = _missing(model["summary"], REQUIRED_SUMMARY)
    if missing_summary:
        errors.append(
            f"summary is missing fields: {', '.join(missing_summary)}"
        )

    for field in ("number", "repository", "head_sha"):
        if not model["pr"].get(field):
            errors.append(f"pr is missing field: {field}")

    # evidence_sha exists only to name a snapshot that is NOT the head. Set to
    # the head it adds a bogus pre-image badge and notice, so reject it.
    evidence_sha = model["pr"].get("evidence_sha")
    if evidence_sha and evidence_sha == model["pr"].get("head_sha"):
        errors.append(
            "pr.evidence_sha equals pr.head_sha; omit it unless the analyzed "
            "snapshot differs from the head"
        )

    system_ids = {system.get("id") for system in model["systems"]}
    if None in system_ids:
        errors.append("every system must have an id")

    node_ids: set[str] = set()
    for index, node in enumerate(model["nodes"]):
        missing_node = _missing(node, REQUIRED_NODE)
        if missing_node:
            errors.append(
                f"node {index} is missing fields: {', '.join(missing_node)}"
            )
            continue
        node_id = node["id"]
        if node_id in node_ids:
            errors.append(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        if node["change_status"] not in CHANGE_STATUSES:
            errors.append(
                f"node {node_id} has invalid change_status: "
                f"{node['change_status']}"
            )
        # Optional, and only worth carrying when it says more than the status
        # word would. An empty string would render as a blank line, and a
        # non-string as "[object Object]", so neither passes silently.
        if "change_note" in node:
            note = node["change_note"]
            if not isinstance(note, str) or not note.strip():
                errors.append(
                    f"node {node_id} change_note must be a non-empty string"
                )
        if node["system"] not in system_ids:
            errors.append(
                f"node {node_id} references unknown system: {node['system']}"
            )
        sources = node["sources"]
        if not isinstance(sources, list) or not sources:
            errors.append(f"node {node_id} must contain at least one source")
            continue
        for source_index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(
                    f"node {node_id} source {source_index} must be an object"
                )
                continue
            missing_source = _missing(source, REQUIRED_SOURCE)
            if missing_source:
                errors.append(
                    f"node {node_id} source {source_index} is missing fields: "
                    f"{', '.join(missing_source)}"
                )
            if source.get("snapshot_sha") != _analysis_sha(model):
                errors.append(
                    f"node {node_id} source {source_index} snapshot_sha "
                    "does not match the analyzed snapshot"
                )

        preview = node["code_preview"]
        if not isinstance(preview, dict):
            errors.append(f"node {node_id} code_preview must be an object")
            continue
        missing_preview = _missing(preview, REQUIRED_CODE_PREVIEW)
        if missing_preview:
            errors.append(
                f"node {node_id} code_preview is missing fields: "
                f"{', '.join(missing_preview)}"
            )
            continue
        if preview["language"] not in PREVIEW_LANGUAGES:
            errors.append(
                f"node {node_id} code_preview has unsupported language: "
                f"{preview['language']}"
            )
        if preview["source_sha"] != _analysis_sha(model):
            errors.append(
                f"node {node_id} code_preview source_sha does not match "
                "the analyzed snapshot"
            )
        source_index = preview["source_index"]
        if (
            not isinstance(source_index, int)
            or source_index < 0
            or source_index >= len(sources)
        ):
            errors.append(
                f"node {node_id} code_preview source_index does not resolve"
            )
        code = preview["code"]
        if not isinstance(code, str) or not code.strip():
            errors.append(f"node {node_id} code_preview has no code")
        else:
            lines = code.splitlines()
            if len(lines) > 12:
                errors.append(
                    f"node {node_id} code_preview exceeds 12 lines"
                )
            if any(len(line) > 110 for line in lines):
                errors.append(
                    f"node {node_id} code_preview contains a line over "
                    "110 characters"
                )

    for index, edge in enumerate(model["edges"]):
        missing_edge = _missing(edge, REQUIRED_EDGE)
        if missing_edge:
            errors.append(
                f"edge {index} is missing fields: {', '.join(missing_edge)}"
            )
            continue
        for endpoint in ("from", "to"):
            if edge[endpoint] not in node_ids:
                errors.append(
                    f"edge {edge['from']} -> {edge['to']} references "
                    f"unknown {endpoint} node"
                )
        if edge["change_status"] not in CHANGE_STATUSES:
            errors.append(
                f"edge {edge['from']} -> {edge['to']} has invalid "
                f"change_status: {edge['change_status']}"
            )
        if not edge["transfer"] and not edge["transformation"]:
            errors.append(
                f"edge {edge['from']} -> {edge['to']} has neither a "
                "transfer object nor transformation"
            )

    referenced_paths: list[str] = []
    referenced_paths.extend(model["shared_before"])
    referenced_paths.append(model["convergence_node"])
    referenced_paths.extend(model["shared_after"])

    for index, branch in enumerate(model["branches"]):
        missing_branch = _missing(branch, REQUIRED_BRANCH)
        if missing_branch:
            errors.append(
                f"branch {index} is missing fields: {', '.join(missing_branch)}"
            )
            continue
        if len(branch["path"]) < 2:
            errors.append(
                f"branch {branch['id']} must contain at least two runtime nodes"
            )
        if branch["system"] not in system_ids:
            errors.append(
                f"branch {branch['id']} references unknown system: "
                f"{branch['system']}"
            )
        referenced_paths.extend(branch["path"])

    unknown_path_nodes = sorted(set(referenced_paths).difference(node_ids))
    if unknown_path_nodes:
        errors.append(
            "paths reference unknown nodes: " + ", ".join(unknown_path_nodes)
        )

    expected_handoffs: set[tuple[str, str]] = set()

    def add_path(path: list[str]) -> None:
        """Record consecutive node pairs from an ordered path."""
        expected_handoffs.update(zip(path, path[1:]))

    add_path(model["shared_before"])
    add_path([model["convergence_node"], *model["shared_after"]])
    origin = model["shared_before"][-1] if model["shared_before"] else None
    for branch in model["branches"]:
        path = branch.get("path", [])
        add_path(path)
        if origin and path:
            expected_handoffs.add((origin, path[0]))
        if path:
            expected_handoffs.add((path[-1], model["convergence_node"]))

    actual_handoffs = {
        (edge.get("from"), edge.get("to"))
        for edge in model["edges"]
        if not _missing(edge, REQUIRED_EDGE)
    }
    for source, destination in sorted(
        expected_handoffs.difference(actual_handoffs)
    ):
        errors.append(f"missing edge for path: {source} -> {destination}")

    return errors


def load_kinds() -> dict:
    """Return the shared kinds table with systems as the only containers."""
    return {**core.load_kinds(KINDS_FILE), "groups": GROUPS}


def _diagram_model(model: dict[str, Any]) -> dict[str, Any]:
    """Map a validated PR model onto the shared diagram model.

    Kinds follow the runtime role unless a node or edge names one: the first
    node is the entry, a dispatch that fans out to several branches is a
    decision, and the last node is the exit. A dispatch-to-branch handoff is
    a branch edge labelled with the branch it opens; every other edge is
    labelled with its verb. Systems become containers, and steps follow the
    trunk, each branch in turn, convergence, then the tail.
    """
    pr_nodes = {node["id"]: node for node in model["nodes"]}
    systems = {system["id"]: system for system in model["systems"]}
    before, after = model["shared_before"], model["shared_after"]
    convergence, branches = model["convergence_node"], model["branches"]
    origin = before[-1] if before else None
    fans_out = origin is not None and len(branches) > 1
    heads = {branch["path"][0]: branch for branch in branches if branch["path"]}

    order: list[str] = []
    for node_id in [*before, *(n for b in branches for n in b["path"]), convergence, *after,
                    *pr_nodes]:
        if node_id not in order:
            order.append(node_id)
    last = after[-1] if after else convergence

    def kind_of(node_id: str) -> str:
        if pr_nodes[node_id].get("kind"):
            return pr_nodes[node_id]["kind"]
        if node_id == order[0]:
            return "entry"
        if fans_out and node_id == origin:
            return "decision"
        return "exit" if node_id == last else "step"

    def diagram_node(node_id: str) -> dict[str, Any]:
        node = pr_nodes[node_id]
        preview = node["code_preview"]
        source = node["sources"][preview["source_index"]]
        return {
            "id": node_id, "kind": kind_of(node_id), "label": node["label"],
            "summary": str(node["purpose"]).strip().split("\n")[0].strip(),
            "group": node["system"], "step": order.index(node_id) + 1,
            "source": {
                "path": source["path"], "start": source["start_line"], "end": source["end_line"],
                "lang": preview["language"], "code": preview["code"],
                "href": source.get("cursor_url") or source["github_url"],
            },
        }

    def diagram_edge(edge: dict[str, Any]) -> dict[str, Any]:
        branch = heads.get(edge["to"]) if fans_out and edge["from"] == origin else None
        kind = edge.get("kind") or ("branch" if branch else "call")
        label = branch["label"] if branch and kind == "branch" else edge["verb"]
        return {"from": edge["from"], "to": edge["to"], "kind": kind, "label": label}

    def view(view_id: str, title: str, kind: str, node_ids: list[str], summary: str) -> dict[str, Any]:
        keep = set(node_ids)
        used = list(dict.fromkeys(pr_nodes[n]["system"] for n in node_ids))
        result = {
            "id": view_id, "title": title, "kind": kind, "summary": summary,
            "groups": [{"id": s, "kind": "system", "label": systems[s].get("label", s)} for s in used],
            "nodes": [diagram_node(n) for n in node_ids],
            "edges": [diagram_edge(e) for e in model["edges"] if e["from"] in keep and e["to"] in keep],
        }
        if kind == "delta":
            result["tag"] = "delta"
        return result

    views = [view("full", "Full request path", "flow", order,
                  "PR changes together with the unchanged context they run through.")]
    # The delta keeps every changed node plus its direct neighbours, so the
    # boundaries a change plugs into stay visible. It is only worth a tab
    # when it actually hides something.
    changed = {n for n in order if pr_nodes[n]["change_status"] != "context"}
    boundary = set(changed)
    for edge in model["edges"]:
        if edge["from"] in changed or edge["to"] in changed:
            boundary.update((edge["from"], edge["to"]))
    if changed and boundary != set(order):
        views.append(view("delta", "PR delta", "delta", [n for n in order if n in boundary],
                          "Only what the PR changed, with the neighbours it connects to."))

    pr = model["pr"]
    return {"title": f"PR {pr['number']}: {model['summary']['goal']}", "views": views}


def _build(model: dict[str, Any]) -> dict[str, Any]:
    """Return the render-ready page model, or raise core.ModelError."""
    def check_group(where: str, raw: dict, out: dict, problems: list[str]) -> None:
        out["label"] = raw["label"]

    def check_node(where: str, raw: dict, out: dict, group: dict | None, problems: list[str]) -> None:
        out["source"] = raw["source"]

    pr = model["pr"]
    sha = _analysis_sha(model) or ""
    built = core.build(
        _diagram_model(model), load_kinds(), view_kinds=VIEW_KINDS, default_group="system",
        check_group=check_group, check_node=check_node, meta={"label": f"{pr['repository']} @ {sha[:10]}"},
    )
    # The extension reads the materialized PR model; the verifier re-checks
    # every displayed excerpt against it and against the Git blob.
    built["pr_model"] = model
    return built


def _render(built: dict[str, Any], output_path: Path) -> None:
    """Write the self-contained page with this skill's extension injected."""
    extension = {key: path.read_text(encoding="utf-8") for key, path in EXTENSION.items()}
    html = core.render(built, load_kinds(), TEMPLATE, extension)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    """Validate a model and render a self-contained PR explorer page."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="HTML page to write; not required with --check",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Validate the model and report every violation without rendering. "
            "Use this before authoring is finished to collect preview-length, "
            "line-width, path, and edge errors in one pass"
        ),
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
        help="Git repository containing the analyzed PR snapshot",
    )
    parser.add_argument(
        "--source-ref",
        help=(
            "Git ref to materialize; defaults to pr.evidence_sha when set, "
            "otherwise pr.head_sha"
        ),
    )
    parser.add_argument(
        "--cursor-root",
        type=Path,
        help=(
            "Optional worktree whose HEAD and source bytes must exactly match "
            "the analyzed snapshot"
        ),
    )
    args = parser.parse_args()

    if args.output is None and not args.check:
        print("ERROR: --output is required unless --check is given")
        return 1

    raw_model = json.loads(args.data.read_text(encoding="utf-8"))
    pr = raw_model.get("pr", {})
    # A deletion-only PR has no evidence at its head, so the analyzed snapshot
    # may legitimately be the pre-image. evidence_sha states that explicitly
    # instead of overloading head_sha to mean something it does not.
    source_ref = args.source_ref or pr.get("evidence_sha") or pr.get("head_sha")
    if not source_ref:
        print("ERROR: source ref is missing")
        return 1
    def warn(message: str) -> None:
        """Report a degraded but non-fatal condition without failing."""
        print(f"WARNING: {message}", file=sys.stderr)

    try:
        model = _materialize_sources(
            raw_model,
            args.repo_root.resolve(),
            source_ref,
            # Passed as given: each editor link resolves its own file, and
            # resolving here would erase a UNC spelling on POSIX.
            args.cursor_root,
            warn,
        )
    except (OSError, UnicodeDecodeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: source materialization failed: {exc}")
        return 1
    errors = _validate_model(model)
    if not errors:
        try:
            built = _build(model)
        except core.ModelError as exc:
            errors = exc.problems
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    if args.check:
        print(
            f"model OK: {len(model['nodes'])} nodes, {len(model['edges'])} "
            f"edges, {len(model['branches'])} branches @ "
            f"{model['pr'].get('evidence_sha') or model['pr']['head_sha']}"
        )
        return 0

    _render(built, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
