-- office: the editor pane's colours, the ZyxWorks greys (preset/README.md#theme): the same
-- palette as the preset's [theme.custom] and theme/office-theme.tmux.conf. Ground and text are the
-- @zyxworks/ui dark tokens. A warning is the stone grey and an error the one red, each with nvim's
-- own sign, so neither rests on colour alone. The quiet code colours are the muted ANSI colours,
-- the same as the Claude Code theme (setup/claude/themes/office.json), so the editor sits beside
-- an agent without a third look.
vim.cmd("highlight clear")
if vim.fn.exists("syntax_on") == 1 then
  vim.cmd("syntax reset")
end
vim.g.colors_name = "office"
vim.o.background = "dark"

local c = {
  bg = "#111111",      -- bg
  band = "#171717",    -- surface: the sidebar
  panel = "#1c1c1c",   -- well: panels, the cursor line
  raised = "#2a2a2a",  -- selected: a selection
  faint = "#3a3a3a",   -- line-ctl: hairlines only, never text
  dim = "#8c8c8c",     -- text-3: the contrast floor for small text
  kicker = "#a3a3a3",  -- text-2
  muted = "#a3a3a3",   -- text-2
  ink = "#ededed",     -- text
  accent = "#ededed",  -- accent = ink: needs you
  alarm = "#ff7a6e",   -- bad: act on this
  green = "#8fa894",   -- ANSI 2: strings, added lines
  blue = "#8c9db5",    -- ANSI 4: numbers and constants
  stone = "#a8a196",   -- ANSI 3, a stone grey and not a yellow: preprocessor and special
  rose = "#c98a82",    -- ANSI 1: removed lines, softer than alarm
  add_bg = "#1a231c",
  del_bg = "#2c1d1b",
}

