# Loaded first: tool locations go on PATH before later fragments check for
# tools with `command -q`. -P: this session only (never fish_user_paths).
#   ~/.local/bin   tools and links from this repo
#   ~/.pixi/bin    `pixi global install` (lab machines; see environment.toml)
fish_add_path -P -m -p "$HOME/.local/bin" "$HOME/.pixi/bin"
