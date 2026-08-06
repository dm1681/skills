---
name: wow-addon-dev
description: Build, debug, package, and publish World of Warcraft retail addons - TOC manifests, the event and widget model, SavedVariables, taint and secure templates, the Midnight-era "secret value" restrictions on combat data, Ace3 and the library ecosystem, and BigWigs-packager CI. Use when writing or reviewing Lua for a WoW addon, editing a .toc file, working under Interface/AddOns, debugging taint or "action blocked" errors, judging whether an addon idea is still possible on modern retail, or publishing to CurseForge, Wago, or WoWInterface.
---

# Retail WoW addon development

Retail WoW addons are Lua 5.1 running in a sandbox, driven by events, drawing through frame widgets, and fenced in by two independent security systems. Get the fences right first; everything else is ordinary programming.

## Step 1 - always verify the client build before writing a TOC

Never trust a remembered Interface number. In-game:

```
/dump select(4, GetBuildInfo())
```

That value goes in `## Interface:`. Confirm the current patch's API changes on `warcraft.wiki.gg` (search "Patch <version>/API changes") before relying on any function name, event, or restriction described here. This domain rewrites itself every patch.

## Step 2 - triage feasibility before designing

Two hard walls, both real, both independent:

1. **Taint + combat lockdown** (long-standing). Protected frames and actions cannot be driven by addon code during combat. Unit frames need secure templates and must be fully configured *out* of combat.
2. **Secret values / "addon disarmament"** (Midnight, 12.0.x). Combat state - health, auras, cooldowns, casts - is handed to addons as opaque *secret values*: displayable, not readable. Arithmetic, comparison, concatenation, or indexing on a secret raises a Lua error. `COMBAT_LOG_EVENT_UNFILTERED` errors on `RegisterEvent`.

Do not start here: WeakAuras-style combat decision engines, damage meters / combat-log parsers, smart arena or DR trackers, rotation or auto-interrupt helpers, anything that creates or moves protected frames mid-fight, addon comms during an active encounter/M+/PvP match.

Start here instead: cosmetic and informational displays, out-of-combat tools (bags, currency, quests, professions), personal class-resource displays (secondary resources are deliberately non-secret), and static clickable unit frames built on secure templates.

Read [references/midnight-restrictions.md](references/midnight-restrictions.md) before committing to any design that touches combat.

## Step 3 - scaffold

Copy `assets/skeleton/` into `World of Warcraft/_retail_/Interface/AddOns/<AddonName>/`, rename both files to match the folder, and set `## Interface:` to the value from step 1. The folder name, the `.toc` base name, and the addon name must match exactly.

Validate the manifest before launching the client (resolve the script path relative to this
`SKILL.md`; do not assume a particular install location):

```bash
python scripts/check_toc.py path/to/AddOns/MyAddon
```

It catches folder/TOC name mismatches, malformed Interface versions, listed files that do not
exist, and invalid SavedVariables names. It cannot tell you whether the Interface number is
*current* - only step 1 can.

Then in-game: `/console scriptErrors 1`, install BugGrabber + BugSack, and iterate with `/reload`.

## Step 4 - build

| Task | Read |
| --- | --- |
| Lua 5.1 semantics, sandbox limits, Blizzard helpers | [references/lua-and-sandbox.md](references/lua-and-sandbox.md) |
| TOC directives, load order, SavedVariables, slash commands | [references/addon-anatomy.md](references/addon-anatomy.md) |
| Events, frames, textures, anchoring, Settings API, Edit Mode | [references/events-and-widgets.md](references/events-and-widgets.md) |
| Taint, secure templates, unit and arena frames | [references/secure-and-taint.md](references/secure-and-taint.md) |
| Secret values, what broke, what replaced it | [references/midnight-restrictions.md](references/midnight-restrictions.md) |
| Libraries, debugging tools, profiling, packaging, publishing | [references/tooling-and-publishing.md](references/tooling-and-publishing.md) |

Defaults that keep code out of trouble: everything `local`; prefer events over `OnUpdate` and `RegisterUnitEvent` over broad events; prefer `C_*` namespaced APIs over deprecated flat globals; guard anything frame-mutating with `InCombatLockdown()`; persist through SavedVariables initialized on `ADDON_LOADED`.

## Step 5 - verify and ship

Pure logic (parsers, transforms, math) is testable outside the client with `busted` plus hand-written API mocks. UI and secure behaviour are not - they require manual in-client verification, so say so plainly rather than claiming coverage you do not have. Package with `.pkgmeta` plus the `BigWigsMods/packager` GitHub Action; keep the addon free, unobfuscated, and free of in-game donation prompts per Blizzard's addon policy.
