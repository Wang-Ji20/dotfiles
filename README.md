# Dotfiles

My environment, declared in one file and applied with one command.

```
environment.toml   what each machine has: tools, config links, keys to create
config/            the config files themselves, one folder per program
apply              makes this machine match environment.toml
```

## New machine

```sh
git clone https://github.com/Wang-Ji20/dotfiles.git ~/dotfiles
cd ~/dotfiles
./apply --machine desktop --dry-run   # see what would change
./apply --machine desktop             # do it (the machine name is remembered)
./apply --update                      # later, e.g. weekly: update everything to latest
```

Machines: `wsl`, `desktop` (openSUSE, sudo), `lab` (shared servers, no sudo).
Afterwards `apply` lists what has to be done by hand: create this machine's SSH and GPG
keys (never copied between machines), `gh auth login`,
logging in to the AI CLIs.

Later runs need no arguments: `./apply` re-applies everything and changes only what
differs, so it also repairs drift. `--only links|system|tools|desktop` runs one part.

## How it works

- **Links.** Files under `config/` are symlinked into `$HOME` one by one, as listed in
  `[links]`. Anything they replace is moved to `~/.dotfiles-backup/<time>/`. Links whose
  file was removed from the repo are cleaned up.
- **One line in `~/.bashrc`** loads `~/.config/bash/dotfiles.bash`; the rest of the file
  (e.g. a lab's site setup) is left alone. If the file a login bash reads (`~/.bash_profile`,
  `~/.bash_login` or `~/.profile`) doesn't source `~/.bashrc`, it gets a line that loads `dotfiles.bash` directly (not `~/.bashrc`,
  which on some sites sources the login file itself). `dotfiles.bash` loads once per shell.
- **Git identity** lives in `~/.gitconfig`, which is per machine and not in the repo;
  the shared settings are in `~/.config/git/`.
- **Tools.** Each machine has groups of tools (`[groups]`); `[tools]` says how each one is
  provided. With sudo: zypper. On lab: the system copy if it is new enough, otherwise
  conda-forge through pixi into `~/.pixi`. Everything else (uv, pnpm, rustup, sdkman,
  ghcup, opam, juliaup, official installers, GitHub releases) installs into `$HOME`.
  Missing tools get their latest version; installed ones are left alone.
- **Updates.** `./apply --update` (or `--only update`) then brings everything declared for the
  machine to its latest version, one step per manager: `sudo zypper dup` (Tumbleweed), pixi,
  uv, pnpm, rustup, sdkman, ghcup, opam, juliaup, git checkouts, `claude update`, the other
  official installers again, and GitHub releases newer than the tag recorded in
  `~/.local/state/dotfiles/releases/`. Update steps don't depend on each other: one failing
  is reported at the end, the rest still run. `archive` tools (Zotero) update themselves.
- **Lab servers** keep bash as the login shell; an interactive bash switches to fish.
  Escape hatch: `ssh -t host 'NOFISH=1 bash -l'`.

Needs Python 3.11+ (for `tomllib`). Where there is none, `apply` installs uv into
`~/.local/bin` and runs with a Python from uv.
