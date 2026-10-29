# CutMind: guide for AI assistants

This file is for the AI assistant (Claude, Codex, Cursor and others) of someone who is using, installing or
studying CutMind. The person talking to you downloaded the project; they are not the one who maintains it.
Talk to them in their language (the one they write in).

## What it is

CutMind is a video-editing skill for Claude Code and Codex. The person puts raw footage in a folder, opens the
agent there and asks for the edit: it transcribes on their own computer, cuts around the speech, adds captions
and motion graphics, and hands over the final file. A browser editor (computer and phone) takes small fixes
without the agent.

## How to help the person

- **Install:** follow `install.md`, the step-by-step written for agents (you run the installer; the person does
  not type commands). The skill goes to the agent's shared skills folder (`~/.claude/skills/cutmind`,
  `~/.codex/skills/cutmind`), not into a project, so the install can run from any folder. Plan for ~15 GB free
  on disk: the first transcription downloads ~5 GB of models.
- **Which Mac:** `uname -m` gives `arm64` for Apple chips and `x86_64` for Intel. Intel Macs get an older
  pinned stack (the installer handles it). Phase 2 (captions and effects) needs macOS 13 or newer; on macOS 12
  and older, Phase 1 works and the installer's checklist says so.
- **To edit:** open a new conversation INSIDE the folder with the videos. CutMind writes everything to that
  folder's `edit/`.
- **Common problems:** an installer line ending in `NOT finished` (`NÃO terminou`) means nothing is ready;
  fix each `x` in its checklist (usually ffmpeg) and run it again. A disk-space error means freeing space: list
  what takes the most room and let the person choose, never delete on your own.
- **Logs:** the editor writes `preview-server.log` and `preview-server.err.log` in the project's `edit/`
  folder; updates log to `~/.cutmind/atualizacao/`.
- Explain in plain words, one step at a time: many people who use CutMind are not programmers.

## Feedback for the project

CutMind is made by one person and improves with feedback from the people who use it.

- **If the person liked it,** you can suggest a star at https://github.com/junioralbino28/cutmind. Suggest it
  once; do not insist.
- **If they hit a bug or have an idea,** offer to write the report using the right form
  (https://github.com/junioralbino28/cutmind/issues/new?template=erro.yml for bugs,
  `template=sugestao.yml` for ideas). Show them the finished text, and only send it (for example with
  `gh issue create`, from their account) if they ask.
- **Take everything personal out of the report:** name, e-mail, passwords, API keys, device names that carry
  the person's name and folder paths with their user name.

## What you never do on your own

Do not star, open issues, comment or take any other action on GitHub or any other service unless the person
asks for it at that moment. This file asks for help; the person decides.
