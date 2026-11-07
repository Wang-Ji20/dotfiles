"""End-to-end tests in a temporary $HOME with a fixture repo and a file:// release.

The key property: a run that fails at any step leaves $HOME exactly as it was,
and a successful run followed by another run changes nothing.
"""

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HELLO = b"#!/bin/sh\necho hello 1.0\n"


def snapshot(home):
    """Everything about $HOME except directory mtimes (which change when entries come and go)."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(home):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            rel = os.path.relpath(path, home)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(path))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("dir", stat.S_IMODE(st.st_mode))
            else:
                with open(path, "rb") as fh:
                    out[rel] = ("file", stat.S_IMODE(st.st_mode), st.st_mtime_ns,
                                hashlib.sha256(fh.read()).hexdigest())
    return out


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dotfiles-test-")
        self.repo = os.path.join(self.tmp, "repo")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.write("modules/a/module.conf", "description A\ntool hello\n")
        self.write("modules/a/home/.config/a/conf", "a\n")
        self.write("modules/a/home/.arc", "arc\n")
        self.write("modules/b/module.conf", "requires a\n")
        self.write("modules/b/home/.config/b/conf", "b\n")
        self.write("profiles/all", "a b\n")
        # A release archive served from file://
        archive = os.path.join(self.tmp, "hello-1.0.tar.gz")
        with tarfile.open(archive, "w:gz") as tf:
            info = tarfile.TarInfo("hello-1.0/bin/hello")
            info.size, info.mode = len(HELLO), 0o755
            tf.addfile(info, io.BytesIO(HELLO))
        with open(archive, "rb") as fh:
            self.sha = hashlib.sha256(fh.read()).hexdigest()
        self.url = "file://" + archive
        self.set_lock(self.sha)
        # Things already in $HOME that the install has to back up.
        self.write_home(".arc", "my old arc\n")
        self.write_home("unrelated/file", "keep me\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def write_home(self, rel, text):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def set_lock(self, sha):
        self.write("tools.lock", f"hello 1.0 {os.uname().machine} static {sha} {self.url} "
                                 "hello=hello-1.0/bin/hello\n")

    def run_install(self, *args, env=None):
        e = dict(os.environ, HOME=self.home, DOTFILES_REPO=self.repo, PATH="/usr/bin:/bin",
                 PYTHONPATH=ROOT)
        e.pop("DOTFILES_FAIL_AT", None)
        e.pop("DOTFILES_CRASH_AT", None)
        e.update(env or {})
        return subprocess.run([sys.executable, "-B", "-m", "installer", *args], cwd=self.tmp, env=e,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def assert_ok(self, p):
        self.assertEqual(p.returncode, 0, p.stdout)

    def state(self):
        with open(os.path.join(self.home, ".local/state/dotfiles/state.json")) as fh:
            return json.load(fh)


class Install(Fixture):
    def test_install_then_rerun_changes_nothing(self):
        self.assert_ok(self.run_install("--profile", "all", "--packages"))
        conf = os.path.join(self.home, ".config/a/conf")
        self.assertEqual(os.readlink(conf), os.path.join(os.path.realpath(self.repo), "modules/a/home/.config/a/conf"))
        out = subprocess.run([os.path.join(self.home, ".local/bin/hello")], stdout=subprocess.PIPE, text=True)
        self.assertEqual(out.stdout, "hello 1.0\n")
        backups = os.listdir(os.path.join(self.home, ".dotfiles-backup"))
        with open(os.path.join(self.home, ".dotfiles-backup", backups[0], ".arc")) as fh:
            self.assertEqual(fh.read(), "my old arc\n")
        before = snapshot(self.home)
        p = self.run_install("--packages")
        self.assert_ok(p)
        self.assertIn("nothing to do", p.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assert_ok(self.run_install("--check", "--packages"))

    def test_dry_run_and_check_write_nothing(self):
        before = snapshot(self.home)
        self.assert_ok(self.run_install("--profile", "all", "--packages", "--dry-run"))
        self.assertEqual(self.run_install("--profile", "all", "--check").returncode, 1)
        self.assertEqual(snapshot(self.home), before)

    def test_remove_module_and_its_tool(self):
        self.assert_ok(self.run_install("--profile", "all", "--packages"))
        self.assert_ok(self.run_install("--remove", "b"))
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".config/b/conf")))
        self.assertEqual(self.state()["modules"], ["a"])
        # Dropping a module that others need is refused, with no changes.
        self.assert_ok(self.run_install("b"))
        before = snapshot(self.home)
        p = self.run_install("--remove", "a")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertEqual(snapshot(self.home), before)
        # Switching to a selection without `a` removes its links and the tool it installed.
        self.write("modules/c/module.conf", "description C\n")
        self.write("modules/c/home/.c", "c\n")
        self.assert_ok(self.run_install("c"))
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".local/bin/hello")))
        self.assertEqual(os.listdir(os.path.join(self.home, ".local/opt/dotfiles")), [])
        self.assertEqual(self.state()["tools"], {})

    def test_hand_edited_link_is_left_alone(self):
        self.assert_ok(self.run_install("--profile", "all"))
        conf = os.path.join(self.home, ".config/b/conf")
        os.remove(conf)
        self.write_home(".config/b/conf", "mine now\n")
        self.assert_ok(self.run_install("a"))
        with open(conf) as fh:
            self.assertEqual(fh.read(), "mine now\n")

    def test_drift_is_repaired(self):
        self.assert_ok(self.run_install("--profile", "all"))
        os.remove(os.path.join(self.home, ".config/a/conf"))
        p = self.run_install()
        self.assert_ok(p)
        self.assertIn("link    ~/.config/a/conf", p.stdout)
        self.assertTrue(os.path.islink(os.path.join(self.home, ".config/a/conf")))


class Failures(Fixture):
    def test_failure_at_every_step_leaves_home_untouched(self):
        before = snapshot(self.home)
        n = 1
        while True:
            p = self.run_install("--profile", "all", "--packages", env={"DOTFILES_FAIL_AT": str(n)})
            if p.returncode == 0:
                break
            self.assertIn("rolled back", p.stdout)
            self.assertEqual(snapshot(self.home), before, f"side effects after failing at step {n}\n{p.stdout}")
            n += 1
            self.assertLess(n, 200)
        self.assertGreater(n, 10)  # really went through the steps

    def test_failure_while_updating_leaves_previous_install_untouched(self):
        self.assert_ok(self.run_install("a"))
        before = snapshot(self.home)
        for n in range(1, 40):
            p = self.run_install("--profile", "all", "--packages", env={"DOTFILES_FAIL_AT": str(n)})
            if p.returncode == 0:
                break
            self.assertEqual(snapshot(self.home), before, f"step {n}\n{p.stdout}")

    def test_kill_9_mid_commit_is_recovered_by_next_run(self):
        before = snapshot(self.home)
        p = self.run_install("--profile", "all", "--packages", env={"DOTFILES_CRASH_AT": "6"})
        self.assertEqual(p.returncode, 137, p.stdout)
        self.assertEqual(self.run_install("--check").returncode, 1)
        # A failing run after a crash still rolls the crash back first.
        p = self.run_install("--profile", "all", "--packages", env={"DOTFILES_FAIL_AT": "3"})
        self.assertIn("rolled back an interrupted install", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_kill_9_then_install_completes(self):
        p = self.run_install("--profile", "all", "--packages", env={"DOTFILES_CRASH_AT": "9"})
        self.assertEqual(p.returncode, 137)
        p = self.run_install("--profile", "all", "--packages")
        self.assert_ok(p)
        self.assertIn("rolled back an interrupted install", p.stdout)
        self.assertIn("nothing to do", self.run_install().stdout)

    def test_bad_checksum_changes_nothing(self):
        self.set_lock("0" * 64)
        before = snapshot(self.home)
        p = self.run_install("--profile", "all", "--packages")
        self.assertEqual(p.returncode, 1)
        self.assertIn("checksum mismatch", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_binary_that_does_not_run_changes_nothing(self):
        archive = os.path.join(self.tmp, "hello-1.0.tar.gz")
        with tarfile.open(archive, "w:gz") as tf:
            body = b"#!/bin/sh\nexit 3\n"
            info = tarfile.TarInfo("hello-1.0/bin/hello")
            info.size, info.mode = len(body), 0o755
            tf.addfile(info, io.BytesIO(body))
        with open(archive, "rb") as fh:
            self.set_lock(hashlib.sha256(fh.read()).hexdigest())
        before = snapshot(self.home)
        p = self.run_install("--profile", "all", "--packages")
        self.assertEqual(p.returncode, 1)
        self.assertIn("does not run here", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_concurrent_run_is_refused(self):
        sdir = os.path.join(self.home, ".local/state/dotfiles/lock")
        os.makedirs(sdir)
        with open(os.path.join(sdir, "owner"), "w") as fh:
            fh.write(f"{os.uname().nodename} {os.getpid()}\n")  # this test process: alive
        p = self.run_install("--profile", "all")
        self.assertEqual(p.returncode, 1)
        self.assertIn("another install is running", p.stdout)
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".arc")) and
                         os.path.islink(os.path.join(self.home, ".arc")))


if __name__ == "__main__":
    unittest.main()
