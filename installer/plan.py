"""desired state + observed state -> list of operations. Everything here is pure.

All paths in the plan and in the state file are relative to $HOME, except link
sources (absolute paths into the repo).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .spec import Release, Repo, Requirement, Version, fmt_version, merge_requirements

STORE = ".local/opt/dotfiles"  # unpacked release binaries, one dir per <name>-<version>
BIN = ".local/bin"
BACKUP = ".dotfiles-backup"
STATE_FORMAT = 1


# --- observation (filled in by observe.py, or by hand in tests) -------------

@dataclass(frozen=True)
class Node:
    kind: str  # "missing" | "link" | "file" | "dir"
    dest: Optional[str] = None  # readlink() for links


MISSING = Node("missing")


@dataclass(frozen=True)
class Found:
    """A command found on PATH (with ~/.local/bin first)."""
    path: str
    version: Optional[Version] = None


@dataclass(frozen=True)
class Managed:
    """A tool this repo installed earlier (listed in the state file)."""
    store_ok: bool
    bins_ok: bool
    runs: bool


@dataclass
class Observation:
    home: str
    euid: int = 1000
    arch: str = "x86_64"
    glibc: Optional[Version] = None
    pm: Optional[str] = None  # "apt" | "zypper" | None
    nodes: Dict[str, Node] = field(default_factory=dict)
    blocked: Dict[str, str] = field(default_factory=dict)  # rel -> why it can't be changed
    found: Dict[str, Found] = field(default_factory=dict)
    managed: Dict[str, Managed] = field(default_factory=dict)
    candidates: Dict[str, Optional[Version]] = field(default_factory=dict)  # pkg -> candidate
    installed: Set[str] = field(default_factory=set)  # system packages already installed
    git_identity: Tuple[Tuple[str, str], ...] = ()
    state: dict = field(default_factory=dict)

    def node(self, rel: str) -> Node:
        return self.nodes.get(rel, MISSING)


@dataclass(frozen=True)
class Options:
    packages: bool = False  # resolve and install tools
    sudo: bool = False  # allowed to run the package manager through sudo
    stamp: str = "backup"  # backup directory name for this run


# --- operations ---------------------------------------------------------------

@dataclass(frozen=True)
class Unlink:
    target: str
    phase = 0

    def describe(self) -> str:
        return f"unlink  ~/{self.target}"


@dataclass(frozen=True)
class RemoveTool:
    name: str
    version: str
    store: str
    bins: Tuple[Tuple[str, str], ...]  # (bin rel, expected link dest)
    phase = 0

    def describe(self) -> str:
        return f"remove  {self.name} {self.version} (~/{self.store})"


@dataclass(frozen=True)
class InstallRelease:
    release: Release
    store: str
    bins: Tuple[Tuple[str, str, Optional[str]], ...]  # (bin rel, link dest, replace)
    phase = 1

    def describe(self) -> str:
        r = self.release
        cmds = ", ".join(os.path.basename(b[0]) for b in self.bins)
        extra = "".join(f"\n          replace ~/{b[0]} (backup in ~/{b[2]})"
                        for b in self.bins if b[2] not in (None, "ours"))
        return f"fetch   {r.name} {fmt_version(r.version)} -> ~/{BIN}/{{{cmds}}}{extra}"


@dataclass(frozen=True)
class Link:
    target: str
    source: str
    backup: Optional[str]  # where the existing file goes, if any
    phase = 2

    def describe(self) -> str:
        if self.backup:
            return f"replace ~/{self.target} (backup in ~/{os.path.dirname(self.backup)})"
        return f"link    ~/{self.target}"


@dataclass(frozen=True)
class Seed:
    target: str
    values: Tuple[Tuple[str, str], ...]
    phase = 3

    def describe(self) -> str:
        keys = ", ".join(k for k, _ in self.values)
        return f"create  ~/{self.target} ({keys} from your old ~/.gitconfig)"


@dataclass(frozen=True)
class WriteState:
    state: dict = field(compare=False, hash=False)
    phase = 4

    def describe(self) -> str:
        return "record  selection in ~/.local/state/dotfiles/state.json"


@dataclass(frozen=True)
class Packages:
    pm: str
    pkgs: Tuple[str, ...]
    sudo: bool
    phase = 5  # last: the one step that cannot be rolled back

    def describe(self) -> str:
        return f"install {'sudo ' if self.sudo else ''}{self.pm}: {' '.join(self.pkgs)}"


@dataclass
class Plan:
    ops: list = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    state: dict = field(default_factory=dict)


# --- planning -------------------------------------------------------------------

def link_sources(repo: Repo, selected: List[str]) -> Dict[str, str]:
    out = {}
    for name in selected:
        for rel in repo.modules[name].files:
            out[rel] = os.path.join(repo.root, "modules", name, "home", rel)
    return out


def pick_release(releases: List[Release], req: Requirement, obs: Observation) -> Optional[Release]:
    for r in releases:
        if r.name != req.name or r.arch != obs.arch:
            continue
        if r.glibc is not None and (obs.glibc is None or r.glibc > obs.glibc):
            continue
        if req.min is not None and r.version < req.min:
            continue
        return r
    return None


def paths_to_observe(repo: Repo, selected: List[str], state: dict) -> Set[str]:
    """Every $HOME-relative path the plan may look at."""
    paths = set(link_sources(repo, selected)) | set(state.get("links", {})) | {".gitconfig.local"}
    names = {r.name for m in selected for r in repo.modules[m].reqs}
    for r in repo.releases:
        if r.name in names:
            paths |= {f"{BIN}/{cmd}" for cmd, _ in r.bins}
    for t in state.get("tools", {}).values():
        paths |= {b[0] for b in t.get("bins", {}).values()}
    return paths


def _bin_dest(store: str, path: str) -> str:
    """Relative symlink target from ~/.local/bin/<cmd> into the store."""
    return os.path.relpath(os.path.join(store, path), BIN)


def _tool_state(rel: Release) -> dict:
    store = f"{STORE}/{rel.dirname}"
    return {"version": fmt_version(rel.version), "store": store,
            "bins": {cmd: [f"{BIN}/{cmd}", _bin_dest(store, path)] for cmd, path in rel.bins}}


def _remove(name: str, old: dict) -> RemoveTool:
    bins = tuple((b[0], b[1]) for b in old.get("bins", {}).values())
    return RemoveTool(name, old.get("version", "?"), old.get("store", ""), bins)


def _install(rel: Release, obs: Observation, opts: Options, plan: Plan) -> Optional[InstallRelease]:
    store = f"{STORE}/{rel.dirname}"
    bins = []
    for cmd, path in rel.bins:
        target = f"{BIN}/{cmd}"
        node = obs.node(target)
        if target in obs.blocked:
            plan.errors.append(f"~/{target}: {obs.blocked[target]}")
            return None
        if node.kind == "missing":
            replace = None
        elif node.kind == "link" and node.dest and node.dest.startswith(os.path.relpath(STORE, BIN) + "/"):
            replace = "ours"
        else:
            replace = f"{BACKUP}/{opts.stamp}/{target}"
        bins.append((target, _bin_dest(store, path), replace))
    return InstallRelease(rel, store, tuple(bins))


def _missing_reason(req: Requirement, obs: Observation) -> str:
    f = obs.found.get(req.name)
    if f and req.min:
        return f"{req.name} {fmt_version(f.version)} is older than {fmt_version(req.min)}"
    return f"{req.name} not found"


def make_plan(repo: Repo, selected: List[str], obs: Observation, opts: Options) -> Plan:
    plan = Plan()
    mods = [repo.modules[n] for n in selected]
    state = obs.state
    old_links: Dict[str, str] = state.get("links", {})
    old_tools: Dict[str, dict] = state.get("tools", {})
    new_tools: Dict[str, dict] = {}

    # Dotfile links.
    desired = link_sources(repo, selected)
    for rel, src in desired.items():
        node = obs.node(rel)
        if node.kind == "link" and node.dest == src:
            continue
        if rel in obs.blocked:
            plan.errors.append(f"~/{rel}: {obs.blocked[rel]}")
            continue
        backup = None if node.kind == "missing" else f"{BACKUP}/{opts.stamp}/{rel}"
        plan.ops.append(Link(rel, src, backup))
    for rel, src in old_links.items():
        if rel in desired:
            continue
        node = obs.node(rel)
        if node.kind == "link" and node.dest == src:
            plan.ops.append(Unlink(rel))
        elif node.kind != "missing":
            plan.warnings.append(f"~/{rel} no longer links to this repo; leaving it alone")

    # Identity from an existing real ~/.gitconfig, before the link replaces it.
    if any(m.seed_git_identity for m in mods) and obs.git_identity \
            and obs.node(".gitconfig.local").kind == "missing":
        plan.ops.append(Seed(".gitconfig.local", obs.git_identity))

    # Tools.
    reqs = merge_requirements(mods)
    privileged = obs.euid == 0 or opts.sudo
    pkgs: List[str] = []
    for req in reqs:
        if req.kind == "package":
            pkg = req.pkg(obs.pm)
            if pkg and pkg in obs.installed:
                continue
            if not opts.packages:
                continue
            if privileged and pkg and obs.candidates.get(pkg):
                pkgs.append(pkg)
            else:
                _unresolved(req, f"package {req.name} needs a package manager and root or --sudo", plan)
            continue

        old = old_tools.get(req.name)
        if old is not None:
            m = obs.managed.get(req.name)
            if m and m.store_ok and m.bins_ok:
                if not m.runs:
                    plan.warnings.append(
                        f"{req.name} {old.get('version')} (installed by this repo) does not run on "
                        "this machine, maybe another host sharing this home; leaving it alone")
                    new_tools[req.name] = old
                    continue
                rel = pick_release(repo.releases, req, obs) if opts.packages else None
                if rel and fmt_version(rel.version) != old.get("version"):
                    op = _install(rel, obs, opts, plan)
                    if op:
                        plan.ops += [_remove(req.name, old), op]
                        new_tools[req.name] = _tool_state(rel)
                    continue
                new_tools[req.name] = old
                continue
            plan.ops.append(_remove(req.name, old))  # broken: clear what is left

        f = obs.found.get(req.name)
        if f and (req.min is None or (f.version is not None and f.version >= req.min)):
            continue
        if not opts.packages:
            if not req.optional:
                plan.warnings.append(f"{_missing_reason(req, obs)}; run with --packages to install it")
            continue
        pkg = req.pkg(obs.pm)
        cand = obs.candidates.get(pkg) if pkg else None
        if privileged and cand and (req.min is None or cand >= req.min):
            pkgs.append(pkg)
            continue
        rel = pick_release(repo.releases, req, obs)
        if rel:
            op = _install(rel, obs, opts, plan)
            if op:
                plan.ops.append(op)
                new_tools[req.name] = _tool_state(rel)
            continue
        where = f"{obs.arch}, glibc {fmt_version(obs.glibc)}"
        how = "no compatible release" + ("" if privileged else " and no root/--sudo for system packages")
        _unresolved(req, f"{_missing_reason(req, obs)}: {how} ({where})", plan)

    wanted = {r.name for r in reqs if r.kind == "tool"}
    for name, old in old_tools.items():
        if name not in wanted:
            plan.ops.append(_remove(name, old))

    if pkgs:
        plan.ops.append(Packages(obs.pm or "?", tuple(sorted(set(pkgs))), sudo=obs.euid != 0))

    plan.state = {
        "format": STATE_FORMAT,
        "repo": repo.root,
        "modules": list(selected),
        "sudo": opts.sudo,
        "links": desired,
        "tools": new_tools,
    }
    if plan.state != state:
        plan.ops.append(WriteState(plan.state))
    plan.ops.sort(key=lambda op: op.phase)
    return plan


def _unresolved(req: Requirement, msg: str, plan: Plan) -> None:
    (plan.warnings if req.optional else plan.errors).append(msg + (" (optional)" if req.optional else ""))
