# Loaded first: the installer puts tools in ~/.local/bin, and later fragments
# check for them with `command -q`.

# Remove the old user path because they can be polluted by user randomly typing `set ...`
# Then we add our .local/bin
set -e -U fish_user_paths
fish_add_path -P -m -p "$HOME/.local/bin"
