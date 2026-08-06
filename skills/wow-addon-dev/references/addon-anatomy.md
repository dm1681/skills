# Addon anatomy: TOC, lifecycle, persistence

## Location and naming

```
World of Warcraft/_retail_/Interface/AddOns/MyAddon/
    MyAddon.toc      <- base name MUST equal the folder name
    Core.lua
```

## TOC format

`## Directive: Value` for metadata, `# ...` for comments, bare relative paths for the file list
(loaded top to bottom). Backslashes are the recommended subpath separator. The client reads only
the first 1024 characters of each line.

### Required

```
## Interface: 120007
```

Verify the number with `/dump select(4, GetBuildInfo())` - never copy it from memory or a
tutorial. Multiple comma-delimited versions support one TOC across flavors:

```
## Interface: 120007, 50504, 11508
```

`C_AddOns.GetAddOnInterfaceVersion` returns the closest listed value at or below the running
client's.

### Common metadata

`## Title`, `## Notes`, `## Version`, `## Author`, `## IconTexture` / `## IconAtlas`,
`## Category` (use the standard localized category names), `## Group`, and `## X-*` custom fields.
Packaging needs `## X-Curse-Project-ID`, `## X-Wago-ID`, `## X-WoWI-ID`.

### Loading control

`## Dependencies` (hard, must load first), `## OptionalDeps`, `## LoadOnDemand: 1`, `## LoadWith`,
`## LoadManagers`, `## DefaultState: disabled`, `## AllowLoadGameType: mainline`.

### SavedVariables

```
## SavedVariables: MyAddonDB
## SavedVariablesPerCharacter: MyAddonCharDB
## LoadSavedVariablesFirst: 1
```

The values are *global variable names*. `LoadSavedVariablesFirst` loads them before your script
files rather than after.

### Conditional directives (11.1.5+)

Per-line conditions and path variables let one TOC serve several clients:

```
MainlineOnly.lua [AllowLoadGameType mainline]
[Family]\File.lua
Localization\[TextLocale].lua
EUOnly.lua [AllowLoadTextLocale enUS, frFR]
```

### Multi-flavor alternative

Separate `MyAddon_Mainline.toc`, `MyAddon_Vanilla.toc`, `MyAddon_Cata.toc`, `MyAddon_Mists.toc`
files. Prefer comma-delimited interfaces or conditional directives where possible - fewer files
to keep in sync.

### Addon compartment

```
## AddonCompartmentFunc: MyAddon_OnClick
```

Adds an entry to the minimap addon dropdown - a lighter alternative to a minimap button library.

## Load and login order

1. Files load top-to-bottom per the TOC.
2. SavedVariables are injected into the declared globals.
3. **`ADDON_LOADED`** fires with the addon name as payload. This is the earliest point you can
   read your SavedVariables, and where defaults belong.
4. **`PLAYER_LOGIN`** fires once, after all non-LoadOnDemand addons have loaded and most game data
   is available. Standard place for one-time init that needs game state.
5. **`PLAYER_ENTERING_WORLD`** fires right after login *and again on every loading screen*
   (zoning, instances, `/reload`). Payload: `isInitialLogin, isReload`. Never put unguarded
   one-time init here.

Combat boundaries: `PLAYER_REGEN_DISABLED` (entering lockdown) and `PLAYER_REGEN_ENABLED`
(leaving it).

## Persistence details

Account-wide files live at
`WTF/Account/<ACCOUNT>/SavedVariables/<AddOn>.lua`; per-character at
`WTF/Account/<ACCOUNT>/<Realm>/<Character>/SavedVariables/<AddOn>.lua`. They are plain Lua tables.

They are written **only** on clean logout, `/reload`, or exit. A client crash loses the session's
changes - do not treat a write as durable the moment you make it.

The SV global is `nil` on the very first run, so initialize on `ADDON_LOADED`:

```lua
local ADDON_NAME = ...

local f = CreateFrame("Frame")
f:RegisterEvent("ADDON_LOADED")
f:SetScript("OnEvent", function(self, event, name)
    if name ~= ADDON_NAME then return end
    MyAddonDB = MyAddonDB or {}
    MyAddonDB.scale = MyAddonDB.scale or 1.0
    self:UnregisterEvent("ADDON_LOADED")
end)
```

AceDB-3.0 handles defaults, profiles, and namespaces for you if you would rather not hand-roll it.

## Slash commands

```lua
SLASH_MYADDON1 = "/myaddon"
SLASH_MYADDON2 = "/ma"
SlashCmdList["MYADDON"] = function(msg, editBox)
    print("MyAddon:", msg)
end
```

The key in `SlashCmdList` must match the `SLASH_<KEY>n` suffix. Pick a token unlikely to collide.
