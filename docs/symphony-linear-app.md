# Symphony's Linear app identity

Use an OAuth application named **Symphony**, with **Client credentials tokens**
enabled in Linear Settings → API → OAuth applications. This is a workspace app
identity, not another personal API key. If registration requires a redirect URL,
use `http://localhost:8766/oauth/callback`; client credentials do not use it. The service requests only `read,write`;
it does not request administration or change interactive Codex connections.

[Linear's client-credentials documentation](https://linear.app/developers/oauth-2-0-authentication#client-credentials-tokens)
describes app tokens, team access and secret rotation. Restrict the app's team
access in Linear to the teams it needs. No webhook or agent-session subscription
is needed for Symphony's existing polling workflow.

## Save and check

Run in a Linux/WSL terminal; both credential prompts are hidden:

```sh
python3 symphony_linear.py save --organization-id YOUR_LINEAR_WORKSPACE_UUID
python3 symphony_linear.py check
```

The default file is `~/.config/symphony/linear-app.json`, outside the repository,
with mode 0600. Its parent must be user-owned with mode 0700. Existing files are
preserved. Never paste secrets into an issue, chat, command argument or workflow.
`check` requests an app token and verifies `viewer.app` and the expected workspace;
it prints only the app identity and does not dispatch or mutate issues.

## Run

```sh
skills symphony start --project-dir /absolute/project --accept-preview
```

Use this standard command as the service's ExecStart. It invokes the app gateway
automatically; no service-specific Linear override is needed. `skills symphony
check` uses the same identity without starting workers. Stop an existing service
before replacing its launch command. Stopped projects remain stopped until
explicitly activated.

The launcher runs normal project readiness checks, then launches the pinned
upstream runtime. An authenticated loopback gateway supplies app authentication
to both scheduler queries and the injected `linear_graphql` tool. OAuth tokens
stay in gateway memory. A random local gateway key reaches only the controller;
the normal worker launcher strips it before starting Codex. The gateway renews
the token before expiry and retries once on HTTP 401. It does not retry ambiguous
network failures or rate-limit responses, and never falls back to personal auth.

App-mode workers disable personal app connectors and refuse to launch if MCP
discovery still exposes Linear or the personal apps server. They are instructed
to use only `linear_graphql` for Linear, including comment/status readback.
This is an identity-routing guard, not a new operating-system security boundary.
The user's interactive connections remain unchanged.

The runtime uses a temporary snapshot of the managed workflow with the gateway
endpoint injected. Regenerating the source workflow takes effect on the next
service start; it does not hot-reload into that snapshot. No tokens are written
into the snapshot. The launcher forwards SIGTERM/SIGINT to the runtime group.

## Verify migration

Verify a fresh app-authenticated comment and a status change on an explicitly
chosen test issue, then fetch the comment author and issue history. Record their
app identity before declaring migration complete. Existing comments/actions retain
their original authorship. An app cannot necessarily edit workpads originally
created by a human; if Linear refuses, preserve the old workpad and explicitly
hand off to one new app-owned workpad rather than using personal credentials.
