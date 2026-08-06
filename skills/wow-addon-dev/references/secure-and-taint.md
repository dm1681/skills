# Taint, secure templates, and unit frames

This is the older of the two security systems and remains fully in force *in addition to* secret
values. Everything here predates Midnight and applies on every flavor.

## Protected frames and combat lockdown

Certain actions - casting, targeting, showing or moving protected frames - can only happen on a
secure execution path. Protected frames are **locked down** between `PLAYER_REGEN_DISABLED` and
`PLAYER_REGEN_ENABLED`: you cannot show, hide, resize, re-anchor, or change attributes on them,
or on anything in their parent/anchor chain.

Test with `InCombatLockdown()`. The standard pattern is to queue work and flush it on regen:

```lua
local pending = false
local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_REGEN_ENABLED")
f:SetScript("OnEvent", function()
    if pending then pending = false; ApplyLayout() end
end)

function Reconfigure()
    if InCombatLockdown() then pending = true return end
    ApplyLayout()
end
```

## Taint

Execution begins secure - Blizzard-signed code. The instant execution touches addon code or addon
data, it becomes **tainted**, and anything tainted code writes becomes tainted too. If a tainted
execution path reaches a protected function, the call is blocked and the user sees "Interface
action failed because of an AddOn". Taint persists until `/reload` or relog.

The classic cause is taint *spreading into Blizzard's own frames* - writing to a global Blizzard
reads, or triggering Blizzard code from inside your event handler. The resulting errors are
intermittent and famously hard to trace, and they get blamed on whichever addon happened to be
loaded, not necessarily yours.

`hooksecurefunc(name, handler)` appends your tainted hook *after* a secure function without
tainting the original path. Use it instead of replacing Blizzard functions.

## Secure templates

For anything that must act during combat, use Blizzard's secure templates and the restricted
environment:

| Template | Purpose |
| --- | --- |
| `SecureActionButtonTemplate` | Click-casting |
| `SecureUnitButtonTemplate` | Unit frames |
| `SecureGroupHeaderTemplate` | Auto-generated party/raid member buttons |
| `SecurePartyHeaderTemplate`, `SecureRaidGroupHeaderTemplate` | Specialized group headers |
| `SecureHandlerStateTemplate` | Secure snippets - small sandboxed Lua that *can* run in combat |

Plus the secure state-driver API: `RegisterUnitWatch`, `RegisterStateDriver`.

## A minimal secure unit frame

```lua
local f = CreateFrame("Button", "MyTargetFrame", UIParent, "SecureUnitButtonTemplate")
f:SetAttribute("unit", "target")
f:SetAttribute("type1", "target")       -- left click targets
f:SetAttribute("type2", "togglemenu")   -- right click opens the unit menu
f:RegisterForClicks("AnyUp")
f:SetSize(120, 40)
f:SetPoint("CENTER")
RegisterUnitWatch(f)                    -- secure show/hide by unit existence
```

Every line of that must run **out of combat**. `RegisterUnitWatch` is what lets the frame appear
and disappear during a fight without your code touching it.

## Arena and enemy frames

This is the hard case, and worth being blunt about with anyone attempting it.

The clickable, targetable frame is still fully buildable: a secure button configured before the
match starts, shown by `RegisterUnitWatch`. You cannot create it, re-anchor it, or reconfigure it
once lockdown begins.

The *intelligent overlay* - what CC is on the enemy, which defensive they popped, DR tracking - is
exactly the class of information Midnight made secret during PvP matches. See
[midnight-restrictions.md](midnight-restrictions.md). Historical addons in this space (Gladius,
GladiusEx, sArena) built that layer on data that is no longer readable.

## Categories blocked by taint alone

Independent of secret values, these do not work and never did:

- Creating or moving action/unit buttons in combat.
- Programmatic targeting or casting sequences.
- Automated ability selection - rotation bots.
- Repositioning protected frames mid-fight.

If an idea requires any of the above, redesign rather than search for a workaround; there isn't
one, and the ones people claim exist ship intermittent "action blocked" errors to users.

## Building on existing work

`oUF` is the established framework for unit frames built on secure headers, and absorbs most of
the lockdown-correctness work. Read it before writing a unit frame from scratch.
