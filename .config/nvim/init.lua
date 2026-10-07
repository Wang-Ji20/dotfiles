-- ~/.config/nvim/init.lua
-- Lightweight Neovim 0.12 config: no custom keymaps, 4-space indent

vim.g.mapleader = " "

local o = vim.o

-- Indentation: 4 spaces everywhere
o.expandtab = true
o.shiftwidth = 4
o.tabstop = 4
o.softtabstop = 4
o.smartindent = true
o.shiftround = true

-- UI
o.number = true
o.relativenumber = true
o.cursorline = true
o.signcolumn = "yes"
o.scrolloff = 8
o.wrap = true
o.linebreak = true
o.breakindent = true
o.showbreak = "↪ "
o.termguicolors = true
o.showmode = false
o.laststatus = 3
o.splitright = true
o.splitbelow = true
o.winborder = "rounded"
o.pumheight = 12
o.list = true
o.listchars = "tab:» ,trail:·,nbsp:␣"
o.fillchars = "eob: "

-- Behaviour
o.mouse = "a"
o.clipboard = "unnamedplus"
o.ignorecase = true
o.smartcase = true
o.inccommand = "split"
o.undofile = true
o.swapfile = false
o.confirm = true
o.updatetime = 250
o.completeopt = "menuone,noselect,popup"
o.wildmode = "longest:full,full"

if vim.fn.executable("rg") == 1 then
    o.grepprg = "rg --vimgrep --smart-case"
    o.grepformat = "%f:%l:%c:%m"
end

vim.g.netrw_banner = 0

-- Plugins (built-in vim.pack) ---------------------------------------
vim.pack.add({
    "https://github.com/echasnovski/mini.statusline",
    "https://github.com/lewis6991/gitsigns.nvim",
    { src = "https://github.com/nvim-treesitter/nvim-treesitter", version = "main" },
    { src = "https://github.com/nvim-treesitter/nvim-treesitter-textobjects", version = "main" },
}, { confirm = false })

require("mini.statusline").setup()
require("gitsigns").setup()

vim.pack.add({
    'https://github.com/nvim-treesitter/nvim-treesitter',
    --'https://github.com/nvim-mini/mini.nvim',            -- if you use the mini.nvim suite
    'https://github.com/nvim-mini/mini.icons',        -- if you use standalone mini plugins
    -- 'https://github.com/nvim-tree/nvim-web-devicons', -- if you prefer nvim-web-devicons
    'https://github.com/MeanderingProgrammer/render-markdown.nvim',
})
require('render-markdown').setup({}) -- only mandatory if you want to set custom options

-- Treesitter parsers (installed asynchronously; needs tree-sitter CLI + C compiler)
require("nvim-treesitter").install({
    "lua", "vim", "vimdoc", "query", "bash", "c", "cpp", "go", "rust",
    "python", "javascript", "typescript", "tsx", "json", "yaml", "toml",
    "html", "css", "markdown", "markdown_inline",
})

-- Treesitter text objects and motions
require("nvim-treesitter-textobjects").setup({
    select = { lookahead = true },
    move = { set_jumps = true },
})

local ts_select = require("nvim-treesitter-textobjects.select")
local ts_move = require("nvim-treesitter-textobjects.move")

local objects = {
    f = "@function",
    c = "@class",
    a = "@parameter",
    l = "@loop",
    i = "@conditional",
}
for key, obj in pairs(objects) do
    vim.keymap.set({ "x", "o" }, "a" .. key, function()
        ts_select.select_textobject(obj .. ".outer", "textobjects")
    end, { desc = "Around " .. obj })
    vim.keymap.set({ "x", "o" }, "i" .. key, function()
        ts_select.select_textobject(obj .. ".inner", "textobjects")
    end, { desc = "Inside " .. obj })
end

local function move(lhs, fn, query)
    vim.keymap.set({ "n", "x", "o" }, lhs, function() fn(query, "textobjects") end)
end
move("]f", ts_move.goto_next_start, "@function.outer")
move("[f", ts_move.goto_previous_start, "@function.outer")
move("]F", ts_move.goto_next_end, "@function.outer")
move("[F", ts_move.goto_previous_end, "@function.outer")
move("]]", ts_move.goto_next_start, "@class.outer")
move("[[", ts_move.goto_previous_start, "@class.outer")
move("][", ts_move.goto_next_end, "@class.outer")
move("[]", ts_move.goto_previous_end, "@class.outer")
move("]a", ts_move.goto_next_start, "@parameter.inner")
move("[a", ts_move.goto_previous_start, "@parameter.inner")

-- Autocmds ------------------------------------------------------------
local aug = vim.api.nvim_create_augroup("user", { clear = true })

vim.api.nvim_create_autocmd("TextYankPost", {
    group = aug,
    callback = function() vim.hl.on_yank() end,
})

vim.api.nvim_create_autocmd("BufReadPost", {
    group = aug,
    callback = function(ev)
        local mark = vim.api.nvim_buf_get_mark(ev.buf, '"')
        if mark[1] > 0 and mark[1] <= vim.api.nvim_buf_line_count(ev.buf) then
            pcall(vim.api.nvim_win_set_cursor, 0, mark)
        end
    end,
})

vim.api.nvim_create_autocmd("BufWritePre", {
    group = aug,
    callback = function()
        local view = vim.fn.winsaveview()
        vim.cmd([[keeppatterns %s/\s\+$//e]])
        vim.fn.winrestview(view)
    end,
})

-- Treesitter highlighting + indent when a parser is available
vim.api.nvim_create_autocmd("FileType", {
    group = aug,
    callback = function(ev)
        if pcall(vim.treesitter.start, ev.buf) then
            vim.bo[ev.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
        end
    end,
})

-- Built-in LSP (enabled only if the server binary is on PATH) ----------
vim.diagnostic.config({
    severity_sort = true,
    virtual_text = { spacing = 2 },
})

local servers = {
    lua_ls = {
        cmd = { "lua-language-server" },
        filetypes = { "lua" },
        root_markers = { ".luarc.json", ".git" },
        settings = { Lua = { runtime = { version = "LuaJIT" } } },
    },
    pyright = {
        cmd = { "pyright-langserver", "--stdio" },
        filetypes = { "python" },
        root_markers = { "pyproject.toml", "setup.py", ".git" },
    },
    ts_ls = {
        cmd = { "typescript-language-server", "--stdio" },
        filetypes = { "javascript", "typescript", "javascriptreact", "typescriptreact" },
        root_markers = { "package.json", "tsconfig.json", ".git" },
    },
    gopls = { cmd = { "gopls" }, filetypes = { "go", "gomod" }, root_markers = { "go.mod", ".git" } },
    rust_analyzer = { cmd = { "rust-analyzer" }, filetypes = { "rust" }, root_markers = { "Cargo.toml", ".git" } },
    clangd = { cmd = { "clangd" }, filetypes = { "c", "cpp" }, root_markers = { "compile_commands.json", ".git" } },
}

local enabled = {}
for name, cfg in pairs(servers) do
    if vim.fn.executable(cfg.cmd[1]) == 1 then
        vim.lsp.config(name, cfg)
        table.insert(enabled, name)
    end
end
if #enabled > 0 then vim.lsp.enable(enabled) end

vim.api.nvim_create_autocmd("LspAttach", {
    group = aug,
    callback = function(ev)
        local client = vim.lsp.get_client_by_id(ev.data.client_id)
        if client and client:supports_method("textDocument/completion") then
            vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
        end
    end,
})