local groups = {
  Normal = { fg = c.ink, bg = c.bg },
  NormalNC = { fg = c.ink, bg = c.bg },
  NormalFloat = { fg = c.ink, bg = c.panel },
  FloatBorder = { fg = c.faint, bg = c.panel },
  FloatTitle = { fg = c.ink, bg = c.panel, bold = true },
  Cursor = { fg = c.bg, bg = c.ink },
  CursorLine = { bg = c.panel },
  CursorColumn = { bg = c.panel },
  ColorColumn = { bg = c.panel },
  LineNr = { fg = c.faint },
  CursorLineNr = { fg = c.ink, bold = true },
  SignColumn = { bg = c.bg },
  FoldColumn = { fg = c.faint, bg = c.bg },
  Folded = { fg = c.muted, bg = c.panel },
  WinSeparator = { fg = c.faint, bg = c.bg },
  VertSplit = { link = "WinSeparator" },
  StatusLine = { fg = c.muted, bg = c.band },
  StatusLineNC = { fg = c.dim, bg = c.band },
  TabLine = { fg = c.dim, bg = c.band },
  TabLineFill = { bg = c.band },
  TabLineSel = { fg = c.ink, bg = c.raised, bold = true },
  WinBar = { fg = c.muted, bg = c.bg },
  WinBarNC = { fg = c.dim, bg = c.bg },
  Visual = { bg = c.raised },
  Search = { fg = c.ink, bg = c.raised, underline = true },
  IncSearch = { fg = c.bg, bg = c.ink },
  CurSearch = { fg = c.bg, bg = c.ink },
  Substitute = { fg = c.bg, bg = c.ink },
  MatchParen = { fg = c.ink, bg = c.raised, bold = true },
  Pmenu = { fg = c.ink, bg = c.panel },
  PmenuSel = { fg = c.ink, bg = c.raised, bold = true },
  PmenuSbar = { bg = c.panel },
  PmenuThumb = { bg = c.faint },
  NonText = { fg = c.faint },
  Whitespace = { fg = c.faint },
  SpecialKey = { fg = c.faint },
  EndOfBuffer = { fg = c.bg },
  Directory = { fg = c.ink },
  Title = { fg = c.ink, bold = true },
  Question = { fg = c.ink },
  MoreMsg = { fg = c.muted },
  ModeMsg = { fg = c.muted },
  MsgArea = { fg = c.muted },
  ErrorMsg = { fg = c.alarm, bold = true },
  WarningMsg = { fg = c.stone, bold = true },
  QuickFixLine = { bg = c.raised },
  WildMenu = { fg = c.ink, bg = c.raised },
  SpellBad = { sp = c.alarm, undercurl = true },
  SpellCap = { sp = c.accent, undercurl = true },
  SpellLocal = { sp = c.muted, undercurl = true },
  SpellRare = { sp = c.muted, undercurl = true },

  -- code: names in ink, the language's own words a step back, comments at the floor
  Comment = { fg = c.dim, italic = true },
  Constant = { fg = c.blue },
  String = { fg = c.green },
  Character = { fg = c.green },
  Number = { fg = c.blue },
  Boolean = { fg = c.blue },
  Float = { fg = c.blue },
  Identifier = { fg = c.ink },
  Function = { fg = c.ink, bold = true },
  Statement = { fg = c.muted },
  Keyword = { fg = c.muted },
  Conditional = { fg = c.muted },
  Repeat = { fg = c.muted },
  Label = { fg = c.muted },
  Exception = { fg = c.muted },
  Operator = { fg = c.kicker },
  PreProc = { fg = c.stone },
  Include = { fg = c.muted },
  Define = { fg = c.stone },
  Macro = { fg = c.stone },
  Type = { fg = c.kicker },
  StorageClass = { fg = c.muted },
  Structure = { fg = c.kicker },
  Typedef = { fg = c.kicker },
  Special = { fg = c.stone },
  SpecialChar = { fg = c.stone },
  Tag = { fg = c.ink },
  Delimiter = { fg = c.kicker },
  SpecialComment = { fg = c.dim, italic = true },
  Underlined = { underline = true },
  Error = { fg = c.alarm },
  Todo = { fg = c.accent, bold = true },
  ["@variable"] = { fg = c.ink },
  ["@variable.builtin"] = { fg = c.muted },
  ["@punctuation"] = { fg = c.kicker },
  ["@markup.heading"] = { fg = c.ink, bold = true },
  ["@markup.link"] = { fg = c.muted, underline = true },
  ["@markup.raw"] = { fg = c.green },

  -- diagnostics: stone for a warning, red for an error, each with its sign
  DiagnosticError = { fg = c.alarm },
  DiagnosticWarn = { fg = c.stone },
  DiagnosticInfo = { fg = c.muted },
  DiagnosticHint = { fg = c.dim },
  DiagnosticOk = { fg = c.green },
  DiagnosticUnderlineError = { sp = c.alarm, undercurl = true },
  DiagnosticUnderlineWarn = { sp = c.stone, undercurl = true },
  DiagnosticUnderlineInfo = { sp = c.muted, underline = true },
  DiagnosticUnderlineHint = { sp = c.dim, underline = true },

  -- diffs and git signs
  DiffAdd = { bg = c.add_bg },
  DiffDelete = { fg = c.rose, bg = c.del_bg },
  DiffChange = { bg = c.panel },
  DiffText = { bg = c.raised },
  Added = { fg = c.green },
  Changed = { fg = c.stone },
  Removed = { fg = c.rose },
  MiniDiffSignAdd = { fg = c.green },
  MiniDiffSignChange = { fg = c.stone },
  MiniDiffSignDelete = { fg = c.rose },
  MiniDiffOverAdd = { bg = c.add_bg },
  MiniDiffOverDelete = { bg = c.del_bg },
  MiniDiffOverChange = { bg = c.panel },
  MiniDiffOverContext = { bg = c.panel },

  -- the picker
  MiniPickNormal = { fg = c.ink, bg = c.panel },
  MiniPickBorder = { fg = c.faint, bg = c.panel },
  MiniPickBorderBusy = { fg = c.muted, bg = c.panel },
  MiniPickBorderText = { fg = c.ink, bg = c.panel, bold = true },
  MiniPickPrompt = { fg = c.ink, bg = c.panel },
  MiniPickMatchCurrent = { bg = c.raised },
  MiniPickMatchRanges = { fg = c.ink, bold = true, underline = true },
  MiniPickMatchMarked = { bg = c.raised, italic = true },
  MiniPickHeader = { fg = c.muted },
  MiniPickPreviewLine = { bg = c.raised },
  MiniPickPreviewRegion = { bg = c.raised },

  -- the file tree, on the sidebar's band like herdr's own
  NvimTreeNormal = { fg = c.ink, bg = c.band },
  NvimTreeNormalNC = { fg = c.ink, bg = c.band },
  NvimTreeEndOfBuffer = { fg = c.band, bg = c.band },
  NvimTreeWinSeparator = { fg = c.faint, bg = c.bg },
  NvimTreeCursorLine = { bg = c.panel },
  NvimTreeRootFolder = { fg = c.muted, bold = true },
  NvimTreeFolderName = { fg = c.ink },
  NvimTreeOpenedFolderName = { fg = c.ink, bold = true },
  NvimTreeEmptyFolderName = { fg = c.muted },
  NvimTreeFolderArrowClosed = { fg = c.dim },
  NvimTreeFolderArrowOpen = { fg = c.dim },
  NvimTreeIndentMarker = { fg = c.faint },
  NvimTreeOpenedHL = { bold = true },
  NvimTreeSymlink = { fg = c.muted, italic = true },
  NvimTreeExecFile = { fg = c.ink },
  NvimTreeSpecialFile = { fg = c.ink },
  NvimTreeGitDirtyIcon = { fg = c.stone },
  NvimTreeGitStagedIcon = { fg = c.green },
  NvimTreeGitNewIcon = { fg = c.green },
  NvimTreeGitDeletedIcon = { fg = c.rose },
  NvimTreeGitRenamedIcon = { fg = c.stone },
  NvimTreeGitMergeIcon = { fg = c.accent },
  NvimTreeGitIgnoredIcon = { fg = c.faint },
  NvimTreeGitFileDirtyHL = { fg = c.ink },
  NvimTreeGitFileNewHL = { fg = c.ink },
  NvimTreeGitFolderDirtyHL = { fg = c.ink },
  NvimTreeGitFolderNewHL = { fg = c.ink },
}

for name, spec in pairs(groups) do
  vim.api.nvim_set_hl(0, name, spec)
end

-- the 16 terminal colours, for :terminal: the same tones, red and yellow on the ladder
local term = { "#2a2a2a", "#c98a82", "#8fa894", "#a8a196", "#8c9db5", "#aa97b0", "#88a8a8", "#a3a3a3",
               "#8c8c8c", "#ff7a6e", "#aec2b2", "#c4beb4", "#aab8cc", "#c3b3c8", "#a8c2c2", "#ededed" }
for i, v in ipairs(term) do
  vim.g["terminal_color_" .. (i - 1)] = v
end
