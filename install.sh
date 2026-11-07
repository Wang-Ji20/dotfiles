#!/bin/sh
# Entry point: find Python 3.9+ and run the installer. See ./install.sh --help.
case "$0" in */*) dir=${0%/*} ;; *) dir=. ;; esac
repo=$(cd "$dir" && pwd -P) || exit 1
for py in python3 python3.13 python3.12 python3.11 python3.10 python3.9 /usr/libexec/platform-python; do
    if command -v "$py" >/dev/null 2>&1 &&
        "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        # -B: no __pycache__ in the repo; -s: ignore user site-packages.
        PYTHONPATH="$repo" exec "$py" -B -s -m installer "$@"
    fi
done
echo "install.sh: needs Python 3.9 or newer (python3); install it first" >&2
exit 1
