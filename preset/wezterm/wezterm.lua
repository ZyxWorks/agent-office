-- Agent Office WezTerm example. Optional: the office runs in any terminal; this one gives the
-- daily look and Mac text keys. Copy it to ~/.config/wezterm/wezterm.lua, or take the parts
-- you want into your own. Font, size and transparency are yours; examples are commented below.
local wezterm = require("wezterm")

local config = wezterm.config_builder()

-- Zyx look: monochrome on #0B0C10, warm-white #F6F5F1, brass #C9903F only for the cursor.
-- Same ANSI palette as theme/iterm-office-theme.json.
config.colors = {
	foreground = "#c9cad0",
	background = "#0b0c10",
	cursor_bg = "#c9903f",
	cursor_fg = "#0b0c10",
	cursor_border = "#c9903f",
	selection_bg = "#2a2d36",
	selection_fg = "#f6f5f1",
	ansi = { "#1c1e26", "#b16c6f", "#769a78", "#8b886a", "#768eac", "#9582a4", "#6a9494", "#c9cad0" },
	brights = { "#4e505a", "#c18286", "#8cb08e", "#a99e80", "#8aa2be", "#a897b6", "#82abab", "#f6f5f1" },
}
-- config.font = wezterm.font("GeistMono Nerd Font")
-- config.font_size = 15.0
-- config.window_background_opacity = 0.9
-- config.macos_window_background_blur = 50
config.hide_tab_bar_if_only_one_tab = true
-- No alert sound on terminal bells: every agent pane rings one when it finishes. herdr plays the
-- one "needs you" sound.
config.audible_bell = "Disabled"
-- A real macOS title bar, like iTerm2: double-click it to zoom, drag it to move.
config.window_decorations = "TITLE | RESIZE"

-- Open straight into the persistent herdr session (it restores tabs and agent chats).
-- herdr exits on detach (Ctrl+Space d with the preset) or if it is missing or cannot start:
-- fall back to a normal shell, never a dead window. A login shell finds herdr on your PATH.
local shell = os.getenv("SHELL") or "/bin/sh"
config.default_prog = { shell, "-lc", "herdr; exec " .. shell .. " -l" }

-- Mac text keys, like iTerm2's "Natural Text Editing": sent as the readline keys that Claude
-- Code, Codex and zsh all read. WezTerm has no such mapping of its own, so without these Cmd and
-- Option arrows do nothing useful in an agent's prompt. The herdr preset binds none of these
-- bytes, so they pass through herdr to the agent; preset/preset-probe checks both sides.
config.keys = {
	{ key = "LeftArrow", mods = "CMD", action = wezterm.action.SendString("\x01") }, -- line start
	{ key = "RightArrow", mods = "CMD", action = wezterm.action.SendString("\x05") }, -- line end
	{ key = "LeftArrow", mods = "OPT", action = wezterm.action.SendString("\x1bb") }, -- word back
	{ key = "RightArrow", mods = "OPT", action = wezterm.action.SendString("\x1bf") }, -- word forward
	{ key = "Backspace", mods = "CMD", action = wezterm.action.SendString("\x15") }, -- delete line
	{ key = "Backspace", mods = "OPT", action = wezterm.action.SendString("\x17") }, -- delete word
}

-- Dim unfocused windows so the focused one is obvious at a glance.
local UNFOCUSED_FOREGROUND_TEXT_HSB = { hue = 1.0, saturation = 0.25, brightness = 0.45 }
local UNFOCUSED_WINDOW_BACKGROUND_OPACITY = 0.62

-- get_config_overrides() hands back a copy, so the current value is never the
-- same table we last stored; compare the fields instead of the identity.
local function same_text_hsb(actual, expected)
	if actual == nil or expected == nil then
		return actual == expected
	end
	return actual.hue == expected.hue
		and actual.saturation == expected.saturation
		and actual.brightness == expected.brightness
end

wezterm.on("window-focus-changed", function(window)
	local overrides = window:get_config_overrides() or {}
	local text_hsb, opacity
	if not window:is_focused() then
		text_hsb = UNFOCUSED_FOREGROUND_TEXT_HSB
		opacity = UNFOCUSED_WINDOW_BACKGROUND_OPACITY
	end

	-- Only write when one of the two values we own actually changes; a redundant
	-- set_config_overrides() call would trigger another config reload.
	if same_text_hsb(overrides.foreground_text_hsb, text_hsb) and overrides.window_background_opacity == opacity then
		return
	end

	overrides.foreground_text_hsb = text_hsb
	overrides.window_background_opacity = opacity
	window:set_config_overrides(overrides)
end)

return config
