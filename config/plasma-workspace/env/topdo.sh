# topdo installs its QML module under ~/.local (see environment.toml), where Plasma doesn't look
# by itself. Sourced by Plasma at login.
export QML_IMPORT_PATH="$HOME/.local/lib64/qt6/qml${QML_IMPORT_PATH:+:$QML_IMPORT_PATH}"
