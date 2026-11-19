# GPU usage on each lab host, printed and saved to ~/cluster/<host>.txt.
# Hosts are arguments, or the universal variable lab_hosts (per machine, not in
# the repo, since host names are private): set -U lab_hosts host1 host2
function cluster-status
    set -l hosts $argv
    test -n "$hosts"; or set hosts $lab_hosts
    if test -z "$hosts"
        echo "usage: cluster-status <host>...   (or: set -U lab_hosts <host>...)" >&2
        return 1
    end
    mkdir -p ~/cluster
    for h in $hosts
        lab $h '~/.local/bin/gpu-status' | tee ~/cluster/$h.txt
    end
end
