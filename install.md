---
name: cutmind-install
description: Install, verify or repair CutMind (Claude Code, Codex, or any agent with a skills directory). When the user asks for it to be installed, YOU run the installer, install what is missing and verify; this file says how.
---

# cutmind install

Use this file only for first-time setup, verification or repair. For daily
editing, read `SKILL.md`. Always read `helpers/` — that's where the scripts live.

> **You install.** When the user asks for CutMind — "instala o CutMind", a link to
> this repository, a folder they downloaded — run the installer yourself and finish
> the job: install what is missing, verify, hand off. Do not give them a command to
> type; not having to is the point of asking you. The only thing that goes back to
> them is a password or an admin prompt you cannot answer. Talk to them in their
> language (the one they write in) the whole way through.
>
> 0. **The install is global, not per project.** The session you install from can be
>    open in any folder; the skill goes to the agent's general skills directory and
>    serves every project. If the user asks where or in which project to install, say
>    exactly that. Desktop apps make them pick a folder first, and the first real
>    user asked.
> 1. **Detect the OS**, and on Windows which shell you are in.
> 2. **`uv`.** If `uv --version` fails, install it: `winget install --id astral-sh.uv -e`
>    (Windows), `brew install uv` (macOS), `curl -LsSf https://astral.sh/uv/install.sh | sh`
>    (Linux). A fresh install is not on THIS terminal's PATH yet. On Windows, reload it
>    from the registry in the same command line that uses it:
>    `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`
> 3. **Run the installer:**
>    - from the internet: `uv run https://raw.githubusercontent.com/junioralbino28/cutmind/main/cutmind_install.py`
>    - from a folder the user already has (download or clone):
>      `uv run --no-project <folder>/cutmind_install.py --source <folder>`
>
>    Add `--idioma pt` when you are talking with the user in Portuguese and `--idioma en`
>    in any other language, so its messages come out in a language they read (without it,
>    it follows the system's language).
>
>    It copies the skill into every agent it finds, runs `uv sync` (torch + WhisperX: a
>    few GB the first time; tell the user it is downloading, then wait), installs
>    Node.js LTS when it is missing, and ends with a checklist. It needs ~3 GB free to
>    install and will not start the download with less; plan for ~15 GB free in all
>    (the first transcription fetches ~5 GB of models, and each edited video takes a
>    few GB). If it ends with `NÃO terminou` (`NOT finished`), nothing is ready, whatever else it printed.
> 4. **Fix every `x` in the checklist** and run the installer again. ffmpeg is the usual
>    one: `winget install Gyan.FFmpeg` / `brew install ffmpeg` (reload the PATH as in
>    step 2). On Linux, `sudo apt-get install -y ffmpeg` needs the user's password: that
>    exact line is the one thing you hand over. For `falta espaço no disco`, help the
>    user free space: list what takes the most room and let them choose; never delete
>    anything on your own.
> 5. **Verify** (below) and **hand off** (end of this file).

## What the install consists of

1. The skill directory itself — `~/.claude/skills/cutmind`, or the equivalent for
   Codex (`~/.codex/skills`) or Antigravity (`~/.gemini/config/skills`). `cutmind_install.py` puts it there; it needs no git on the user's
   machine because it unpacks a tarball.
2. Python deps via `uv sync`, which includes **WhisperX** — transcription is a
   normal dependency, not an extra.
3. `ffmpeg` + `ffprobe` on PATH — Phase 1 cannot run without them.
4. **Node.js 18+** and the `remotion-best-practices` skill — Phase 2 only. The
   installer fetches that skill too, and installs Node.js LTS by itself when it
   is missing (winget on Windows, Homebrew on macOS; `--no-node` turns that off).
   An existing Node is never upgraded, only reported when older than 18.
5. **Windows only: the editor on the phone.** The installer asks Windows once, with the
   administrator prompt, to let the kit's Python receive connections on private networks:
   the same as clicking Allow in the firewall dialog, done while the user is at the PC.
   Someone driving the agent from the phone app later cannot click that dialog. If they
   decline, the checklist says so and the dialog shows on the first phone open instead;
   `--no-firewall` skips the question. The tunnel (`start_preview.py --tunel`, any network)
   does not need this: it downloads `cloudflared` the first time it is used.
**No key is part of the install.** WhisperX transcribes locally, and Phase 1 needs
nothing else. Phase 2/3 have a few optional keys for illustrative images and the
AI soundtrack; they live in the track reference and are asked for only when the
user reaches that feature. Never raise the subject during install — it makes a
keyless tool look like it needs an account.

## Two layouts

- **User layout** (what the installer produces, and what you should assume): the
  skill directory IS `~/.claude/skills/cutmind` or `~/.codex/skills/cutmind`.
  Nothing to register, no symlink, identical on every OS.
- **Contributor layout**: repo cloned wherever the user keeps projects, plus a
  link into the skills directory. Only for someone developing the skill. The
  installer detects a `.git` there and refuses to overwrite it.

    ```bash
    # macOS / Linux
    ln -sfn ~/Developer/cutmind ~/.claude/skills/cutmind
    ln -sfn ~/Developer/cutmind ~/.codex/skills/cutmind
    ```

    ```powershell
    # Windows — a junction needs no admin rights, unlike a symlink
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\cutmind" `
      -Target "$env:USERPROFILE\Developer\cutmind"
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.codex\skills\cutmind" `
      -Target "$env:USERPROFILE\Developer\cutmind"
    ```

## Repair steps

Detect the platform before emitting commands. Do not hand a Windows user `ln`,
`brew`, `chmod`, `grep`, `sed`, or `curl -s -w` — in PowerShell `curl` is an
alias for `Invoke-WebRequest` and takes different flags. Use `Select-String`,
`Select-Object -First`, `Set-Content`, `Invoke-RestMethod`.

Everything below calls the skill directory `<CUTMIND>`.

### Python deps

```bash
uv sync --directory <CUTMIND>
```

`uv` reads `pyproject.toml`, provisions a Python 3.10–3.13 interpreter on its own
when the system one doesn't fit, and builds a `.venv` inside the skill. That venv
is why helpers run as `uv run python helpers/…` — a bare `python` won't see them.

**The Python cap is load-bearing:** `requires-python = ">=3.10,<3.14"` exists
because torch publishes no cp314 wheels. Without the cap, `uv` picks 3.14 and
every torch-backed feature (transcription, and matting through `--motor torch`)
fails to install. The default matting runs on ONNX Runtime and downloads its model
(~15 MB) on first use.

If `uv` is missing: `brew install uv` (macOS), `winget install astral-sh.uv`
(Windows), or the installer at https://docs.astral.sh/uv/. On Windows a
`winget install` only reaches `$PATH` in a **new** PowerShell window.

### ffmpeg

```bash
# macOS
command -v ffmpeg >/dev/null || brew install ffmpeg

# Debian / Ubuntu
# sudo apt-get update && sudo apt-get install -y ffmpeg
# Arch
# sudo pacman -S ffmpeg
```

```powershell
# Windows
winget install Gyan.FFmpeg
```

If a package manager needs sudo/admin, tell the user the exact command and wait.
Do not invent a password.

### Mac without Homebrew (no admin password)

Homebrew's own installer asks for the admin password. When the user can't type it
(or would rather not), everything the kit needs installs inside their home folder,
no password at all:

```bash
mkdir -p ~/.local/bin ~/.local/opt
if [ "$(uname -m)" = arm64 ]; then ff=arm64; nd=arm64; else ff=amd64; nd=x64; fi
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# ffmpeg + ffprobe, static builds
for p in ffmpeg ffprobe; do
  curl -fsSL -o /tmp/$p.zip "https://ffmpeg.martin-riedl.de/redirect/latest/macos/$ff/release/$p.zip"
  unzip -oq /tmp/$p.zip -d ~/.local/bin && chmod +x ~/.local/bin/$p && rm /tmp/$p.zip
done
# Node.js 22 LTS, checked against the official checksum list
base=https://nodejs.org/dist/latest-v22.x
curl -fsSL -o /tmp/SHASUMS256.txt $base/SHASUMS256.txt
v=$(grep -o "node-v[0-9.]*-darwin-$nd.tar.gz" /tmp/SHASUMS256.txt | head -1)
curl -fsSL -o /tmp/$v $base/$v
(cd /tmp && grep " $v\$" SHASUMS256.txt | shasum -a 256 -c -) || echo "CHECKSUM FAILED: stop here"
tar -xzf /tmp/$v -C ~/.local/opt && rm /tmp/$v /tmp/SHASUMS256.txt
for b in node npm npx; do ln -sf ~/.local/opt/${v%.tar.gz}/bin/$b ~/.local/bin/$b; done
grep -q '.local/bin' ~/.zshrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

Then open a new terminal (or `export PATH="$HOME/.local/bin:$PATH"`) and run the
installer. Node 22 runs on macOS 11 and later; newer Node lines need a newer macOS.

**Don't call `python3` or `git` on a Mac without the Command Line Tools**: they are
stubs that open an "install developer tools" window on the user's screen. The kit
needs neither (uv brings its own Python; the installer downloads with Python's own
HTTP).

**Phase 2 needs macOS 13 (Ventura) or newer.** Remotion's compositor, which reads
the video frames, is built for macOS 13+ and aborts on macOS 12 with `Symbol not
found: _AVCaptureDeviceTypeContinuityCamera`. On macOS 12 and older, Phase 1 works
(transcription, the cut, the editor, a montage with nothing on top); the installer
says so in its checklist, and the montage stops with a clear message instead of a
dead render. Tell the user before they plan captions or effects on such a Mac.

**Intel Macs** get an older, pinned stack (the comment in `pyproject.toml` has the
versions): PyTorch stopped publishing Intel Mac builds at 2.2.2. The installer asks
`uv sync` for Python 3.12 on those machines by itself; a manual sync there is
`uv sync --python 3.12`.

### Node.js + the Remotion skill (Phase 2)

The installer handles both. Node.js: when `node` is absent it runs
`winget install --id OpenJS.NodeJS.LTS -e --silent` (Windows may show its
permission prompt — the official Node.js installer) or `brew install node`, then
finds the new `node` even though this terminal's PATH does not have it yet; the
user opens a new terminal afterwards. Linux gets the command only (apt asks for a
password, and the distribution's package is often older than 18).

To do the Remotion skill by hand: it lives in a
**subdirectory** of its repo (`skills/remotion-best-practices` — upstream
renamed it from `skills/remotion` and turned it into a router bundling a dozen
sub-skills), so it cannot be cloned into place. The repo is small, which makes
copying the cheapest answer — and re-running the copy IS the update.

```bash
node --version    # must be 18+
```

```powershell
node --version    # if missing: winget install OpenJS.NodeJS.LTS, then reopen PowerShell
```

## Verify end-to-end

Run one real thing. Prefer the lightest check that still proves the pipeline is
wired up.

```bash
# macOS / Linux
cd <CUTMIND>
uv run python helpers/timeline_view.py --help >/dev/null && echo "helpers OK"
uv run python -c "import cv2; print('opencv', cv2.__version__)"          # Phase-2 face tracking
uv run python -c "import whisperx; print('whisperx OK')"                 # transcription
ffprobe -hide_banner -filters | grep -qE '\bdeesser\b' && echo "ffmpeg has voice-master filters"
ffprobe -version | head -1
node --version && echo "node OK (Phase 2)"
```

```powershell
# Windows — no grep/head; use Select-String and Select-Object
cd <CUTMIND>
uv run python helpers/timeline_view.py --help > $null; if ($?) { "helpers OK" }
uv run python -c "import cv2; print('opencv', cv2.__version__)"
uv run python -c "import whisperx; print('whisperx OK')"
if (ffprobe -hide_banner -filters | Select-String -Pattern '\bdeesser\b' -Quiet) { "ffmpeg has voice-master filters" }
ffprobe -version | Select-Object -First 1
node --version; if ($?) { "node OK (Phase 2)" }
```

A full transcription is a fine smoke test now that it costs nothing but CPU —
but the first run downloads the models (several GB), so only do it if the user
is ready to wait. Better to let their first real clip be the test.

## Hand off

Tell the user, in one short message:

- Where the skill is installed, and that it is the general skills directory: it
  serves every project, so they never install it again per folder.
- That they should `cd` into their footage folder and start their agent there.
- That all outputs land in `<videos_dir>/edit/` — the skill directory stays clean.
- That the first transcription downloads its models once.

Do NOT propose a first prompt or an editing strategy. PHASE 1 opens by looking at
the material and asking questions shaped by it; a suggestion invented at install
time, before anything has been inspected, pre-empts that with a guess.

## Keeping the skill current

- Re-run the install command. It replaces the skill and preserves `.env`.
- On the contributor layout: `git -C <CUTMIND> pull --ff-only`, then
  `uv sync --directory <CUTMIND>` if `pyproject.toml` changed.

## Cold-start reminders

- Helpers run as `uv run python helpers/<name>.py`. A bare `python` misses the
  `.venv` — the most common post-install failure.
- Never ask for a transcription API key. There isn't one.
- On Windows, prefer a **junction** over a symlink (no admin needed) — and
  prefer the user layout over both.
- After any `winget install`, `$PATH` only refreshes in a **new** PowerShell
  window. A "command not found" right after a successful install is almost
  always this.
- `ffmpeg` from static builds is fine. Any modern (≥4.x) build is enough.
- `yt-dlp` is a Python dependency, not a system package. If a URL source fails
  with "yt-dlp not on PATH", the venv is stale — `uv sync --directory <CUTMIND>`.
- Node 18+ and `remotion-best-practices` are Phase-2 only. Phase 1 (cut + grade)
  works without them, so a user who only wants a clean cut can start immediately.
- Remotion projects are scaffolded per-video by copying the skill's own template
  from `assets/` and running `npm install` there. `create-video` is not used: the
  template carries the compositions the skill knows how to fill, with the
  Remotion version pinned so an upstream release can't break a render.
- If the user is on a Linux without a package manager you recognize, print the
  manual `ffmpeg` install URL and wait rather than guessing.
