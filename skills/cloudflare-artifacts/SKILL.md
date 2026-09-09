---
name: cloudflare-artifacts
description: Publish files or static browser artifacts to the user's Cloudflare artifact library and return verified public URLs and Markdown links. Use when sharing an artifact through Cloudflare, making a report or visualization accessible without a VPN, or attaching a hosted artifact link to a GitHub issue.
version: 1.0.0
---

# Cloudflare Artifacts

Publish completed artifacts to the existing Cloudflare library using the bundled
client. Viewing is public; uploading requires an upload-only publishing key.
Links have no automatic expiry and continue working when the publishing
machine is offline.

Resolve `<skill-root>` relative to this `SKILL.md`. The client needs Node.js 22
or newer and uses only built-in modules; no npm installation, Wrangler, browser
session, or Cloudflare account token is needed for routine uploads.

## Publish

1. Select the finished file or a folder containing `index.html` and its assets.
   Browser builds must use relative asset URLs. Use `--entry` for a different
   entry point. Confirm the selected content is within the user's authorized
   public-sharing scope; existing authorization is sufficient.
2. Use the host's publishing key through `ARTIFACT_PUBLISH_TOKEN_FILE` or a
   secret-store-injected `ARTIFACT_PUBLISH_TOKEN`. For a new host or missing key,
   read [references/credentials.md](references/credentials.md). Keep credentials
   out of arguments, artifact files, output, source control, and issue bodies.
3. Run the bundled client against the existing library:

   ```sh
   node "<skill-root>/scripts/publish.mjs" "/path/to/artifact" --title "Artifact title" --description "Short description"
   ```

   The default destination is `https://artifact-library.dm1681.workers.dev`.
   `ARTIFACT_PUBLISH_URL` or `--endpoint` can select a compatible service when
   the user explicitly requests another destination. Use that destination's key.
4. Require a zero exit code and JSON containing `verified: true`. The client
   uploads every registered file, completes the artifact, then fetches its
   public entry point without credentials and checks its SHA-256 checksum.
   Return the resulting `url` or `markdown` only after verification succeeds.
5. If the user authorized a comment on a specific GitHub issue, use the agent's
   existing GitHub tool or CLI to post the returned Markdown. Confirm the issue
   contains the link. Publishing alone does not authorize a GitHub comment.

## Retry and revisions

The client prints the artifact id to stderr before uploading. After a transient
failure, retry unchanged files with `--id <that-uuid>` to keep the same URL.
Use a new id for changed content; completed files cannot be overwritten or
deleted through the upload API.

On HTTP 401 or 403, resolve the publishing credential before retrying. On a
conflict, check the id, key, and input files. For other failures or unverified
output, preserve the id and report publishing as incomplete. Repeated failures
need diagnosis rather than new ids or automatic infrastructure changes.

## Artifact boundaries

The service accepts up to 256 files per artifact, 25 MiB per file, and 100 MiB
total. The client omits hidden files and `node_modules`, and rejects symlinks.
Choose a reviewed output folder; these exclusions are not a secret scanner.

HTML, CSS, JavaScript, images, PDFs, and downloadable files work. A local server,
filesystem link, or private network dependency will not become reachable by
uploading its frontend. Prepare a self-contained build before publishing.

The library appears at the endpoint's root. Artifacts receive immutable
`/a/<uuid>/` URLs and appear in its catalog after completion. Routine uploads
add individual artifacts; they do not redeploy or replace the library.
