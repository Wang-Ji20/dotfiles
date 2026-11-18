# `y`: launch yazi and cd to its directory on quit (like y.fish).
y() {
    local tmp cwd
    tmp=$(mktemp -t "yazi-cwd.XXXXXX") || return
    yazi "$@" --cwd-file="$tmp"
    IFS= read -r -d '' cwd <"$tmp"
    [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
    rm -f -- "$tmp"
}
