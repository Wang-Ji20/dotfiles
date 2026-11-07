"""Command line: select -> observe -> plan -> (stage -> commit -> verify)."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import time
from typing import List, Optional

from .apply import StageError, commit, stage
from .observe import StateError, load_state, observe, state_dir
from .plan import Options, Plan, make_plan
from .spec import Repo, SpecError, load_repo, select
from .txn import InjectedFailure, Lock, LockError, Txn

USAGE_EXAMPLES = """
examples:
  ./install.sh --profile lab --packages     shared server: links + tools in ~/.local
  ./install.sh --profile desktop --packages workstation: system packages via sudo
  ./install.sh fish nvim git                pick modules directly
  ./install.sh --remove yazi                drop a module from the saved selection
  ./install.sh                              re-apply the saved selection
  ./install.sh --dry-run ...                show the plan, change nothing
"""


class Abort(Exception):
    pass


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="install.sh", description="Link dotfiles modules into $HOME "
                                "and install the tools they need, as one all-or-nothing transaction.",
                                epilog=USAGE_EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("modules", nargs="*", metavar="MODULE", help="modules to select (adds to --profile)")
    p.add_argument("-p", "--profile", help="start from profiles/PROFILE")
    p.add_argument("-x", "--exclude", nargs="+", default=[], metavar="MODULE", help="leave these out")
    p.add_argument("-r", "--remove", nargs="+", default=[], metavar="MODULE",
                   help="remove from the saved selection")
    p.add_argument("--packages", action="store_true", help="also install missing tools")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--sudo", dest="sudo", action="store_true", default=None,
                   help="allow the package manager through sudo")
    g.add_argument("--no-sudo", dest="sudo", action="store_false", help="never use sudo")
    p.add_argument("-n", "--dry-run", action="store_true", help="print the plan, change nothing")
    p.add_argument("--check", action="store_true", help="exit 1 if anything would change")
    p.add_argument("--list", action="store_true", help="list modules and profiles")
    return p.parse_args(argv)


def tilde(path: str, home: str) -> str:
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def list_modules(repo: Repo, state: dict) -> None:
    saved = set(state.get("modules", []))
    print("modules (* = selected on this machine):")
    for m in repo.modules.values():
        print(f"  {'*' if m.name in saved else ' '} {m.name:<11} {m.description}")
    print("profiles:")
    for p in repo.profiles.values():
        print(f"    {p.name:<11} {' '.join(p.modules)}{'  [sudo]' if p.sudo else ''}")


def check_ownership(home: str, root: str) -> None:
    euid = os.geteuid()
    if os.stat(home).st_uid != euid:
        raise Abort(f"$HOME ({home}) is not owned by you (uid {euid}). Under sudo? "
                    "Run as the user whose home this is; the installer uses sudo itself with --sudo.")
    owner = os.stat(root).st_uid
    if owner not in (euid, 0):
        raise Abort(f"the repo {root} is owned by uid {owner}. Linking your shell config to files "
                    "another user can edit is unsafe; clone it yourself.")


def resolve_selection(args, repo: Repo, state: dict) -> List[str]:
    base: List[str] = []
    if args.profile:
        if args.profile not in repo.profiles:
            raise Abort(f"unknown profile {args.profile!r}; have: {', '.join(repo.profiles)}")
        base += repo.profiles[args.profile].modules
    base += args.modules
    if not base:
        base = list(state.get("modules", []))
        if not base:
            raise Abort("nothing selected yet: pass --profile NAME or module names (see --list)")
    missing = [m for m in args.remove if m not in base]
    if missing:
        print(f"note: not selected, nothing to remove: {' '.join(missing)}", file=sys.stderr)
    return select(repo.modules, base, list(args.exclude) + list(args.remove))


def print_plan(plan: Plan) -> None:
    for op in plan.ops:
        print("  " + op.describe())
    for w in plan.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in plan.errors:
        print(f"error:   {e}", file=sys.stderr)


def hints(repo: Repo, selected: List[str], home: str) -> None:
    if "git" in selected and not os.path.lexists(os.path.join(home, ".gitconfig.local")):
        example = tilde(os.path.join(repo.root, "modules/git/gitconfig.local.example"), home)
        print(f"next: cp {example} ~/.gitconfig.local  and fill in your identity")
    if "fish" in selected and os.path.basename(os.environ.get("SHELL", "")) != "fish":
        fish = shutil.which("fish", path=os.pathsep.join([os.path.join(home, ".local/bin"),
                                                          os.environ.get("PATH", "")]))
        if fish:
            try:
                with open("/etc/shells") as fh:
                    listed = fish in fh.read().split()
            except OSError:
                listed = False
            if listed:
                print(f"next: chsh -s {fish}   # then log in again")
            else:
                print(f"next: start fish with `{tilde(fish, home)} -l` "
                      f"(from your machine: ssh -t HOST {tilde(fish, home)} -l)")
    local_bin = os.path.join(home, ".local/bin")
    if os.path.isdir(local_bin) and local_bin not in os.environ.get("PATH", "").split(os.pathsep):
        print("note: ~/.local/bin is not on this shell's PATH (fish adds it itself)")


def _raise_on_signal(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def run(argv: List[str]) -> int:
    args = parse_args(argv)
    home = os.path.realpath(os.environ.get("HOME") or os.path.expanduser("~"))
    root = os.path.realpath(os.environ.get("DOTFILES_REPO") or
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    repo = load_repo(root)
    state = load_state(home)
    if args.list:
        list_modules(repo, state)
        return 0
    check_ownership(home, root)
    selected = resolve_selection(args, repo, state)
    sudo = args.sudo
    if sudo is None:
        sudo = repo.profiles[args.profile].sudo if args.profile else bool(state.get("sudo", False))
    opts = Options(packages=args.packages, sudo=sudo, stamp=time.strftime("%Y%m%d-%H%M%S"))
    txn = Txn(state_dir(home))

    print(f"modules: {' '.join(selected)}")
    if txn.pending():
        print("note: an interrupted install will be rolled back first", file=sys.stderr)
    plan = make_plan(repo, selected, observe(repo, selected, home, opts, state), opts)
    print_plan(plan)
    if plan.errors:
        print("nothing was changed", file=sys.stderr)
        return 1
    if args.check:
        return 1 if plan.ops or txn.pending() else 0
    if args.dry_run:
        print("dry run: nothing was changed" if plan.ops else "nothing to do")
        return 0
    if not plan.ops and not txn.pending():
        print("nothing to do")
        hints(repo, selected, home)
        return 0

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_on_signal)
    with Lock(state_dir(home)):
        done = txn.recover()
        if done:
            print(f"note: {done}", file=sys.stderr)
        # Re-plan under the lock: the machine may have changed since the preview.
        state = load_state(home)
        plan = make_plan(repo, selected, observe(repo, selected, home, opts, state), opts)
        if plan.errors:
            print_plan(plan)
            print("nothing was changed", file=sys.stderr)
            return 1
        if plan.ops:
            apply_plan(plan, txn, repo, selected, home, opts)
    print("done")
    hints(repo, selected, home)
    return 0


def apply_plan(plan: Plan, txn: Txn, repo: Repo, selected: List[str], home: str, opts: Options) -> None:
    txn.begin()
    try:
        staged = stage(plan, txn, home)
        commit(plan, txn, staged, home)
        after = make_plan(repo, selected, observe(repo, selected, home, opts, load_state(home)), opts)
        if after.ops or after.errors:
            left = "; ".join([op.describe() for op in after.ops] + after.errors)
            raise StageError(f"verification failed, still to do: {left}")
    except BaseException:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        try:
            txn.rollback()
        except BaseException as e:  # leave the journal for the next run
            print(f"error: rollback incomplete ({e}); the next run will retry it", file=sys.stderr)
            raise
        txn.discard()
        print("rolled back: nothing was changed", file=sys.stderr)
        raise
    txn.finish()


def main(argv: Optional[List[str]] = None) -> int:
    # Keep the plan (stdout) and warnings/progress (stderr) in order when piped.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except (Abort, SpecError, StateError, LockError, StageError, InjectedFailure) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
