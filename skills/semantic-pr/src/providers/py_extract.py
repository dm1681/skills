#!/usr/bin/env python3
"""Stdlib-`ast` symbol extractor for the semantic-pr Python provider.

Reads a job on stdin: {"repo": "<abs>", "files": [{"file": "<rel>", "ranges": [[a,b],...]}]}
and prints {"symbols": [...]} on stdout. A symbol is a function/method/class whose body
overlaps a changed line-range. Positions are pyright/LSP-native (0-based line + char) so the
Node side can query `textDocument/references` at the name identifier.

No third-party deps — pairs with pyright (bundled typeshed) for precise edge resolution.
"""
import ast
import json
import os
import sys

SHORT = {"function": "fn", "method": "method", "class": "class"}


def name_char(line_text: str, node: ast.AST) -> int:
    """0-based column of the name identifier on the def/class line.

    Search from the keyword's column so extra whitespace (`def   foo`) is tolerated.
    """
    try:
        return line_text.index(node.name, node.col_offset)
    except ValueError:
        return node.col_offset


def collect(source: str, rel: str):
    """All def/method/class nodes in a file, with spans + name positions."""
    src_lines = source.splitlines()
    tree = ast.parse(source)
    out = []

    def visit(node, class_stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                is_class = isinstance(child, ast.ClassDef)
                kind = "class" if is_class else ("method" if class_stack else "function")
                qual = ".".join(class_stack + [child.name])
                line = child.lineno            # 1-based def/class line (post-decorators, py3.8+)
                end = getattr(child, "end_lineno", line)
                lt = src_lines[line - 1] if line - 1 < len(src_lines) else ""
                seg = ast.get_source_segment(source, child) or child.name
                out.append({
                    "id": f"{rel}::{qual}@{line}",
                    "name": qual,
                    "kind": kind,
                    "shortKind": SHORT[kind],
                    "file": rel,
                    "line": line,
                    "endLine": end,
                    "nameLine": line - 1,             # 0-based, for LSP
                    "nameChar": name_char(lt, child),  # 0-based, for LSP
                    "snippet": seg[:500],
                })
                visit(child, class_stack + [child.name] if is_class else class_stack)
            else:
                visit(child, class_stack)

    visit(tree, [])
    return out


def innermost(syms, line):
    """The tightest def/class/method whose span contains `line` (mirrors ts-morph's
    `enclosingNamed`: one symbol per changed line, the innermost). `syms` is innermost-first."""
    for sym in syms:
        if sym["line"] <= line <= sym["endLine"]:
            return sym
    return None


def main():
    job = json.load(sys.stdin)
    repo = job["repo"]
    result = []
    seen = set()
    for entry in job["files"]:
        rel = entry["file"]
        ranges = entry["ranges"]
        path = os.path.join(repo, rel)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            continue
        try:
            syms = collect(source, rel)
        except SyntaxError:
            continue  # tolerate a non-parsing diff side, like tree-sitter would
        # innermost-first so `innermost()` returns the tightest enclosing symbol
        syms.sort(key=lambda s: -s["line"])
        for a, b in ranges:
            for line in range(a, b + 1):
                sym = innermost(syms, line)
                if sym and sym["id"] not in seen:
                    seen.add(sym["id"])
                    result.append(sym)
    json.dump({"symbols": result}, sys.stdout)


if __name__ == "__main__":
    main()
