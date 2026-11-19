# Loaded by the line `apply` keeps in ~/.bashrc, and by the one in the login file when
# that doesn't source ~/.bashrc. Once per shell: on a lab, ~/.bashrc sources
# ~/.bash_profile, so both lines run.
[ -z "${__dotfiles_loaded:-}" ] || return 0
__dotfiles_loaded=1
#
# Fragments in ~/.config/bash/conf.d/ are loaded in name order,
# the same way fish loads ~/.config/fish/conf.d/. Not in ~/.bashrc.d/ on purpose:
# RHEL's default .bashrc already sources that, which would load everything twice.
for __dotfiles_f in "$HOME"/.config/bash/conf.d/*.bash; do
    [ -r "$__dotfiles_f" ] && . "$__dotfiles_f"
done
unset __dotfiles_f
