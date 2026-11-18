# Windows-side VS Code under WSL. Needed because /etc/wsl.conf sets
# `appendWindowsPath = false`, which keeps the Windows PATH out of WSL.
# -a appends, so inside VS Code's own terminal its remote-cli `code` still wins.
if set -q WSL_DISTRO_NAME
    for code_bin in \
            "/mnt/c/Users/"*"/AppData/Local/Programs/Microsoft VS Code/bin" \
            "/mnt/c/Program Files/Microsoft VS Code/bin"
        test -d "$code_bin"; and fish_add_path -P -m -a "$code_bin"
    end
end
