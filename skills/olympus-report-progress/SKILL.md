---
name: olympus-report-progress
description: Report an agent session's Repository Checkout and append a Session Update to the Olympus Project for the repository you are working in. Use when the user says "report progress to Olympus", "log this to Olympus", "append a session update", when finishing or pausing work in a repository that has an Olympus Project, or when a GitHub issue carries an `Olympus-Task:` marker and the session must leave a record of what happened.
---

<!--
Vendored copy. Source of truth: the Olympus repository, at
`.claude/skills/olympus-report-progress/SKILL.md`, commit 252f467.
Everything below this comment is a byte-for-byte copy of that file.

This is therefore a second copy, and it will drift. Changes to the Olympus
Agent Interface — the MCP tool names, the `/api/agent/v1` request or response
shapes, the Session Update fields, `docs/workflow.md` — land upstream first.
Re-sync this file from that path afterwards instead of editing it here, and
update the commit named above when you do.
-->

# Olympus: report progress

Self-contained on purpose. This skill runs in **any** repository, including
ones that have never heard of Olympus, so everything needed to report is
below. Do not go hunting for Olympus's own documentation — `docs/workflow.md`,
`docs/agents/*`, `CONTEXT.md` — outside the Olympus checkout it is not there,
and its absence is not a reason to stop.

That is why this is long. Nothing here can be replaced by a link: an agent
standing in an unrelated repository cannot follow one. What earns its place is
what a session cannot re-derive and cannot safely guess — the identity values
and where they persist, the shell that produces a reportable remote without
putting a credential on the wire, the request shapes, and the failure modes
that look like success. Read it top to bottom once; the sequence at the end is
what you run.

That is not a licence to ignore the repository you are working in. If this
repository has its own `AGENTS.md` or `CLAUDE.md`, those instructions still
apply while you collect checkout state and run commands here — they can
restrict which commands you may run, what may leave the machine, and what
must be verified first. Where the host repository's rules and this skill
conflict, the host repository wins; report what you are permitted to report,
and say what you withheld.

## What you are reporting

Two things, in this order:

1. **Repository Checkout** — where the work is happening: this Device, this
   repository, this filesystem path. Olympus upserts it and returns a
   `checkoutId`.
2. **Session Update** — what changed, why, what blocked you, where you
   stopped, what comes next, and references to the issues and PRs. It is
   Project-scoped and needs both the `checkoutId` and a `projectId`. It is
   **short**: a few lines a field, pointing at the evidence rather than
   restating it. See "Keep it short" in step 3.

A Session Update is not the narrative of the session; the Task's **state** is
the one-word answer to where the work stands. Write both. Set the state from
your own reading of the work, without waiting to be told — In Progress when
you pick a Task up, Blocked when you are stuck, Done when it is done (ADR 0010
in the Olympus repository). Olympus itself still infers nothing; it stores the state you
reported, tagged with your session, for the owner to review and override.

Done deserves the most care. A wrong link announces itself by conflicting; a
wrong Done just looks right, and an agent's sense of "finished" runs optimistic.
Nothing enforces this — prefer Blocked, or say so in the Session Update, when
you are not sure.

## Reaching Olympus

Prefer the MCP adapter; fall back to HTTP.

- **MCP adapter** — an MCP server usually registered as `olympus`, exposing
  `olympus_repository_checkout_upsert`, `olympus_project_resolve`,
  `olympus_session_update_append`, `olympus_project_briefing_append`,
  `olympus_task_get`, `olympus_task_update`, `olympus_task_create`,
  `olympus_idea_create`, `olympus_idea_update`, `olympus_project_create`,
  `olympus_project_update`, and the five scoped reads a resuming session needs:
  `olympus_project_get`, `olympus_idea_get`, `olympus_task_list`,
  `olympus_project_briefing_get`, `olympus_session_update_list`. Sixteen in
  all. If those tools are not present, the adapter is not registered in this
  session — use HTTP.
- **HTTP** — the canonical Agent Interface at `<base>/api/agent/v1/...`, same
  bodies, `content-type: application/json`, and an `idempotency-key` header on
  every write. `<base>` is the origin of the owner's running Olympus server.
  If you do not know it and it is not in this session's environment as
  `OLYMPUS_BASE_URL`, ask the user for it rather than guessing.

If the server enforces a token, send `Authorization: Bearer $OLYMPUS_AGENT_TOKEN`.
The MCP adapter does this for you when its own env carries the variable.

**Only send that token where the transport protects it.** It is a static
shared secret with no expiry, rotated only when the owner deliberately
replaces it and restarts both sides, and Olympus itself speaks plain
HTTP, so the scheme and the host of `<base>` decide whether sending it is safe:

- `https://<anything>` — fine. TLS is terminated by the owner's tunnel or
  reverse proxy in front of Olympus.
- `http://localhost`, `http://127.0.0.1`, `http://[::1]` — fine. The traffic
  never leaves this machine.
- `http://` on a private-network address the owner runs Olympus on — fine, and
  the normal case; this is the trusted-LAN deployment Olympus is built for.
- `http://` anywhere else — a public hostname, a shared or untrusted network,
  anything reached over the internet — **do not send the token.** Plain HTTP
  puts the credential and the Session Update contents on the wire in
  cleartext, and off-network exposure without TLS is unsupported. Stop and ask
  the owner for an `https://` origin instead of reporting over that base.

If you cannot tell which case a base URL falls into, ask the owner before
sending the token rather than assuming the network is trusted.

## Identity fields, and where they come from

Every write carries these. The **identity** fields — agent, Device, checkout —
are provenance: get them right once at the start of the session and reuse the
same values for every call in it, because inconsistent values fragment the
owner's history. `requestedAt` is **not** one of them.

