#!/usr/bin/env python3
"""Validate a source-linked interactive PR explorer page.

The page is the shared flow-diagram page with this skill's extension
injected. Default checks prove it is a self-contained, populated page; with
`--strict` every displayed excerpt, label and link is re-derived from the Git
snapshot and compared, the semantic contract is re-checked on the embedded PR
model, and the page must carry the PR extension and the dark-only palette.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

CHANGE_STATUSES = {"added", "modified", "removed", "context"}
EXTENSION_HOOKS = ("header", "nodeCard", "edgeCard", "sourceBlock", "decorateNode", "decorateEdge", "legend")


def _scripts(text: str) -> list[tuple[str, str]]:
    """Return (opening tag, body) for every <script> element."""
    return re.findall(r"(<script\b[^>]*>)(.*?)</script>", text, re.DOTALL | re.IGNORECASE)


def _embedded(text: str) -> dict[str, Any] | None:
    """Return the page model the build embedded, or None."""
    for tag, body in _scripts(text):
        if 'id="diagram-model"' in tag:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
    return None


def _extension(text: str) -> str:
    """Return the injected extension script, or an empty string."""
    for tag, body in _scripts(text):
        if 'id="diagram-extension"' in tag:
            return body
    return ""


def _check_page(text: str, built: dict[str, Any] | None) -> list[str]:
    """Return errors that make the page unusable for any reader."""
    errors: list[str] = []
    if not re.match(r"\s*<!doctype html>", text, re.IGNORECASE):
        errors.append("page is not a complete HTML document")
    if "__DIAGRAM_" in text:
        errors.append("page contains unresolved template placeholders")
    if built is None:
        return errors + ["page has no parseable embedded diagram model"]
    if not isinstance(built.get("pr_model"), dict):
        errors.append("page model does not embed the PR model")
    if not built.get("views"):
        errors.append("page model has no views")
    if "window.diagramExtension" not in _extension(text):
        errors.append("page does not carry the PR extension script")
    # The shared page can poll a live state file, but only when its model
    # names one; an explorer is a snapshot and must never fetch anything.
    if built.get("live"):
        errors.append("page enables a live feed; an explorer must make no network requests")
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
        if forbidden in _extension(text):
            errors.append(f"page extension contains forbidden network API: {forbidden}")
    code = "\n".join(body for tag, body in _scripts(text) if "application/json" not in tag)
    # Source links leave the page; they must never replace it.
    if 'target: "_blank", rel: "noopener"' not in code:
        errors.append("page source links do not open a new browsing context")
    for view in built.get("views", []):
        for node in view.get("nodes", []):
            href = (node.get("source") or {}).get("href", "")
            if not re.search(r"#L\d+|^cursor://file/.+:\d+$", href):
                errors.append(f"view {view.get('id')} node {node.get('id')} has no line-anchored source link")
    return errors


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


def _cursor_target(url_path: str) -> Path:
    """Return the on-disk file a Cursor URL path addresses.

    A Windows drive path rides behind the URL's leading separator, so
    `/C:/repo/api.py` names `C:/repo/api.py` on disk.
    """
    if re.fullmatch(r"/[A-Za-z]:/.*", url_path):
        url_path = url_path[1:]
    return Path(url_path)


def _check_source_contract(
    model: dict[str, Any],
    repo_root: Path,
    source_ref: str | None,
) -> list[str]:
    """Verify every preview and editor link against one Git snapshot."""
    errors: list[str] = []
    pr = model.get("pr", {})
    # Deletion-only PRs anchor evidence at the pre-image; everything still
    # has to agree on that one commit, whichever field named it.
    expected_sha = pr.get("evidence_sha") or pr.get("head_sha")
    if not expected_sha:
        return [
            "source validation cannot resolve missing pr.head_sha "
            "or pr.evidence_sha"
        ]

    try:
        resolved_sha = _git(
            repo_root,
            "rev-parse",
            f"{source_ref or expected_sha}^{{commit}}",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"source ref cannot be resolved: {exc}"]
    if resolved_sha != expected_sha:
        errors.append(
            "source ref does not match the embedded analysis sha: "
            f"{resolved_sha} != {expected_sha}"
        )
        return errors

    repository = model.get("pr", {}).get("repository", "")
    for node in model.get("nodes", []):
        node_id = node.get("id")
        sources = node.get("sources") or []
        for source_index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(
                    f"node {node_id} source {source_index} is not an object"
                )
                continue
            source_path = source.get("path")
            start_line = source.get("start_line")
            end_line = source.get("end_line")
            if (
                not isinstance(source_path, str)
                or not isinstance(start_line, int)
                or not isinstance(end_line, int)
                or start_line < 1
                or end_line < start_line
            ):
                errors.append(
                    f"node {node_id} source {source_index} has no exact range"
                )
                continue
            if source.get("snapshot_sha") != expected_sha:
                errors.append(
                    f"node {node_id} source {source_index} snapshot mismatch"
                )
            encoded_path = quote(source_path, safe="/")
            expected_github = (
                f"https://github.com/{repository}/blob/{expected_sha}/"
                f"{encoded_path}#L{start_line}-L{end_line}"
            )
            if source.get("github_url") != expected_github:
                errors.append(
                    f"node {node_id} source {source_index} GitHub URL mismatch"
                )

            try:
                blob = _blob_text(repo_root, expected_sha, source_path)
            except (
                OSError,
                UnicodeDecodeError,
                subprocess.CalledProcessError,
            ) as exc:
                errors.append(
                    f"node {node_id} source {source_index} cannot be read: {exc}"
                )
                continue
            lines = blob.splitlines()
            if end_line > len(lines):
                errors.append(
                    f"node {node_id} source {source_index} range exceeds file"
                )
                continue

            cursor_url = source.get("cursor_url")
            if cursor_url:
                match = re.fullmatch(
                    r"cursor://file(?P<path>/.*):(?P<line>\d+)",
                    cursor_url,
                )
                if not match:
                    errors.append(
                        f"node {node_id} source {source_index} has invalid "
                        "Cursor URL"
                    )
                else:
                    cursor_file = _cursor_target(match.group("path"))
                    if int(match.group("line")) != start_line:
                        errors.append(
                            f"node {node_id} source {source_index} Cursor "
                            "line mismatch"
                        )
                    try:
                        cursor_sha = _git(
                            cursor_file.parent,
                            "rev-parse",
                            "HEAD^{commit}",
                        )
                        cursor_text = cursor_file.read_text(encoding="utf-8")
                    except (
                        OSError,
                        UnicodeDecodeError,
                        subprocess.CalledProcessError,
                    ) as exc:
                        errors.append(
                            f"node {node_id} source {source_index} Cursor "
                            f"target cannot be verified: {exc}"
                        )
                    else:
                        if cursor_sha != expected_sha:
                            errors.append(
                                f"node {node_id} source {source_index} Cursor "
                                "worktree snapshot mismatch"
                            )
                        if cursor_text != blob:
                            errors.append(
                                f"node {node_id} source {source_index} Cursor "
                                "source bytes mismatch"
                            )

        preview = node.get("code_preview")
        if not isinstance(preview, dict):
            continue
        source_index = preview.get("source_index")
        if (
            not isinstance(source_index, int)
            or source_index < 0
            or source_index >= len(sources)
        ):
            continue
        source = sources[source_index]
        source_path = source.get("path")
        start_line = source.get("start_line")
        end_line = source.get("end_line")
        if not (
            isinstance(source_path, str)
            and isinstance(start_line, int)
            and isinstance(end_line, int)
        ):
            continue
        try:
            lines = _blob_text(
                repo_root,
                expected_sha,
                source_path,
            ).splitlines()
        except (
            OSError,
            UnicodeDecodeError,
            subprocess.CalledProcessError,
        ):
            continue
        expected_code = "\n".join(lines[start_line - 1 : end_line])
        if preview.get("code") != expected_code:
            errors.append(f"node {node_id} code_preview bytes mismatch")
        expected_label = f"{Path(source_path).name} · {start_line}–{end_line}"
        if preview.get("source_label") != expected_label:
            errors.append(f"node {node_id} code_preview label mismatch")
        if preview.get("source_sha") != expected_sha:
            errors.append(f"node {node_id} code_preview snapshot mismatch")

    return errors


def _expected_handoffs(model: dict[str, Any]) -> set[tuple[str, str]]:
    """Return consecutive handoffs required by the model's rendered paths."""
    pairs: set[tuple[str, str]] = set()

    def add_path(path: list[str]) -> None:
        """Add consecutive node pairs from one ordered path."""
        pairs.update(zip(path, path[1:]))

    shared_before = model.get("shared_before", [])
    shared_after = model.get("shared_after", [])
    convergence = model.get("convergence_node")
    add_path(shared_before)
    add_path([convergence, *shared_after] if convergence else shared_after)

    origin = shared_before[-1] if shared_before else None
    for branch in model.get("branches", []):
        path = branch.get("path", [])
        add_path(path)
        if origin and path:
            pairs.add((origin, path[0]))
        if convergence and path:
            pairs.add((path[-1], convergence))

    return pairs


