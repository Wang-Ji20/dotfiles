# Windows-side editors under WSL. Needed when /etc/wsl.conf sets
# `appendWindowsPath = false`, which keeps the Windows PATH out of WSL.
# -P edits this session's $PATH directly (not fish_user_paths, which fish puts in
# front of everything and, by default, saves for later sessions even outside WSL);
# -a appends, so inside VS Code's own terminal its remote-cli `code` still wins.
if set -q WSL_DISTRO_NAME
    for editor_bin in \
            /mnt/c/Users/*/AppData/Local/Programs/Zed/bin \
            "/mnt/c/Users/"*"/AppData/Local/Programs/Microsoft VS Code/bin" \
            "/mnt/c/Program Files/Microsoft VS Code/bin"
        test -d "$editor_bin"; and fish_add_path -P -m -a "$editor_bin"
    end
end
