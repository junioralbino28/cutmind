<h1><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/preview/cutmind-logo-white.png">
  <img src="assets/preview/cutmind-logo.png" alt="CutMind" height="44">
</picture></h1>

English · [Português](README.pt-BR.md)

Video editing by conversation, in Claude Code and Codex. Put your raw footage in a
folder, open the agent there and ask for the edit: it transcribes, picks the best
takes, cuts on the speech, adds captions and motion, and hands you the final file.

Vertical (Reels, TikTok, Shorts) and horizontal (YouTube). Transcription runs on
your own computer.

> Under construction.

## Edit from your phone

The same editor opens in your phone's browser, CapCut style: a timeline you work
with your finger, caption styles previewed on your own video, uploads from your
gallery and a download of the final cut. Ask the agent to "open the editor on my
phone" and scan the QR code behind the **Open on phone** button in the editor on
your computer. Over the network, only someone who opened the link or the QR code
gets in, because both carry a code from this computer.

The editor follows your browser's language, and the **PT | EN** button at the top
switches it.

## Install

Ask your agent (Claude Code or Codex): **"install CutMind for me, in the shared skills
folder, so I can use it in every project: https://github.com/junioralbino28/cutmind"**.
It runs the installer, installs whatever is missing (uv, ffmpeg, Node.js) and checks
that everything works. Its step-by-step guide is in [install.md](install.md).

The install belongs to your agent, not to a project: you can have the install
conversation in any folder. CutMind goes to the shared skills folder
(`~/.claude/skills/cutmind` in Claude Code) and shows up in every new conversation. To
edit, open a new conversation INSIDE the folder with your videos: the kit creates that
project's `edit/` folder there.

Got the kit as a zip? Extract it and ask: **"install CutMind from the folder
<where you extracted it>, in the shared skills folder"**.

By hand, it's a single command:

    uv run https://raw.githubusercontent.com/junioralbino28/cutmind/main/cutmind_install.py --lang en

Already downloaded this folder? From inside it:

    uv run --no-project cutmind_install.py --source . --lang en

You need [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`. The installer adds Node.js (Phase 2) by itself when it's missing: with winget on Windows and Homebrew on a Mac. On Linux it shows you the command.
