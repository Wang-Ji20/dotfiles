# Windows-side VS Code under WSL (like wsl.fish). Appended, so VS Code's own
# terminal keeps its remote-cli `code` first.
if [ -n "${WSL_DISTRO_NAME:-}" ]; then
    for __dotfiles_d in /mnt/c/Users/*/AppData/Local/Programs/"Microsoft VS Code"/bin \
        "/mnt/c/Program Files/Microsoft VS Code/bin"; do
        __dotfiles_path_add append "$__dotfiles_d"
    done
    unset __dotfiles_d
fi
