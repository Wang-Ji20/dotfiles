"""Read-only snapshot of the machine. Nothing here writes anything."""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
from typing import List, Optional

from .plan import BACKUP, Found, Managed, Node, Observation, Options, paths_to_observe
from .spec import Repo, Version, merge_requirements, parse_version

STATE_DIR = ".local/state/dotfiles"
GIT_IDENTITY_KEYS = ("user.name", "user.email", "user.signingkey", "commit.gpgsign")


def probe_env() -> dict:
    """Environment for running `tool --version`: C locale, and no log file from Neovim."""
    return dict(os.environ, LC_ALL="C", NVIM_LOG_FILE=os.devnull)


class StateError(Exception):
    pass


def state_dir(home: str) -> str:
    return os.path.join(home, STATE_DIR)


def load_state(home: str) -> dict:
    path = os.path.join(state_dir(home), "state.json")
    try:
        with open(path) as fh:
            state = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise StateError(f"cannot read {path}: {e}") from e
    if not isinstance(state, dict) or state.get("format") != 1:
        raise StateError(f"{path}: unknown format; move it away to start fresh")
    return state


def node(path: str) -> Node:
    try:
        st = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return Node("missing")
    if stat.S_ISLNK(st.st_mode):
        return Node("link", os.readlink(path))
    if stat.S_ISDIR(st.st_mode):
        return Node("dir")
    return Node("file")


def _existing_ancestor(path: str) -> str:
    while not os.path.lexists(path):
        path = os.path.dirname(path)
    return path


def _device(path: str) -> int:
    return os.stat(_existing_ancestor(path)).st_dev


def glibc_version() -> Optional[Version]:
    try:
        name = os.confstr("CS_GNU_LIBC_VERSION") or ""
    except (ValueError, OSError):
        return None
    return parse_version(name) if name.startswith("glibc") else None


def arch() -> str:
    m = platform.machine()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(m, m)


def package_manager() -> Optional[str]:
    if shutil.which("zypper"):
        return "zypper"
    if shutil.which("apt-get") and shutil.which("dpkg-query"):
        return "apt"
    return None


def _run(argv: List[str], timeout: int = 20) -> Optional[str]:
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, env=probe_env(), check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.decode(errors="replace") if p.returncode == 0 else None


def tool_version(path: str) -> Optional[Version]:
    out = _run([path, "--version"])
    return parse_version(out) if out is not None else None


def candidate(pm: Optional[str], pkg: str) -> Optional[Version]:
    """Version the package manager would install, without changing anything."""
    if pm == "apt":
        out = _run(["apt-cache", "policy", pkg]) or ""
        for line in out.splitlines():
            if line.strip().startswith("Candidate:"):
                v = line.split(":", 1)[1].strip()
                return None if v == "(none)" else parse_version(v)
        return None
    if pm == "zypper":
        out = _run(["zypper", "--non-interactive", "--no-refresh", "info", pkg], timeout=60) or ""
        for line in out.splitlines():
            if line.startswith("Version"):
                return parse_version(line.split(":", 1)[1])
    return None


def is_installed(pm: Optional[str], pkg: str) -> bool:
    if pm == "apt":
        out = _run(["dpkg-query", "-W", "-f=${Status}", pkg]) or ""
        return "install ok installed" in out
    if pm == "zypper":
        return _run(["rpm", "-q", "--whatprovides", pkg]) is not None
    return False


def git_identity(home: str) -> tuple:
    old = os.path.join(home, ".gitconfig")
    if node(old).kind != "file" or not shutil.which("git"):
        return ()
    pairs = []
    for key in GIT_IDENTITY_KEYS:
        out = _run(["git", "config", "--file", old, "--get", key])
        if out is not None:
            pairs.append((key, out.strip()))
    return tuple(pairs)


def observe(repo: Repo, selected: List[str], home: str, opts: Options, state: dict) -> Observation:
    obs = Observation(home=home, euid=os.geteuid(), arch=arch(), glibc=glibc_version(),
                      pm=package_manager(), state=state)
    repo_prefix = os.path.realpath(repo.root) + os.sep
    state_dev = _device(state_dir(home))
    backup_ok = _device(os.path.join(home, BACKUP)) == state_dev
    for rel in sorted(paths_to_observe(repo, selected, state)):
        full = os.path.join(home, rel)
        obs.nodes[rel] = node(full)
        parent = os.path.realpath(os.path.dirname(full))
        if (parent + os.sep).startswith(repo_prefix):
            obs.blocked[rel] = f"its directory resolves into the repo ({parent}); move that symlink away"
        elif not backup_ok or _device(os.path.dirname(full)) != state_dev:
            obs.blocked[rel] = "on a different filesystem from ~/.local/state (no atomic rename)"

    reqs = merge_requirements([repo.modules[n] for n in selected])
    search = os.pathsep.join([os.path.join(home, ".local/bin"), os.environ.get("PATH", "")])
    privileged = obs.euid == 0 or opts.sudo
    for req in reqs:
        pkg = req.pkg(obs.pm)
        if req.kind == "package":
            if pkg and is_installed(obs.pm, pkg):
                obs.installed.add(pkg)
            elif opts.packages and privileged and pkg:
                obs.candidates[pkg] = candidate(obs.pm, pkg)
            continue
        path = shutil.which(req.name, path=search)
        if path:
            obs.found[req.name] = Found(path, tool_version(path) if req.min else None)
        if opts.packages and privileged and pkg and pkg not in obs.candidates:
            satisfied = path and (req.min is None or (obs.found[req.name].version or ()) >= req.min)
            if not satisfied:
                obs.candidates[pkg] = candidate(obs.pm, pkg)

    for name, t in state.get("tools", {}).items():
        store = os.path.join(home, t.get("store", ""))
        bins = list(t.get("bins", {}).values())
        bins_ok = bool(bins) and all(obs.node(b[0]) == Node("link", b[1]) for b in bins)
        runs = False
        if bins_ok and os.path.isdir(store):
            runs = _run([os.path.join(home, bins[0][0]), "--version"]) is not None
        obs.managed[name] = Managed(os.path.isdir(store), bins_ok, runs)

    if any(repo.modules[n].seed_git_identity for n in selected):
        obs.git_identity = git_identity(home)
    return obs
