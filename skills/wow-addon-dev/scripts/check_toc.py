#!/usr/bin/env python3
"""Validate a World of Warcraft addon folder's .toc manifest.

Usage:
    python check_toc.py path/to/AddOns/MyAddon

Catches the manifest mistakes that make an addon silently fail to load: a .toc
base name that does not match its folder, a missing or malformed Interface
version, listed files that do not exist on disk, and SavedVariables names that
are not valid Lua identifiers.

It cannot tell you whether the Interface number is current. Get that in-game
with: /dump select(4, GetBuildInfo())
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FLAVOR_SUFFIXES = (
    "_Mainline",
    "_Standard",
    "_Vanilla",
    "_Classic",
    "_TBC",
    "_Wrath",
    "_Cata",
    "_Mists",
)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INTERFACE_VALUE = re.compile(r"^\d{5,6}$")
MAX_LINE = 1024


def parse(text):
    """Return (directives, file_entries) from a .toc body."""
    directives = {}
    files = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("##"):
            body = line[2:]
            if ":" in body:
                key, value = body.split(":", 1)
                directives[key.strip()] = (value.strip(), number)
            continue
        if line.startswith("#"):
            continue
        files.append((line, number))
    return directives, files


def check_interface(directives, errors):
    entry = directives.get("Interface")
    if entry is None:
        errors.append("no '## Interface:' directive - the addon will not load")
        return
    value, number = entry
    for part in value.split(","):
        part = part.strip()
        if not INTERFACE_VALUE.match(part):
            errors.append(
                "line %d: '%s' is not a valid interface version "
                "(expected 5-6 digits, e.g. 120007)" % (number, part)
            )


def check_saved_variables(directives, errors):
    for key in ("SavedVariables", "SavedVariablesPerCharacter"):
        entry = directives.get(key)
        if entry is None:
            continue
        value, number = entry
        for name in value.split(","):
            name = name.strip()
            if not IDENTIFIER.match(name):
                errors.append(
                    "line %d: %s entry '%s' is not a valid Lua global name"
                    % (number, key, name)
                )


def check_files(root, files, errors):
    for entry, number in files:
        # Strip a trailing per-line conditional such as "[AllowLoadGameType mainline]".
        path_part = entry.split("[")[0].strip() if entry.endswith("]") else entry
        if "[" in path_part:
            # Path variables like [Family]\File.lua resolve at load time; skip.
            continue
        relative = path_part.replace("\\", "/")
        if not (root / relative).is_file():
            errors.append("line %d: listed file does not exist: %s" % (number, path_part))


def check(root):
    errors = []
    warnings = []

    if not root.is_dir():
        return ["not a directory: %s" % root], []

    tocs = sorted(root.glob("*.toc"))
    if not tocs:
        return ["no .toc file in %s" % root], []

    expected = root.name
    accepted = {expected.lower()}
    for suffix in FLAVOR_SUFFIXES:
        accepted.add((expected + suffix).lower())

    for toc in tocs:
        if toc.stem.lower() not in accepted:
            errors.append(
                "%s: base name must equal the folder name '%s' "
                "(optionally with a flavor suffix)" % (toc.name, expected)
            )

        text = toc.read_text(encoding="utf-8-sig", errors="replace")
        for number, raw in enumerate(text.splitlines(), start=1):
            if len(raw) > MAX_LINE:
                warnings.append(
                    "%s line %d: longer than %d characters; the client truncates it"
                    % (toc.name, number, MAX_LINE)
                )

        directives, files = parse(text)
        check_interface(directives, errors)
        check_saved_variables(directives, errors)
        check_files(root, files, errors)

        if not files:
            warnings.append("%s: lists no files to load" % toc.name)
        for key in ("Title", "Version"):
            if key not in directives:
                warnings.append("%s: no '## %s:' directive" % (toc.name, key))

    return errors, warnings


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    root = Path(argv[1]).resolve()
    errors, warnings = check(root)

    for warning in warnings:
        print("WARN: %s" % warning, file=sys.stderr)
    for error in errors:
        print("ERROR: %s" % error, file=sys.stderr)

    if errors:
        return 1
    print("%s: manifest OK (%d warning(s))" % (root.name, len(warnings)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
