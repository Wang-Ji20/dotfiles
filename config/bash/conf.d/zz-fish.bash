# Switch an interactive bash to fish, for machines where bash is the login shell
# and chsh isn't allowed (lab). Loaded last, so fish from ~/.pixi/bin is on PATH.
# Stays in bash when:
#   - non-interactive (scripts, scp, rsync, `ssh host cmd`)
#   - started from fish (you ran `bash` on purpose)
#   - NOFISH is set:  ssh -t host 'NOFISH=1 bash -l'
[[ $- == *i* ]] || return 0
[ -z "${NOFISH:-}" ] || return 0
command -v fish >/dev/null 2>&1 || return 0
[ "$(ps -o comm= -p "$PPID" 2>/dev/null)" != fish ] || return 0

if shopt -q login_shell; then
    exec fish -l
else
    exec fish
fi
