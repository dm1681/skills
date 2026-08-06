# Secret values and "addon disarmament" (Midnight, 12.0.x)

> **This is the fastest-moving area of the WoW API.** The content below was verified against
> patch 12.0.7 "Revelations", Interface 120007, in August 2026. Blizzard has stated the ruleset is
> not set in stone, and the exact whitelists shift per patch. Before relying on any specific
> behaviour here, re-read the current `warcraft.wiki.gg` "Patch <version>/API changes" page.

## The principle

Blizzard's stated goal, from Game Director Ion Hazzikostas in the Blizzard News article "Combat
Philosophy and Addon Disarmament in Midnight": addons should no longer offer a competitive
advantage in combat. Combat state is treated as a black box - addons can change the box's size,
shape, and colour, but cannot look inside it.

The argument is that addons had shifted from *displaying* information to *processing* it into
combat decisions, which forced Blizzard to design encounters and classes around addon assistance
and disadvantaged players who did not use them.

## The mechanism

Combat-state APIs (`UnitHealth`, aura and cooldown queries, cast info on other units) return
**secret values** when called on a tainted path. Tainted code may **store and pass** a secret. It
may not:

- do arithmetic on it
- concatenate it
- compare it or use it in a boolean test
- take its length
- index it
- use it as a table key
- call it

Any of those raises an immediate Lua error. There is no soft-fail to inspect.

A limited whitelist of widget setters accepts secrets so the UI still works - `StatusBar:SetValue(secret)`
being the canonical example - tracked internally as "secret aspects" and "secret anchors".

**Curves and ColorCurves** (`C_CurveUtil`) are the sanctioned escape hatch: they map a secret
number onto an output (for instance a health bar's green-to-red colour) without the addon ever
reading the input. If a design needs "display changes based on a combat value", this is the
mechanism to reach for.

Detection helpers: `issecretvalue`, `canaccesssecrets`, `canaccessvalue`, `issecrettable`.
Namespaces: `C_Secrets` (`ShouldUnitHealthMaxBeSecret`, `ShouldAurasBeSecret`, ...) and
`C_RestrictedActions`. Event: `ADDON_RESTRICTION_STATE_CHANGED`.

## The combat log is gone

`COMBAT_LOG_EVENT_UNFILTERED` and `COMBAT_LOG_EVENT` **error on `RegisterEvent`**. The
`CombatLog*` accessor functions, including `CombatLogGetCurrentEventInfo`, were removed from the
addon surface. Combat-log chat output is now unparseable "KStrings".

Replacements Blizzard shipped are outcome-oriented rather than event-stream:

- `UNIT_DIED`, `PARTY_KILL`, `PLAYER_TARGET_DIED`, `UNIT_LOOT`
- `DAMAGE_METER_*` events fed by Blizzard's built-in, server-validated damage meter
- `COMBAT_LOG_EVENT_INTERNAL_UNFILTERED`, described by addon developers as restricted to Blizzard
  code. *(Attested by developers, not by a verbatim primary source - treat as likely, not
  certain.)*

**Classic flavors are unaffected.** CLEU works there exactly as before. If you package
cross-flavor, this is a behavioural difference, not just an interface-number difference.

## Scope: triggered, not blanket

This nuance matters and is frequently reported wrong.

- **Chat/addon-comms lockdown and cooldown secrecy** apply only while an instance encounter is in
  progress, a Mythic+ run is underway, or a PvP match is active. Blizzard walked back the original
  "entire instance" approach one day into alpha, specifically so that tools sharing information
  *before or after* combat keep working.
- **Aura and unit-combat-state secrecy** additionally binds to a general combat trigger, so it
  activates in ordinary combat too. It is therefore **wrong** to say every secret-value
  restriction is limited to encounters/M+/PvP.
- **Open-world, out-of-combat play is unaffected.**
- **Class secondary resources** (Death Knight Runes, Paladin Holy Power, and so on) were
  deliberately left fully non-secret so custom resource displays keep working.

*(The encounter/M+/PvP scoping is documented explicitly for 12.0.0 and reaffirmed structurally
through 12.0.5, 12.0.7, and 12.1.0. There is no verbatim restatement in the 12.0.7 docs - treat
the live wording as verified-by-structure.)*

## Native replacements

Players did not simply lose these features; Blizzard shipped in-client versions: Cooldown Manager
(early form in 11.1.5, refined in Midnight), Boss Warnings / Encounter Timeline, Assisted
Highlight / One-Button Rotation (11.1.7), Combat Audio Alerts and text-to-speech, improved raid
frames, an External Defensives tracker, and a built-in server-validated Damage Meter. The native
meter does not persist through logout and lacks Details!-level granularity.

## Where the ecosystem landed

- **WeakAuras**: Team WeakAuras announced they do not expect to release a Midnight retail version.
  Their stated reason is that applying secret values to one's *own* combat state - personal buffs,
  resources, cooldowns - makes Conditions, Actions, and cloning triggers impossible, to the point
  that replicating even the built-in Cooldown Manager is impractical. They reaffirmed this after
  Blizzard's partial loosening.
- **Details!** survived with partial combat-data blocking.
- **DBM / BigWigs** adapted around the native boss-timer and warning systems.
- **Nameplate and cosmetic addons** (Plater/Platynator, BetterBlizzFrames/Plates, Plumber)
  continue as visual tools.
- **Recount-style CLEU parsers** are effectively obsolete.

## What this means for a design

Anything that reads or reasons about live combat state in instanced endgame is impossible or
badly constrained: enemy or party auras, cooldowns and casts; "when should I press X" logic; smart
arena/CC/DR trackers; combat-log damage parsing.

Build in the display, out-of-combat, cosmetic, or personal-resource space instead, or lean on the
native systems plus `LibEditMode` and `oUF`.

**Re-scope trigger:** if a future patch loosens *personal* combat-state secrecy, personal cooldown
and aura displays become viable again. Check each patch's API-change page rather than assuming the
state described here still holds.
