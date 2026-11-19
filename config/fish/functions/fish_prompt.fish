# ❰user@host cwd (git status branch)❱ ✓ λ
#
# Git info comes from ONE call: `git status --porcelain=v2 --branch`.
# Its output, line by line (see `git help status`, section "Porcelain Format Version 2"):
#   # branch.head main              branch name, or "(detached)"
#   # branch.ab +1 -2               ahead 1, behind 2 (only when there is an upstream)
#   1 .M N... <modes> <hashes> path        changed file; XY = 2 chars after "1 "
#   2 R. N... <modes> <hashes> R100 path   renamed/copied
#   u UU N... ...                          merge conflict
#   ? path                                 untracked
# XY: X = staged (index), Y = worktree; "." means unchanged (porcelain v1 used a space).

function fish_prompt --description 'Write out the prompt'
    set -l laststatus $status

    set -l git_info
    # Not a repo (or git missing): git fails, and the prompt has no git part.
    if set -l lines (command git status --porcelain=v2 --branch 2>/dev/null)
        set -l branch
        set -l ahead 0
        set -l behind 0
        set -l changes          # every line that describes a file
        for line in $lines
            switch $line
                case '# branch.head *'
                    set branch (string replace '# branch.head ' '' -- $line)
                case '# branch.ab *'
                    set -l ab (string split ' ' -- $line)   # '#' 'branch.ab' '+1' '-2'
                    set ahead (string trim -c + -- $ab[3])
                    set behind (string trim -c - -- $ab[4])
                case '#*'
                case '*'
                    set -a changes $line
            end
        end

        # Symbols are collected as a list and joined with spaces below.
        set -l syms
        test "$ahead" -gt 0; and set -a syms (set_color red)↑
        test "$behind" -gt 0; and set -a syms (set_color red)↓

        # One symbol per kind of change, always in this order; nothing when clean.
        # XY sits right after the line type: "1 .M ..." -> X='.' (staged), Y='M' (worktree).
        string match -q '1 A*' -- $changes; and set -a syms (set_color green)+
        string match -qr '^[12] (M|.M)' -- $changes; and set -a syms (set_color green)'*'
        string match -qr '^1 (D|.D)' -- $changes; and set -a syms (set_color red)x
        string match -q '2 *' -- $changes; and set -a syms (set_color purple)'>'
        string match -q 'u *' -- $changes; and set -a syms (set_color brown)=
        string match -q '? *' -- $changes; and set -a syms (set_color red)'?'

        set -q syms[1]; and set -a syms ''   # space before the branch only if there are symbols
        # Via a quoted variable: an empty (cmd) inside a concatenation would empty the whole string.
        set -l sym_str (string join ' ' $syms)
        set git_info " (git $sym_str"(set_color -o blue)"$branch"(set_color white)")"
    end

    # Full path, no shortening.
    set -q fish_prompt_pwd_dir_length
    or set -lx fish_prompt_pwd_dir_length 0

    set_color -b normal
    printf '%s❰%s%s@%s %s%s%s%s❱ ' \
        (set_color -o white) (set_color green) $USER (prompt_hostname) \
        (set_color yellow) (prompt_pwd) \
        $git_info (set_color -o white)
    if test $laststatus -eq 0
        printf '%s✓ %sλ%s ' (set_color -o green) (set_color white) (set_color normal)
    else
        printf '%s✗ %sλ%s ' (set_color -o red) (set_color white) (set_color normal)
    end
end
