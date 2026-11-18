# Neovim as the editor, only when it is installed. `vim` stays vim.
if command -q nvim
    set -gx EDITOR nvim
    set -gx VISUAL nvim
end
