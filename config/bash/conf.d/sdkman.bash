# SDKMAN! for bash, like sdkman.fish: candidates on PATH and JAVA_HOME at startup;
# the full sdkman-init.sh is only loaded the first time `sdk` is used.
export SDKMAN_DIR="${SDKMAN_DIR:-$HOME/.sdkman}"
if [ -d "$SDKMAN_DIR" ]; then
    for __dotfiles_d in "$SDKMAN_DIR"/candidates/*/current/bin; do
        __dotfiles_path_add prepend "$__dotfiles_d"
    done
    unset __dotfiles_d
    [ -d "$SDKMAN_DIR/candidates/java/current" ] && export JAVA_HOME="$SDKMAN_DIR/candidates/java/current"

    sdk() {
        unset -f sdk
        . "$SDKMAN_DIR/bin/sdkman-init.sh" && sdk "$@"
    }
fi
