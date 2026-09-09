# Configure an agent host

The client uses an artifact publishing key, not a Cloudflare API token.
Publishing keys can create and complete artifacts but cannot delete them,
replace completed files, edit Workers, or administer the Cloudflare account.
They have no automatic expiry and can be revoked individually by the library's
administrator. Read access is public and needs no key.

## Existing host

Use the host's configured secret store or credential file. The client reads
`ARTIFACT_PUBLISH_TOKEN` first, then the UTF-8 file named by
`ARTIFACT_PUBLISH_TOKEN_FILE`. The file contains just the publishing credential;
its value must stay outside the repository and the selected artifact folder.
POSIX hosts should restrict it to the current user; Windows hosts should use
equivalent file ACLs or a managed secret store.

Set the file-path environment variable without putting the credential itself in
a command:

```sh
export ARTIFACT_PUBLISH_TOKEN_FILE="/path/to/protected/publisher-token"
```

```powershell
$env:ARTIFACT_PUBLISH_TOKEN_FILE = 'C:\path\to\protected\publisher-token'
```

The command examples use placeholder paths; resolve the host's actual secret
location from its configuration. The skill carries no credential and does not
depend on a particular user's home directory or a previous agent task.

## New host or CI

Ask the library administrator to provision an upload-only key through the
host's secret store. Prefer a distinct key per host for independent revocation.
Install or copy this entire skill folder so `scripts/publish.mjs` and
`scripts/protocol.mjs` remain adjacent. The publisher needs Node.js 22 or newer;
the skills installer itself remains Python-based and needs no Node.js.

For GitHub Actions, make the publishing key available as the repository or
environment secret `ARTIFACT_PUBLISH_TOKEN`, then expose it only to the publish
step through its `env` mapping. GitHub comments use separate GitHub credentials
and permissions. Adding this skill does not create repository secrets or grant
issue-write access.

Creating a new key or revoking one requires an administrator to update the
existing Worker's `PUBLISH_KEY_HASHES` configuration. This publishing skill
does not grant that administration permission. Resolve missing credentials
without creating new Cloudflare resources or changing the library's access.
