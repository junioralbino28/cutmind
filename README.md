<h1><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/preview/cutmind-logo-white.png">
  <img src="assets/preview/cutmind-logo.png" alt="CutMind" height="44">
</picture></h1>

English · [Português](README.pt-BR.md)

Video editing by conversation, in Claude Code and Codex. Put your raw footage in a
folder, open the agent there and ask for the edit: it transcribes, picks the best
takes, cuts around the speech, adds captions and motion graphics, and hands you the final file.

Vertical (Reels, TikTok, Shorts) and horizontal (YouTube). Transcription runs on
your own computer.

> Under construction.

## Edit from your phone

The same editor opens in your phone's browser, CapCut style: a touch-friendly
timeline, caption styles previewed on your own video, uploads from your
camera roll and a one-tap download of the final video. Ask the agent to "open the editor on my
phone" and scan the QR code behind the **Open on phone** button in the editor on
your computer. On your network, only people who open that link or QR code
can get in, since both carry an access code from your computer.

The editor follows your browser's language, and the **PT | EN** button at the top
switches it.

## Edit only by chatting

Small fixes in the editor are free. Save applies them on the spot and Download builds
the final video, all without the agent. In the chat, every request puts the agent to
work, and that uses your Claude or Codex limit. You can edit only by chatting, and it
costs less like this:

- put several requests in one message, one per line;
- give the time ("from 0:12 to 0:15") so the agent finds the spot right away;
- ask for the result you want, not for how to do it.

Requests that work well:

- "Cut 0:12 to 0:15, that's where I'm reading the script."
- "Cut the breath at 0:41."
- "Move the opening text up and make it bigger."
- "Bigger captions."
- "Lower the volume from 1:02 to 1:10."
- "Make the whole video black and white."

In the editor, what you do by hand costs nothing. Markers (the M key) and written
requests wait for the **Done, Claude takes over** button, which wakes the agent just
once, with everything together.

## Install

Ask your agent (Claude Code or Codex): **"install CutMind for me, in the shared skills
folder, so I can use it in every project: https://github.com/junioralbino28/cutmind"**.
It runs the installer, installs whatever is missing (uv, ffmpeg, Node.js) and checks
that everything works. Its step-by-step guide is in [install.md](install.md).

CutMind installs into your agent, not into a project, so you can run the
install from any folder. CutMind goes to the shared skills folder
(`~/.claude/skills/cutmind` in Claude Code) and shows up in every new conversation. To
edit, open a new conversation INSIDE the folder with your videos: the kit creates that
project's `edit/` folder there.

Got the kit as a zip? Extract it and ask: **"install CutMind from the folder
<where you extracted it>, in the shared skills folder"**.

To install manually, it's a single command:

    uv run https://raw.githubusercontent.com/junioralbino28/cutmind/main/cutmind_install.py --lang en

Already downloaded this folder? From inside it:

    uv run --no-project cutmind_install.py --source . --lang en

You need [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`. The installer adds Node.js (Phase 2) automatically if it's missing: via winget on Windows and Homebrew on a Mac. On Linux it shows you the command.