| Field | Value | Reuse | Rule |
| --- | --- | --- | --- |
| `agent.name` | Your product name, e.g. `Claude Code`, `Codex` | once per session | 1–120 chars, no control characters |
| `agent.sessionId` | One stable id for this whole session | once per session | 1–240 chars, no control characters |
| `device.id` | UUID identifying **this computer** | once per session | Must be byte-identical across every session on this machine |
| `device.name` | Human name of this computer | once per session | 1–120 chars; `hostname` is a good default |
| `checkout.path` | **Absolute** path of the working copy | once per session | Relative paths are rejected with `VALIDATION_ERROR` on `checkout.path` |
| `checkout.pathStyle` | `posix` or `windows` | once per session | Match the path you sent |
| `requestedAt` | Now, ISO 8601 **with offset** | **per call** | e.g. `2026-08-11T16:04:00.000Z`; `date -u +%Y-%m-%dT%H:%M:%S.000Z` |

**Recompute `requestedAt` immediately before each call.** It is when *that*
write was requested, not when the session started — a Session Update appended
an hour in is persisted and exported with the timestamp you send, so a reused
one backdates the owner's history to the session's first call. It also feeds
the server's idempotency fingerprint, so a stale value quietly changes which
retries replay and which conflict. The one exception is an explicit retry of a
call that did not come back confirmed: resend the *exact* body you sent,
`requestedAt` included, so it replays instead of duplicating.

**`agent.sessionId`** — use the session identifier your harness already has if
there is one (for Claude Code, the session URL or its id). Otherwise generate
one UUID at the start of the session and reuse it. Never generate a fresh one
per call: the owner reads a session as one thread of work.

**`device.id`** — this is the identity Olympus upserts Devices by, so a new
UUID means a new Device in the owner's workspace. Keep it in a file and reuse
it forever:

```sh
DEVICE_ID_FILE="$HOME/.olympus/device-id"
mkdir -p "$(dirname "$DEVICE_ID_FILE")"
# An empty file is a leftover from an interrupted first run, not an identity.
if [ -e "$DEVICE_ID_FILE" ] && [ ! -s "$DEVICE_ID_FILE" ]; then
  rm -f "$DEVICE_ID_FILE"
fi
if [ ! -e "$DEVICE_ID_FILE" ]; then
  # Each source is TRIED, not merely detected. `elif command -v` commits to the
  # first generator that exists, so a `uuidgen` that is present and broken —
  # a stub on PATH, a missing shared library, a container without
  # /dev/urandom — blocked a perfectly readable /proc. Fall through on an
  # empty result as well as a missing binary.
  CANDIDATE=""
  if command -v uuidgen >/dev/null 2>&1; then
    CANDIDATE=$(uuidgen 2>/dev/null | tr 'A-Z' 'a-z') || CANDIDATE=""
  fi
  if [ -z "$CANDIDATE" ] && command -v node >/dev/null 2>&1; then
    CANDIDATE=$(node -e 'process.stdout.write(crypto.randomUUID())' 2>/dev/null) || CANDIDATE=""
  fi
  if [ -z "$CANDIDATE" ] && [ -r /proc/sys/kernel/random/uuid ]; then
    CANDIDATE=$(cat /proc/sys/kernel/random/uuid 2>/dev/null) || CANDIDATE=""
  fi
  if [ -n "$CANDIDATE" ]; then
    # Write first, publish second — the same form `olympus-repository-id` uses,
    # and for a reason `set -C` cannot cover. An exclusive redirection creates
    # the name *empty* and fills it a moment later, and the empty-file recovery
    # above is another session's cue to delete it: a second session starting in
    # that window unlinks the winner's file mid-write, then mints and publishes
    # its own. One machine becomes two Devices, which is the exact outcome this
    # file exists to prevent. Composing in a private file and hard-linking it
    # into place means the name never exists empty. `ln` fails rather than
    # overwrite, so the first session to publish still wins and the rest fall
    # through to the read below.
    DEVICE_ID_TMP="$DEVICE_ID_FILE.$$"
    rm -f "$DEVICE_ID_TMP"
    if printf '%s\n' "$CANDIDATE" > "$DEVICE_ID_TMP"; then
      # `ln` first, because it cannot overwrite and the name never exists
      # empty. Not every filesystem has hard links, though -- exFAT or FAT on
      # an external or synced home, some FUSE and SMB mounts -- and there this
      # would otherwise delete the only copy of a UUID that was generated
      # perfectly well. `set -C` is the older form and still exclusive; its
      # empty-name window is narrow, and a narrow window beats no identity.
      ln "$DEVICE_ID_TMP" "$DEVICE_ID_FILE" 2>/dev/null \
        || ( set -C; printf '%s\n' "$CANDIDATE" > "$DEVICE_ID_FILE" ) 2>/dev/null \
        || true
    fi
    rm -f "$DEVICE_ID_TMP"
  fi
fi
if [ ! -s "$DEVICE_ID_FILE" ]; then
  # Two different failures, and telling the owner the wrong one wastes their
  # time: "no UUID source" is unanswerable advice when a UUID was generated
  # and the file simply could not be created.
  if [ -n "${CANDIDATE:-}" ]; then
    echo "generated a Device UUID but could not create $DEVICE_ID_FILE; check that path is writable" >&2
  else
    echo "no UUID source; ask the owner for the Device UUID" >&2
  fi
fi
cat "$DEVICE_ID_FILE"
```

Three things in that snippet are load-bearing:

