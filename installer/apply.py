"""Stage (everything that can fail, inside the transaction directory), then commit (renames)."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from typing import Dict

from .observe import probe_env, state_dir
from .plan import InstallRelease, Link, Packages, Plan, RemoveTool, Seed, Unlink, WriteState
from .spec import fmt_version
from .txn import Txn


class StageError(Exception):
    pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- downloads and archives -------------------------------------------------------

def download(url: str, dest: str, sha256: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "dotfiles-installer"})
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                out.write(chunk)
    except OSError as e:
        raise StageError(f"download failed: {url}: {e}") from e
    if h.hexdigest() != sha256:
        raise StageError(f"checksum mismatch for {url}\n  expected {sha256}\n  got      {h.hexdigest()}")


def _inside(root: str, name: str) -> str:
    path = os.path.realpath(os.path.join(root, name))
    if not (path + os.sep).startswith(os.path.realpath(root) + os.sep):
        raise StageError(f"archive member escapes the target directory: {name}")
    return path


def unpack(archive: str, dest: str, single_name: str) -> None:
    os.makedirs(dest)
    name = archive.lower()
    if name.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2")):
        with tarfile.open(archive) as tf:
            if hasattr(tarfile, "data_filter"):
                tf.extractall(dest, filter="data")
            else:
                for m in tf.getmembers():
                    _inside(dest, m.name)
                    if (m.issym() or m.islnk()) and (os.path.isabs(m.linkname)
                                                     or ".." in m.linkname.split("/")):
                        raise StageError(f"unsafe link in archive: {m.name} -> {m.linkname}")
                    if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
                        raise StageError(f"unsupported archive member: {m.name}")
                tf.extractall(dest)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                path = _inside(dest, info.filename)
                mode = info.external_attr >> 16
                if info.is_dir():
                    os.makedirs(path, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if stat.S_ISLNK(mode):
                    target = zf.read(info).decode()
                    if os.path.isabs(target) or ".." in target.split("/"):
                        raise StageError(f"unsafe link in archive: {info.filename}")
                    os.symlink(target, path)
                    continue
                with zf.open(info) as src, open(path, "wb") as out:
                    shutil.copyfileobj(src, out)
                if mode & 0o777:
                    os.chmod(path, mode & 0o777)
    elif name.endswith(".gz"):
        path = os.path.join(dest, single_name)
        with gzip.open(archive) as src, open(path, "wb") as out:
            shutil.copyfileobj(src, out)
        os.chmod(path, 0o755)
    else:
        raise StageError(f"unknown archive type: {archive}")


def trial_run(path: str) -> None:
    try:
        p = subprocess.run([path, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=60, env=probe_env(), check=False)
    except (OSError, subprocess.SubprocessError) as e:
        raise StageError(f"{path} does not run here: {e}") from e
    if p.returncode != 0:
        out = p.stdout.decode(errors="replace").strip().splitlines()
        raise StageError(f"{path} does not run here: {out[-1] if out else 'exit ' + str(p.returncode)}")


# --- stage ----------------------------------------------------------------------------

def stage(plan: Plan, txn: Txn, home: str) -> Dict[int, str]:
    """Prepare every new file under txn.stage. Returns op index -> staged path."""
    staged: Dict[int, str] = {}
    dl = os.path.join(txn.dir, "downloads")
    os.mkdir(dl)
    for i, op in enumerate(plan.ops):
        out = os.path.join(txn.stage, str(i))
        if isinstance(op, InstallRelease):
            r = op.release
            log(f"  ... downloading {r.name} {fmt_version(r.version)}")
            archive = os.path.join(dl, os.path.basename(r.url))
            download(r.url, archive, r.sha256)
            unpack(archive, out, r.bins[0][1])
            os.remove(archive)
            for cmd, path in r.bins:
                if not os.path.isfile(os.path.join(out, path)):
                    raise StageError(f"{r.name}: {path} missing from {r.url}")
            trial_run(os.path.join(out, r.bins[0][1]))
            # Bin symlinks, staged so the commit only renames.
            os.mkdir(out + ".bins")
            for j, (_, dest, _) in enumerate(op.bins):
                os.symlink(dest, os.path.join(out + ".bins", str(j)))
            staged[i] = out
        elif isinstance(op, Link):
            os.symlink(op.source, out)
            staged[i] = out
        elif isinstance(op, Seed):
            with open(out, "w"):
                pass
            for key, value in op.values:
                subprocess.run(["git", "config", "--file", out, key, value], check=True)
            staged[i] = out
        elif isinstance(op, WriteState):
            with open(out, "w") as fh:
                json.dump(op.state, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            staged[i] = out
    return staged


# --- commit ---------------------------------------------------------------------------

def commit(plan: Plan, txn: Txn, staged: Dict[int, str], home: str) -> None:
    H = lambda rel: os.path.join(home, rel)  # noqa: E731
    for i, op in enumerate(plan.ops):
        if isinstance(op, Unlink):
            txn.to_trash(H(op.target))
        elif isinstance(op, RemoveTool):
            for target, dest in op.bins:
                try:
                    if os.readlink(H(target)) == dest:
                        txn.to_trash(H(target))
                except OSError:
                    pass
            if op.store and os.path.lexists(H(op.store)):
                txn.to_trash(H(op.store))
        elif isinstance(op, InstallRelease):
            if os.path.lexists(H(op.store)):  # leftover not recorded in state
                txn.to_trash(H(op.store))
            txn.move(staged[i], H(op.store))
            for j, (target, _, replace) in enumerate(op.bins):
                if os.path.lexists(H(target)):
                    if replace == "ours" or replace is None:
                        txn.to_trash(H(target))
                    else:
                        txn.move(H(target), H(replace))
                txn.move(os.path.join(staged[i] + ".bins", str(j)), H(target))
        elif isinstance(op, Link):
            if op.backup and os.path.lexists(H(op.target)):
                txn.move(H(op.target), H(op.backup))
            txn.move(staged[i], H(op.target))
        elif isinstance(op, Seed):
            txn.move(staged[i], H(op.target))
        elif isinstance(op, WriteState):
            path = os.path.join(state_dir(home), "state.json")
            if os.path.lexists(path):
                txn.to_trash(path)
            txn.move(staged[i], path)
        elif isinstance(op, Packages):
            install_packages(op)


def install_packages(op: Packages) -> None:
    interactive = sys.stdin.isatty()
    if op.pm == "apt":
        argv = ["apt-get", "install", "--no-install-recommends"] + ([] if interactive else ["-y"])
        env = None if interactive else dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    elif op.pm == "zypper":
        argv = ["zypper"] + ([] if interactive else ["--non-interactive"]) + ["install"]
        env = None
    else:
        raise StageError(f"unknown package manager {op.pm}")
    argv = (["sudo"] if op.sudo else []) + argv + list(op.pkgs)
    log("run     " + " ".join(argv))
    if subprocess.run(argv, env=env).returncode != 0:
        raise StageError(f"{op.pm} failed; links were rolled back, packages it installed (if any) remain")
