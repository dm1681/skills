# Optional Olympus integration

Olympus (`dm1681/Olympus`) is the continuity record for work across machines.
The ability to *talk* to it normally lives inside that checkout: the MCP
adapter is code under `apps/mcp`, the bearer token sits in its untracked
settings, and the reporting skill is one of its `.claude/skills`. A session in
any other repository therefore has no adapter, no credential, and no skill —
the reporting step silently does not exist outside one directory.

`--olympus` closes that gap for one machine:

```sh
./install.sh --olympus
./install.sh --olympus --olympus-path ~/code/Olympus
./install.sh --olympus --olympus-token "$OLYMPUS_AGENT_TOKEN"
./install.sh --olympus --dry-run          # print every write, change nothing
```

It does two things:

1. **Registers the adapter at user scope** — an `olympus` entry under
   `mcpServers` in `~/.claude.json`, with an **absolute** path to the
   checkout's built `apps/mcp/dist/index.js`, `OLYMPUS_BASE_URL`, and
   `OLYMPUS_AGENT_TOKEN` when one was resolved. User scope is the point: any
   repository, in any working directory, finds the adapter.
2. **Installs `olympus-report-progress`** into the roots `--agent` and
   `--scope` resolve, through the same `install_one` path as everything else.
   It is recorded in the install receipt with `origin: olympus`, so
   `skills status`, `skills doctor`, and `skills uninstall` all see it.

The skill is **not vendored into this repository**. Its source of truth is the
Olympus checkout, next to the API it calls; a copy here would be a second
version of it to keep honest.

`olympus-start-task` is deliberately left out. Unlike `olympus-report-progress`
it is not self-contained — it reads Olympus's own `docs/`, which are not there
in another repository — so installing it machine-wide would hand every session
a skill that cannot complete outside one directory.

## Finding the checkout

The adapter is code in a checkout rather than a published package, so the
installer needs a path. In order:

1. `--olympus-path PATH`
2. the `OLYMPUS_CHECKOUT` environment variable
3. the conventional locations: `~/projects/olympus`, `~/projects/Olympus`,
   `~/olympus`, `~/Olympus`

Every candidate must contain `apps/mcp` before it is accepted. A path you
*named* that fails that check is an error rather than a fall-through to the
probe, so a typo does not silently register somebody else's directory. Finding
nothing at all names both the flag and the variable.

## The build preflight

`dist/` is gitignored, so a fresh clone has no adapter until it is built. A
registration pointing at a missing `dist/index.js` fails at MCP connect time,
where the error names neither this installer nor the missing file and every
`olympus_*` tool is simply absent. So the installer checks first and, when the
adapter is missing, prints the fix:

```sh
pnpm build      # in the Olympus checkout
```

Nothing here connects to Olympus. A preflight that dialled the server would
hang on exactly the machines that need this most — see the network caveat
below — so the base URL is printed for you to judge instead.

## The token

`OLYMPUS_AGENT_TOKEN` has been enforced since 2026-08-13: every
`/api/agent/v1` write without it is refused with `401 UNAUTHORIZED`. Resolution
order:

1. `--olympus-token VALUE`
2. the `OLYMPUS_AGENT_TOKEN` environment variable
3. the checkout's `.claude/settings.local.json` — any `env` block in it, parsed
   defensively; anything unexpected means "no token", never an error
4. none

With none, the install still happens and prints a prominent warning saying what
will fail and how to fix it. **Rotation is a re-run**: the same command with the
new token replaces the entry.

Prefer the environment variable over the flag — a command line lands in shell
history. The token is written to `~/.claude.json` and nowhere else: never into
this repository, never into an install receipt, and never into anything the
installer prints. The pre-write backup of `~/.claude.json` is created `0600`,
as is a `~/.claude.json` this installer creates from nothing.

## What the merge guarantees

`~/.claude.json` is yours and holds a great deal besides MCP servers, so:

- **Absent** — created, with just the one server in it.
- **Present and parseable** — every other key and every other `mcpServers`
  entry is preserved; only `olympus` is written. An existing `olympus` entry is
  replaced, which is the rotation path above.
- **Present and unparseable** — the run **refuses** and changes nothing. A
  missing comma is not permission to discard the rest of your configuration.
- **Every write is backed up first**, by copy, into
  `~/.skills-backups/claude-config/`, following the same convention as every
  other file this collection displaces.

## Removal

```sh
skills uninstall --olympus                  # the MCP registration
./install.sh --uninstall --olympus          # the same, without the `skills` command
skills uninstall olympus-report-progress    # the skill, the ordinary way
```

Removal is the mirror of the merge: the same parse refusal, the same backup,
and only the `olympus` entry goes — every other server stays. Removing twice is
not an error. The skill is removed by name through the generic ledger path,
with the same backup and restore guarantees as any other skill, so there is no
second removal path here to keep honest.

## Caveats worth reading before you rely on it

**Repositories with no Olympus Project.** Session Updates are Project-scoped
and need a `projectId`. Only some repositories have an Olympus Project, so
reporting from an arbitrary one may have nowhere to land. The skill resolves
the Project and **asks** rather than inventing one — it does not create a
Project on your behalf, and it does not move a Task's state because of what a
session did.

**Machines off the meshnet.** `OLYMPUS_BASE_URL` defaults to
`http://hades.nord:4317`, which resolves only on that private network (LAN
fallback `http://192.168.0.52:4317`). Reaching Olympus from outside is blocked
on `dm1681/Olympus#69`. The installer prints the URL it registered and this
caveat, and never tries the connection, so an off-network machine registers
in a second instead of hanging. Point it somewhere else with `--olympus-url`,
for example `http://127.0.0.1:4317` when the server runs locally.

## Opt into the habit

The tools are one half; the instruction to use them is the other, and it stays
separate so you can install either alone. `global/AGENTS.md` is deliberately
untouched by `--olympus`. To make reporting a habit on this machine, paste this
into your own global `AGENTS.md`:

```markdown
## Olympus reporting

Olympus is the continuity record for work across machines and sessions. When
finishing or pausing work in a repository, use the `olympus-report-progress`
skill to report the Repository Checkout and append a Session Update: what
changed, why, what blocked you, where you stopped, and what comes next.

- Session Updates are progress, not status. Never move a Task's state because
  of what a session did; change it only when the user says so, as
  transcription of what they said.
- Session Updates are Project-scoped. If this repository resolves to no
  Olympus Project, ask which Project to report to rather than inventing one.
- If Olympus is unreachable, say so and carry on — a missing record is not a
  reason to stop the work.
```

Install your global instructions with `./install.sh --global-instructions`, and
see the README for how the two pointer files chain back to this checkout.

Primary references:

- `dm1681/Olympus` README, "Connect an MCP client" — why the tracked
  `.mcp.json` keeps a relative path, and why an absolute one belongs in your
  own configuration
- `dm1681/Olympus` `docs/operations.md`, "Agent Interface authentication
  (`OLYMPUS_AGENT_TOKEN`)" — both sides must carry the same RFC 6750 token
- `dm1681/Olympus#69` — a reachable endpoint for agents outside the trusted
  network
