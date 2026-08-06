# Lua 5.1 in the WoW sandbox

WoW runs Lua 5.1 plus a handful of Blizzard extensions. If you arrive from Python or a modern
Lua, these are the differences that actually cause bugs.

## Language traps

- **Tables are the only data structure.** Arrays, dicts, objects, namespaces, and classes are all
  tables. There is no separate list/dict/set/tuple.
- **1-based indexing.** `t[1]` is first. `ipairs` stops at the first `nil` hole; `#t` is only
  well-defined for hole-free sequences.
- **Globals are the default.** Always write `local`. Undeclared names land in `_G`, where they
  collide with other addons and become a taint vector.
- **Only `nil` and `false` are falsy.** `0` and `""` are truthy. This is the single most common
  Python-brain bug.
- **`nil` deletes.** Assigning `nil` removes the key; reading a missing key returns `nil` rather
  than raising.
- **`a and b or c` is the ternary** - but it breaks when `b` is `false` or `nil`.
- **Multiple return values, not tuples.** `local a, b = f()`. `{f()}` collects them, but stops
  early on embedded `nil`s.
- **Varargs `...` are everywhere.** Event handlers receive payloads as varargs. Use
  `select("#", ...)` to count and `select(n, ...)` to slice.
- **Lua patterns are not regex.** `%` introduces classes (`%d`, `%a`, `%s`), `-` is the lazy
  quantifier. No alternation, no lookahead, no groups-as-alternatives. Functions:
  `string.match`, `gmatch`, `gsub`, `find`.
- **Missing from 5.1:** integer division `//`, `goto`, native bitwise operators. Use
  `math.floor` and Blizzard's `bit` library (`bit.band`, `bit.bor`, `bit.lshift`).
- **Metatables** provide operator overloading and prototype inheritance. `setmetatable(obj,
  {__index = Class})` is the OOP backbone; `__index`, `__newindex`, `__call` are the ones you
  will actually reach for.
- **Closures capture upvalues by reference** and are used far more heavily than in most
  languages, because every event handler and callback is one.

## What the sandbox removes

No `io`, no `require`/`package`/`dofile`/`loadfile`, no `loadstring`/`load` for arbitrary runtime
code, no sockets, no filesystem. `os` is reduced to a whitelist (`time`, `date`, `clock`,
`difftime`). `debug` is heavily restricted.

Consequences worth stating out loud when someone asks for them: an addon cannot self-update,
cannot read or write arbitrary files, cannot phone home, and cannot execute code it downloaded.
The **only** persistence is SavedVariables.

## What the sandbox adds

- The global WoW API (`UnitHealth`, `CreateFrame`, `GetTime`, ...).
- The widget API - methods on frame objects.
- The event system.
- `C_*` namespaced API tables.
- Helpers: `strsplit`, `strjoin`, `tContains`, `wipe(t)`, `CopyTable`, `Mixin`,
  `CreateFromMixins`, `tinsert`/`tremove` aliases, `format`/`gsub` aliases.

## The `C_*` migration

Blizzard has spent several expansions moving flat globals into namespaced tables:

| Legacy global | Modern namespace |
| --- | --- |
| `GetSpellCooldown` | `C_Spell.GetSpellCooldown` |
| `GetContainerItemInfo` | `C_Container.GetContainerItemInfo` |
| `UnitAura` and friends | `C_UnitAuras.*` |

Many legacy globals survive as deprecated shims (see `Blizzard_Deprecated.lua` in the exported UI
source), but new code should not depend on them - Midnight's 12.0 removed a large batch outright.
When you are unsure of the current canonical name, check the function's page on
`warcraft.wiki.gg`, which annotates the introducing and removing patch.

## Finding ground truth

1. **`warcraft.wiki.gg`** - the community standard, successor to Wowpedia. Per-patch API change
   pages are the highest-value resource. Community-maintained, so cross-check version-sensitive
   claims.
2. **Blizzard news and patch notes** - highest authority for policy and upcoming changes.
3. **Blizzard's own exported UI source** - ground truth for how the default UI works. Get it via
   `ExportInterfaceFiles code` typed into the console at the login/character-select screen, or
   read the maintained mirror `Gethe/wow-ui-source` (branch `live`). The older
   `tekkub/wow-ui-source` is stale; do not use it.

Avoid pre-2024 tutorials for anything version-sensitive.
