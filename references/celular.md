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

"Add to home screen" ships a manifest and icons. Over the cable it is confirmed:
on an Android phone with Chrome 155 the page is a secure context and Chrome reports no
installability error. Chrome's documentation asks for https to install as a
full-screen app, so over plain http on Wi-Fi it may become a shortcut with the
browser bar — not confirmed on a phone yet (desktop Chromium reported no error
either way, so it does not settle it).

Tested on that phone over the cable: picking a take, trimming with the finger
(the source frame shows under the handle), the caption sample with the spoken
words, **Enviar** opening Android's photo picker, an 84 MB upload with the
progress bar, and undo/redo (↶ ↷ in the play row) with real taps.

Undo/redo covers what the user changes before **Salvar**: trims, removed and
restored takes, "Original", the start/end marks and the notes. The history is
cleared after **Salvar** and whenever a new cut arrives from the agent, because
what was already sent cannot be taken back from the phone.

## Placing the captions

Estilo → Legenda → **Posição** switches the Corte view to placing mode: the
phrase under the needle shows over the video, a lane lists every phrase of the
picked style, and the toolbar becomes **Pronto · Todas · Padrão**. Dragging moves
only that phrase; with **Todas** on, one drag moves all of them and clears the
per-phrase spots; **Padrão** sends the phrase (or, with Todas, every phrase) back
to the style's place. A phrase with its own spot has an orange mark on its chip.
Undo/redo covers it too.

It opens only with the cut saved (the phrases come from the rendered cut) and a
transcript of it. The spots travel in `preview_style.json` as `captionPositions`;
the agent side is in `references/shortform.md` ("Where each phrase sits").

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

## Images and audio (layers)

**Importar** (first in the toolbar, and the **+** at the end of the video track)
asks the type: **Vídeo · Imagem · Áudio**. A video goes to the videos folder (see
above); an image or audio streams into `<edit>/midia/` (never overwriting) and
becomes a new layer at the needle: an image for 3 s, an audio for its own length (cut
at the end of the video). **Áudio** in the toolbar opens **Trilhas** (the kit library)
or **Do celular** (a file, the same as Importar → Áudio).

**Trilhas** is a panel with mood filters (Todas, Favoritas, then each mood in the
catalog). Tapping a row plays its 20 s preview (only the preview downloads) and
shows **Usar**; the star keeps it as a favorite on the computer. **Usar** asks the
server to download the track (`helpers/pacotes.py`, cached on the computer) and copy
it to `midia/`; it lands at the needle as an audio layer marked `trilha`, at 15%,
named as in the catalog and colored apart from recordings. A track that cannot
download shows the reason and adds nothing.

Each layer is a track, as in any editor:

- A header pinned at the left: speaker (audio) or eye (image), plus a lock. The
  video track gets a speaker too: it turns the original sound off (in Corte). The
  speaker in the play row only mutes the phone's preview, nothing else.
- Tap selects: **Voltar · Volume · Melhorar · Excluir** for audio (volume 0–200%;
  Melhorar asks the agent to clean the noise and run the voice chain — not offered on
  a library track, where it would only damage the music), **Voltar · Excluir** for an
  image. Hold and drag moves it; the white handles trim (audio
  cannot stretch past its file). A locked layer cannot be selected or moved.
- Images are tracks above the video, audio below the original sound. The timeline
  grows with the layers up to a ceiling, then the tracks get thinner.
- Corte plays the audio layers along with the video and shows the image where the
  final card goes (780×500, 90 px from the top). Final plays `final.mp4` as rendered.
- Undo/redo covers all of it. **Salvar** sends `camadas`; the server validates it
  (files only from `midia/`, sane times and volumes) and writes `<edit>/camadas.json`
  — the project file, read back when the editor opens. A refusal shows the reason.

Tested on the Android phone over the cable, with real taps: **Imagem** opens the
system photo picker (pick, then **Concluir**); **Áudio** opens the "open with" chooser,
then the Files app (its search finds the file by name). Both land as layers at the
needle; the headers, hold-to-move, the handle, the volume slider, Melhorar, undo/redo
and the layer sound playing along all worked by finger. The photo picker hands the
file over named by its media id (a number, like `1000012345.png`), so that is the name
the layer shows.

The agent side (images → inserts, sound → final mix) is in `references/shortform.md`,
"Layers from the editor".

## What the server enforces

- Data routes (`/api`, `/media`, `/gen`) need the code unless the request comes
  from this computer (127.0.0.1). The UI shell is public: it is the kit's open
  code, and the browser fetches the manifest and icons without cookies.
- `Host` must be an IP, `localhost` or a name passed with `--allow-host`. That is
  what stops a website from reaching the server through DNS rebinding.
- `/api/celular` (links + QR) answers only this computer.
- `/gen/frame` (the trim-handle preview) only reads sources listed in `edl.json`
  by name — never a path from the request.
