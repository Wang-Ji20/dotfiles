"""Lock, undo journal, rollback and crash recovery.

Every change to $HOME is a mkdir or a rename. Before each one, its undo is
appended to the journal and fsynced, so an interrupted run, even kill -9, can
be rolled back by the next run. Nothing is deleted until the transaction is
marked committed.
"""

from __future__ import annotations

import json
import os
import shutil
import socket


class LockError(Exception):
    pass


class InjectedFailure(Exception):
    pass


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class Lock:
    """mkdir-based lock (works on NFS/GPFS). Removes the directories it created if the run fails."""

    def __init__(self, sdir: str):
        self.sdir = sdir
        self.path = os.path.join(sdir, "lock")
        self.created = []
        self.ok = False

    def __enter__(self):
        missing, d = [], self.sdir
        while not os.path.isdir(d):
            missing.append(d)
            d = os.path.dirname(d)
        for d in reversed(missing):
            os.mkdir(d)
            self.created.append(d)
        for _ in range(2):
            try:
                os.mkdir(self.path)
            except FileExistsError:
                if not self._clear_stale():
                    raise
                continue
            # Line 1: owner. Then the directories this run created, so whoever
            # cleans up after a crash can remove them too.
            with open(os.path.join(self.path, "owner"), "w") as fh:
                fh.write("\n".join([f"{socket.gethostname()} {os.getpid()}"] + self.created) + "\n")
            return self
        raise LockError(f"could not take {self.path}")

    def _clear_stale(self) -> bool:
        try:
            with open(os.path.join(self.path, "owner")) as fh:
                lines = fh.read().splitlines()
            host, pid = lines[0].split()
        except (OSError, ValueError, IndexError):
            raise LockError(f"{self.path} exists without an owner; remove it if no install is running")
        if host != socket.gethostname():
            raise LockError(f"another install holds {self.path} (host {host}, pid {pid})")
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            shutil.rmtree(self.path)
            self.created = [d for d in lines[1:] if d] + self.created
            return True
        except PermissionError:
            pass
        raise LockError(f"another install is running (pid {pid}); lock: {self.path}")

    def __exit__(self, exc_type, exc, tb):
        shutil.rmtree(self.path, ignore_errors=True)
        if exc_type is not None:
            for d in reversed(self.created):
                try:
                    os.rmdir(d)
                except OSError:
                    break
        return False


class Txn:
    def __init__(self, sdir: str):
        self.dir = os.path.join(sdir, "txn")
        self.journal_path = os.path.join(self.dir, "journal")
        self.stage = os.path.join(self.dir, "stage")
        self.trash = os.path.join(self.dir, "trash")
        self._journal = None
        self._count = 0
        self._ntrash = 0
        self.fail_at = int(os.environ.get("DOTFILES_FAIL_AT", "0") or 0)  # tests only
        self.crash_at = int(os.environ.get("DOTFILES_CRASH_AT", "0") or 0)  # tests only

    # lifecycle ----------------------------------------------------------------

    def pending(self) -> bool:
        return os.path.lexists(self.dir)

    def begin(self) -> None:
        os.mkdir(self.dir)
        os.mkdir(self.stage)
        os.mkdir(self.trash)
        self._journal = open(self.journal_path, "a")
        _fsync_dir(os.path.dirname(self.dir))

    def finish(self) -> None:
        """Point of no return: mark committed, then delete staging and trash."""
        self._close()
        marker = os.path.join(self.dir, "committed")
        with open(marker, "w") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        _fsync_dir(self.dir)
        self.discard()

    def discard(self) -> None:
        self._close()
        # A file that is still open elsewhere on NFS can make this fail; the
        # change is already committed, so the next run finishes the cleanup.
        shutil.rmtree(self.dir, ignore_errors=True)

    def recover(self) -> str:
        """Finish or undo an interrupted run. Returns what was done."""
        if not self.pending():
            return ""
        if os.path.exists(os.path.join(self.dir, "committed")):
            self.discard()
            return "cleaned up after a completed install"
        self.rollback()
        self.discard()
        return "rolled back an interrupted install"

    def rollback(self) -> None:
        self._close()
        try:
            with open(self.journal_path) as fh:
                entries = [json.loads(line) for line in fh if line.strip().endswith("}")]
        except FileNotFoundError:
            entries = []
        for e in reversed(entries):
            if e["undo"] == "rmdir":
                try:
                    os.rmdir(e["path"])
                except OSError:
                    pass
            elif e["undo"] == "move":
                # Tolerant: the forward action may never have happened.
                if os.path.lexists(e["src"]) and not os.path.lexists(e["dst"]):
                    os.rename(e["src"], e["dst"])

    def _close(self) -> None:
        if self._journal:
            self._journal.close()
            self._journal = None

    # journaled actions ----------------------------------------------------------

    def _record(self, entry: dict) -> None:
        self._count += 1
        self._journal.write(json.dumps(entry) + "\n")
        self._journal.flush()
        os.fsync(self._journal.fileno())
        if self._count == self.fail_at:
            raise InjectedFailure(f"DOTFILES_FAIL_AT={self.fail_at}")
        if self._count == self.crash_at:
            os._exit(137)

    def mkdirs(self, path: str) -> None:
        missing = []
        while not os.path.isdir(path):
            missing.append(path)
            path = os.path.dirname(path)
        for d in reversed(missing):
            self._record({"undo": "rmdir", "path": d})
            os.mkdir(d)

    def move(self, src: str, dst: str) -> None:
        """Rename src to dst (dst must not exist); undo moves it back."""
        if os.path.lexists(dst):
            raise FileExistsError(dst)
        self.mkdirs(os.path.dirname(dst))
        self._record({"undo": "move", "src": dst, "dst": src})
        os.rename(src, dst)

    def to_trash(self, path: str) -> None:
        self._ntrash += 1
        self.move(path, os.path.join(self.trash, str(self._ntrash)))
