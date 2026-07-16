# Changelog

All notable changes to this repository are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.0.0] - 2026-07-15

### Changed

- Converted the collection into a locked uv project with Python 3.12 as the
  development and launcher default.
- POSIX and PowerShell launchers now prefer `uv` and let it provision Python,
  while retaining direct system-Python fallbacks.
- CI and releases now sync and test the locked uv environment on macOS, Linux,
  and Windows; release archives include all uv project metadata.

## [1.0.0] - 2026-07-15

### Changed

- Running the installer without options in an interactive terminal now opens a
  confirmation-based setup wizard. Non-terminal and option-based invocations
  retain the existing non-interactive behavior.

### Added

- Interactive terminal setup for choosing installation scope, coding agents,
  skills, copy or link mode, and optional Graphify configuration.
- Responsive output that adapts to narrow terminals, with Unicode and color
  enhancements only when the terminal supports them.
- Review and confirmation screens, safe conflict backup prompts, and explicit
  `--interactive`, `--non-interactive`, and `--no-color` controls.

## [0.2.0] - 2026-07-15

### Added

- Optional `--graphify` installation: installs or upgrades the official
  `graphifyy` package with `uv` and registers Graphify for the selected coding
  agents using its current platform-specific CLI.

## [0.1.0] - 2026-07-15

### Added

- Initial `orchestrate-olympus` skill, including role prompts, review policy,
  recovery guidance, and checkpoint tooling.
- Cross-platform Python installer with POSIX and PowerShell launchers.
- Shared `.agents/skills` installation for Codex, Cursor, and GitHub Copilot,
  plus native Claude Code installation.
- CI validation, release archives, checksums, and tag/version enforcement.
