if status is-interactive; and isatty stdin
    set -gx GPG_TTY (tty)
end