def _check_quality_contract(text: str, built: dict[str, Any]) -> list[str]:
    """Return strict semantic and presentation contract errors."""
    errors: list[str] = []
    model = built.get("pr_model") or {}
    pr = model.get("pr", {})

    if not re.search(rf"<title>PR {re.escape(str(pr.get('number', '')))}\b", text):
        errors.append("strict page title does not identify the PR")

    # Dark-only: one palette, so an excerpt reads the same for every reader.
    # Scoped to stylesheets so prose that discusses theming still validates.
    stylesheets = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.DOTALL | re.IGNORECASE))
    for label, pattern in (
        ("a light-dark() palette", r"light-dark\s*\("),
        ("a prefers-color-scheme block", r"@media[^{]*prefers-color-scheme"),
    ):
        if re.search(pattern, stylesheets):
            errors.append(f"strict page reintroduces {label}")
    if not re.search(r"--base:\s*#1e1e2e\b", stylesheets):
        errors.append("strict page is missing the Catppuccin Mocha base")
    # The shared page can offer themes; the explorer stays on Mocha alone.
    if set(built.get("themes") or {"mocha": None}) != {"mocha"}:
        errors.append("strict page offers other colour themes; the explorer is locked to Catppuccin Mocha")
    for forbidden in (r"word-break:\s*break-all", r"overflow-wrap:\s*anywhere"):
        if re.search(forbidden, stylesheets):
            errors.append(f"strict page contains unsafe identifier wrapping: {forbidden}")

    extension = _extension(text)
    for hook in EXTENSION_HOOKS:
        if not re.search(rf"\b{hook}\s*\(", extension):
            errors.append(f"strict page extension is missing the {hook} hook")
    for label, pattern in (
        ("degraded build notice region", r"[\"']data-role[\"']\s*:\s*[\"']notices[\"']"),
        ("analyzed snapshot badge", r"[\"']data-role[\"']\s*:\s*[\"']pr-snapshot[\"']"),
        ("semantic identifier wrapping", r"createElement\([\"']wbr[\"']\)"),
        ("markdown excerpt rendering", r"renderMarkdownExcerpt\("),
        ("markdown link scheme guard", r"https\?:.{0,20}mailto:"),
        ("corner change mark", r"prx-mark"),
    ):
        if not re.search(pattern, extension):
            errors.append(f"strict page extension is missing {label}")

    if not pr.get("head_sha"):
        errors.append("embedded PR metadata is missing head_sha")
    summary = model.get("summary", {})
    for field in ("goal", "old_to_new", "ownership_chain", "payoff", "residual_debt"):
        if not summary.get(field):
            errors.append(f"embedded summary is missing {field}")

    pr_nodes = {node.get("id"): node for node in model.get("nodes", [])}
    for node_id, node in pr_nodes.items():
        if node.get("change_status") not in CHANGE_STATUSES:
            errors.append(f"node {node_id} has invalid or missing change_status")
        sources = node.get("sources") or []
        if not sources:
            errors.append(f"node {node_id} has no source references")
        preview = node.get("code_preview")
        if not isinstance(preview, dict):
            errors.append(f"node {node_id} has no code_preview")
            continue
        for field in ("language", "source_label", "source_index", "code"):
            if field not in preview:
                errors.append(f"node {node_id} code_preview is missing {field}")
        source_index = preview.get("source_index")
        if not isinstance(source_index, int) or not 0 <= source_index < len(sources):
            errors.append(f"node {node_id} code_preview source_index does not resolve")
        code = preview.get("code")
        if not isinstance(code, str) or not code.strip():
            errors.append(f"node {node_id} code_preview has no code")
        elif len(code.splitlines()) > 12:
            errors.append(f"node {node_id} code_preview exceeds 12 lines")

    actual_handoffs: set[tuple[str, str]] = set()
    for edge in model.get("edges", []):
        pair = (edge.get("from"), edge.get("to"))
        actual_handoffs.add(pair)
        if edge.get("change_status") not in CHANGE_STATUSES:
            errors.append(f"edge {pair[0]} -> {pair[1]} has invalid or missing change_status")
        if not edge.get("transfer") and not edge.get("transformation"):
            errors.append(f"edge {pair[0]} -> {pair[1]} has no transfer or transformation")
        if not edge.get("evidence"):
            errors.append(f"edge {pair[0]} -> {pair[1]} has no evidence")
    for source, destination in sorted(_expected_handoffs(model).difference(actual_handoffs)):
        errors.append(f"rendered path lacks edge {source} -> {destination}")
    for branch in model.get("branches", []):
        path = branch.get("path", [])
        if len(path) < 2:
            errors.append(f"branch {branch.get('id')} has fewer than two runtime nodes")
        unknown = set(path).difference(pr_nodes)
        if unknown:
            errors.append(f"branch {branch.get('id')} references unknown nodes: " + ", ".join(sorted(unknown)))

    # What the reader sees must be what was verified: every drawn excerpt and
    # link is the PR model's own, and the full view draws every node and edge.
    views = {view.get("id"): view for view in built.get("views", [])}
    full = views.get("full")
    if full is None:
        return errors + ["page has no full request path view"]
    drawn = {node.get("id") for node in full.get("nodes", [])}
    for missing in sorted(set(pr_nodes).difference(drawn), key=str):
        errors.append(f"full view does not draw node {missing}")
    drawn_edges = {(e.get("from"), e.get("to")): e for e in full.get("edges", [])}
    for pair in sorted(actual_handoffs.difference(drawn_edges), key=str):
        errors.append(f"full view does not draw edge {pair[0]} -> {pair[1]}")
    for pair, edge in drawn_edges.items():
        if not edge.get("label"):
            errors.append(f"edge {pair[0]} -> {pair[1]} has no visible label")
    for view in views.values():
        for node in view.get("nodes", []):
            pn = pr_nodes.get(node.get("id"))
            preview = (pn or {}).get("code_preview") or {}
            sources = (pn or {}).get("sources") or []
            index = preview.get("source_index")
            if not pn or not isinstance(index, int) or not 0 <= index < len(sources):
                errors.append(f"view {view.get('id')} draws node {node.get('id')} with no PR record")
                continue
            source, shown = sources[index], node.get("source") or {}
            expected = {
                "code": preview.get("code"), "path": source.get("path"), "start": source.get("start_line"),
                "end": source.get("end_line"), "href": source.get("cursor_url") or source.get("github_url"),
            }
            for key, value in expected.items():
                if shown.get(key) != value:
                    errors.append(f"view {view.get('id')} node {node.get('id')} displays a different {key} than its PR record")
    return errors


def main() -> int:
    """Run validation and return a shell-friendly status code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=Path)
    parser.add_argument(
        "--source-repo",
        type=Path,
        help="Git repository used to verify exact embedded source excerpts",
    )
    parser.add_argument(
        "--source-ref",
        help="Optional ref; defaults to the embedded analyzed snapshot",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="enforce the explorer's semantic, source and presentation contract",
    )
    args = parser.parse_args()

    text = args.page.read_text(encoding="utf-8")
    built = _embedded(text)
    errors = _check_page(text, built)
    if args.strict and built is not None:
        errors.extend(_check_quality_contract(text, built))
        if args.source_repo is None:
            errors.append("strict validation requires --source-repo for source equality")
        elif isinstance(built.get("pr_model"), dict):
            errors.extend(_check_source_contract(built["pr_model"], args.source_repo.resolve(), args.source_ref))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("PR explorer validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
