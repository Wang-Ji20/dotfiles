# Neovim as the editor, only when it is installed.
if command -q nvim
    set -gx EDITOR nvim
    set -gx VISUAL nvim

    if status is-interactive
        # Preserve original vim/ed binaries
        function vim-old --wraps vim --description 'Original vim'
            command vim $argv
        end

        function ed-old --wraps ed --description 'Original ed'
            command ed $argv
        end

        # Remap vim and ed to Neovim
        function vim --wraps nvim --description 'Alias vim to nvim'
            command nvim $argv
        end

        function ed --wraps nvim --description 'Alias ed to nvim'
            command nvim $argv
        end
    end
end
