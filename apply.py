"""Make this machine match environment.toml.

Every step checks the current state first and only acts on the difference, so
running it again changes nothing. Versions are "latest": a missing tool is
installed at its latest release; tools that are present are left alone.
"""
from __future__ import annotations

import argparse
import configparser
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent
SPEC = REPO / "environment.toml"
HOME = Path.home()
STATE = HOME / ".local/state/dotfiles"
LOCAL_BIN = HOME / ".local/bin"
PNPM_HOME = HOME / ".local/share/pnpm"

# Where tools installed into $HOME live; on PATH for this run so later steps find them.
USER_PATHS = [LOCAL_BIN, HOME / ".pixi/bin", PNPM_HOME / "bin", PNPM_HOME,
              HOME / ".cargo/bin", HOME / ".ghcup/bin", HOME / ".cabal/bin", HOME / ".juliaup/bin"]
SDKMAN = HOME / ".sdkman"
SUDO_PROVIDERS = ("zypper",)


def expand(p: str) -> Path:
    return Path(os.path.expanduser(p)) if p.startswith("~") else REPO / p


# ── steps ────────────────────────────────────────────────────────────────────

@dataclass
class Step:
    what: str                    # shown in the plan
    do: Callable[[], None]


class Failed(Exception):
    pass


def run(cmd: str | list[str], *, input: str | None = None, env: dict | None = None,
        quiet: bool = False) -> subprocess.CompletedProcess:
    args = cmd if isinstance(cmd, list) else ["sh", "-c", cmd]
    shown = cmd if isinstance(cmd, str) else shlex.join(cmd)
    print(f"    $ {shown}")
    r = subprocess.run(args, input=input, text=True, env={**os.environ, **(env or {})},
                       stdout=subprocess.PIPE if quiet else None,
                       stderr=subprocess.STDOUT if quiet else None)
    if r.returncode != 0:
        if quiet and r.stdout:
            print(r.stdout[-2000:])
        raise Failed(f"exit {r.returncode}: {shown}")
    return r


def out(cmd: list[str]) -> str:
    """Read-only query; empty string if the command is missing or fails."""
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def version_of(cmd: str) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", out([cmd, "--version"]))
    return tuple(int(x) for x in m.groups() if x is not None) if m else None


def meets(cmd: str, minimum: str | None) -> bool:
    if not have(cmd):
        return False
    if not minimum:
        return True
    v = version_of(cmd)
    return v is not None and v >= tuple(int(x) for x in minimum.split("."))


# ── links ────────────────────────────────────────────────────────────────────

