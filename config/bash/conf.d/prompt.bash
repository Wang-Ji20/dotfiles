# Same prompt as fish_prompt.fish:
#   ❰user ~/path (git ↑ ↓ + * x > = ? branch)❱ ✓ λ
# Git info from one `git status --porcelain=v2 --branch`; nothing extra when clean.
[[ $- == *i* ]] || return 0

__dotfiles_prompt() {
    local last=$?
    # \001 \002 mark non-printing bytes, so colours inside variables work.
    local s=$'\001' e=$'\002'
    local reset="$s"$'\e[0m'"$e" bold="$s"$'\e[1m'"$e" bg_black="$s"$'\e[40m'"$e"
    local red="$s"$'\e[31m'"$e" green="$s"$'\e[32m'"$e" yellow="$s"$'\e[33m'"$e"
    local blue="$s"$'\e[34m'"$e" purple="$s"$'\e[35m'"$e" white="$s"$'\e[37m'"$e"

    __dotfiles_git=
    local out
    if out=$(command git status --porcelain=v2 --branch 2>/dev/null); then
        local branch= ahead=0 behind=0 line syms=()
        while IFS= read -r line; do
            case $line in
                '# branch.head '*) branch=${line#'# branch.head '} ;;
                '# branch.ab '*) read -r _ _ ahead behind <<<"$line"; ahead=${ahead#+}; behind=${behind#-} ;;
            esac
        done <<<"$out"
        ((ahead > 0)) && syms+=("$red↑")
        ((behind > 0)) && syms+=("$red↓")
        # One symbol per kind of change, fixed order. XY follows the line type.
        local o=$'\n'"$out"
        [[ $o == *$'\n1 A'* ]] && syms+=("$green+")
        [[ $o == *$'\n'[12]' M'* || $o == *$'\n'[12]' '?'M'* ]] && syms+=("$green*")
        [[ $o == *$'\n1 D'* || $o == *$'\n1 '?'D'* ]] && syms+=("${red}x")
        [[ $o == *$'\n2 '* ]] && syms+=("$purple>")
        [[ $o == *$'\nu '* ]] && syms+=("$yellow=")
        [[ $o == *$'\n? '* ]] && syms+=("$red?")
        local sym_str=
        ((${#syms[@]})) && { local IFS=' '; sym_str="${syms[*]} "; }
        __dotfiles_git=" (git $sym_str$bold$blue$branch$white)"
    fi

    if ((last == 0)); then
        __dotfiles_status="$bold$green✓ $white"
    else
        __dotfiles_status="$bold$red✗ $white"
    fi
    # Bold and the black background stay on until the final reset (like set_color).
    # Git info stays in a variable PS1 only references: a branch named like $(cmd)
    # is shown, never run.
    PS1="$bg_black$bold$white❰$green\\u$white $yellow\\w$white"'${__dotfiles_git}'"$white❱ "'${__dotfiles_status}'"λ$reset "
}

case ";${PROMPT_COMMAND:-};" in
    *";__dotfiles_prompt;"*) ;;
    *) PROMPT_COMMAND="__dotfiles_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
esac
