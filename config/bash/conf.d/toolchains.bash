# Language toolchains installed in $HOME, each added only if present (like toolchains.fish).

# pnpm
export PNPM_HOME="$HOME/.local/share/pnpm"
__dotfiles_path_add prepend "$PNPM_HOME/bin"

# Rust / Cargo
export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
__dotfiles_path_add prepend "$CARGO_HOME/bin"
__dotfiles_path_add prepend "$CARGO_HOME/bin/bin"

# Haskell (ghcup / cabal)
export GHCUP_INSTALL_BASE_PREFIX="${GHCUP_INSTALL_BASE_PREFIX:-$HOME}"
__dotfiles_path_add prepend "$HOME/.cabal/bin"
__dotfiles_path_add prepend "$HOME/.ghcup/bin"

# OCaml / opam
[ -r "$HOME/.opam/opam-init/init.sh" ] && . "$HOME/.opam/opam-init/init.sh" >/dev/null 2>&1

# Go and Flutter
__dotfiles_path_add append "$HOME/go/bin"
__dotfiles_path_add append "$HOME/flutter/bin"

# Julia (juliaup)
__dotfiles_path_add append "$HOME/.juliaup/bin"
