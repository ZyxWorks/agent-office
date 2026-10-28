-- office: the editor pane's colours, the office palette (theme/office-theme.tmux.conf and the
-- preset's [theme.custom]). State is tone, not hue. Amber means "this needs you" and red means
-- "act on this", so here they mark only warnings and errors. The quiet code colours are the
-- Claude Code theme's (setup/claude/themes/office.json), so the editor sits beside an agent
-- without a third look.
vim.cmd("highlight clear")
if vim.fn.exists("syntax_on") == 1 then
  vim.cmd("syntax reset")
end
vim.g.colors_name = "office"
vim.o.background = "dark"

local c = {
  bg = "#0b0c10",      -- ink
  band = "#0e1016",    -- the sidebar
  panel = "#16181f",   -- panels, the cursor line
  raised = "#2a2d36",  -- a selection
  faint = "#4e505a",   -- hairlines only, never text
  dim = "#6a6c77",     -- the contrast floor for small text
  kicker = "#8a8d96",
  muted = "#9a9ca6",
  ink = "#f6f5f1",     -- text
  accent = "#C9903F",  -- needs you
  alarm = "#C25450",   -- act on this
  green = "#68866a",   -- the Claude theme's success: strings, added lines
  blue = "#768eac",    -- its permission blue: numbers and constants
  olive = "#8b886a",   -- its warning olive: preprocessor and special
  rose = "#b16c6f",    -- its error rose: removed lines, softer than alarm
  add_bg = "#162e1f",
  del_bg = "#401c21",
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
  WarningMsg = { fg = c.accent },
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
  PreProc = { fg = c.olive },
  Include = { fg = c.muted },
  Define = { fg = c.olive },
  Macro = { fg = c.olive },
  Type = { fg = c.kicker },
  StorageClass = { fg = c.muted },
  Structure = { fg = c.kicker },
  Typedef = { fg = c.kicker },
  Special = { fg = c.olive },
  SpecialChar = { fg = c.olive },
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

  -- diagnostics: the office ladder, amber then red
  DiagnosticError = { fg = c.alarm },
  DiagnosticWarn = { fg = c.accent },
  DiagnosticInfo = { fg = c.muted },
  DiagnosticHint = { fg = c.dim },
  DiagnosticOk = { fg = c.green },
  DiagnosticUnderlineError = { sp = c.alarm, undercurl = true },
  DiagnosticUnderlineWarn = { sp = c.accent, undercurl = true },
  DiagnosticUnderlineInfo = { sp = c.muted, underline = true },
  DiagnosticUnderlineHint = { sp = c.dim, underline = true },

  -- diffs and git signs
  DiffAdd = { bg = c.add_bg },
  DiffDelete = { fg = c.rose, bg = c.del_bg },
  DiffChange = { bg = c.panel },
  DiffText = { bg = c.raised },
  Added = { fg = c.green },
  Changed = { fg = c.olive },
  Removed = { fg = c.rose },
  MiniDiffSignAdd = { fg = c.green },
  MiniDiffSignChange = { fg = c.olive },
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
  NvimTreeGitDirtyIcon = { fg = c.olive },
  NvimTreeGitStagedIcon = { fg = c.green },
  NvimTreeGitNewIcon = { fg = c.green },
  NvimTreeGitDeletedIcon = { fg = c.rose },
  NvimTreeGitRenamedIcon = { fg = c.olive },
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
local term = { c.bg, c.alarm, c.green, c.accent, c.blue, c.kicker, c.olive, c.muted,
               c.faint, c.alarm, c.green, c.accent, c.blue, c.kicker, c.olive, c.ink }
for i, v in ipairs(term) do
  vim.g["terminal_color_" .. (i - 1)] = v
end