- `uuidgen` is absent on minimal Linux images. Each branch writes to a
  variable and only a successful branch reaches the file, so a missing or
  broken generator never leaves an empty file behind an invalid `device.id`.
- **The publish is exclusive, and every session reads the file afterwards.**
  Two sessions starting at once would otherwise both mint a UUID and each
  report its own — one machine arriving in the owner's workspace as two
  Devices, the exact thing `device.id` exists to prevent. Each contender
  composes its UUID in a private `device-id.<pid>`; the publish is the `ln`,
  only one of those can succeed, and every session sends the value it read
  back from the file rather than the one it generated. **On a filesystem with
  no hard links this is weaker**, knowingly: the `set -C` fallback creates the
  name empty and fills it a moment later, so the empty-file recovery above can
  unlink a winner mid-write and two Devices can still appear. It beats having
  no identity at all, but if `$HOME` is on exFAT, FAT, or a synced or SMB
  mount, set the Device UUID by hand once instead.
- Do not "improve" this into a temp file and an `mv`. `mv` overwrites, which
  reintroduces the race exclusivity closes. The one cost of this form, shared
  with `olympus-repository-id`: a session killed between the `printf` and the
  `rm -f` leaves an orphan `device-id.<pid>`, which is inert — the identity is
  read from `device-id` only — and safe to delete.

If you cannot write that file, ask the user for the Device UUID they already
use. Do not invent one silently.

**`idempotencyKey`** — required on every write, 1–200 printable ASCII
characters, no spaces. Make it deterministic for the write it identifies so
that an explicit retry is a replay and not a duplicate.

A session id is valid provenance at up to 240 characters and may contain
spaces, so concatenating it raw can exceed the key's 200-character limit or
introduce an illegal space. Neither is a `VALIDATION_ERROR`: over HTTP the
key fails to parse and the route answers `400 IDEMPOTENCY_KEY_REQUIRED`, and
over MCP — the transport to prefer — the key is part of each tool's input
schema, so the call fails validation locally and never reaches Olympus at all.
Derive a bounded token from it once, then build every key from that:

```sh
# Set this to the `agent.sessionId` you settled on above. There is no default
# and no fallback: an unset SESSION_ID hashes to e3b0c44298fc1c14 — the hash
# of the empty string — identically on every machine and in every session, so
# the second session to report would reuse the first session's keys under a
# different body and be answered with IDEMPOTENCY_CONFLICT.
SESSION_ID=${SESSION_ID:-}
if [ -z "$SESSION_ID" ]; then
  echo "SESSION_ID is empty; set it to this session's agent.sessionId" >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
  KEY_PREFIX=$(printf '%s' "$SESSION_ID" | sha256sum | cut -c1-16)
else
  KEY_PREFIX=$(printf '%s' "$SESSION_ID" | shasum -a 256 | cut -c1-16)
fi
if [ -z "$KEY_PREFIX" ]; then
  echo "no sha256 tool; ask the owner how to build keys" >&2
  exit 1
fi
printf '%s\n' "$KEY_PREFIX"
```

The hash is deterministic, so a retry within the same session rebuilds the
same prefix — which is what makes the retry a replay. It is also derived from
the session id and nothing else, so two sessions never collide: that is the
whole reason the guard above refuses to run on an empty one.

**Number every key, including the checkout.** One session commonly reports
more than once — at a blocker, then again at the stopping point — and each
report is a fresh Repository Checkout upsert followed by a fresh Session
Update. Keep a counter `N` for the report, starting at 1 and incremented for
each new report in the session:

```
report 1:  <KEY_PREFIX>-checkout-1   <KEY_PREFIX>-session-update-1
report 2:  <KEY_PREFIX>-checkout-2   <KEY_PREFIX>-session-update-2
```

The checkout key must move with the counter, not stay at `-checkout-1`. The
server fingerprints the whole request — `requestedAt` included — so a second
checkout upsert reusing `-checkout-1` carries a later `requestedAt` than the
first, fails the fingerprint comparison, and comes back `IDEMPOTENCY_CONFLICT`
with no `checkoutId`. That blocks the Session Update the second report exists
to deliver. The identity in the body is unchanged, so the upsert is harmless
and cheap to repeat; only the key needs to move.

Reuse the **same** key, with the **same body**, only when retrying a call that
did not come back confirmed — that is the replay the key exists for. Use a
**new** key for genuinely new content. Sending a different body under a key
already used returns `IDEMPOTENCY_CONFLICT`.

## The repository identity

```json
{ "kind": "git", "remote": "<sanitized origin URL>" }
```

**Never send `git remote get-url origin` raw.** An HTTPS remote can carry
userinfo — `https://x-access-token:ghp_…@github.com/owner/repo.git` is what CI
runners and some credential helpers leave in `origin` — and that userinfo is a
live credential. Olympus drops it when it canonicalizes, but only *after* the
request has crossed the network, and this skill permits reporting over plain
HTTP on a trusted LAN, so the secret is on the wire and in your session
transcript before the server ever sees it. Strip it locally first:

```sh
REMOTE=$(git remote get-url origin 2>/dev/null || true)

# 1. Userinfo. `[^/]*@` is greedy and cannot cross the first `/`, so it strips
#    through the *last* `@` of the authority and leaves an `@` inside a path
#    alone. Greedy is what makes it safe: a password may legally contain a
#    literal `@` (`https://user:tok@seg@host/...`), and stopping at the first
#    one would report `seg@host` — part of the secret, still on the wire.
#    A bare `git@` is the fixed SSH user, not a credential, so it is dropped
#    without an alarming message — the identity does not move either way,
#    because Olympus discards userinfo when it canonicalizes.
USERINFO=$(printf '%s' "$REMOTE" | sed -n 's#^[A-Za-z][A-Za-z0-9+.-]*://\([^/]*\)@.*#\1#p')
SAFE=$(printf '%s' "$REMOTE" | sed 's#^\([A-Za-z][A-Za-z0-9+.-]*://\)[^/]*@#\1#')
if [ "$SAFE" != "$REMOTE" ]; then
  case "$USERINFO" in
    git) ;;
    *) echo "origin carried userinfo; reporting the credential-free form" >&2 ;;
  esac
  REMOTE="$SAFE"
