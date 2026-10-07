# if status is-interactive
    # Commands to run in interactive sessions can go here
#     eval (zellij setup --generate-auto-start fish | string collect)
# end

# opam configuration
source /root/.opam/opam-init/init.fish >/dev/null 2>/dev/null; or true

# pnpm
set -gx PNPM_HOME '/root/.local/share/pnpm'
if not string match -q -- "$PNPM_HOME/bin" $PATH
  set -gx PATH "$PNPM_HOME/bin" $PATH
end
# pnpm end

# local
set -gx LOCAL_HOME "/root/.local/bin"
if not string match -q -- $LOCAL_HOME $PATH
    set -gx PATH "$LOCAL_HOME" $PATH
end
# local end

# cargo
set -gx CARGO_HOME "/root/.cargo/bin"
if not string match -q -- $CARGO_HOME $PATH
    set -gx PATH "$CARGO_HOME" $PATH
end
# cargo end

# cargo extra
set -gx CARGO_HOME_EXTRA "/root/.cargo/bin/bin"
if not string match -q -- $CARGO_HOME_EXTRA $PATH
    set -gx PATH "$CARGO_HOME_EXTRA" $PATH
end
# cargo end


set -gx ZED "/mnt/c/Users/Ji Wang/AppData/Local/Programs/Zed/bin"
if not string match -q -- $VSCODE $PATH
    set -gx PATH "$ZED" $PATH
end

set -q GHCUP_INSTALL_BASE_PREFIX[1]; or set GHCUP_INSTALL_BASE_PREFIX $HOME ; set -gx PATH $HOME/.cabal/bin /root/.ghcup/bin $PATH # ghcup-env

# Preserve the original binaries
function vim-old --wraps vim --description 'Original vim'
    command vim $argv
end

function ed-old --wraps ed --description 'Original ed'
    command ed $argv
end

# Remap vim and ed to Neovim
function vim --wraps nvim --description 'alias vim to nvim'
    command nvim $argv
end

function ed --wraps nvim --description 'alias ed to nvim'
    command nvim $argv
end

