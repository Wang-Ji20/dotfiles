# Dotfiles

My dotfiles for Linux, split into modules you can combine. The installer
works on openSUSE, Debian/Ubuntu and RHEL-like systems, as root or as a
normal user without sudo.

## Install

```sh
git clone https://github.com/Wang-Ji20/dotfiles.git ~/dotfiles
cd ~/dotfiles
./install.sh --list                          # modules and profiles
./install.sh --profile lab --packages --dry-run
./install.sh --profile lab --packages        # shared servers: no sudo, tools in ~/.local
./install.sh --profile desktop --packages    # workstation: system packages via sudo
```

Needs Python 3.9+ (standard library only) and nothing else.

Other things you can do:

```sh
./install.sh                    # re-apply the saved selection (also repairs drift)
./install.sh fish nvim git      # pick modules directly (adds to --profile)
./install.sh --profile lab --exclude cpp
./install.sh --remove yazi      # drop a module: its links and the tools it installed go away
./install.sh --check            # exit 1 if anything would change
```

Then, on a new machine:

- Create `~/.gitconfig.local` from `modules/git/gitconfig.local.example` (the installer
  does this for you from an existing `~/.gitconfig`). On a shared server, leave out
  `gpgsign` rather than putting a private key there.
- Run `gh auth login`.
- Use fish: `chsh -s $(command -v fish)` where allowed; otherwise start it with
  `~/.local/bin/fish -l`, or from your own machine `ssh -t HOST ~/.local/bin/fish -l`.
- Open `nvim` once to download plugins and parsers.

## How the installer behaves

- **Links, not copies.** Every file under `modules/<name>/home/` is symlinked to the same
  path under `$HOME`. Anything it replaces is moved to `~/.dotfiles-backup/<timestamp>/`.
- **Idempotent.** It computes the desired state, compares it with the machine, and only
  acts on the difference. A second run prints `nothing to do` and writes nothing.
- **All or nothing.** Downloads, checksums, unpacking and a trial run of each binary
  happen in a staging directory first. Changes to `$HOME` are then journaled renames;
  if any step fails (or you press Ctrl-C) they are undone, and a run killed outright is
  rolled back by the next one. Two caveats: packages installed by the system package
  manager can't be rolled back (so that step runs last), and backups are kept on
  success.
- **Tools.** With `--packages`, a missing or too-old tool is taken from the package
  manager when running as root (or with `--sudo`) and the packaged version is new
  enough; otherwise from a pinned, checksummed release in [`tools.lock`](tools.lock),
  unpacked to `~/.local/opt/dotfiles/` and linked into `~/.local/bin`. The release is
  chosen to match the machine's glibc, so RHEL 9 (glibc 2.34) gets tree-sitter 0.25.10
  while Ubuntu 24.04 gets 0.27.2. Required tools that can't be provided stop the
  install before anything changes; optional ones are reported.
- **Safety.** It refuses to run when `$HOME` isn't yours (e.g. under `sudo`) or the repo
  is owned by another non-root user, and it never runs `chsh` or edits files it doesn't
  link.

State lives in `~/.local/state/dotfiles/state.json`.

## Modules

| Module | What it links | Tools |
|---|---|---|
| `fish` | `config.fish`, prompt, theme, `~/.local/bin` on PATH | fish |
| `toolchains` | PATH for cargo, pnpm, ghcup, opam, go, flutter (when present) | |
| `nvim` | `init.lua`, plugin lockfile, `EDITOR` and `vim`/`ed` aliases | nvim ≥ 0.12; optional rg, tree-sitter, cc |
| `git` | `.gitconfig`, global ignore | git |
| `gh` | GitHub credential helper (included from `.gitconfig`) | gh |
| `yazi` | `y` function | yazi |
| `cpp` | `~/.config/clangd/config.yaml`, `.clang-format` | optional clangd, clang-format |
| `lsp` | | optional lua-language-server, gopls |
| `sdkman` | Fisher and SDKMAN! for fish | |
| `grit` | grit environment | |
| `wsl` | Windows-side Zed on PATH | |
| `desktop` | | optional wl-clipboard, Nerd Font symbols, Qt pinentry |

Profiles are plain lists in [`profiles/`](profiles): `lab` and `desktop`.

A module is a directory with a `module.conf`:

```
description Neovim 0.12 config
requires fish                      # other modules
tool nvim min=0.12 zypper=neovim apt=neovim
tool rg optional zypper=ripgrep apt=ripgrep
package pinentry-qt6 optional zypper=pinentry-qt6   # package without a command
```

Modules add to shared directories without touching each other's files: for example
`yazi` brings `~/.config/fish/functions/y.fish`, and `gh` brings
`~/.config/git/gh.gitconfig`, which `.gitconfig` includes only if it exists.

## Contents

- **Fish Shell**: vi key bindings, Yazi integration (`y`), `vim`/`ed` mapped to Neovim
  (originals as `vim-old`, `ed-old`), toolchain PATH entries with existence checks, a
  `conf.d/` fragment per module.
- **Neovim** (>= 0.12): `vim.pack` plugins (`gitsigns.nvim`, `mini.statusline`,
  `mini.icons`, `nvim-treesitter`, `nvim-treesitter-textobjects`,
  `render-markdown.nvim`), native LSP via `vim.lsp.config`/`vim.lsp.enable` for servers
  found on PATH. On older Neovim it loads only the basic options; without a C compiler
  and tree-sitter it skips parser installs.
- **C / C++**: clangd with inlay hints, `-Wall -Werror`, C++20 for C++ files and
  clang-tidy checks; `.clang-format`.
- **Git**: `main` default branch, global ignores, identity and signing in
  `~/.gitconfig.local`.

## Tests

```sh
python3 -B -m unittest discover -s tests -t .
```

The tests include forcing a failure at every journaled step and checking that `$HOME`
is byte-for-byte unchanged. CI runs them and real installs on AlmaLinux 9,
Ubuntu 24.04, Debian 13 and Tumbleweed, as root and as a user without sudo.