fi

# 2. Query and fragment. `https://host/repo.git?access_token=SECRET` is a
#    live credential in a component Olympus rejects outright rather than
#    canonicalizes, so the raw value would be a secret on the wire buying a
#    VALIDATION_ERROR. Cut at the first `?` or `#` locally instead.
TRIMMED=${REMOTE%%[?#]*}
if [ "$TRIMMED" != "$REMOTE" ]; then
  echo "origin carried a query or fragment; reporting without it" >&2
  REMOTE="$TRIMMED"
fi

# 3. SSH host aliases. `~/.ssh/config` can give a host a local name that git
#    accepts and nothing else has heard of — `Host github-dm1681` with
#    `HostName github.com`. The classification below only asks whether a host
#    is well *formed*, and an alias usually is, so
#    `git@github-dm1681:dm1681/Olympus.git` passes it and Olympus
#    canonicalizes the alias as a host in its own right: a second Repository
#    `git:v1:github-dm1681/dm1681/Olympus`, distinct from the
#    `git:v1:github.com/dm1681/Olympus` the owner linked to a Project. The
#    checkout upsert answers 201 instead of 200, Project resolution then 404s
#    with REPOSITORY_NOT_LINKED, and everything after it lands on a Repository
#    nobody is watching. Resolve the alias to the host ssh really dials first.
olympus_ssh_hostname() {
  # `ssh -G` is the effective configuration — `Host` blocks, `Match` blocks and
  # `Include` files all applied — and it echoes the name back unchanged when
  # nothing matches, so "not an alias" and "an alias for itself" look the same
  # and both mean leave the remote alone. A successful `ssh -G` always prints a
  # `hostname` line, so an empty result is a failure and not an answer: fall
  # through to reading the config, the same TRIED-not-detected rule the UUID
  # sources follow, because an `ssh` that is present and broken must not hide
  # an alias a plain read would have found.
  _resolved=
  if command -v ssh >/dev/null 2>&1; then
    _resolved=$(ssh -G "$1" 2>/dev/null | awk '$1 == "hostname" { print $2; exit }')
  fi
  if [ -z "$_resolved" ] && [ -r "$HOME/.ssh/config" ]; then
    # Exact `Host` names only. Matching the `Host *.example` patterns ssh
    # supports would take an ssh-compatible glob, and guessing one wrong
    # rewrites a host that was never an alias. Note also that ssh resolves `~`
    # from the password database rather than `$HOME`, so in a session where the
    # two differ this fallback reads a different file than `ssh -G` did.
    _resolved=$(awk -v want="$1" '
      tolower($1) == "host" {
        inblock = 0
        for (i = 2; i <= NF; i++) if ($i == want) inblock = 1
        next
      }
      inblock && tolower($1) == "hostname" { print $2; exit }
    ' "$HOME/.ssh/config")
  fi
  printf '%s' "$_resolved"
}
ALIAS_FORM=
ALIAS_USER=
ALIAS_HOST=
ALIAS_PORT=
ALIAS_PATH=
case "$REMOTE" in
  ssh://*)
    ALIAS_FORM=ssh
    AUTHORITY_PART=${REMOTE#ssh://}
    case "$AUTHORITY_PART" in
      */*) ALIAS_PATH=/${AUTHORITY_PART#*/}; AUTHORITY_PART=${AUTHORITY_PART%%/*} ;;
    esac
    case "$AUTHORITY_PART" in
      *@*) ALIAS_USER=${AUTHORITY_PART%@*}@; AUTHORITY_PART=${AUTHORITY_PART##*@} ;;
    esac
    case "$AUTHORITY_PART" in
      *:*) ALIAS_PORT=:${AUTHORITY_PART##*:}; AUTHORITY_PART=${AUTHORITY_PART%%:*} ;;
    esac
    ALIAS_HOST=$AUTHORITY_PART
    ;;
  # https:// never consults ~/.ssh/config, and neither does anything the
  # classifier below is going to refuse anyway.
  *://*) ;;
  *:*)
    HOST_FIELD=${REMOTE%%:*}
    ALIAS_PATH=${REMOTE#*:}
    case "$HOST_FIELD" in
      */*) ;;  # a colon after a slash is part of a path, not a host
      *@*) ALIAS_FORM=scp; ALIAS_USER=${HOST_FIELD%@*}@; ALIAS_HOST=${HOST_FIELD##*@} ;;
      *)   ALIAS_FORM=scp; ALIAS_HOST=$HOST_FIELD ;;
    esac
    ;;
esac
# Only ask ssh about a name that cannot be read as an option or a pattern.
case "$ALIAS_HOST" in
  "" | -* | *[!A-Za-z0-9._-]*) ALIAS_HOST= ;;
esac
if [ -n "$ALIAS_HOST" ]; then
  REAL_HOST=$(olympus_ssh_hostname "$ALIAS_HOST")
  # Compare case-insensitively. `ssh -G` lowercases what it echoes back, and
  # Olympus lowercases the host when it canonicalizes, so a difference in case
  # alone is not an alias — rewriting on it would relabel `C:\repos\olympus`
  # as an alias for `c` and mangle a path that was never an ssh host.
  ALIAS_HOST_LC=$(printf '%s' "$ALIAS_HOST" | tr 'A-Z' 'a-z')
  REAL_HOST_LC=$(printf '%s' "$REAL_HOST" | tr 'A-Z' 'a-z')
  if [ -n "$REAL_HOST" ] && [ "$REAL_HOST_LC" != "$ALIAS_HOST_LC" ]; then
    echo "origin's host $ALIAS_HOST is an ssh alias for $REAL_HOST; reporting the real host" >&2
    case "$ALIAS_FORM" in
      ssh) REMOTE="ssh://$ALIAS_USER$REAL_HOST$ALIAS_PORT$ALIAS_PATH" ;;
      scp) REMOTE="$ALIAS_USER$REAL_HOST:$ALIAS_PATH" ;;
    esac
  fi
