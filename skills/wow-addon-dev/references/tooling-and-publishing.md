# Tooling, libraries, performance, publishing

## Editor setup

VS Code + the Lua Language Server (sumneko/LuaLS) + Ketho's `vscode-wow-api` extension, which
ships LuaLS annotations for the WoW API - functions, `C_*` namespaces, events, widget methods -
and auto-activates when it sees a `.toc`. It also offers optional annotated FrameXML source.
**Update the annotation package every major patch**, or it will confidently autocomplete removed
functions.

Alternatives: IntelliJ + EmmyLua stubs. `Septh/vscode-wow-bundle` provides grammar and
colorization but is no longer guaranteed API-accurate.

## In-game tooling

| Tool | Use |
| --- | --- |
| `/reload` | Picks up changed *and newly added* files and TOC metadata (since 9.0.1) |
| `/console scriptErrors 1` | Surface Lua errors at all |
| `/api` | In-client API browser |
| `/dump <expr>` | Pretty-print any value or table |
| `/etrace` | Live event trace with payloads |
| `/fstack` | Identify the frame under the cursor |

Install **BugGrabber + BugSack** to capture and browse errors - the default error display loses
them. **DevTool** inspects tables live. **Numy's Addon Profiler** is the popular CPU/memory
front-end.

The iteration loop is: edit -> `/reload` -> test. There is no hot reload beyond that.

## Libraries

- **LibStub** - the near-universal library versioning shim: `LibStub("LibName-1.0")`. Almost
  everything embeds it.
- **CallbackHandler-1.0** - the callback engine underneath Ace and LibDataBroker.
- **Ace3** - the dominant application framework, embedded per-addon in a `Libs/` folder:
  - `AceAddon-3.0` - lifecycle (`NewAddon`, `OnInitialize`, `OnEnable`, `OnDisable`)
  - `AceEvent-3.0` - event registration with automatic cleanup and better error reporting
  - `AceDB-3.0` - SavedVariables with profiles, defaults, per-char/account/namespace scoping.
    The single biggest win over hand-rolled persistence.
  - `AceConfig-3.0` (+ Dialog/Registry/Cmd) - declarative options tables generating both a
    Settings panel and slash-command config
  - `AceGUI-3.0` - widget toolkit for custom config windows
  - `AceComm-3.0` - chunked addon-to-addon messaging (note the in-instance comms lockdown during
    active encounters/M+/PvP)
  - Also AceConsole, AceHook, AceTimer, AceLocale, AceSerializer, AceBucket
- **LibDataBroker-1.1** - the standard for minimap and panel plugins. Must not be stripped when
  packaging.
- **LibSharedMedia-3.0** - shared registry of fonts, bar textures, sounds, borders.
- **oUF** - unit frames on secure headers.
- **LibEditMode** / **LibEditModeOverride** - register custom frames into Blizzard's Edit Mode.

**When to skip libraries:** a small, single-purpose, or performance-critical addon is lighter and
has less taint surface with the plain API plus the modern Settings API. Reach for Ace3 once you
need profiles, rich options, or cross-addon comms.

## Performance discipline

Profiling: CPU profiling is gated by the `scriptProfile` CVar (persists across sessions, needs a
`/reload` to take effect), read via `GetScriptCPUUsage`, `UpdateAddOnCPUUsage`,
`GetAddOnCPUUsage`, `GetFunctionCPUUsage`. Memory via `UpdateAddOnMemoryUsage` /
`GetAddOnMemoryUsage`. Blizzard added a built-in profiler to the AddOns list during 11.x; the
exact CVar defaults shifted in that era, so verify against the live client rather than assuming.

Rules that matter:

- **Minimize garbage.** Lua GC pauses become frame hitches. No table, closure, or string-concat
  allocation inside `OnUpdate` or high-frequency events.
- **Recycle tables.** Keep a pool and `wipe(t)` rather than allocating per event. Reuse one
  closure rather than creating handlers in a loop.
- **Throttle and filter.** `RegisterUnitEvent` over broad events; coalesce bursts (accumulate
  `UNIT_AURA` and update once per tick).
- **Anti-patterns:** unthrottled `OnUpdate`; timer polling where an event exists; string building
  in hot paths; giant global tables; registrations never removed; work performed while the frame
  is hidden.

Rough refactor trigger: >~1ms/frame or growing memory means go event-driven and start recycling
before adding features.

## Testing

WoW has no headless client, so testing splits in two:

- **Out-of-game CI** - `busted` (LuaJIT/5.1) with hand-written WoW API mocks, `luacov` for
  coverage, often in a container image, wired into GitHub Actions. This covers **pure logic only**:
  parsing, data transforms, state machines.
- **In-game** - WoWUnit / wowUnit run suites via slash command inside the client with API-mocking
  hooks.

UI behaviour and secure/taint correctness cannot be tested outside the client. Say so rather than
implying coverage you do not have.

## Packaging

The **BigWigs packager** (`BigWigsMods/packager`) is the community standard. `release.sh` builds a
zip from a Git checkout, substitutes `@localization@` and version keywords, fetches externals,
generates multi-flavor TOCs (`-S`), and uploads to CurseForge, WoWInterface, Wago, and GitHub
Releases.

GitHub Action: `uses: BigWigsMods/packager@v2` after `actions/checkout@v4` with
`fetch-depth: 0`. Trigger release builds on tag pushes, alpha builds on commits.

`.pkgmeta` directives: `package-as`, `externals` (embed Ace3 and other libs), `ignore`,
`move-folders`, `enable-nolib-creation`, `enable-toc-creation`, `manual-changelog`,
`required-dependencies`, `embedded-libraries`.

Repository secrets: `CF_API_KEY` (CurseForge API tokens page), `WOWI_API_TOKEN`,
`WAGO_API_TOKEN` (`addons.wago.io/account/apikeys`), plus the default `GITHUB_TOKEN`. Project IDs
go in the TOC as `X-Curse-Project-ID` (from the project page's About Project box), `X-WoWI-ID`
(from the addon URL), `X-Wago-ID` (developer dashboard).

Every interface value across your TOC files is reported as a supported game version on upload
(packager v2.3+). CurseForge can host retail and classic in one project but does not auto-package
both; WoWInterface needs separate projects per flavor.

## Blizzard's addon policy

Durable rules, worth checking any design against:

- Free of charge.
- Code fully visible - no obfuscation.
- No advertisements, no in-game solicitation of donations.
- No offensive material; abide by the EULA/ToU.
- Blizzard reserves the right to disable addon functionality at will - which is exactly what
  Midnight's disarmament exercised.

Paywalling features or nagging for donations in-game is the fastest route to being actioned.
Out-of-game Patreon and CurseForge reward points sit in a tolerated grey area. Automation that
plays the game, or reading now-secret combat data through an exploit, risks bans for users and
removal for the addon.
