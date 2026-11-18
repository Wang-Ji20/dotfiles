# Loaded first, like fish's 00-path.fish. Defines the helper the other fragments
# use to change PATH, then puts ~/.local/bin and ~/.pixi/bin in front.

# __dotfiles_path_add prepend|append DIR
#   Like fish's `fish_add_path -P -m -p|-a DIR`: do nothing if DIR doesn't exist;
#   otherwise make DIR appear exactly once in PATH, at the front or the end,
#   moving it if it is already there.
__dotfiles_path_add() {
    local mode=$1 dir=$2
    [[ -d $dir ]] || return 0
    # Remove every existing copy: wrap in ':' so first/last entries match too.
    local p=":$PATH:"
    while [[ $p == *":$dir:"* ]]; do p=${p//":$dir:"/:}; done
    p=${p#:}; p=${p%:}
    case $mode in
        prepend) PATH="$dir${p:+:$p}" ;;
        append)  PATH="${p:+$p:}$dir" ;;
    esac
    export PATH
}

__dotfiles_path_add prepend "$HOME/.pixi/bin"   # pixi global (lab machines)
__dotfiles_path_add prepend "$HOME/.local/bin"
