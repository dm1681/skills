# Events, widgets, and options UI

## The event model

```lua
local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:RegisterUnitEvent("UNIT_AURA", "player", "target")   -- filtered, much cheaper

f:SetScript("OnEvent", function(self, event, ...)
    if self[event] then self[event](self, ...) end     -- method-per-event dispatch
end)

function f:PLAYER_LOGIN() print("ready") end
```

`RegisterUnitEvent` only fires for the named units. Prefer it over the unfiltered form for every
`UNIT_*` event - it is the cheapest performance win available.

Unregister when idle. A hidden frame with live registrations still burns CPU on every dispatch.

## `OnUpdate` and throttling

`OnUpdate` runs every rendered frame and is the main performance foot-gun in the ecosystem. Prefer
an event. When you genuinely must poll, throttle:

```lua
local acc = 0
frame:SetScript("OnUpdate", function(self, elapsed)
    acc = acc + elapsed
    if acc < 0.1 then return end
    acc = 0
    -- runs at most every 100ms
end)
```

## Frames and regions

`CreateFrame(frameType, name, parent, template)`. Types include `Frame`, `Button`, `StatusBar`,
`CheckButton`, `Slider`, `EditBox`, `ScrollFrame`, `Cooldown`, `GameTooltip`. The `name` argument
is optional - **omit it** unless something genuinely needs a global handle, to avoid `_G`
pollution.

Drawing primitives are regions, not frames:

- `frame:CreateTexture(name, layer)` for icons, bars, backgrounds. Layers: `BACKGROUND`,
  `ARTWORK`, `OVERLAY`.
- `frame:CreateFontString(name, layer, inherits)` for text, inheriting a font object such as
  `GameFontNormal`, or configured with `SetFont`.

## Layout

- `frame:SetPoint(point, relativeTo, relativePoint, x, y)`, `SetAllPoints`, `ClearAllPoints`.
  Anchors are relational and propagate.
- `frame:SetFrameStrata("MEDIUM" | "HIGH" | "TOOLTIP" | ...)` for coarse z-ordering,
  `frame:SetFrameLevel(n)` within a strata.

## Templates, intrinsics, mixins

XML `<templates>` and Blizzard-provided templates (`BackdropTemplate`, `UIPanelButtonTemplate`,
`SecureUnitButtonTemplate`) supply reusable layout and behaviour. "Intrinsics" are engine-level
frame subtypes.

The current Blizzard-style OOP idiom is the mixin: define a table of methods, then attach it.

```lua
MyBarMixin = {}
function MyBarMixin:OnLoad() self:SetMinMaxValues(0, 1) end
function MyBarMixin:SetPercent(p) self:SetValue(p) end

local bar = CreateFrame("StatusBar", nil, UIParent)
Mixin(bar, MyBarMixin)
bar:OnLoad()
```

XML supports `mixin="MyBarMixin"` with an automatic `OnLoad`. Prefer mixins over the old
global-function-per-frame style.

## XML versus pure Lua

Both are valid. Pure Lua diffs, versions, and generates more easily. XML integrates with templates
and intrinsics and gets better language-server support. A common modern split: minimal XML for
templates only, everything else in Lua.

## Options panel - the modern Settings API

Dragonflight 10.0 introduced it; 11.0.2 revised it. `InterfaceOptions_AddCategory` is deprecated.

```lua
local category = Settings.RegisterVerticalLayoutCategory("My AddOn")

local setting = Settings.RegisterAddOnSetting(
    category, "MYADDON_ENABLED", "enabled", MyAddonDB,
    type(true), "Enable feature", true)
Settings.CreateCheckbox(category, setting, "Turns the feature on.")

Settings.RegisterAddOnCategory(category)
-- later: Settings.OpenToCategory(category:GetID())
```

Use `Settings.RegisterCanvasLayoutCategory(frame, name)` when you need a fully custom panel.
`Settings.CreateSlider` and `Settings.CreateDropdown` cover the other common controls.

If you are already on Ace3, AceConfig-3.0 generates both a Settings panel and slash-command
config from one declarative options table.

## Edit Mode

Blizzard's Edit Mode manages movable UI from Dragonflight onward. Custom frames do **not**
participate natively. The community libraries `LibEditMode` (p3lim) and `LibEditModeOverride`
(plusmouse) register your frames into Edit Mode with taint-aware handling. This is the
recommended path for anything movable, and strictly better than hand-rolling drag handlers that
fight Blizzard's positioning.
