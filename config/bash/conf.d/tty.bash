# For gpg's pinentry, like fish's tty.fish.
if [[ $- == *i* ]] && [ -t 0 ]; then
    GPG_TTY=$(tty)
    export GPG_TTY
fi
