-- Skeleton retail addon.
-- Rename the folder, this addon's .toc, and every MyAddon* identifier together.
-- Set ## Interface to the value of: /dump select(4, GetBuildInfo())

local ADDON_NAME, ns = ...  -- addon name, plus a private namespace table shared across files

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")

frame:SetScript("OnEvent", function(self, event, ...)
    if self[event] then
        self[event](self, ...)
    end
end)

-- Earliest point SavedVariables are readable. Initialize defaults here.
function frame:ADDON_LOADED(name)
    if name ~= ADDON_NAME then return end

    MyAddonDB = MyAddonDB or {}
    MyAddonDB.logins = (MyAddonDB.logins or 0) + 1

    ns.db = MyAddonDB
    self:UnregisterEvent("ADDON_LOADED")
end

-- Fires once, after all addons have loaded and game state is available.
function frame:PLAYER_LOGIN()
    print(("|cff00ff00%s|r loaded. Logins: %d"):format(ADDON_NAME, ns.db.logins))
end

SLASH_MYADDON1 = "/myaddon"
SLASH_MYADDON2 = "/ma"
SlashCmdList["MYADDON"] = function(msg)
    print(ADDON_NAME .. ":", msg ~= "" and msg or "(no args)")
end
