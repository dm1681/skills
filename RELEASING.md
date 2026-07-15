# Releasing

The repository follows Semantic Versioning and is released as a single skills
collection.

## Prepare a release

1. Update `VERSION` to `MAJOR.MINOR.PATCH` without a `v` prefix.
2. Move the relevant `CHANGELOG.md` entries from `Unreleased` into a heading
   named `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD`.
3. Run the repository validator and tests.
4. Merge the version change to `main`.

## Publish

Use the **Release** workflow in GitHub Actions and enter the exact value from
`VERSION`. The workflow validates the repository, packages `.tar.gz` and `.zip`
archives, writes SHA-256 checksums, creates tag `vMAJOR.MINOR.PATCH`, and
publishes a GitHub release with generated notes.

Pushing a matching `v*` tag manually runs the same validation and packaging
path. A tag that does not exactly match `VERSION` fails before publishing.

## Verify

```sh
gh release view vMAJOR.MINOR.PATCH --repo dm1681/skills
gh release download vMAJOR.MINOR.PATCH --repo dm1681/skills --pattern 'SHA256SUMS'
```
