# Dotfiles

My dotfiles for Linux.

## Install

On openSUSE Tumbleweed (Leap's Neovim may be older than the 0.12 this config needs):

```sh
sudo zypper install git
git clone https://github.com/Wang-Ji20/dotfiles.git ~/dotfiles
cd ~/dotfiles
./install.sh --dry-run     # preview
./install.sh --packages    # install packages.txt, then symlink everything
```

Files are symlinked into `$HOME`. Anything replaced is saved in `~/.dotfiles-backup/<timestamp>/`.

Then, on a new machine:

- Create `~/.gitconfig.local` from `.gitconfig.local.example`, and import your GPG key.
- Run `gh auth login`.
- Change your shell with `chsh -s /usr/bin/fish`, then log out and back in.
- Open `nvim` once to download plugins and parsers.
- Optional language servers not packaged for openSUSE: `uv tool install pyright` and `pnpm add -g typescript-language-server typescript`.

## Contents

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