fi

# 4. Classification. Olympus accepts only https://, ssh:// and the SCP form
#    `[user@]host:path`, and it is stricter than git about both the host and
#    the path. Anything else is a VALIDATION_ERROR, so classify before
#    reporting. The server remains the authority; this only rules out the
#    forms it definitely cannot canonicalize.
olympus_path_ok() {
  # Mirrors the server's `normalizeGitPath`: drop empty segments, strip one
  # trailing `.git`, then reject an empty result or any `.`/`..` segment —
  # so `host:../repo.git` is caught here rather than by the server.
  _rest=$1
  _joined=
  while [ -n "$_rest" ]; do
    case "$_rest" in
      */*) _seg=${_rest%%/*}; _rest=${_rest#*/} ;;
      *)   _seg=$_rest;       _rest= ;;
    esac
    [ -n "$_seg" ] || continue
    _joined=${_joined:+$_joined/}$_seg
  done
  _joined=${_joined%.git}
  [ -n "$_joined" ] || return 1
  case "/$_joined/" in */../* | */./*) return 1 ;; esac
  return 0
}
olympus_scp_host_ok() {
  # Mirrors the server's SCP host rule: every dot-separated label is
  # alphanumeric with interior hyphens only. An `~/.ssh/config` alias such as
  # `gh_work` is a legal git remote and not a legal Olympus host.
  case "$1" in
    "" | *[!A-Za-z0-9.-]* | .* | *. | *..* | -* | *- | *-.* | *.-*) return 1 ;;
  esac
  return 0
}

REMOTE_SUPPORTED=no
case "$REMOTE" in
  https://* | ssh://*)
    AFTER=${REMOTE#*://}
    case "$AFTER" in
      */*) AUTHORITY=${AFTER%%/*}; URL_PATH=${AFTER#*/} ;;
      *)   AUTHORITY=$AFTER;       URL_PATH= ;;
    esac
    # `https://github.com` parses as a URL and still has no Repository path.
    if [ -n "${AUTHORITY%%:*}" ] && olympus_path_ok "$URL_PATH"; then
      REMOTE_SUPPORTED=yes
    fi
    ;;
  *://*) ;;
  *)
    HOST_PART=${REMOTE%%:*}
    PATH_PART=${REMOTE#*:}
    case "$HOST_PART" in
      # no colon at all / empty host / colon after a slash / drive letter
      "$REMOTE" | "" | */* | ?) ;;
      *)
        SCP_USER=
        SCP_HOST=$HOST_PART
        case "$HOST_PART" in
          *@*@*) SCP_HOST= ;;
          *@*) SCP_USER=${HOST_PART%@*}; SCP_HOST=${HOST_PART#*@} ;;
        esac
        # A URI scheme typed with a single colon, e.g. `git:owner/repo` — but
        # only when no user was given, exactly as the server has it.
        if [ -z "$SCP_USER" ]; then
          case "$SCP_HOST" in
            file | ftp | ftps | git | gopher | http | https | rsync | sftp | ssh | svn | ws | wss) SCP_HOST= ;;
          esac
        fi
        case "$SCP_USER" in *[!A-Za-z0-9'._~!$&'"'"'()*+,;=%-']*) SCP_HOST= ;; esac
        case "$PATH_PART" in *@*) SCP_HOST= ;; esac
        if olympus_scp_host_ok "$SCP_HOST" && olympus_path_ok "$PATH_PART"; then
          REMOTE_SUPPORTED=yes
        fi
        ;;
    esac
    ;;
esac
if [ "$REMOTE_SUPPORTED" = no ]; then
  echo "origin is not a remote Olympus can canonicalize: $REMOTE" >&2
fi
printf '%s\n' "$REMOTE"
```

Step 1 removes userinfo from scheme-bearing URLs only. It leaves the SCP form
`git@github.com:owner/repo.git` alone, because the pattern needs a `://`, and
it leaves an `@` inside a path alone, because the pattern cannot cross the
first `/`. Report the sanitized value everywhere the remote appears: the
Repository Checkout **and** the Project resolution. Do not paste the raw
remote into a Session Update either.

**Step 3 is the one nothing else catches.** A stripped credential announces
itself and an unsupported scheme is refused, but an unresolved SSH alias is a
well-formed host that Olympus accepts and files under a Repository of its own
— the checkout succeeds, the Project resolution fails, and the failure looks
like "this repository is not linked" rather than "you reported the wrong
repository". Resolve the host before you compare anything to it, and if
`ssh -G` is unavailable and there is no readable `~/.ssh/config`, say which
host you reported rather than assuming the name in `origin` is the real one.

**A valid git remote is not automatically a reportable one.** `origin` may
legitimately be `http://gitserver.lan/olympus.git`, `git://…`, `file:///srv/…`
or a plain filesystem path like `/srv/repos/olympus.git` — git clones all of
them, and Olympus canonicalizes none of them. Sending one as `{ "kind": "git" }`
returns `VALIDATION_ERROR` and nothing is reported. When the classifier above
says `no`:

- Ask the owner for the canonical `https://` or SSH remote for this repository
  and report that, since it is the same Repository either way. Do not invent
  one by rewriting the scheme — `http://` and `https://` on the same host are
  not guaranteed to be the same server.
- If there is no canonical remote — a repository that only ever exists on this
  disk — use the local-identity flow below instead, exactly as for a working
  copy with no remote at all.

Olympus canonicalizes the remote itself, so SSH and HTTPS forms of the same
remote resolve to one Repository — and because it discards userinfo, the
stripped form resolves to the identical Repository the raw one would have.

For a working copy with no remote, use `{ "kind": "local", "key":
"local:<uuid>" }`. That UUID must be as stable as `device.id`: a new one is a
second logical Repository, and Project resolution against it returns
`REPOSITORY_NOT_LINKED` even though the owner already linked the first. So
**read before you mint**, from a location the next session will find:

```sh
GIT_COMMON=$(git rev-parse --git-common-dir 2>/dev/null || true)
[ -n "$GIT_COMMON" ] || { echo "not a git checkout; ask the owner for the key" >&2; exit 1; }
REPO_ID_FILE="$GIT_COMMON/olympus-repository-id"
# An empty file is a first run interrupted between creating the name and
# writing to it, not an identity. Without this the `-e` test below is
# satisfied forever and every later session reads an empty key.
if [ -e "$REPO_ID_FILE" ] && [ ! -s "$REPO_ID_FILE" ]; then
  rm -f "$REPO_ID_FILE"
fi
if [ ! -e "$REPO_ID_FILE" ]; then
  # The same three UUID sources as `device.id`, and for the same reason:
  # gating on /proc alone dead-ends this whole flow on macOS and BSD, where
  # there is no /proc but `uuidgen` is always present.
  # Each source is TRIED, not merely detected. `elif command -v` commits to the
  # first generator that exists, so a `uuidgen` that is present and broken —
  # a stub on PATH, a missing shared library, a container without
  # /dev/urandom — blocked a perfectly readable /proc. Fall through on an
  # empty result as well as a missing binary.
  CANDIDATE=""
  if command -v uuidgen >/dev/null 2>&1; then
    CANDIDATE=$(uuidgen 2>/dev/null | tr 'A-Z' 'a-z') || CANDIDATE=""
  fi
  if [ -z "$CANDIDATE" ] && command -v node >/dev/null 2>&1; then
    CANDIDATE=$(node -e 'process.stdout.write(crypto.randomUUID())' 2>/dev/null) || CANDIDATE=""
  fi
  if [ -z "$CANDIDATE" ] && [ -r /proc/sys/kernel/random/uuid ]; then
    CANDIDATE=$(cat /proc/sys/kernel/random/uuid 2>/dev/null) || CANDIDATE=""
  fi
  if [ -n "$CANDIDATE" ]; then
    # Write first, publish second: the key is composed in a private file and
    # hard-linked into place, so the name never exists empty. `ln` fails
    # rather than overwrite, so the first session to publish wins and the
    # rest fall through to the read below. The `set -C` arm below is the
    # exception to "never exists empty" — see the note under `device.id`.
    REPO_ID_TMP="$REPO_ID_FILE.$$"
    rm -f "$REPO_ID_TMP"
    if printf 'local:%s\n' "$CANDIDATE" > "$REPO_ID_TMP"; then
      # Same fallback as `device.id`, for the same reason: a `.git` on a
      # filesystem without hard links must still end up with a key.
      ln "$REPO_ID_TMP" "$REPO_ID_FILE" 2>/dev/null \
        || ( set -C; printf 'local:%s\n' "$CANDIDATE" > "$REPO_ID_FILE" ) 2>/dev/null \
        || true
    fi
    rm -f "$REPO_ID_TMP"
  fi
fi
[ -s "$REPO_ID_FILE" ] || echo "no repository key; ask the owner for it" >&2
cat "$REPO_ID_FILE"
```

`--git-common-dir` rather than `--git-dir` on purpose: every worktree of one
repository shares the common dir, so they all report the same Repository
instead of one each. Anything under `.git/` is outside the working tree, so
the file is invisible to `git status` and can never be committed by accident.
Concurrency, the hard-link publish, the `set -C` fallback and its narrowed
guarantee, and the inert orphan a killed session leaves behind are all exactly
as described for `device.id` above — same form, same reasons.

Ask the user whether a key already exists for this repository before minting
one, and if there is no git checkout to hang the file off, ask rather than
inventing a key that nothing will remember.

## The sequence

**A session that changed nothing reports nothing.** If there is genuinely
nothing to say — you read code and answered a question, the work was abandoned
before it touched anything, someone else's session already reported it — say so
to the user and stop. That is the same escape the Stop hook offers in the
Olympus checkout ("if this session genuinely has nothing to report, say so and
stop"), and it is the right one here too. Do not append a Session Update whose
`changed` field restates the task, records that nothing happened, or is padded
to get past the "at least one non-empty field" rule: a Session Update is
progress, and an update that carries none is noise in the record the owner
reads to find out what moved. A session that changed nothing but *learned*
something — a blocker, a dead end, a decision — has something to report; write
that, in `blockers` or `why`, and skip the fields that do not apply.

### 1. Report the Repository Checkout — always first

Every other mutation needs the `checkoutId` this returns.

`olympus_repository_checkout_upsert` / `POST /api/agent/v1/repository-checkouts`

```json
{
  "idempotencyKey": "<KEY_PREFIX>-checkout-<N>",
  "body": {
    "agent": { "name": "Claude Code", "sessionId": "<sessionId>" },
    "requestedAt": "<now, recomputed for this call>",
    "device": { "id": "<device uuid>", "name": "<hostname>" },
    "repository": { "kind": "git", "remote": "<sanitized remote>" },
    "checkout": { "pathStyle": "posix", "path": "<absolute path>" }
  }
}
```

Over HTTP, `body` is the whole request body and `idempotencyKey` is the
`idempotency-key` header.

**The result path differs by transport.** The MCP tool wraps the server's reply
in `{ "kind": "success", "httpStatus": …, "response": … }`, so the body is one
level down; over HTTP you are handed that body directly. Read the `checkoutId`
from whichever you used:

| transport | path to the checkout id |
| --- | --- |
| `olympus_repository_checkout_upsert` (MCP) | `response.checkout.id` |
| `POST /api/agent/v1/repository-checkouts` | `checkout.id` |

Reading `response.checkout.id` off an HTTP reply yields `undefined`, and since
every later mutation needs the `checkoutId`, the report stops there.

**Compare the id you got back with the one this checkout already had.** Many
sessions persist their Olympus identity beside the working copy so the next one
can resume it — in the Olympus repository that file is `.olympus-session.json`,
holding the `checkoutId`, `projectId` and Device — and a later report in the
same checkout expects the same `checkoutId` back. The upsert is keyed on
repository + Device + path, so a *different* id means one of those three moved:
almost always the repository identity, from an unresolved SSH alias, a rewritten
`origin`, or a `local:` key that was minted twice. **Stop and re-verify the
identity rather than overwriting the persisted value** — re-run the remote
sanitization above and check the Device UUID — because writing the new id into
that file is what makes the mistake permanent: the next session resumes the
wrong Repository, and the checkout that was linked to a Project is no longer
the one anyone reports against.

Two signals say the same thing before you even compare. Over MCP the envelope's
`httpStatus` is `201` when the upsert *created* a checkout and `200` when it
matched an existing one, and over HTTP that is the status code itself; a `201`
where you expected to be resuming known work is the alias failure arriving
early. And a Project resolution that answers `404 REPOSITORY_NOT_LINKED` for a
repository you know is linked means you reported a repository identity nobody
linked — check the remote you sent before concluding the Project is missing.

### 2. Resolve the Project

`olympus_project_resolve` / `POST /api/agent/v1/project-resolution`

```json
{ "repository": { "kind": "git", "remote": "<sanitized remote>" } }
```

Read the `projectId` by the same rule as the checkout id: `response.project.id`
from the MCP tool, `project.id` from the HTTP reply.

A `404` with `REPOSITORY_NOT_LINKED` means this repository has no Olympus
Project. **Stop and tell the user.** Linking a Repository to a Project is an
owner action; do not create a Project to work around it unless the user asks
you to.

### 3. Append the Session Update

`olympus_session_update_append` / `POST /api/agent/v1/session-updates`

```json
{
  "idempotencyKey": "<KEY_PREFIX>-session-update-<N>",
  "body": {
    "agent": { "name": "Claude Code", "sessionId": "<sessionId>" },
    "requestedAt": "<now, recomputed for this call — later than the checkout's>",
    "checkoutId": "<checkoutId from step 1>",
    "projectId": "<projectId from step 2>",
    "content": {
      "changed": "...",
      "why": "...",
      "blockers": "...",
      "stoppingPoint": "...",
      "nextActions": "...",
      "references": "..."
    }
  }
}
```

Every `content` field is optional and at least one must be non-empty; omit
what does not apply rather than padding it. Each is plain text. Tabs, newlines
and carriage returns are allowed — `nextActions` wants line breaks — but every
other control character is rejected. The Workspace renders these fields as
Markdown, so a short bullet list is fine and usually clearer than a paragraph.

#### Keep it short

**Budget about 250 characters per field, about 1,200 for the whole update.**
The hard input cap is 2,000 characters per field; longer is rejected. That is a
cap, not a target — it used to be 20,000, and every update written under it grew
to thousands of characters, turning the continuity record into the chat
transcript it exists to replace. Markdown is not licence for length either:
bullets are for structure, not for fitting more in.

Brevity is achievable because a Session Update **points at** the evidence rather
than restating it. The issue, the PR, the commit and the branch already hold the
detail, and `references` is what lets the other five fields stay short. When
there is genuinely more to say, say it where it belongs — the PR description,
the issue, the commit message — and reference it from the update. A Session
Update is an index, not the archive.

Write the fields for an owner who was not in the session:

- **changed** — what is different now, concretely. Files, behavior, contracts. Not how you got there.
- **why** — the reason, not a restatement of the change.
- **blockers** — what stopped you, and what would unblock it. Omit if nothing did.
- **stoppingPoint** — the state you are leaving behind: branch, whether it builds, what is uncommitted.
- **nextActions** — the next concrete steps, in order.
- **references** — issue and PR URLs or `owner/repo#123` forms, plus branch names.

#### A good one, in full

All six fields, 832 characters in total and none over 250, from a session that
fixed one bug and found another:

```json
{
  "changed": "- `POST /api/import` now rejects an unknown export `version` with 422 `UNSUPPORTED_EXPORT_VERSION` instead of throwing a 500.\n- Guard plus three cases in `tests/integration/import.test.ts`.",
  "why": "An export written by an older release crashed the route on a field that no longer exists, so a stale file read to the owner as a server outage. Stack trace on #131.",
  "blockers": "Import still writes rows before validating the whole payload, so a bad file can half-apply. Needs a transaction-boundary decision — filed as #134, out of scope here.",
  "stoppingPoint": "Branch `fix/import-version-guard`, tree clean, `pnpm typecheck` and `pnpm test:integration` green. Draft PR #133 open against main.",
  "nextActions": "1. Mark #133 ready for review.\n2. Settle the transaction boundary on #134 before touching import again.",
  "references": "Closes #131. PR #133 (draft). Follow-up #134. Branch `fix/import-version-guard`."
}
```

Nothing in it is padded and nothing in it is retold. The reproduction lives on
#131, the diff lives on #133, the open question lives on #134, and the update
says only which of them to open and why. Copy that shape.

Append one update at a natural boundary — finishing, pausing, hitting a
blocker, or being asked. Not per commit.

Reporting again later in the same session means running steps 1–3 again with
`N` incremented and a freshly computed `requestedAt` on each call. Step 2 needs
no key: Project resolution is a read.

## Reading the result

This section describes the **MCP adapter's** envelope. Over HTTP there is no
envelope: the status code carries what `kind` would have, and every field named
`response.x` below is `x` at the top level of the reply body.

Every adapter call returns `kind`:

- **`success`** — recorded. `response.replayed: true` means your idempotency
  key matched an earlier identical write; that is a replay, not a duplicate,
  and needs no action.
- **`http_error`** — Olympus received and rejected it. `error.error.code` says
  why and `error.error.retryable` says whether retrying can help. Fix the
  input; do not retry an unchanged body against `VALIDATION_ERROR`,
  `IDEMPOTENCY_KEY_REQUIRED`, `REPOSITORY_NOT_LINKED`, `TASK_NOT_FOUND`,
  `STALE_WRITE`, or `IDEMPOTENCY_CONFLICT`. `IDEMPOTENCY_KEY_REQUIRED` means
  the header was missing or the key itself did not parse — over 200 characters,
  or carrying a space; see the key-derivation note above.
- **`undelivered`** — Olympus may or may not have received it. The result
  carries `attemptedInput` back; retry by sending that exact input, with the
  same idempotency key, so a write that did land replays instead of
  duplicating.

Honor `retryable`. `retryable: false` means stop:

- `UNAUTHORIZED` — the token is wrong. Tell the user to check
  `OLYMPUS_AGENT_TOKEN` on both the adapter and the server. Do not retry.
- `CONNECTION_FAILED` or `TIMEOUT` with `retryable: false` — the adapter has
  got no response at all on several consecutive attempts, whether the
  connection was refused or the host accepted it and answered nothing, and now
  treats the host as unreachable rather than merely restarting. **Stop
  retrying.** Report to the user that Olympus was unreachable, name
  `OLYMPUS_BASE_URL` as the thing to check, and put the Session Update you
  could not deliver in your final message so the work is not lost. Common
  causes: the base URL is a private-network hostname and you are not on that
  network, or something in front of it swallows the connection.

At most two or three retries of anything, ever. Olympus being down is worth a
sentence to the user, not a session spent retrying.

## Related tools, and the boundary around them

Available on the same interface, all requiring the `checkoutId`:

- `olympus_project_briefing_append` — append a Project Briefing, the versioned
  snapshot of where work stopped and what could be done next. A Project
  Briefing is owner-curated, so one you wrote is an Agent Proposal and needs
  the user's approval in-session first, unless this session is explicitly in
  Auto-apply mode. Olympus retains every version it accepts and this
  interface has no route to withdraw one — the owner can delete a briefing in
  Olympus itself, you cannot — so propose a briefing only when the stopping
  point or the next possible steps have genuinely changed — not every session — and send
  only the text the user approved.
- `olympus_project_briefing_get` — read the current Project Briefing, or
  `null`. Off-repo this is the only way to see what the briefing already says,
  so it is what makes the "genuinely changed" test above answerable rather
  than guessed at. Read before proposing.
- `olympus_session_update_list` — the most recent Session Updates, newest
  first. What a resuming session reads to find out where it left off.
- `olympus_task_list` — the resolved Project's Tasks, for discovery when you
  do not already hold a Task id.
- `olympus_project_get` / `olympus_idea_get` — read a Project or an Idea with
  the `revision` an update must present. The Idea read also returns its whole
  `projectIds` set, which an update replaces wholesale — so read it first
  unless you intend to erase the relationships you cannot see.
- `olympus_task_get` — read a Task scoped to a Project; returns the `revision`
  an update must send as `expectedRevision`.
- `olympus_task_update` — transcribe an owner-dictated change to a Task,
  including state. **Only when the user says so.**
- `olympus_task_create` — transcribe a Task the user dictated, or propose one
  you discovered. A proposal you were not asked for needs the user's approval
  in-session first, unless this session is explicitly in Auto-apply mode.

The Approval Mode is the agent session's own policy, not something Olympus
stores or enforces: **Review** — the default, and what to assume unless the
user has said otherwise — requires approval before each proposal is sent,
while **Auto-apply** permits routine, non-destructive changes without
individual approval. The Repository Checkout and the Session Update are your
own record of the session and need no approval. Everything that adds to or
changes owner-curated content — a Project Briefing, a Task, an Idea, a
Project — is an Agent Proposal in Review mode, and creating a Project always
needs explicit in-session approval regardless of mode.

Recording a Task ↔ GitHub issue link, and unlinking one, is open to any agent
with no preconditions (ADR 0010) — but the agent interface has no route for it
yet, so until one exists the link is recorded by the owner in the app. Not
having the route is a gap in the surface, not a boundary you are respecting.
