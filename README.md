# Dotfiles

My dotfiles for Linux.

- **Fish Shell** (`~/.config/fish/`):
  - Vi key bindings (`fish_vi_key_bindings`).
  - Yazi shell integration (`y` command to navigate and change directory on quit).
  - Aliases mapping `vim` and `ed` to Neovim while preserving original binaries (`vim-old`, `ed-old`).
  - Automatic toolchain integration (Cargo, PNPM, SDKMAN, OPAM, GHCup) with existence checks.
  - Clean modular `conf.d/` (color theme, GPG tty guard, truecolor support).

- **Neovim** (`~/.config/nvim/`):
  - Neovim >= 0.12.
  - Built-in package management via `vim.pack`.
  - Built-in native LSP configuration via `vim.lsp.config` and `vim.lsp.enable`.
  - Plugins: `gitsigns.nvim`, `mini.statusline`, `mini.icons`, `nvim-treesitter`, `nvim-treesitter-textobjects`, `render-markdown.nvim`.

- **C / C++ Tooling**:
  - `~/.config/clangd/config.yaml`: Inlay hints, `-Wall -Werror`, C++20 default for C++ files, and clang-tidy checks (`bugprone-*`, `modernize-*`, `abseil-*`, `performance-*`, etc.).
  - `~/.clang-format`: Formatting style configuration for C and C++.

- **Git** (`~/.gitconfig` and `~/.config/git/ignore`):
  - Portable global Git configuration with `main` default branch and GitHub credential helper.
  - **Modular GPG & Identity**: Uses `[include] path = ~/.gitconfig.local` to keep personal names, emails, and GPG signing keys on machine-local storage without breaking across machines.
  - Global git ignores for editor artifacts, swap files, and system files.
