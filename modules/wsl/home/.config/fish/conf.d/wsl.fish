# WSL host binary integration (e.g. Zed editor)
if set -q WSL_DISTRO_NAME
    for zed_path in /mnt/c/Users/*/AppData/Local/Programs/Zed/bin
        fish_add_path -m -a "$zed_path"
    end
end
