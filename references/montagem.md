# Montage on the beat (`montagem.py`)

A montage is a video with no speech to cut: photos and clips that change on the beats of a song,
with the drop landing on a marked slot. It is not a Phase-1 cut, so the phase gate and the
transcript do not apply. Use it when the person asks for "um vídeo na batida", "as fotos no ritmo
da música", "um Reels com essas fotos e essa música", or picks a template in the editor's
Modelos de montagem panel (or Nova montagem in Projetos).

## The pieces

| File / helper | What it is |
|---|---|
| `helpers/batida.py` | the beat grid of a song (Beat This!, local): beats, downbeats, BPM, energy per bar, the drop and the strength of each half beat. Cached per song in `<edit>/batidas/` |
| a template (`montagens.py`) | the rhythm: slots (`vagas`, each N beats, optional `repetir` and `movimento`), `drop_na_vaga`, texts and transitions. The user's in `~/.cutmind/montagens/`, the kit's in `assets/montagens/` and in the package library (type `montagem`) |
| `helpers/montagem.py` | builds the project and the video: `usar`, `montar`, `aplicar`, `render`, `conferir`, `capturar` |
| `helpers/mural.py` | the community mural (only with `CUTMIND_MURAL`): list, take a template, share one |

## Making one

1. **Template.** `python helpers/montagens.py listar` shows the ids (the user's first, then the
   kit's and the library's). Pick by the song: a template whose slots before the drop add up to
   more beats than the song has before its drop cannot put the drop on the marked slot (the
   `usar` summary warns). When unsure, run `batida.py` on the song first and read where the drop is.
2. **Song and media.** The song is an audio file; media are photos and clips, in order. With fewer
   media than slots they repeat in order; with more, the extra ones stay out.
3. **Build.** `python helpers/montagem.py usar <template id or JSON> --musica <song> --midias <files or
   folders> --edit <edit>` (`--formato 16:9|1:1|9:16` to override the template's). It normalises each
   slot (a clip shorter than its slot slows down to 0.5× and then holds its last frame; photos get
   the slot's movement), renders, mixes, and checks the result.
4. **Check.** `usar` ends with the beat check: every cut must land within one frame of its beat
   (`conferir` measures it again on any render). A failed image check right after a heavy job on the
   machine is load, not a bug: render again with nothing running beside it.

From the editor, the panel's Montar saves `montagem.usar` and the watcher says to run
`montagem.py montar <edit>`. Changes after that (a slot's media, the part of a clip that enters, the
framing, the format, texts) are in `references/pelo-chat.md` (A montage on the beat).

## Which part of a clip enters

The start of the clip, unless the person says otherwise: `arquivo@segundos` in `--midias`, or
`montagem.py aplicar <edit> --lugar N --de <s>` later. Only open a clip to choose a better part when
asked; then look with `watch_video.py` or `contact_sheet.py`, never by reading machine data.

## Templates from the library

The package library (`pacotes.py`, type `montagem`) carries templates written in the catalog, so the
panel lists them with no download, plus an example video (`previa`) made only with kit material:
numbered cards where the person's photos and clips go, on a beat the kit generates. The editor's
play button on the card downloads and shows it; from the chat, `pacotes.py listar --tipo montagem`
lists them and `pacotes.py obter <id>` gets the template file. A user template with the same name
wins over a library one.

## Music changed in the app

If the person posts the video and swaps the song inside Instagram or TikTok, it has to be the same
song starting at the same point the montage used, or the cuts leave the beat. Say so when handing
over a montage whose song the person said they will add in the app.

## The community mural

With `CUTMIND_MURAL` set, the panel has a Da comunidade tab and a share button on the person's own
templates. `mural.py lista`, `mural.py pegar <code>` and `mural.py link <id>` do the same from the
chat. Publishing always happens on the mural's own page, by the person, never from the agent.