def link_steps(spec: dict, backup: Path) -> list[Step]:
    steps: list[Step] = []
    wanted: dict[Path, Path] = {}
    for src_s, dst_s in spec["links"].items():
        src, dst = expand(src_s), expand(dst_s)
        if src.is_dir():
            for f in sorted(p for p in src.rglob("*") if p.is_file()):
                wanted[dst / f.relative_to(src)] = f
        else:
            wanted[dst] = src

    def make_link(dst: Path, src: Path) -> Callable[[], None]:
        def do() -> None:
            if dst.is_symlink() or dst.exists():
                bak = backup / dst.relative_to(HOME)
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), bak)
                print(f"    moved old file to {bak}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)
        return do

    for dst, src in wanted.items():
        if dst.is_symlink() and dst.resolve() == src.resolve():
            continue
        state = "replace" if (dst.exists() or dst.is_symlink()) else "link"
        steps.append(Step(f"{state} {tilde(dst)} -> {src.relative_to(REPO)}", make_link(dst, src)))

    # Links into config/ whose source was removed from the repo.
    for dst_s in spec["links"].values():
        root = expand(dst_s)
        if not root.is_dir() or root.is_symlink():
            continue
        for p in root.rglob("*"):
            if p.is_symlink() and p not in wanted:
                target = Path(os.readlink(p))
                if (REPO / "config") in target.parents and not target.exists():
                    steps.append(Step(f"remove stale link {tilde(p)}", p.unlink))

    ssh = HOME / ".ssh"
    if any(ssh in d.parents for d in wanted) and (not ssh.exists() or ssh.stat().st_mode & 0o077):
        steps.insert(0, Step("~/.ssh: create with mode 700", lambda: (ssh.mkdir(exist_ok=True), ssh.chmod(0o700))))
    return steps


def bashrc_step(spec: dict) -> list[Step]:
    rc, line = HOME / ".bashrc", spec["bashrc"]["line"]
    if rc.exists() and line in rc.read_text().splitlines():
        return []

    def do() -> None:
        text = rc.read_text() if rc.exists() else ""
        rc.write_text(text + ("" if text.endswith("\n") or not text else "\n") + line + "\n")
    return [Step("~/.bashrc: add the dotfiles line", do)]


def git_identity_steps(spec: dict, machine: dict) -> list[Step]:
    # ~/.gitconfig is the per-machine file. It must exist before `git config --global`
    # runs, or git would write into ~/.config/git/config, i.e. into this repo.
    gc = HOME / ".gitconfig"
    keys = ("user.name", "user.email", "user.signingkey", "commit.gpgsign")
    current = {k: out(["git", "config", "--file", str(gc), k]).strip() for k in keys} if gc.exists() else {}
    want = {"user.name": spec["git-identity"]["name"]}
    # Sign only once this machine has its own key; signing without one breaks every commit.
    key = gpg_key(current.get("user.email", "")) if machine.get("gpg-signing") else None
    if key:
        want["user.signingkey"] = key
    want["commit.gpgsign"] = "true" if key else "false"
    steps = [Step(f"~/.gitconfig: {k} = {v}", (lambda k=k, v=v: (gc.touch(), run(["git", "config", "--file", str(gc), k, v]))))
             for k, v in want.items() if current.get(k) != v]

    if not current.get("user.email"):
        def ask() -> None:
            if not sys.stdin.isatty():
                raise Failed("user.email not set; run: git config --file ~/.gitconfig user.email you@example.com")
            email = input("    git user.email: ").strip()
            gc.touch()
            run(["git", "config", "--file", str(gc), "user.email", email])
        steps.append(Step("~/.gitconfig: user.email (asked)", ask))
    return steps


def gpg_key(email: str) -> str | None:
    """Newest usable signing key on this machine for `email`, or None."""
    if not email:
        return None
    found = None
    for line in out(["gpg", "--list-secret-keys", "--with-colons", f"<{email}>"]).splitlines():
        f = line.split(":")
        if f[0] == "sec" and f[1] not in ("r", "e", "d", "i") and "S" in f[11]:
            found = f[4]
    return found


def machine_link_steps(machine: dict) -> list[Step]:
    steps = []
    for dst_s, src_s in machine.get("links", {}).items():
        dst, src = expand(dst_s), Path(src_s)
        if dst.is_symlink() and Path(os.readlink(dst)) == src:
            continue
        if dst.exists() or dst.is_symlink():
            steps.append(Step(f"{tilde(dst)} exists and is not a link to {src}: leave it, check by hand", lambda: None))
        else:
            steps.append(Step(f"link {tilde(dst)} -> {src}", lambda d=dst, s=src: d.symlink_to(s)))
    return steps


# ── system (sudo) ────────────────────────────────────────────────────────────

def wsl_conf_steps(machine: dict) -> list[Step]:
    want = machine.get("wsl-conf")
    if not want:
        return []
    path = Path("/etc/wsl.conf")
    cp = configparser.ConfigParser()
    cp.optionxform = str
    if path.exists():
        cp.read(path)
    changes = []
    for section, values in want.items():
        for k, v in values.items():
            v = str(v).lower() if isinstance(v, bool) else str(v)
            if cp.get(section, k, fallback=None) != v:
                if not cp.has_section(section):
                    cp.add_section(section)
                cp.set(section, k, v)
                changes.append(f"{section}.{k}={v}")
    if not changes:
        return []

    def do() -> None:
        buf = io.StringIO()
        cp.write(buf)
        run(["sudo", "tee", str(path)], input=buf.getvalue(), quiet=True)
    return [Step(f"/etc/wsl.conf: {', '.join(changes)} (takes effect after `wsl --shutdown`)", do)]


def hostname_steps(machine: dict) -> list[Step]:
    h = machine.get("hostname")
    etc = Path("/etc/hostname")
    if not h or (etc.exists() and etc.read_text().strip() == h):
        return []
    return [Step(f"hostname {h}", lambda: run(["sudo", "hostnamectl", "set-hostname", h]))]


def btrfs_quota_steps(machine: dict) -> list[Step]:
    """btrfs-quota = false: no qgroups on /, and snapper not relying on them.
    With qgroups, every snapshot delete makes btrfs-cleaner pin a core and stall writes."""
    if machine.get("btrfs-quota", True):
        return []
    steps: list[Step] = []
    snapper = Path("/etc/snapper/configs/root")
    if snapper.exists() and re.search(r'^QGROUP="[^"]+"', snapper.read_text(), re.M):
        steps.append(Step("snapper: stop using qgroups (QGROUP=\"\")", lambda: run(
            ["sudo", "sed", "-i", 's/^QGROUP=.*/QGROUP=""/', str(snapper)])))
    uuid = out(["findmnt", "-no", "UUID", "/"]).strip()
    if uuid and Path(f"/sys/fs/btrfs/{uuid}/qgroups").exists():
        steps.append(Step("btrfs: disable quota on /", lambda: run(["sudo", "btrfs", "quota", "disable", "/"])))
    return steps


def kernel_args_steps(machine: dict) -> list[Step]:
    """kernel-args = [...]: present in /etc/kernel/cmdline (a `key=` already there is replaced,
    other args are kept), then sdbootutil rewrites the systemd-boot entries from it."""
    want = machine.get("kernel-args", [])
    path = Path("/etc/kernel/cmdline")
    if not want or not path.exists():
        return []
    have_args = path.read_text().split()
    args = list(have_args)
    for a in want:
        key = a.split("=", 1)[0]
        same = [i for i, x in enumerate(args) if x.split("=", 1)[0] == key]
        if same:
            args[same[0]] = a
            for i in reversed(same[1:]):
                del args[i]
        else:
            args.append(a)
    if args == have_args:
        return []

    def do() -> None:
        run(["sudo", "tee", str(path)], input=" ".join(args) + "\n", quiet=True)
        run(["sudo", "sdbootutil", "update-all-entries"])
    added = [a for a in want if a not in have_args]
    return [Step(f"kernel cmdline: {' '.join(added)} (takes effect next boot)", do)]


def polkit_steps(machine: dict) -> list[Step]:
    """polkit = [...]: rule files from system/polkit/ copied into /etc/polkit-1/rules.d/."""
    steps: list[Step] = []
    for name in machine.get("polkit", []):
        src, dst = REPO / "system/polkit" / name, Path("/etc/polkit-1/rules.d") / name
        # rules.d is root:polkitd 750, so compare against a copy of what we last installed.
        seen = STATE / "polkit" / name
        if seen.exists() and seen.read_bytes() == src.read_bytes():
            continue

        def do(s: Path = src, d: Path = dst, k: Path = seen) -> None:
            run(["sudo", "install", "-m", "644", str(s), str(d)])
            k.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(s, k)
        steps.append(Step(f"polkit: install {name}", do))
    return steps


def driver_steps(spec: dict, machine: dict) -> list[Step]:
    """[drivers]: DKMS modules from system/<name>/, signed with an enrolled MOK, loaded at boot."""
    dmi = Path("/sys/class/dmi/id/product_name")
    product = dmi.read_text() if dmi.exists() else ""
    kernel = os.uname().release
    steps: list[Step] = []
    built = [n for n in machine.get("drivers", []) if spec["drivers"][n]["hardware"] in product]
    for name in built:
        src = REPO / "system" / name
        conf = (src / "dkms.conf").read_text()
        ver = re.search(r'PACKAGE_VERSION="([^"]+)"', conf)[1]
        mod = re.search(r'BUILT_MODULE_NAME\[0\]="([^"]+)"', conf)[1]
        dst = Path(f"/usr/src/{name}-{ver}")

        pkgs = ["kernel-default-devel", "dkms", "mokutil"]
        missing = [p for p in pkgs if p not in out(["rpm", "-q", "--qf", "%{NAME}\n", *pkgs]).split()]
        if missing:
            steps.append(Step(f"{name}: zypper install {' '.join(missing)}",
                              lambda m=missing: run(["sudo", "zypper", "-n", "install", *m])))

        files = sorted(p.name for p in src.iterdir() if p.is_file())
        same = dst.is_dir() and sorted(p.name for p in dst.iterdir() if p.is_file()) == files and \
            all((src / f).read_bytes() == (dst / f).read_bytes() for f in files)
        dkms = shutil.which("dkms") or "/usr/sbin/dkms"   # sbin is not on a user's PATH
        installed = "installed" in out([dkms, "status", "-m", name, "-v", ver, "-k", kernel])
        if not same or not installed:
            q = shlex.quote
            steps.append(Step(f"{name}: dkms build + sign for {kernel}, load {mod}", lambda q=q, d=dst, s=src, n=name, v=ver, m=mod: (
                run(f"sudo rm -rf {q(str(d))} && sudo cp -r {q(str(s))} {q(str(d))}"),
                run(f"sudo dkms remove {n}/{v} --all >/dev/null 2>&1 || true"),
                run(["sudo", "dkms", "install", f"{n}/{v}", "--force"]),
                run(f"sudo modprobe -r {m} 2>/dev/null; sudo modprobe {m} || echo '    (loads after the MOK is enrolled)'"))))

        load = Path(f"/etc/modules-load.d/{name}.conf")
        if not load.exists() or load.read_text().strip() != mod:
            steps.append(Step(f"{name}: load {mod} at boot", lambda l=load, m=mod:
                              run(["sudo", "tee", str(l)], input=m + "\n", quiet=True)))

    key = "/var/lib/dkms/mok.pub"
    if built and "already enrolled" not in out(["mokutil", "--test-key", key]):
        steps.append(Step("dkms: enroll signing key (pick a one-time password; reboot, then "
                          "Enroll MOK -> Continue -> Yes -> password)",
                          lambda: run(["sudo", "mokutil", "--import", key])))
    return steps


def kde_steps(spec: dict, machine: dict) -> list[Step]:
    """[kde] settings, on machines whose desktop is KDE Plasma (once Plasma is installed)."""
    if not str(machine.get("desktop", "")).startswith("KDE") or not have("kwriteconfig6"):
        return []
    kde = spec.get("kde", {})
    read = lambda f, g, k: out(["kreadconfig6", "--file", f, "--group", g, "--key", k]).rstrip("\n")
    steps: list[Step] = []
    laf = kde.get("look-and-feel")
    if laf and read("kdeglobals", "KDE", "LookAndFeelPackage") != laf:
        steps.append(Step(f"kde: look and feel {laf}", lambda: run(["plasma-apply-lookandfeel", "-a", laf])))
    for f, groups in kde.get("settings", {}).items():
        for group, keys in groups.items():
            g = os.path.expanduser(group)
            for k, v in keys.items():
                val = str(v).lower() if isinstance(v, bool) else str(v)
                if read(f, g, k) != val:
                    args = ["kwriteconfig6", "--file", f, "--group", g, "--key", k,
                            *(["--type", "bool"] if isinstance(v, bool) else []), val]
                    steps.append(Step(f"kde: {f} [{tilde(Path(g)) if g.startswith('/') else g}] {k} = {val}",
                                      lambda a=args: run(a)))
    return steps


def zypper_steps(spec: dict, tools: list[str]) -> list[Step]:
    T = spec["tools"]
    steps: list[Step] = []
    repos = sorted({T[t]["repo"] for t in tools if "repo" in T[t]})
    have_repos = out(["zypper", "-q", "lr", "-u"])
    for name in repos:
        r = spec["repos"][name]
        if r["url"].rstrip("/") in have_repos:
            continue
        steps.append(Step(f"zypper repo {name}", lambda r=r, n=name: (
            run(["sudo", "rpm", "--import", r["key"]]),
            run(["sudo", "zypper", "-n", "addrepo", "--refresh", r["url"], n]))))

    pkgs = [p for t in tools for p in T[t].get("zypper", [])]
    # rpm prints the name for installed packages, "package X is not installed" otherwise.
    installed = {l for l in out(["rpm", "-q", "--qf", "%{NAME}\n", *pkgs]).splitlines() if " " not in l} if pkgs else set()
    missing = [p for p in dict.fromkeys(pkgs) if p not in installed]
    if missing:
        steps.append(Step(f"zypper install {' '.join(missing)}",
                          lambda: run(["sudo", "zypper", "-n", "--gpg-auto-import-keys", "install", *missing])))

    for t in tools:
        svc = T[t].get("firewall")
        if svc and have("firewall-cmd") and svc not in out(["firewall-cmd", "--list-services"]).split():
            steps.append(Step(f"firewall: open {svc}", lambda s=svc: (
                run(["sudo", "firewall-cmd", "--permanent", f"--add-service={s}"]),
                run(["sudo", "firewall-cmd", "--reload"]))))
    return steps


# ── user-level tools ─────────────────────────────────────────────────────────

def fetch(url: str) -> bytes:
    print(f"    GET {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def run_script(url: str, *args: str, shell: str = "bash") -> None:
    """Official install script: download it fully first, then run it."""
    run([shell, "-s", "--", *args], input=fetch(url).decode())


def install_release(name: str, url: str, bindir: Path, unpack: Path | None = None) -> None:
    """Download a binary, .tar.gz or .zip and put the executable `name` into bindir.
    With `unpack`, the whole archive goes there (for programs that need files next
    to them) and bindir gets a symlink to `name` inside it."""
    data = fetch(url)
    bindir.mkdir(parents=True, exist_ok=True)
    dst = bindir / name
    if unpack:
        tmpdir = unpack.with_name(unpack.name + ".tmp")
        shutil.rmtree(tmpdir, ignore_errors=True)
        tmpdir.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            tf.extractall(tmpdir, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        if not (tmpdir / name).is_file():
            raise Failed(f"no {name} at the top of the download")
        shutil.rmtree(unpack, ignore_errors=True)
        tmpdir.replace(unpack)
        dst.unlink(missing_ok=True)
        dst.symlink_to(unpack / name)
        return
    if url.endswith((".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            m = pick(name, members, lambda m: Path(m.name).name)
            payload = tf.extractfile(m).read()
    elif url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            payload = zf.read(pick(name, names, lambda n: Path(n).name))
    else:
        payload = data
    tmp = dst.with_suffix(".tmp")
    tmp.write_bytes(payload)
    tmp.chmod(0o755)
    tmp.replace(dst)


def pick(name: str, items: list, base: Callable) -> object:
    for exact in (True, False):
        for it in items:
            b = base(it)
            if (b == name) if exact else b.startswith(name + "-"):
                return it
    raise Failed(f"no file named {name}* in the download")


def tool_steps(spec: dict, machine: dict, tools: list[str]) -> list[Step]:
    T = spec["tools"]
    sudo = machine.get("sudo", False)
    provide = machine.get("provide", [])
    steps: list[Step] = []

    for t in machine.get("bootstrap", []):
        cfg = T[t]
        bindir = expand(cfg.get("bin", "~/.local/bin"))
        if not (bindir / t).exists():
            url = f"https://github.com/{cfg['github']}/releases/latest/download/{cfg['asset']}"
            steps.append(Step(f"{t}: latest release -> {tilde(bindir)}", lambda t=t, u=url, b=bindir: install_release(t, u, b)))

    # Tools that others are installed with (pnpm, uv) go first, or e.g. `pnpm add -g`
    # would run before pnpm itself is installed.
    providers = {k for t in tools for k in T[t]} & set(tools)
    for t in sorted(tools, key=lambda t: t not in providers):
        cfg = T[t]
        # Tools covered by zypper on sudo machines are handled in zypper_steps.
        if sudo and "zypper" in cfg and not set(cfg) - {"zypper", "repo", "firewall", "min"}:
            continue
        if not sudo and "conda" in cfg:
            if "system" in provide and meets(t, cfg.get("min")):
                continue
            if "conda" in provide:
                steps.append(Step(f"{t}: pixi global install {cfg['conda']}",
                                  lambda c=cfg["conda"]: run(["pixi", "global", "install", c])))
                continue
        steps += provider_steps(t, cfg, sudo)
    return steps


def provider_steps(t: str, cfg: dict, sudo: bool) -> list[Step]:
    s: list[Step] = []
    if "installer" in cfg and not have(t):
        s.append(Step(f"{t}: run {cfg['installer']}", lambda u=cfg["installer"]: run_script(u)))
    if "github" in cfg:
        bindir = expand(cfg.get("bin", "~/.local/bin"))
        if not have(t) and not (bindir / t).exists():
            url = f"https://github.com/{cfg['github']}/releases/latest/download/{cfg['asset']}"
            unpack = expand(cfg["dir"]) if "dir" in cfg else None
            s.append(Step(f"{t}: latest {cfg['github']} release -> {tilde(unpack or bindir)}",
                          lambda t=t, u=url, b=bindir, d=unpack: install_release(t, u, b, d)))
    # uv lists normalized names (huggingface_hub -> huggingface-hub).
    norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
    if "uv" in cfg and norm(cfg["uv"]) not in {norm(l.split()[0]) for l in out(["uv", "tool", "list"]).splitlines() if l and not l.startswith("-")}:
        s.append(Step(f"{t}: uv tool install {cfg['uv']}", lambda p=cfg["uv"]: run(["uv", "tool", "install", p])))
    if "uv-python" in cfg and not out(["uv", "python", "list", "--only-installed"]).strip():
        s.append(Step(f"{t}: uv python install", lambda: run(["uv", "python", "install"])))
    if "pnpm" in cfg:
        listed = out(["pnpm", "ls", "-g", "--parseable"])
        miss = [p for p in cfg["pnpm"] if f"/node_modules/{p}" not in listed]
        if miss:
            s.append(Step(f"{t}: pnpm add -g {' '.join(miss)}",
                          lambda m=miss: run(["pnpm", "add", "-g", *m], env={"PNPM_HOME": str(PNPM_HOME)})))
    if "rustup" in cfg:
        r = cfg["rustup"]
        for tc in r.get("toolchains", ["stable"]):
            comps = r.get("components", [])
            installed = out(["rustup", "component", "list", "--installed", "--toolchain", tc])
            if tc not in out(["rustup", "toolchain", "list"]) or any(c not in installed for c in comps):
                args = ["rustup", "toolchain", "install", tc, "--profile", "minimal"] + [x for c in comps for x in ("--component", c)]
                s.append(Step(f"{t}: rustup {tc} + {', '.join(comps)}", lambda a=args: run(a)))
        if "default" not in out(["rustup", "toolchain", "list"]):
            s.append(Step(f"{t}: rustup default stable", lambda: run(["rustup", "default", "stable"])))
    if "sdkman" in cfg:
        if not (SDKMAN / "bin/sdkman-init.sh").exists():
            s.append(Step("sdkman: install (no shell rc edits)",
                          lambda: run_script("https://get.sdkman.io?rcupdate=false")))
        for c in cfg["sdkman"]:
            if not (SDKMAN / "candidates" / c / "current").exists():
                s.append(Step(f"{t}: sdk install {c}", lambda c=c: run(
                    ["bash", "-c", f'source "{SDKMAN}/bin/sdkman-init.sh" && sdk install {c}'], input="y\n" * 5)))
    if "ghcup" in cfg:
        ghcup = HOME / ".ghcup/bin/ghcup"
        if not ghcup.exists():
            s.append(Step("ghcup: download binary", lambda: install_release(
                "ghcup", "https://downloads.haskell.org/~ghcup/x86_64-linux-ghcup", ghcup.parent)))
        cmds = {"ghc": "ghc", "cabal": "cabal", "stack": "stack", "hls": "haskell-language-server-wrapper"}
        for g in cfg["ghcup"]:
            if not have(cmds.get(g, g)):
                s.append(Step(f"{t}: ghcup install {g} recommended", lambda g=g: run([str(ghcup), "install", g, "recommended", "--set"])))
    if "opam" in cfg:
        if not (HOME / ".opam").exists():
            s.append(Step("opam init", lambda: run(["opam", "init", "-n", "--bare", "-y"])))
        sw = cfg["opam"].get("switch", "default")
        if sw not in out(["opam", "switch", "list", "-s"]).split():
            s.append(Step(f"{t}: opam switch create {sw} (latest ocaml)",
                          lambda sw=sw: run(["opam", "switch", "create", sw, "ocaml-base-compiler", "-y"])))
    if "juliaup" in cfg and not have("juliaup"):
        s.append(Step(f"{t}: juliaup", lambda: run_script("https://install.julialang.org", "--yes", "--add-to-path=no", shell="sh")))
    if "git" in cfg:
        g = cfg["git"]
        path = expand(g["path"])
        if not path.exists():
            s.append(Step(f"{t}: git clone {g['url']} ({g['branch']}) -> {tilde(path)}",
                          lambda g=g, p=path: run(["git", "clone", "-b", g["branch"], g["url"], str(p)])))
    return s


# ── report ───────────────────────────────────────────────────────────────────

def secrets_report(spec: dict, machine: dict) -> list[str]:
    # Keys are created fresh on each machine and registered with GitHub; nothing is copied.
    todo = []
    ssh = expand(spec["secrets"]["ssh-key"])
    if not ssh.exists():
        todo.append(f"ssh key: ssh-keygen -t ed25519 -f {tilde(ssh)}")
    if not (HOME / ".config/gh/hosts.yml").exists():
        todo.append("gh: gh auth login   (offers to upload the ssh key)")
    if machine.get("gpg-signing"):
        gc = HOME / ".gitconfig"
        email = out(["git", "config", "--file", str(gc), "user.email"]).strip() if gc.exists() else ""
        if email and not gpg_key(email):
            name = spec["git-identity"]["name"]
            todo.append(f"gpg key: gpg --quick-gen-key '{name} <{email}>' ed25519 sign 2y\n"
                        f"      gh auth refresh -s admin:gpg_key && gpg --armor --export {email} | gh gpg-key add -\n"
                        f"      then ./apply again to turn on commit signing")
    ai = [t for t in spec["secrets"].get("ai-logins", []) if t in machine_tools(spec, machine)]
    if ai:
        todo.append(f"log in once: {', '.join(ai)}")
    return todo


def machine_tools(spec: dict, machine: dict) -> list[str]:
    return list(dict.fromkeys(t for g in machine["groups"] for t in spec["groups"][g]))


def tilde(p: Path) -> str:
    try:
        return "~/" + str(p.relative_to(HOME))
    except ValueError:
        return str(p)


# ── main ─────────────────────────────────────────────────────────────────────

def validate(spec: dict) -> list[str]:
    errs = []
    G, T, R = spec["groups"], spec["tools"], spec["repos"]
    for m, v in spec["machines"].items():
        for g in v["groups"]:
            if g not in G:
                errs.append(f"machine {m}: unknown group {g}")
        for t in [t for g in v["groups"] for t in G.get(g, [])] + v.get("bootstrap", []):
            if t not in T:
                errs.append(f"machine {m}: tool {t} has no [tools] entry")
        for d in v.get("drivers", []):
            if d not in spec.get("drivers", {}):
                errs.append(f"machine {m}: driver {d} has no [drivers] entry")
            elif not (REPO / "system" / d / "dkms.conf").exists():
                errs.append(f"driver {d}: system/{d}/dkms.conf does not exist")
    for t, cfg in T.items():
        if "repo" in cfg and cfg["repo"] not in R:
            errs.append(f"tool {t}: unknown repo {cfg['repo']}")
    for src in spec["links"]:
        if not expand(src).exists():
            errs.append(f"links: {src} does not exist")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Make this machine match environment.toml.")
    ap.add_argument("--machine", help="machine name from environment.toml (remembered after the first run)")
    ap.add_argument("-n", "--dry-run", action="store_true", help="show what would change, change nothing")
    ap.add_argument("--only", choices=["links", "system", "tools", "desktop"], help="run one part only")
    args = ap.parse_args()

    spec = tomllib.loads(SPEC.read_text())
    errs = validate(spec)
    if errs:
        print("environment.toml has errors:\n  " + "\n  ".join(errs))
        return 2

    saved = STATE / "machine"
    mname = args.machine or (saved.read_text().strip() if saved.exists() else None)
    if mname not in spec["machines"]:
        print(f"apply: pass --machine, one of: {', '.join(spec['machines'])}")
        return 2
    machine = spec["machines"][mname]
    tools = machine_tools(spec, machine)
    os.environ["PATH"] = os.pathsep.join([str(p) for p in USER_PATHS] + [os.environ.get("PATH", "")])
    os.environ.setdefault("PNPM_HOME", str(PNPM_HOME))

    backup = HOME / ".dotfiles-backup" / time.strftime("%Y%m%d-%H%M%S")
    parts: list[tuple[str, Callable[[], list[Step]]]] = [
        ("links", lambda: link_steps(spec, backup) + bashrc_step(spec) + git_identity_steps(spec, machine) + machine_link_steps(machine)),
        ("system", lambda: (wsl_conf_steps(machine) + zypper_steps(spec, tools) + hostname_steps(machine)
                            + driver_steps(spec, machine) + btrfs_quota_steps(machine) + polkit_steps(machine)
                            + kernel_args_steps(machine)) if machine.get("sudo") else []),
        ("tools", lambda: tool_steps(spec, machine, tools)),
        ("desktop", lambda: kde_steps(spec, machine)),
    ]

    print(f"machine: {mname} ({', '.join(machine['groups'])})")
    rc_before = {f: f.read_text() if f.exists() else None for f in (HOME / ".bashrc", HOME / ".profile")}
    if not args.dry_run:
        STATE.mkdir(parents=True, exist_ok=True)
        saved.write_text(mname + "\n")
    done: list[Step] = []
    for name, plan in parts:
        if args.only and args.only != name:
            continue
        steps = plan()
        print(f"\n== {name}: {'nothing to do' if not steps else f'{len(steps)} change(s)'}")
        for st in steps:
            print(f"  - {st.what}")
            if args.dry_run:
                continue
            try:
                st.do()
                done.append(st)
            except Exception as e:  # stop at the first failure: later steps build on earlier ones
                print(f"    FAILED: {type(e).__name__}: {e}")
                print("\napply: stopped. Fix the cause and run ./apply again; finished steps are skipped.")
                return 1

    if not args.dry_run and any(st.what.startswith("kde:") for st in done):
        print("\nnote: log out and back in for all KDE settings to take effect.")
    if not args.dry_run:
        for f, before in rc_before.items():
            after = f.read_text() if f.exists() else None
            if before is not None and after != before and args.only != "links":
                print(f"\nnote: an installer changed {tilde(f)}; only the dotfiles line is wanted there.")

    todo = secrets_report(spec, machine)
    if todo:
        print("\n== by hand (secrets, not in the repo):")
        for t in todo:
            print(f"  - {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
