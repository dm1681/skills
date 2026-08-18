#!/usr/bin/env python3
"""Validate a source-linked interactive changeset explorer."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _check_fragment(text: str) -> list[str]:
    """Return validation errors for an inline visualization fragment."""
    errors: list[str] = []

    for tag in ("doctype", "html", "head", "body"):
        if re.search(rf"<\s*/?\s*{tag}\b", text, re.IGNORECASE):
            errors.append(f"fragment contains forbidden <{tag}> markup")

    if not re.search(r'<div\s+id="[^"]+"', text):
        errors.append("fragment has no root div with a unique id")
    if "document.getElementById(" not in text:
        errors.append("script does not select its root with getElementById")
    if "document.currentScript" in text:
        errors.append("script derives its root from document.currentScript")

    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket"):
        if forbidden in text:
            errors.append(f"fragment contains forbidden network API: {forbidden}")

    if "data-p54-node" not in text and "data-pr-node" not in text:
        errors.append("fragment has no interactive changeset flow nodes")
    if "detail-sources" not in text:
        errors.append("fragment has no selected-node source-link area")

    has_github_lines = bool(re.search(r"github\.com/.+?#L\d+", text))
    has_cursor_lines = bool(re.search(r"cursor://file/.+?:\d+", text))
    has_dynamic_lines = bool(re.search(r"#L\d+", text))
    if not (has_github_lines or has_cursor_lines or has_dynamic_lines):
        errors.append("fragment has no line-anchored code references")

    if "cursor://file/" in text:
        static_target = bool(
            re.search(
                r'<a[^>]+href="cursor://file/[^"]+"[^>]+target="_blank"',
                text,
                re.IGNORECASE,
            )
        )
        has_dynamic_links = "document.createElement(\"a\")" in text
        dynamic_target = "link.target = \"_blank\"" in text
        if not static_target and not has_dynamic_links:
            errors.append("Cursor links must use target=_blank")
        if has_dynamic_links and not dynamic_target:
            errors.append("dynamic Cursor links must set target=_blank")

    return errors


def _embedded_model(text: str) -> dict[str, Any] | None:
    """Return a JSON model embedded by the standard explorer template."""
    match = re.search(
        r"const model = (\{.*\});\s*const nodes =",
        text,
        re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


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


def _check_quality_contract(text: str) -> list[str]:
    """Return strict semantic and presentation contract errors."""
    errors: list[str] = []

    markers = {
        "orientation block": "data-pr-summary",
        "analyzed snapshot": 'data-role="pr-snapshot"',
        "change-status legend": "data-change-legend",
        "execution branches": "data-pr-branch",
        "branch convergence": "data-pr-convergence",
        "runtime edge records": "data-pr-edge",
        "edge transfer metadata": "data-transfer",
        "node change-status metadata": "data-change-status",
        "rich tooltip container": "data-pr-rich-tooltip",
        "hover path emphasis": "dataset.pathHover",
        "node code previews": "code_preview",
        "syntax highlighting": "appendHighlightedCode",
        "Catppuccin syntax theme": "--ctp-base",
        "pointer-enterable tooltip": "pointer-events: auto",
        "delayed tooltip dismissal": "scheduleRichTooltipHide",
        "tooltip source link": "prx-tooltip-source",
    }
    marker_aliases = {
        "analyzed snapshot": ("Analyzed snapshot",),
        "change-status legend": ("p54-change-legend",),
        "execution branches": ("dataset.prBranch", "p54-lane"),
        "runtime edge records": ("dataset.prEdge", "p54-edge"),
        "edge transfer metadata": ("dataset.transfer", "data-tooltip=\"DTO"),
        "node change-status metadata": ("dataset.changeStatus",),
        "rich tooltip container": ("p54-rich-tooltip",),
        "hover path emphasis": ("dataset.p54HoverMode",),
    }
    for label, marker in markers.items():
        aliases = marker_aliases.get(label, ())
        if marker not in text and not any(alias in text for alias in aliases):
            errors.append(f"strict explorer is missing {label}")

    required_visual_guards = {
        "scoped code styling": re.compile(r"\.[\w-]*node\s+code\s*\{"),
        "semantic identifier wrapping": re.compile(
            r"<wbr>|createElement\([\"']wbr[\"']\)"
        ),
        "normal word breaking": re.compile(r"word-break:\s*normal"),
        "normal overflow wrapping": re.compile(r"overflow-wrap:\s*normal"),
        # Tooltip prose must reach the card through the backtick-to-<code>
        # renderer, whether it is written straight into the card or through
        # the line-preserving prose wrapper.
        "rich tooltip code rendering": re.compile(
            r"renderCodeAware\(\s*richTooltip|renderTooltipProse\("
        ),
        # Tooltip prose is authored as lines; collapsing them runs bullet
        # lists together on one line.
        "line-preserving tooltip prose": re.compile(
            r"\.[\w-]*tooltip-copy\s*\{[^}]*white-space:\s*pre-line",
            re.DOTALL,
        ),
        "rich tooltip code styling": re.compile(
            r"\.[\w-]*rich-tooltip[^{]*code\s*\{"
        ),
        "code preview block": re.compile(r"\.[\w-]*code-preview\s*\{"),
        "Catppuccin Mocha code surface": re.compile(
            r"--ctp-base:\s*#1e1e2e\b"
        ),
        "local syntax tokenizer": re.compile(r"function\s+syntaxPattern\("),
        "pointer-enterable rich tooltip": re.compile(
            r"\.[\w-]*rich-tooltip\s*\{[^}]*pointer-events:\s*auto",
            re.DOTALL,
        ),
        "tooltip hover persistence": re.compile(
            r"richTooltip\.addEventListener\([\"']pointerenter[\"']"
        ),
        # The gap between trigger and card has to belong to the card, or
        # whatever sits under it steals the pointer on the way in.
        "tooltip hover bridge": re.compile(
            r"\.[\w-]*rich-tooltip\[data-prx-side[^{]*\]::before\s*\{"
        ),
        # A trigger merely swept over en route to an open card must not take
        # the card over before the pointer settles on it.
        "tooltip trigger settle delay": re.compile(
            r"TOOLTIP_SWAP_DELAY_MS"
        ),
        "tooltip source target": re.compile(
            r"sourceLabel\.target\s*=\s*[\"']_blank[\"']"
        ),
        # aria-pressed alone leaves stepping invisible to sighted readers.
        "selected node styling": re.compile(
            r"\.[\w-]*node\[aria-pressed=\"true\"\]"
        ),
        # A changed node must read as changed before the delta view is on.
        "change marker outside the delta view": re.compile(
            r":not\(\[data-change-status=\"context\"\]\)::(?:after|before)"
        ),
        # A degraded build has to explain itself to whoever reads the page.
        "degraded build notice region": re.compile(
            r"data-role=\"notices\""
        ),
    }
    for label, pattern in required_visual_guards.items():
        if not pattern.search(text):
            errors.append(f"strict explorer is missing {label}")

    for forbidden in (
        r"word-break:\s*break-all",
        r"overflow-wrap:\s*anywhere",
        r"data-tooltip=\"[^\"]*`",
    ):
        if re.search(forbidden, text):
            errors.append(
                f"strict explorer contains unsafe identifier wrapping: {forbidden}"
            )

    # The explorer is dark-only: one palette means an excerpt reads the same
    # for every reader, whatever their OS is set to. Scoped to stylesheets so
    # a changeset that legitimately discusses theming in prose still validates.
    stylesheets = "\n".join(
        re.findall(r"<style[^>]*>(.*?)</style>", text, re.DOTALL | re.IGNORECASE)
    )
    for label, pattern in (
        ("a light-dark() palette", r"light-dark\s*\("),
        ("a prefers-color-scheme block", r"@media[^{]*prefers-color-scheme"),
    ):
        if re.search(pattern, stylesheets):
            errors.append(f"strict explorer reintroduces {label}")

    model = _embedded_model(text)
    if model is None:
        errors.append("strict explorer has no parseable embedded data model")
        return errors

    summary = model.get("summary", {})
    if not model.get("pr", {}).get("head_sha"):
        errors.append("embedded snapshot metadata is missing head_sha")
    for field in (
        "goal",
        "old_to_new",
        "ownership_chain",
        "payoff",
        "residual_debt",
    ):
        if not summary.get(field):
            errors.append(f"embedded summary is missing {field}")

    node_ids = {node.get("id") for node in model.get("nodes", [])}
    for node in model.get("nodes", []):
        node_id = node.get("id")
        if node.get("change_status") not in {
            "added",
            "modified",
            "removed",
            "context",
        }:
            errors.append(
                f"node {node_id} has invalid or missing change_status"
            )
        sources = node.get("sources") or []
        if not sources:
            errors.append(f"node {node_id} has no source references")
        preview = node.get("code_preview")
        if not isinstance(preview, dict):
            errors.append(f"node {node_id} has no code_preview")
            continue
        for field in ("language", "source_label", "source_index", "code"):
            if field not in preview:
                errors.append(
                    f"node {node_id} code_preview is missing {field}"
                )
        source_index = preview.get("source_index")
        if (
            not isinstance(source_index, int)
            or source_index < 0
            or source_index >= len(sources)
        ):
            errors.append(
                f"node {node_id} code_preview source_index does not resolve"
            )
        code = preview.get("code")
        if not isinstance(code, str) or not code.strip():
            errors.append(f"node {node_id} code_preview has no code")
        elif len(code.splitlines()) > 12:
            errors.append(
                f"node {node_id} code_preview exceeds 12 lines"
            )

    actual_handoffs: set[tuple[str, str]] = set()
    for edge in model.get("edges", []):
        pair = (edge.get("from"), edge.get("to"))
        actual_handoffs.add(pair)
        if edge.get("change_status") not in {
            "added",
            "modified",
            "removed",
            "context",
        }:
            errors.append(
                f"edge {pair[0]} -> {pair[1]} has invalid or missing "
                "change_status"
            )
        if not edge.get("transfer") and not edge.get("transformation"):
            errors.append(
                f"edge {pair[0]} -> {pair[1]} has no transfer or transformation"
            )
        if not edge.get("evidence"):
            errors.append(f"edge {pair[0]} -> {pair[1]} has no evidence")

    missing_handoffs = _expected_handoffs(model).difference(actual_handoffs)
    for source, destination in sorted(missing_handoffs):
        errors.append(f"rendered path lacks edge {source} -> {destination}")

    for branch in model.get("branches", []):
        path = branch.get("path", [])
        if len(path) < 2:
            errors.append(
                f"branch {branch.get('id')} has fewer than two runtime nodes"
            )
        unknown = set(path).difference(node_ids)
        if unknown:
            errors.append(
                f"branch {branch.get('id')} references unknown nodes: "
                + ", ".join(sorted(unknown))
            )

    return errors


def _title_identifies_changeset(text: str) -> bool:
    """Return whether the standalone title names the reviewed changeset.

    A pull request is identified by its number, but the same explorer also
    describes a ref comparison, a commit range, or a snapshot of working-tree
    changes, so any unambiguous changeset anchor counts.
    """
    title = re.search(r"<title>([^<]*)</title>", text, re.IGNORECASE)
    if title is None:
        return False
    heading = title.group(1)
    return bool(
        # a pull request number
        re.search(r"\bPR\s+\d+", heading, re.IGNORECASE)
        # an abbreviated or full commit SHA; the digit keeps an ordinary
        # a-f word such as "deadbeef" from passing as an anchor
        or re.search(r"\b(?=[0-9a-f]{7,40}\b)[0-9a-f]*\d[0-9a-f]*\b", heading, re.IGNORECASE)
        # a ref comparison or commit range, such as main...feature
        or re.search(r"\S\.{2,3}\S", heading)
        # an explicitly uncommitted changeset
        or re.search(r"working tree|staged|uncommitted", heading, re.IGNORECASE)
    )


def _check_standalone(
    text: str,
    fragment_has_cursor: bool,
    strict: bool,
) -> list[str]:
    """Return validation errors for a rendered standalone page."""
    errors: list[str] = []

    if strict and not _title_identifies_changeset(text):
        errors.append(
            "strict standalone title does not identify the changeset "
            "(PR number, ref range, snapshot SHA, or working tree)"
        )

    csp_match = re.search(
        r'<meta[^>]+http-equiv="Content-Security-Policy"'
        r'[^>]+content="([^"]+)"',
        text,
        re.IGNORECASE,
    )
    csp = csp_match.group(1) if csp_match else ""
    if "script-src 'unsafe-inline'" not in csp:
        errors.append("standalone CSP blocks the explorer's inline script")
    if "style-src 'unsafe-inline'" not in csp:
        errors.append("standalone CSP blocks the explorer's inline styles")

    has_base_styles = (
        "data-pr-explorer-base" in text
        or "--font-sans:" in text
    )
    if not has_base_styles:
        errors.append("standalone page omits the explorer base stylesheet")

    has_static_target = (
        'target="_blank"' in text
        or "target=&quot;_blank&quot;" in text
    )
    has_dynamic_target = (
        'link.target = "_blank"' in text
        or "link.target = &quot;_blank&quot;" in text
    )
    if fragment_has_cursor and not (has_static_target or has_dynamic_target):
        errors.append("rendered Cursor links do not target a new context")

    if re.search(
        r"<main\b[^>]*\bdata-pr-explorer-standalone\b",
        text,
        re.IGNORECASE,
    ):
        return errors

    sandbox_match = re.search(r'<iframe[^>]+sandbox="([^"]*)"', text)
    if not sandbox_match:
        errors.append(
            "standalone page is neither a direct explorer nor a sandboxed iframe"
        )
        return errors

    permissions = set(sandbox_match.group(1).split())
    if "allow-scripts" not in permissions:
        errors.append("standalone iframe does not allow scripts")
    if fragment_has_cursor and "allow-popups" not in permissions:
        errors.append("standalone iframe blocks Cursor popup links")
    if fragment_has_cursor and "allow-popups-to-escape-sandbox" not in permissions:
        errors.append("standalone iframe traps Cursor popup links in the sandbox")

    return errors


def main() -> int:
    """Run validation and return a shell-friendly status code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("fragment", type=Path)
    parser.add_argument("--standalone", type=Path)
    parser.add_argument(
        "--source-repo",
        type=Path,
        help="Git repository used to verify exact embedded source excerpts",
    )
    parser.add_argument(
        "--source-ref",
        help="Optional ref; defaults to the embedded analyzed SHA",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="enforce the reusable explorer's semantic and layout contract",
    )
    args = parser.parse_args()

    fragment_text = args.fragment.read_text(encoding="utf-8")
    errors = _check_fragment(fragment_text)
    if args.strict:
        errors.extend(_check_quality_contract(fragment_text))
        model = _embedded_model(fragment_text)
        if args.source_repo is None:
            errors.append(
                "strict validation requires --source-repo for source equality"
            )
        elif model is not None:
            errors.extend(
                _check_source_contract(
                    model,
                    args.source_repo.resolve(),
                    args.source_ref,
                )
            )

    if args.standalone:
        standalone_text = args.standalone.read_text(encoding="utf-8")
        errors.extend(
            _check_standalone(
                standalone_text,
                fragment_has_cursor="cursor://file/" in fragment_text,
                strict=args.strict,
            )
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("Explorer validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
