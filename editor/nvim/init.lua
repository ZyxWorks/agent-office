-- The editor pane's Neovim config: `office editor` starts nvim with it (`nvim -u` this file),
-- so your own ~/.config/nvim is never read or changed. Small on purpose: a file tree, fuzzy
-- find, git signs, the office colours, and one key for the files the agent changed.
--
-- The plugins are two, at the commits config/components.toml pins ([[nvim_plugin]]).
-- `office install` checks them out into the folder AGENT_OFFICE_NVIM_PACK names; nothing in
-- here fetches, updates or installs anything. Without them it still starts, with the colours,
-- the changed-files list (in the quickfix window) and nvim's own netrw for files.
--
-- Keys (leader is Space):
--   Space e   file tree            Space f   find a file       Space /   search the text
--   Space c   files changed here   Space b   open buffers      Space g   show the git changes inline
--   ]h / [h   next / previous change in this file              q in the tree: close it

local here = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h")
vim.opt.runtimepath:prepend(here) -- colors/office.lua
local pack = vim.env.AGENT_OFFICE_NVIM_PACK
if pack and pack ~= "" then
  vim.opt.packpath:prepend(pack)
end

vim.g.mapleader = " "
vim.g.maplocalleader = " "

local o = vim.opt
o.number = true
o.signcolumn = "yes"
o.cursorline = true
o.termguicolors = true
o.mouse = "a"
o.clipboard = "unnamedplus"
o.ignorecase = true
o.smartcase = true
o.splitright = true
o.splitbelow = true
o.scrolloff = 4
o.laststatus = 3
o.showmode = false
o.undofile = true
o.updatetime = 250
o.expandtab = true
o.shiftwidth = 2
o.tabstop = 2
o.wrap = false
o.fillchars = { eob = " ", vert = "│" }
-- the agent writes these files while you read them: take its changes in as they land
o.autoread = true

vim.cmd.colorscheme("office")

-- One status line for the pane: the file, from the worktree, and where the cursor is. The tree
-- and the picker are named for what they are, not by their buffer names.
function _G.office_status()
  local ft = vim.bo.filetype
  if ft == "NvimTree" then
    return " files  " .. vim.fn.fnamemodify(vim.fn.getcwd(), ":t")
  elseif ft == "minipick" then
    return " pick"
  end
  local name = vim.fn.expand("%:~:.")
  return " " .. (name == "" and "[no file]" or name) .. (vim.bo.modified and " +" or "")
    .. (vim.bo.readonly and " (read-only)" or "") .. "%=%l:%c "
end
o.statusline = "%!v:lua.office_status()"

local function has(name)
  return pcall(vim.cmd.packadd, name)
end

-- Every few seconds and on focus, read files the agent changed on disk. A buffer you changed
-- yourself is never overwritten: nvim asks first, as it always does.
local timer = vim.uv.new_timer()
timer:start(2000, 2000, vim.schedule_wrap(function()
  if vim.fn.mode() ~= "c" and vim.fn.getcmdwintype() == "" then
    pcall(vim.cmd.checktime)
  end
end))
vim.api.nvim_create_autocmd({ "FocusGained", "BufEnter" }, { command = "silent! checktime" })

-- The files this branch changed: against where it left the default branch, plus anything not
-- committed yet. That is what an agent in this worktree did, committed or not.
local function git(args)
  local r = vim.system(vim.list_extend({ "git", "-C", vim.fn.getcwd() }, args), { text = true }):wait()
  if r.code ~= 0 then
    return nil
  end
  return r.stdout
end

local function changed_files()
  local base
  for _, ref in ipairs({ "origin/HEAD", "origin/main", "origin/master", "main", "master" }) do
    local mb = git({ "merge-base", "HEAD", ref })
    if mb then
      base = vim.trim(mb)
      break
    end
  end
  local seen, files = {}, {}
  local function add(out)
    for line in (out or ""):gmatch("[^\n]+") do
      if not seen[line] and vim.uv.fs_stat(line) then
        seen[line] = true
        table.insert(files, line)
      end
    end
  end
  -- --relative: paths from this folder, which is where they are opened from
  add(git({ "diff", "--name-only", "--relative", base or "HEAD" }))
  add(git({ "ls-files", "--others", "--exclude-standard" }))
  table.sort(files)
  return files
end

local pick_ok, pick = false, nil
if has("mini.nvim") then
  pick_ok, pick = pcall(require, "mini.pick")
  if pick_ok then
    pick.setup({ window = { config = { border = "single" } } })
  end
  local diff_ok, diff = pcall(require, "mini.diff")
  if diff_ok then
    diff.setup({ view = { style = "sign", signs = { add = "▎", change = "▎", delete = "▁" } } })
    vim.keymap.set("n", "<leader>g", diff.toggle_overlay, { desc = "show the git changes inline" })
  end
end

local function show_changed()
  local files = changed_files()
  if #files == 0 then
    vim.notify("No changed files here", vim.log.levels.INFO)
    return
  end
  if pick_ok then
    pick.start({ source = { items = files, name = "Changed here" } })
  else
    vim.fn.setqflist({}, " ", { title = "Changed here", lines = files, efm = "%f" })
    vim.cmd.copen()
  end
end
vim.api.nvim_create_user_command("OfficeChanged", show_changed, { desc = "files changed in this worktree" })
vim.keymap.set("n", "<leader>c", show_changed, { desc = "files changed here" })

if pick_ok then
  vim.keymap.set("n", "<leader>f", pick.builtin.files, { desc = "find a file" })
  vim.keymap.set("n", "<leader>/", pick.builtin.grep_live, { desc = "search the text" })
  vim.keymap.set("n", "<leader>b", pick.builtin.buffers, { desc = "open buffers" })
end

local tree_ok = false
if has("nvim-tree.lua") then
  -- nvim-tree replaces netrw, and asks for it to be off before it starts
  vim.g.loaded_netrw = 1
  vim.g.loaded_netrwPlugin = 1
  local ok, tree = pcall(require, "nvim-tree")
  if ok then
    tree_ok = true
    -- Plain glyphs: the defaults need a Nerd Font, and not every terminal has one.
    tree.setup({
      view = { width = 32 },
      renderer = {
        group_empty = true,
        root_folder_label = ":t",
        icons = {
          show = { file = false, folder = false, folder_arrow = true, git = true },
          glyphs = {
            folder = { arrow_closed = "▸", arrow_open = "▾" },
            git = { unstaged = "M", staged = "S", unmerged = "U", renamed = "R",
                    untracked = "?", deleted = "D", ignored = "◌" },
          },
        },
      },
      update_focused_file = { enable = true },
      filters = { git_ignored = false, custom = { "^\\.git$" } },
      actions = { open_file = { window_picker = { enable = false } } },
      on_attach = function(bufnr)
        local api = require("nvim-tree.api")
        api.config.mappings.default_on_attach(bufnr)
        vim.keymap.set("n", "q", api.tree.close, { buffer = bufnr, desc = "close the tree" })
      end,
    })
    vim.keymap.set("n", "<leader>e", "<cmd>NvimTreeToggle<cr>", { desc = "file tree" })
  end
end
if not tree_ok then
  vim.keymap.set("n", "<leader>e", "<cmd>Lexplore<cr>", { desc = "file tree" })
end

-- Opened on a folder or on nothing: show the tree, and say how many files changed here.
vim.api.nvim_create_autocmd("VimEnter", {
  callback = function()
    local arg = vim.fn.argv(0)
    if tree_ok and (arg == "" or vim.fn.isdirectory(arg) == 1) then
      require("nvim-tree.api").tree.open({ focus = false })
    end
    local n = #changed_files()
    if n > 0 then
      vim.api.nvim_echo({ { string.format("%d changed here. Space c to open one", n), "Comment" } }, false, {})
    end
  end,
})
