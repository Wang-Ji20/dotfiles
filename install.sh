#!/usr/bin/env bash
# Symlink these dotfiles into $HOME. Safe to re-run; replaced files are backed up.
#
#   ./install.sh               link the dotfiles
#   ./install.sh --packages    install packages.txt with zypper first
#   ./install.sh --dry-run     show what would happen, change nothing
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backup="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"
dry_run=false
packages=false

for arg in "$@"; do
    case "$arg" in
        -n | --dry-run) dry_run=true ;;
        --packages) packages=true ;;
        *)
            echo "usage: $0 [--packages] [--dry-run]" >&2
            exit 2
            ;;
    esac
done

run() {
    if $dry_run; then
        echo "would run: $*"
    else
        "$@"
    fi
}

install_packages() {
    if ! command -v zypper >/dev/null; then
        echo "error: --packages needs zypper (openSUSE)" >&2
        exit 1
    fi
    local list sudo=()
    mapfile -t list < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$repo/packages.txt")
    [ "$(id -u)" -eq 0 ] || sudo=(sudo)
    run "${sudo[@]}" zypper install "${list[@]}"
}

# Move the identity out of a real ~/.gitconfig before the repo's version replaces it.
migrate_git_identity() {
    local old="$HOME/.gitconfig" new="$HOME/.gitconfig.local" key value
    [ -f "$old" ] && [ ! -L "$old" ] && [ ! -e "$new" ] || return 0
    for key in user.name user.email user.signingkey commit.gpgsign; do
        if value="$(git config --file "$old" --get "$key")"; then
            run git config --file "$new" "$key" "$value"
        fi
    done
}

link_file() {
    local rel="$1" source="$repo/$1" target="$HOME/$1"
    if [ "$target" -ef "$source" ]; then
        return 0
    fi
    run mkdir -p "$(dirname "$target")"
    if [ -e "$target" ] || [ -L "$target" ]; then
        if ! cmp -s "$source" "$target"; then
            echo "backup: ~/$rel"
            run mkdir -p "$(dirname "$backup/$rel")"
            run cp -P "$target" "$backup/$rel"
        fi
        run rm -f "$target"
    fi
    echo "link:   ~/$rel"
    run ln -s "$source" "$target"
}

$packages && install_packages

migrate_git_identity

while IFS= read -r rel; do
    case "$rel" in
        README.md | .gitignore | .gitconfig.local.example | install.sh | packages.txt) continue ;;
    esac
    [ -e "$repo/$rel" ] && link_file "$rel"
done < <(git -C "$repo" ls-files --cached --others --exclude-standard)

# Things the links alone can't settle.
if command -v nvim >/dev/null; then
    version="$(nvim --version | sed -n '1s/^NVIM v//p')"
    if [ "$(printf '%s\n0.12.0\n' "$version" | sort -V | head -1)" != "0.12.0" ]; then
        echo "warning: Neovim $version is too old; init.lua needs >= 0.12 (vim.pack)." >&2
    fi
else
    echo "warning: nvim is not installed (try --packages)." >&2
fi

if [ ! -e "$HOME/.gitconfig.local" ] && ! $dry_run; then
    echo "next: cp $repo/.gitconfig.local.example ~/.gitconfig.local and fill in your identity."
fi
if [ "$(basename "${SHELL:-}")" != fish ] && command -v fish >/dev/null; then
    echo "next: chsh -s $(command -v fish)   # then log out and back in"
fi
