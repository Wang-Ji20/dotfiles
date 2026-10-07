# ~/.config/fish/config.fish

# Environment variables
set -gx EDITOR nvim
set -gx VISUAL nvim

# -----------------------------------------------------------------------------
# Path configuration (idempotent, portable)
# -----------------------------------------------------------------------------
fish_add_path -m -p "$HOME/.local/bin"

# pnpm
set -gx PNPM_HOME "$HOME/.local/share/pnpm"
test -d "$PNPM_HOME/bin"; and fish_add_path -m -p "$PNPM_HOME/bin"

# Rust / Cargo
set -q CARGO_HOME; or set -gx CARGO_HOME "$HOME/.cargo"
test -d "$CARGO_HOME/bin"; and fish_add_path -m -p "$CARGO_HOME/bin"
test -d "$CARGO_HOME/bin/bin"; and fish_add_path -m -p "$CARGO_HOME/bin/bin"

# Haskell (ghcup / cabal)
set -q GHCUP_INSTALL_BASE_PREFIX[1]; or set -gx GHCUP_INSTALL_BASE_PREFIX "$HOME"
test -d "$HOME/.cabal/bin"; and fish_add_path -m -p "$HOME/.cabal/bin"
test -d "$HOME/.ghcup/bin"; and fish_add_path -m -p "$HOME/.ghcup/bin"

# OCaml / opam
if test -f "$HOME/.opam/opam-init/init.fish"
    source "$HOME/.opam/opam-init/init.fish" >/dev/null 2>&1; or true
end

# WSL host binary integration (e.g. Zed editor)
set -l zed_path "/mnt/c/Users/Ji Wang/AppData/Local/Programs/Zed/bin"
if test -d "$zed_path"
    fish_add_path -m -a "$zed_path"
end

# -----------------------------------------------------------------------------
# Interactive session configuration
# -----------------------------------------------------------------------------
if status is-interactive
    # Vi key bindings
    set -g fish_key_bindings fish_vi_key_bindings

    # Preserve original vim/ed binaries
    function vim-old --wraps vim --description 'Original vim'
        command vim $argv
    end

    function ed-old --wraps ed --description 'Original ed'
        command ed $argv
    end

    # Remap vim and ed to Neovim
    function vim --wraps nvim --description 'Alias vim to nvim'
        command nvim $argv
    end

    function ed --wraps nvim --description 'Alias ed to nvim'
        command nvim $argv
    end
end
