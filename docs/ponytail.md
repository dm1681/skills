# Ponytail provenance and integration

The core skill was already imported in collection commit `e3e5b18`. DIE-61
verified that import and added focused regression coverage; it does not install
or activate a plugin on the developer's machine.

## Pinned source

- Publisher: [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail).
- Commit: `9cc65d03aa2da1db7121b912d03596409ee340b8` (2026-10-08, tag `v5.1.0`).
- Source: `skills/ponytail/SKILL.md`; that upstream directory contains only this file.
- Normalized SHA256: `ba68ff26239c3c3b05b2a9a47ee0d9a6b93a69639a2555ec87a5d44bffaf2f0c`.
- [MIT license at the same commit](https://github.com/DietrichGebert/ponytail/blob/9cc65d03aa2da1db7121b912d03596409ee340b8/LICENSE),
  copyright 2026 DietrichGebert, copied to `skills/ponytail/LICENSE`.
  Normalized license SHA256: `fb1bc6909ac3ef82d5c22106e32ef682b0cff66788fa915fb9b53b15c9d2f3ab`.

Upstream entrypoint bytes are preserved except for the removable provenance
comment, following `install.VENDORED_SKILLS`. Hashes normalize line endings.
`agents/openai.yaml` is collection-authored discovery metadata. No companion
skills, hooks, MCP server, benchmark scripts, or executables are included.
Update upstream first, then re-sync the pinned files and hashes together.

## Vetting snapshot (2026-10-08)

Refreshed for the v5.1.0 re-sync (previous pin `356918e`, 2026-09-07; the
LICENSE is byte-identical across both). GitHub's repository API reported an
unarchived MIT repository, last pushed 2026-10-08, with 158,261 stars. This
indicates activity and adoption, not a security guarantee. The public
repository advisories endpoint returned no published advisories. An issue
search for security and malware reports opened since the previous snapshot
found nothing new that touches the core skill. Earlier reports still apply:

- [#735](https://github.com/DietrichGebert/ponytail/issues/735) reports malware in
  an unrelated lookalike fork. This import uses the named upstream and contains
  no binaries or installer scripts.
- [#199](https://github.com/DietrichGebert/ponytail/issues/199),
  [#200](https://github.com/DietrichGebert/ponytail/issues/200), and
  [#201](https://github.com/DietrichGebert/ponytail/issues/201) report MCP dependency,
  hook command quoting, and benchmark path-handling risks respectively. Those
  components are excluded; their reports were inspected, not reproduced here.
- [#823](https://github.com/DietrichGebert/ponytail/issues/823) concerns the core
  skill's instruction to leave one runnable check even for security paths.
  Upstream closed it on 2026-10-03 without merging the proposed fix (#849).
  v5 drops the "ONE runnable check, no frameworks" cap but still asks only for
  "one small test or an assert-based self-check" on money or security logic.
  Project-required validation and explicit task requirements still apply; the
  skill cannot waive them. This is a known instruction limitation, not a
  runtime exploit. The import remains byte-pinned rather than silently
  patching upstream instructions.

Integration treated upstream instructions as data and did not activate Ponytail.

## User path and validation

Run `./install.sh --skill ponytail` (Windows: `./install.ps1 --skill ponytail`),
or open `./install.ps1 --interactive` on Windows and select Ponytail under
YOUR SKILLS. It uses the existing installer and supports copy/link modes;
then explicitly ask the agent to use `ponytail`.

`tests/test_ponytail.py` checks exact package scope, provenance hashes, newline
normalization, drift detection, isolated copy/link installs, and repeat installs.
Dashboard coverage checks discovery and selection through the existing UI.
Real-install tests use temporary homes and disable live plugin status.
