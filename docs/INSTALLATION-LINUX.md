# Installing AURORA on Linux

Target platforms: Ubuntu, Debian, Kali Linux (x86_64), Python 3.11+.
Verified on: Ubuntu 24.04.5 LTS with Python 3.12.3 and GCC 13.3.0.

---

## 1. Prerequisites

```bash
python3 --version        # 3.11 or newer
python3 -m venv --help   # venv must be available
```

Ubuntu/Debian/Kali, if `venv` is missing:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

For the native component (Phase 5, not present in this milestone):

```bash
sudo apt install -y build-essential cmake
# optional sanitizer support
sudo apt install -y clang
```

## 2. Install into a virtual environment

```bash
git clone https://github.com/0x7f3a/AURORA.git
cd AURORA

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

`-e` installs in editable mode, so source changes take effect without
reinstalling. Use `python -m pip install .` if you want a fixed install.

If your distribution reports `error: externally-managed-environment`, you are
installing outside the virtual environment — activate it first. Do not use
`--break-system-packages`.

## 3. Verify

```bash
aurora version
```

Expected output includes the version, `platform` line for your host, the
workspace paths and `schema` state. Exit code must be `0`:

```bash
aurora version; echo "exit=$?"
```

Create a workspace:

```bash
aurora init
ls -l "${XDG_CONFIG_HOME:-$HOME/.config}/aurora"
```

You should see `config.json`, `aurora.db` and `reports/`. Use an isolated
workspace for lab work:

```bash
aurora init --home ./lab-workspace
aurora version --home ./lab-workspace
```

## 4. Run the test suite

```bash
python -m pytest
```

Expected on this milestone: `130 passed`. Tests never contact the network and
never touch your home directory — they use temporary paths.

## 5. Terminal notes

- Unicode banner requires a UTF-8 locale. Check with `locale`; if `LANG` is
  `C`/`POSIX`, either export `LANG=C.UTF-8` or pass `--ascii`.
- Colour is disabled automatically when stdout is not a TTY or `NO_COLOR` is set.
- `aurora --ascii` guarantees ASCII-only output, useful for logs collected from
  minimal containers.

## 6. Uninstall

```bash
python -m pip uninstall aurora-framework
rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/aurora"   # removes workspace + database
```

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `aurora: command not found` | The virtual environment is not activated, or `~/.local/bin` is not on `PATH` |
| `error: externally-managed-environment` | Install inside the venv (see §2) |
| Banner shows `?` characters | Locale is not UTF-8; use `--ascii` or set `LANG=C.UTF-8` |
| `database is not initialized` | Run `aurora init --home <path>` for that workspace |
| `database schema version N is newer` | The workspace was created by a newer AURORA; upgrade or use another `--home` |
| `config.json` unreadable after editing | Validation errors name the exact field; restore with `aurora init --force` |
