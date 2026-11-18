# Neovim as the editor, only when it is installed (like nvim.fish). `vim` stays vim.
if command -v nvim >/dev/null 2>&1; then
    export EDITOR=nvim VISUAL=nvim
fi
