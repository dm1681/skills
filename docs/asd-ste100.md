# ASD-STE100 skill

Source: [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill),
commit `7d4a135a199a5d7447c4886bcd7ffe742a627bc9`, upstream version 0.4.0.
The MIT license is included. The upstream entrypoint is unchanged except for a
removable provenance comment. Its existing version is upstream metadata, not a
collection-owned version. The vendor hash covers that metadata too.

Included: SKILL.md, LICENSE, writing-rules reference, both example files and the
stdlib-only, read-only Python linter. Supporting-file hashes are recorded in
[asd-ste100-files.json](asd-ste100-files.json) and checked by the integration test.
Re-sync the upstream files, commit and hashes together. The official ASD dictionary
is not bundled; this skill does not guarantee formal STE compliance.

Install with `./install.sh --skill asd-ste100`, or select it in the skills dashboard.
It also supports the installer's normal `--target` and `--scope` options.

Symphony provisions it for fresh and resumed workers. The workflow requires
STE-flavored mode for replies, workpads, PR descriptions and final reports.
Required evidence, uncertainty and checklist structure take precedence over
shortening. Existing active sessions receive new instructions on their next pickup.

Run the optional linter with:

```sh
python3 skills/asd-ste100/scripts/ste-lint.py --selftest
python3 skills/asd-ste100/scripts/ste-lint.py --json document.md
```

The linter reads text and reports heuristic findings; it does not edit files.
