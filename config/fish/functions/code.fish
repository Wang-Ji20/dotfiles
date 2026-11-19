# Under KDE, VS Code runs through XWayland: Electron exports its menu to
# Plasma's top bar only on X11. The menu entry does the same (see [kde]).
function code --wraps=code --description 'VS Code, menu in the top bar on KDE'
    if test "$XDG_CURRENT_DESKTOP" = KDE
        command code --ozone-platform=x11 $argv
    else
        command code $argv
    end
end
