# Loaded by the one line `apply` keeps in ~/.bashrc.
#
# Fragments in ~/.config/bash/conf.d/ are loaded in name order,
# the same way fish loads ~/.config/fish/conf.d/. Not in ~/.bashrc.d/ on purpose:
# RHEL's default .bashrc already sources that, which would load everything twice.
for __dotfiles_f in "$HOME"/.config/bash/conf.d/*.bash; do
    [ -r "$__dotfiles_f" ] && . "$__dotfiles_f"
done
unset __dotfiles_f
