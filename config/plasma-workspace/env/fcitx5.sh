# Sourced by Plasma at login. Wayland apps talk to fcitx5 through KWin
# (kwinrc [Wayland] InputMethod); X11 apps under XWayland need XIM.
# GTK_IM_MODULE / QT_IM_MODULE stay unset on Wayland, as fcitx5 recommends.
command -v fcitx5 >/dev/null 2>&1 && export XMODIFIERS=@im=fcitx
