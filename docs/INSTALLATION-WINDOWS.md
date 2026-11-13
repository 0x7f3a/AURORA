# Installing AURORA on Windows

Target platforms: Windows 10 x86_64 and Windows 11 x86_64, Python 3.11+.

> **Verification status: NOT EXECUTED ON WINDOWS.**
> The instructions below follow the code's design (pathlib paths, `%APPDATA%`
> workspace, `aurora.dll` naming, ASCII console fallback) and the Windows CI
> workflow in `.github/workflows/windows.yml`, but no Windows host was available
> during development. Treat the first run on Windows as unverified until the CI
> job and a manual run succeed.

---

## 1. Prerequisites

1. **Python 3.11 or newer** from <https://www.python.org/downloads/windows/>.
   During installation tick *Add python.exe to PATH*. Verify in PowerShell:

   ```powershell
   python --version
   py -0p            # lists installed interpreters
   ```

2. **Microsoft Visual C++ Build Tools** — required only for the native component
   (Phase 5, not in this milestone). Install *Build Tools for Visual Studio* with
   the "Desktop development with C++" workload. A C compiler is **not** needed to
   run the current milestone.

3. Optional secondary compiler: MinGW-w64 (MSVC is the primary target).

## 2. Install into a virtual environment

```powershell
git clone https://github.com/0x7f3a/AURORA.git
cd AURORA

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell refuses to run the activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

`-Scope Process` applies to the current window only and does not change the
machine policy.

`cmd.exe` equivalent:

```bat
.venv\Scripts\activate.bat
```

## 3. Verify

```powershell
aurora version
echo "exit=$LASTEXITCODE"
```

Expected: version `0.1.0-dev`, a `platform` line such as
`Windows 11 x86_64 · CPython 3.12.x`, workspace paths under
`%APPDATA%\aurora`, and `native  aurora.dll (not built)`.

Create a workspace:

```powershell
aurora init
dir $env:APPDATA\aurora
```

You should see `config.json`, `aurora.db` and `reports\`. For an isolated lab
workspace:

```powershell
aurora init --home .\lab-workspace
aurora version --home .\lab-workspace
```

## 4. Run the test suite

```powershell
python -m pytest
```

Tests use temporary directories and never touch the network. The
`chmod`-based permission assertions are skipped on Windows by design.

## 5. Console notes

- Windows Terminal and PowerShell 7 handle the Unicode banner; `cmd.exe` with a
  legacy code page may not. AURORA probes stdout's encoding and switches to the
  ASCII banner automatically. Force it with `aurora --ascii`.
- Colour is disabled when output is redirected or `NO_COLOR` is set.
- `%APPDATA%` may be unset in some service contexts; AURORA then falls back to
  `%USERPROFILE%\AppData\Roaming\aurora`.

## 6. Filesystem permissions

POSIX-style `chmod 0700` has no meaning on Windows; AURORA skips it rather than
pretending to harden the directory. If you need strict access control on a
workspace, restrict the folder's ACL manually (Properties → Security) or place it
in a directory already limited to your account. The database is unencrypted —
see `docs/SECURITY.md`.

## 7. Uninstall

```powershell
python -m pip uninstall aurora-framework
Remove-Item -Recurse -Force "$env:APPDATA\aurora"
```

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `python` opens the Microsoft Store | The Store alias shadows the real interpreter; use `py -3.12` or reinstall Python with PATH enabled |
| `Activate.ps1 cannot be loaded` | Execution policy; use the `-Scope Process` command above |
| `aurora` not found after install | The venv is not active; check `(Get-Command aurora).Source` |
| Garbled banner characters | Legacy code page; use Windows Terminal or `aurora --ascii` |
| `database schema version N is newer` | Workspace was created by a newer build; upgrade or use another `--home` |
| Antivirus blocks the venv | Some products quarantine console tools; add an exclusion for the project folder only if you trust the source |
