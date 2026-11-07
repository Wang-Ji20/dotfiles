"""Pure tests: module selection and planning, no filesystem."""

import unittest

from installer.plan import (BIN, InstallRelease, Link, Managed, Node, Observation, Options,
                            Packages, RemoveTool, Seed, Unlink, WriteState, Found, make_plan)
from installer.spec import (Release, Repo, SpecError, merge_requirements, parse_lock, parse_module,
                            parse_version, select)

LOCK = """
nvim 0.12.6 x86_64 2.34 {s} https://x/nvim.tar.gz nvim=nvim/bin/nvim
tree-sitter 0.27.2 x86_64 2.39 {s} https://x/ts.gz tree-sitter=tree-sitter
tree-sitter 0.25.10 x86_64 2.34 {s} https://x/ts25.gz tree-sitter=tree-sitter
yazi 26.9.1 x86_64 static {s} https://x/yazi.zip yazi=y/yazi,ya=y/ya
""".format(s="0" * 64)


def make_repo():
    mods = {
        "fish": parse_module("fish", "tool fish min=3.2 apt=fish", (".config/fish/config.fish",)),
        "nvim": parse_module("nvim", "tool nvim min=0.12 apt=neovim\n"
                                     "tool tree-sitter optional min=0.25", (".config/nvim/init.lua",)),
        "yazi": parse_module("yazi", "requires fish\ntool yazi", (".config/fish/functions/y.fish",)),
        "git": parse_module("git", "tool git apt=git\nseed-git-identity", (".gitconfig",)),
        "desk": parse_module("desk", "package fonts optional apt=fonts-x"),
    }
    return Repo("/repo", mods, {}, parse_lock(LOCK))


def src(mod, rel):
    return f"/repo/modules/{mod}/home/{rel}"


def kinds(plan):
    return [type(op).__name__ for op in plan.ops]


class Selection(unittest.TestCase):
    def test_requires_are_added(self):
        self.assertEqual(select(make_repo().modules, ["yazi"], []), ["fish", "yazi"])

    def test_dropping_a_requirement_is_an_error(self):
        with self.assertRaises(SpecError):
            select(make_repo().modules, ["yazi"], ["fish"])

    def test_unknown_module(self):
        with self.assertRaises(SpecError):
            select(make_repo().modules, ["nope"], [])

    def test_merge_takes_highest_min_and_required_wins(self):
        a = parse_module("a", "tool x optional min=1.0")
        b = parse_module("b", "tool x min=2.1")
        (r,) = merge_requirements([a, b])
        self.assertEqual((r.min, r.optional), ((2, 1), False))

    def test_parse_version(self):
        self.assertEqual(parse_version("NVIM v0.12.6"), (0, 12, 6))
        self.assertEqual(parse_version("1:14.0-55.7~deb12u1"), (14, 0))
        self.assertIsNone(parse_version("none"))


