# Language toolchains installed in $HOME. Each is added only if present.
# -P: edit this session's $PATH only, so an uninstalled toolchain disappears next session.

# pnpm
set -gx PNPM_HOME "$HOME/.local/share/pnpm"
test -d "$PNPM_HOME/bin"; and fish_add_path -P -m -p "$PNPM_HOME/bin"

# Rust / Cargo
set -q CARGO_HOME; or set -gx CARGO_HOME "$HOME/.cargo"
test -d "$CARGO_HOME/bin"; and fish_add_path -P -m -p "$CARGO_HOME/bin"
test -d "$CARGO_HOME/bin/bin"; and fish_add_path -P -m -p "$CARGO_HOME/bin/bin"

# Haskell (ghcup / cabal)
set -q GHCUP_INSTALL_BASE_PREFIX[1]; or set -gx GHCUP_INSTALL_BASE_PREFIX "$HOME"
test -d "$HOME/.cabal/bin"; and fish_add_path -P -m -p "$HOME/.cabal/bin"
test -d "$HOME/.ghcup/bin"; and fish_add_path -P -m -p "$HOME/.ghcup/bin"

# OCaml / opam
if test -f "$HOME/.opam/opam-init/init.fish"
    source "$HOME/.opam/opam-init/init.fish" >/dev/null 2>&1; or true
end

# Go and Flutter
test -d "$HOME/go/bin"; and fish_add_path -P -m -a "$HOME/go/bin"
test -d "$HOME/flutter/bin"; and fish_add_path -P -m -a "$HOME/flutter/bin"
