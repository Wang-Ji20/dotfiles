# Loaded first: the installer puts tools in ~/.local/bin, and later fragments
# check for them with `command -q`.
fish_add_path -m -p "$HOME/.local/bin"
