"""Repository data: modules, profiles, tools.lock. Parsing and selection are pure."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Version = Tuple[int, ...]


class SpecError(Exception):
    pass


def parse_version(text: str) -> Optional[Version]:
    """First dotted number in `text`: 'NVIM v0.12.6' -> (0, 12, 6), '1:14.0-55' -> (14, 0)."""
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def fmt_version(v: Optional[Version]) -> str:
    return ".".join(map(str, v)) if v else "?"


@dataclass(frozen=True)
class Requirement:
    """A command (kind 'tool') or a system package without a command (kind 'package')."""

    name: str
    kind: str = "tool"
    min: Optional[Version] = None
    optional: bool = False
    pkgs: Tuple[Tuple[str, str], ...] = ()  # (package manager, package name)

    def pkg(self, pm: Optional[str]) -> Optional[str]:
        return dict(self.pkgs).get(pm) if pm else None


@dataclass(frozen=True)
class Module:
    name: str
    description: str = ""
    requires: Tuple[str, ...] = ()
    reqs: Tuple[Requirement, ...] = ()
    seed_git_identity: bool = False
    files: Tuple[str, ...] = ()  # paths relative to modules/<name>/home == relative to $HOME


@dataclass(frozen=True)
class Release:
    name: str
    version: Version
    arch: str
    glibc: Optional[Version]  # None means static
    sha256: str
    url: str
    bins: Tuple[Tuple[str, str], ...]  # (command, path inside the unpacked archive)

    @property
    def dirname(self) -> str:
        return f"{self.name}-{fmt_version(self.version)}"


@dataclass(frozen=True)
class Profile:
    name: str
    modules: Tuple[str, ...]
    sudo: bool = False


def _lines(text: str):
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if line:
            yield n, line.split()


def parse_module(name: str, text: str, files: Tuple[str, ...] = ()) -> Module:
    description, requires, reqs, seed = "", [], [], False
    for n, words in _lines(text):
        key, rest = words[0], words[1:]
        where = f"modules/{name}/module.conf:{n}"
        if key == "description":
            description = " ".join(rest)
        elif key == "requires":
            requires += rest
        elif key in ("tool", "package"):
            if not rest:
                raise SpecError(f"{where}: {key} needs a name")
            minv, optional, pkgs = None, False, []
            for opt in rest[1:]:
                if opt == "optional":
                    optional = True
                elif opt.startswith("min="):
                    minv = parse_version(opt[4:])
                    if minv is None:
                        raise SpecError(f"{where}: bad version {opt!r}")
                elif opt.startswith(("zypper=", "apt=")):
                    pm, pkg = opt.split("=", 1)
                    pkgs.append((pm, pkg))
                else:
                    raise SpecError(f"{where}: unknown option {opt!r}")
            reqs.append(Requirement(rest[0], key, minv, optional, tuple(pkgs)))
        elif key == "seed-git-identity":
            seed = True
        else:
            raise SpecError(f"{where}: unknown directive {key!r}")
    return Module(name, description, tuple(requires), tuple(reqs), seed, files)


def parse_profile(name: str, text: str) -> Profile:
    mods, sudo = [], False
    for n, words in _lines(text):
        if words[0] == "option":
            for opt in words[1:]:
                if opt != "sudo":
                    raise SpecError(f"profiles/{name}:{n}: unknown option {opt!r}")
                sudo = True
        else:
            mods += words
    return Profile(name, tuple(mods), sudo)


def parse_lock(text: str) -> List[Release]:
    out = []
    for n, words in _lines(text):
        if len(words) != 7:
            raise SpecError(f"tools.lock:{n}: expected 7 fields, got {len(words)}")
        name, ver, arch, glibc, sha, url, bins = words
        pairs = []
        for item in bins.split(","):
            cmd, _, path = item.partition("=")
            if not cmd or not path or path.startswith("/") or ".." in path.split("/"):
                raise SpecError(f"tools.lock:{n}: bad bin {item!r}")
            pairs.append((cmd, path))
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise SpecError(f"tools.lock:{n}: bad sha256")
        version = parse_version(ver)
        if version is None:
            raise SpecError(f"tools.lock:{n}: bad version {ver!r}")
        out.append(Release(name, version, arch, None if glibc == "static" else parse_version(glibc),
                           sha, url, tuple(pairs)))
    return out


@dataclass
class Repo:
    root: str
    modules: Dict[str, Module] = field(default_factory=dict)
    profiles: Dict[str, Profile] = field(default_factory=dict)
    releases: List[Release] = field(default_factory=list)


def load_repo(root: str) -> Repo:
    """Read the repository (read-only)."""
    repo = Repo(root)
    mdir = os.path.join(root, "modules")
    for name in sorted(os.listdir(mdir)):
        conf = os.path.join(mdir, name, "module.conf")
        if not os.path.isfile(conf):
            continue
        home = os.path.join(mdir, name, "home")
        files = []
        for dirpath, dirnames, filenames in os.walk(home):
            dirnames.sort()
            for f in sorted(filenames):
                files.append(os.path.relpath(os.path.join(dirpath, f), home))
        with open(conf) as fh:
            repo.modules[name] = parse_module(name, fh.read(), tuple(files))
    pdir = os.path.join(root, "profiles")
    if os.path.isdir(pdir):
        for name in sorted(os.listdir(pdir)):
            with open(os.path.join(pdir, name)) as fh:
                repo.profiles[name] = parse_profile(name, fh.read())
    lock = os.path.join(root, "tools.lock")
    if os.path.isfile(lock):
        with open(lock) as fh:
            repo.releases = parse_lock(fh.read())
    validate(repo)
    return repo


def validate(repo: Repo) -> None:
    owner: Dict[str, str] = {}
    for m in repo.modules.values():
        for r in m.requires:
            if r not in repo.modules:
                raise SpecError(f"module {m.name} requires unknown module {r!r}")
        for f in m.files:
            if f in owner:
                raise SpecError(f"~/{f} is provided by both {owner[f]} and {m.name}")
            owner[f] = m.name
    for p in repo.profiles.values():
        for name in p.modules:
            if name not in repo.modules:
                raise SpecError(f"profile {p.name} lists unknown module {name!r}")


def select(modules: Dict[str, Module], base: List[str], drop: List[str]) -> List[str]:
    """Modules in `base` plus everything they require, minus `drop`. Pure."""
    for name in list(base) + list(drop):
        if name not in modules:
            raise SpecError(f"unknown module {name!r} (see --list)")
    chosen, todo = set(), [m for m in base if m not in drop]
    while todo:
        name = todo.pop()
        if name in chosen:
            continue
        chosen.add(name)
        for dep in modules[name].requires:
            if dep in drop:
                raise SpecError(f"{name} requires {dep}; drop {name} too or keep {dep}")
            todo.append(dep)
    return sorted(chosen)


def merge_requirements(mods: List[Module]) -> List[Requirement]:
    """One requirement per (kind, name): highest minimum, optional only if optional everywhere."""
    merged: Dict[Tuple[str, str], Requirement] = {}
    for m in mods:
        for r in m.reqs:
            key = (r.kind, r.name)
            old = merged.get(key)
            if old is None:
                merged[key] = r
                continue
            mins = [v for v in (old.min, r.min) if v]
            pkgs = dict(old.pkgs)
            pkgs.update(dict(r.pkgs))
            merged[key] = Requirement(r.name, r.kind, max(mins) if mins else None,
                                      old.optional and r.optional, tuple(sorted(pkgs.items())))
    return [merged[k] for k in sorted(merged)]
