#!/usr/bin/env python3
"""Merge changes into a live diagram's state file, atomically.

A page built from a model with `"live": {"url": "<state file>"}` polls that
file and applies it with `diagram.update`. This script is the safe way for an
agent or a program to write it: it merges into what is there, refuses the
fields that would move the layout, checks ids against the model when given
one, and replaces the file in one step so the page never reads half a write.

    update_state.py state.json --node fetch status=running "summary=Fetching 3 of 10"
    update_state.py state.json --edge "fetch>parse" label=retrying --model pipeline.json
    update_state.py state.json --reset

A VALUE is parsed as JSON when it can be (`3`, `true`, `null`, `["a"]`,
`{"k": 1}`) and kept as a string otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

FIXED = {"nodes": {"id", "group", "step", "drill"}, "edges": {"from", "to"}}


def parse_pairs(table: str, entry: list[str]) -> tuple[str, dict]:
    """Turn `ID KEY=VALUE ...` into (id, fields), or raise ValueError."""
    if len(entry) < 2:
        raise ValueError(f"--{table[:-1]} needs an id and at least one KEY=VALUE")
    target, fields = entry[0], {}
    if table == "edges" and ">" not in target:
        raise ValueError(f"edge {target!r} must be written FROM>TO")
    for pair in entry[1:]:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"{pair!r} is not KEY=VALUE")
        if key in FIXED[table]:
            raise ValueError(f"{table[:-1]} {target}: {key} places the element and cannot change live")
        try:
            fields[key] = json.loads(raw)
        except json.JSONDecodeError:
            fields[key] = raw
    return target, fields


def model_ids(model_path: Path) -> dict[str, set[str]]:
    """Every node id and FROM>TO edge key across a model's views."""
    model = json.loads(model_path.read_text(encoding="utf-8"))
    ids: dict[str, set[str]] = {"nodes": set(), "edges": set()}
    for view in model.get("views", []):
        ids["nodes"].update(n.get("id") for n in view.get("nodes", []))
        ids["edges"].update(f"{e.get('from')}>{e.get('to')}" for e in view.get("edges", []))
    return ids


def write_atomic(path: Path, state: dict) -> None:
    """Replace `path` in one step; a reader sees the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("state", type=Path, help="state file the page polls (created if missing)")
    parser.add_argument("--node", nargs="+", action="append", default=[], metavar="ID KEY=VALUE",
                        help="fields to set on one node; repeat for more nodes")
    parser.add_argument("--edge", nargs="+", action="append", default=[], metavar="FROM>TO KEY=VALUE",
                        help="fields to set on one edge; repeat for more edges")
    parser.add_argument("--model", type=Path, help="diagram model to check ids against")
    parser.add_argument("--reset", action="store_true", help="start from an empty state before applying changes")
    args = parser.parse_args(argv)

    problems: list[str] = []
    changes: dict[str, dict[str, dict]] = {"nodes": {}, "edges": {}}
    for table, entries in (("nodes", args.node), ("edges", args.edge)):
        for entry in entries:
            try:
                target, fields = parse_pairs(table, entry)
            except ValueError as exc:
                problems.append(str(exc))
                continue
            changes[table].setdefault(target, {}).update(fields)
    if args.model:
        known = model_ids(args.model)
        for table in ("nodes", "edges"):
            for target in changes[table]:
                if target not in known[table]:
                    problems.append(f"{args.model} has no {table[:-1]} {target!r}")
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    state: dict = {"nodes": {}, "edges": {}}
    if args.state.exists() and not args.reset:
        try:
            state = json.loads(args.state.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"error: {args.state} is not valid JSON ({exc}); fix it or pass --reset", file=sys.stderr)
            return 1
    for table in ("nodes", "edges"):
        bucket = state.setdefault(table, {})
        for target, fields in changes[table].items():
            bucket.setdefault(target, {}).update(fields)
    write_atomic(args.state, state)
    count = sum(len(changes[t]) for t in changes)
    print(f"updated {args.state}: {count} element(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
