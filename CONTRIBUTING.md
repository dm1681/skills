# Contributing

## Add or update a skill

1. Put the skill in `skills/<skill-name>/` with a required `SKILL.md`.
2. Keep referenced scripts, examples, assets, and reference documents inside
   that skill directory and use relative paths.
3. Run `uv sync --locked`.
4. Run `uv run python scripts/validate_repo.py`.
5. Run `uv run python -m unittest discover -s tests -v`.
6. Add an entry under `Unreleased` in `CHANGELOG.md`.

The frontmatter `name` must match the directory name. Do not commit credentials,
task checkpoints, machine-local paths, or generated session state.

## Versioning

This repository is versioned as one collection. Skill additions and backwards-
compatible updates are minor releases; backwards-incompatible behavior or
installer changes are major releases; fixes are patch releases.
