# Editing from the phone

The phone editor is the same app at `/celular`: same `state.json`, same
`preview_edits.json` / `preview_style.json`, same watcher. Nothing about the edit
changes — only how the user reaches the server.

## Three ways in

| Way | When | How | Code? |
|---|---|---|---|
| Wi-Fi | same network as the PC | `start_preview.py --root <edit> --host 0.0.0.0` | yes, inside the link |
| Tailscale | away from home, Tailscale on PC and phone | same `--host 0.0.0.0`; add `--allow-host .ts.net` for the MagicDNS name | yes |
| Cable (Android) | phone on USB with debugging on | server as usual (127.0.0.1) + `adb reverse tcp:<port> tcp:<port>`, open `http://127.0.0.1:<port>/celular` | no: it arrives as 127.0.0.1 |

"Add to home screen" ships a manifest and icons. Chrome's documentation asks for
https to install as a full-screen app; 127.0.0.1 (the cable) counts as secure.
Over plain http on Wi-Fi it may become a shortcut with the browser bar — not yet
confirmed on a phone (desktop Chromium reported no installability error either
way, so it does not settle it).

## Turning it on

1. Only when the user asks ("abre no celular", "quero editar pelo celular"). The
   default stays 127.0.0.1 — never open the server to the network on your own.
2. Stop the running preview and start it again with `--host 0.0.0.0` (same
   port). `start_preview.py` prints one link per network ("Wi-Fi de casa",
   "Tailscale (fora de casa)"). Give the user the link, or tell them to click
   **Abrir no celular** in the PC editor and scan the QR.
3. **Windows asks once.** The first time Python listens on the network, Windows
   Firewall shows a dialog. Tell the user to allow it on **private networks**. If
   the phone loads nothing, that dialog (or a network marked as public) is the
   first suspect — not the code.
4. The link is `/c?t=<code>`: it stores the code in a cookie and redirects to
   `/celular`, so the address bar never shows it. The code lives in
   `<edit>/.preview_cache/celular-token` and survives restarts. Never paste it
   anywhere public. To revoke: delete that file and restart — old links and
   installed shortcuts stop working.

## Videos sent from the phone

**Enviar** streams the file into the videos dir (the parent of `<edit>`, or
`--upload-dir`), never overwriting (`nome (2).mp4`), and lists it in
`<edit>/preview_upload.json`; `watch_edits.py` announces it. With no cut yet,
that video is the source: start Phase 1. With a cut ready, ask what it is for.
Delete `preview_upload.json` once handled. Limits: `--max-upload-gb` (default 8)
and the disk is never filled past its last 512 MB.

## What the server enforces

- Data routes (`/api`, `/media`, `/gen`) need the code unless the request comes
  from this computer (127.0.0.1). The UI shell is public: it is the kit's open
  code, and the browser fetches the manifest and icons without cookies.
- `Host` must be an IP, `localhost` or a name passed with `--allow-host`. That is
  what stops a website from reaching the server through DNS rebinding.
- `/api/celular` (links + QR) answers only this computer.
- `/gen/frame` (the trim-handle preview) only reads sources listed in `edl.json`
  by name — never a path from the request.
