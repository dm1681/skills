#!/usr/bin/env python3
"""Build a PR explorer fragment from a source-verified JSON model."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
    expected_sha = materialized.get("pr", {}).get("head_sha")
    if expected_sha != source_sha:
        raise ValueError(
            "model head_sha does not match source ref: "
            f"{expected_sha!r} != {source_sha!r}"
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
            if source.get("snapshot_sha") != model["pr"]["head_sha"]:
                errors.append(
                    f"node {node_id} source {source_index} snapshot_sha "
                    "does not match pr.head_sha"
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
        if preview["source_sha"] != model["pr"]["head_sha"]:
            errors.append(
                f"node {node_id} code_preview source_sha does not match "
                "pr.head_sha"
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


def _root_id(model: dict[str, Any], requested: str | None) -> str:
    """Return a safe fragment root ID."""
    if requested:
        candidate = requested
    else:
        number = model.get("pr", {}).get("number", "unknown")
        candidate = f"pr-{number}-semantic-explorer"
    candidate = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(candidate)).strip("-")
    if not candidate:
        raise ValueError("root ID is empty after normalization")
    return candidate


def _render(
    model: dict[str, Any],
    template_path: Path,
    output_path: Path,
    requested_root_id: str | None,
) -> None:
    """Render one fragment from the reusable template."""
    template = template_path.read_text(encoding="utf-8")
    root_id = _root_id(model, requested_root_id)
    model_json = json.dumps(model, separators=(",", ":"), ensure_ascii=False)
    model_json = model_json.replace("</", "<\\/")

    rendered = template.replace("__PR_EXPLORER_ROOT_ID__", root_id)
    rendered = rendered.replace("__PR_EXPLORER_DATA__", model_json)
    if "__PR_EXPLORER_" in rendered:
        raise ValueError("template contains unresolved explorer placeholders")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def main() -> int:
    """Validate a model and render a reusable PR explorer fragment."""
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
        help="Git repository containing the analyzed PR snapshot",
    )
    parser.add_argument(
        "--source-ref",
        help="Git ref to materialize; defaults to pr.head_sha",
    )
    parser.add_argument(
        "--cursor-root",
        type=Path,
        help=(
            "Optional worktree whose HEAD and source bytes must exactly match "
            "the analyzed snapshot"
        ),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=skill_root / "assets" / "pr-explorer-template.html",
    )
    parser.add_argument("--root-id")
    args = parser.parse_args()

    raw_model = json.loads(args.data.read_text(encoding="utf-8"))
    source_ref = args.source_ref or raw_model.get("pr", {}).get("head_sha")
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
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    _render(model, args.template, args.output, args.root_id)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
