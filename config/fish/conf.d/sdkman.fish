# SDKMAN! for fish, without the sdkman-for-fish plugin.
#
# sdkman is bash functions, not a binary. Day to day, fish only needs the
# `current` version of each candidate (java, gradle, kotlin, ...) on PATH.
# Switching per shell (`sdk use`) and auto_env are not used, so no bash at startup.

set -q SDKMAN_DIR; or set -gx SDKMAN_DIR "$HOME/.sdkman"
test -d "$SDKMAN_DIR"; or return

for b in $SDKMAN_DIR/candidates/*/current/bin
    fish_add_path -P -m -p $b
end
test -d "$SDKMAN_DIR/candidates/java/current"; and set -gx JAVA_HOME $SDKMAN_DIR/candidates/java/current

# `sdk install|default|upgrade ...` still works: run it in bash, then start a
# new fish (or `exec fish`) to pick up a changed `current`.
function sdk --description 'Run SDKMAN! in bash'
    bash -c 'source "$SDKMAN_DIR/bin/sdkman-init.sh" && sdk "$@"' sdk $argv
end
