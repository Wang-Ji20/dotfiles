# ~/.config/fish/config.fish
#
# Fish sources conf.d/*.fish before this file. Each dotfiles module adds its
# own fragment there (PATH in 00-path.fish, editor in nvim.fish, ...).

if status is-interactive
    # Vi key bindings
    set -g fish_key_bindings fish_vi_key_bindings
end
