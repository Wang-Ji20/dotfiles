# Interactive behaviour close to the fish config.
[[ $- == *i* ]] || return 0

# Vi key bindings, with fish's mode indicator: bold green [I], bold red [N].
set -o vi
bind 'set show-mode-in-prompt on'
bind $'set vi-ins-mode-string \1\e[1;32m\2[I]\1\e[0m\2 '
bind $'set vi-cmd-mode-string \1\e[1;31m\2[N]\1\e[0m\2 '

# Completion a little more like fish: case-insensitive, list on first Tab, colours.
bind 'set completion-ignore-case on'
bind 'set show-all-if-ambiguous on'
bind 'set colored-stats on'
bind 'set mark-symlinked-directories on'

# History like fish: large, shared between sessions, without duplicates.
HISTCONTROL=ignoreboth:erasedups
HISTSIZE=10000
HISTFILESIZE=20000
shopt -s histappend

# Same as fish's ll / la functions.
alias ll='ls -lh'
alias la='ls -lAh'