class Links(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.found = {"fish": Found("/usr/bin/fish", (4, 0))}

    def plan(self, obs, sel=("fish",), **kw):
        obs.found = obs.found or self.found
        return make_plan(self.repo, list(sel), obs, Options(stamp="T", **kw))

    def test_fresh_install(self):
        p = self.plan(Observation("/h"))
        self.assertEqual(kinds(p), ["Link", "WriteState"])
        self.assertIsNone(p.ops[0].backup)

    def test_existing_file_is_backed_up(self):
        obs = Observation("/h", nodes={".config/fish/config.fish": Node("file")})
        (link, _) = self.plan(obs).ops
        self.assertEqual(link.backup, ".dotfiles-backup/T/.config/fish/config.fish")

    def test_converged_state_gives_empty_plan(self):
        first = self.plan(Observation("/h"))
        obs = Observation("/h", nodes={".config/fish/config.fish": Node("link", src("fish", ".config/fish/config.fish"))},
                          state=first.state)
        self.assertEqual(self.plan(obs).ops, [])

    def test_blocked_path_is_an_error(self):
        obs = Observation("/h", blocked={".config/fish/config.fish": "into repo"})
        p = self.plan(obs)
        self.assertTrue(p.errors)
        self.assertNotIn("Link", kinds(p))

    def test_deselected_link_is_removed_only_if_still_ours(self):
        state = {"format": 1, "links": {".old": "/repo/modules/x/home/.old", ".mine": "/repo/m/.mine"}}
        obs = Observation("/h", state=state, nodes={".old": Node("link", "/repo/modules/x/home/.old"),
                                                    ".mine": Node("file")})
        p = self.plan(obs)
        self.assertIn(Unlink(".old"), p.ops)
        self.assertNotIn(Unlink(".mine"), p.ops)
        self.assertTrue(any(".mine" in w for w in p.warnings))

    def test_git_identity_seeded_once(self):
        ident = (("user.name", "A"),)
        p = self.plan(Observation("/h", git_identity=ident, found={"git": Found("/usr/bin/git")}), sel=["git"])
        self.assertIn(Seed(".gitconfig.local", ident), p.ops)
        obs = Observation("/h", git_identity=ident, found={"git": Found("/usr/bin/git")},
                          nodes={".gitconfig.local": Node("file")})
        self.assertNotIn("Seed", kinds(self.plan(obs, sel=["git"])))


class Tools(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()

    def plan(self, obs, sel=("nvim",), **kw):
        return make_plan(self.repo, list(sel), obs, Options(stamp="T", **kw))

    def installs(self, plan):
        return {op.release.name: op.release.version for op in plan.ops if isinstance(op, InstallRelease)}

    def test_without_packages_only_warns(self):
        p = self.plan(Observation("/h", found={"nvim": Found("/usr/bin/nvim", (0, 9, 5))}))
        self.assertEqual(self.installs(p), {})
        self.assertTrue(any("older than 0.12" in w for w in p.warnings))
        self.assertFalse(p.errors)

    def test_rhel9_gets_release_nvim_and_old_tree_sitter(self):
        p = self.plan(Observation("/h", glibc=(2, 34)), packages=True)
        self.assertEqual(self.installs(p), {"nvim": (0, 12, 6), "tree-sitter": (0, 25, 10)})

    def test_ubuntu_2404_gets_new_tree_sitter(self):
        p = self.plan(Observation("/h", glibc=(2, 39)), packages=True)
        self.assertEqual(self.installs(p)["tree-sitter"], (0, 27, 2))

    def test_old_glibc_required_tool_is_an_error_optional_a_warning(self):
        p = self.plan(Observation("/h", glibc=(2, 31)), packages=True)
        self.assertTrue(any(e.startswith("nvim") for e in p.errors))
        self.assertTrue(any(w.startswith("tree-sitter") for w in p.warnings))

    def test_root_uses_package_manager_when_candidate_is_new_enough(self):
        obs = Observation("/h", euid=0, pm="apt", glibc=(2, 39), candidates={"neovim": (0, 12, 4)})
        p = self.plan(obs, packages=True)
        self.assertEqual(p.ops[-1], Packages("apt", ("neovim",), sudo=False))
        self.assertNotIn("nvim", self.installs(p))

    def test_root_falls_back_to_release_when_package_too_old(self):
        obs = Observation("/h", euid=0, pm="apt", glibc=(2, 39), candidates={"neovim": (0, 9, 5)})
        p = self.plan(obs, packages=True)
        self.assertIn("nvim", self.installs(p))
        self.assertNotIn("Packages", kinds(p))

    def test_non_root_never_uses_package_manager_without_sudo(self):
        obs = Observation("/h", pm="apt", glibc=(2, 39), candidates={"neovim": (0, 12, 4)})
        self.assertNotIn("Packages", kinds(self.plan(obs, packages=True)))
        self.assertIn("Packages", kinds(self.plan(obs, packages=True, sudo=True)))

    def test_package_kind_needs_privilege(self):
        p = self.plan(Observation("/h", pm="apt"), sel=["desk"], packages=True)
        self.assertTrue(p.warnings and not p.errors)

    def test_existing_bin_is_backed_up_and_ours_is_replaced(self):
        obs = Observation("/h", glibc=(2, 39), nodes={f"{BIN}/yazi": Node("file"),
                                                      f"{BIN}/ya": Node("link", "../opt/dotfiles/yazi-1/ya")},
                          found={"fish": Found("/usr/bin/fish", (4, 0))})
        (op,) = [o for o in self.plan(obs, sel=["yazi"], packages=True).ops if isinstance(o, InstallRelease)]
        self.assertEqual(dict((b[0], b[2]) for b in op.bins),
                         {f"{BIN}/yazi": f".dotfiles-backup/T/{BIN}/yazi", f"{BIN}/ya": "ours"})

    def managed_state(self, version="0.12.6"):
        return {"format": 1, "tools": {"nvim": {
            "version": version, "store": f".local/opt/dotfiles/nvim-{version}",
            "bins": {"nvim": [f"{BIN}/nvim", f"../opt/dotfiles/nvim-{version}/nvim/bin/nvim"]}}}}

    def test_managed_tool_that_does_not_run_here_is_left_alone(self):
        obs = Observation("/h", glibc=(2, 28), state=self.managed_state(),
                          managed={"nvim": Managed(True, True, runs=False)})
        p = self.plan(obs, packages=True)
        self.assertNotIn("RemoveTool", kinds(p))
        self.assertEqual(self.installs(p).get("nvim"), None)
        self.assertTrue(any("does not run" in w for w in p.warnings))

    def test_pin_bump_replaces_managed_tool(self):
        obs = Observation("/h", glibc=(2, 39), state=self.managed_state("0.12.5"),
                          managed={"nvim": Managed(True, True, True)})
        p = self.plan(obs, packages=True)
        self.assertIn("RemoveTool", kinds(p))
        self.assertEqual(self.installs(p)["nvim"], (0, 12, 6))

    def test_deselected_managed_tool_is_removed(self):
        obs = Observation("/h", state=self.managed_state(), managed={"nvim": Managed(True, True, True)},
                          found={"fish": Found("/usr/bin/fish", (4, 0))})
        p = self.plan(obs, sel=["fish"])
        self.assertTrue(any(isinstance(o, RemoveTool) and o.name == "nvim" for o in p.ops))

    def test_operations_are_ordered_by_phase(self):
        obs = Observation("/h", euid=0, pm="apt", glibc=(2, 39), candidates={"neovim": (0, 12, 4)},
                          nodes={".config/nvim/init.lua": Node("file")})
        p = self.plan(obs, packages=True)
        phases = [op.phase for op in p.ops]
        self.assertEqual(phases, sorted(phases))
        self.assertIsInstance(p.ops[-1], Packages)
        self.assertIsInstance(p.ops[-2], WriteState)
        self.assertIsInstance(p.ops[0], InstallRelease)
        self.assertTrue(any(isinstance(o, Link) for o in p.ops))


class Lock(unittest.TestCase):
    def test_rejects_bad_lines(self):
        for bad in ["x 1.0 x86_64 static short https://u x=y",
                    "x 1.0 x86_64 static " + "0" * 64 + " https://u x=../y",
                    "x 1.0 x86_64 static"]:
            with self.assertRaises(SpecError):
                parse_lock(bad)

    def test_static_means_no_glibc(self):
        (r,) = parse_lock("x 1.0 x86_64 static " + "0" * 64 + " https://u x=bin/x")
        self.assertIsInstance(r, Release)
        self.assertIsNone(r.glibc)


if __name__ == "__main__":
    unittest.main()
