# Doing the editor's edits from the chat

Every tool in the editor (`assets/preview/celular.*`, the same app on the computer and
the phone) only writes a file that the agent's pipeline reads. So any edit the user can
make there, you can make from a chat request: write the same file by hand, run the same
helper, verify the same way. Nothing here is a second implementation — it is the same
data, written by you instead of by the Salvar button.

Use this when the user asks for an edit in words ("deixa a tomada 3 em 2×", "põe um P&B
no começo", "abaixa a música") and the editor is not the faster way. Prefer the editor
when the choice is a matter of taste the user has to see or hear (which of 145 filters,
which caption style, whether a song fits): open it and say where to look.

**Every times rule from the editor holds here too.** Cut times (layers, effects, the
Phase 2 blocks) are seconds of the current `cut.mp4`; take edges are seconds of the
SOURCE. Never sum `end − start` to find where a take sits in the cut — read it from
`helpers/tempo.py` (`tomadas_no_corte`), which knows speed, curves and the J-cut.

After any edit: bump `state.json` (`message`, and `phase` if it moved) so the open
editor reloads by itself, and tell the user what changed and where.

## The takes (`edl.json`, Phase 1)

| Editor tool | Chat request | What to write | Then |
|---|---|---|---|
| trim (handles) | "começa a tomada 2 meio segundo depois" | `ranges[i].start` / `end` (source seconds); validate against `speech_regions.py` | `render.py`, `verify_cut.py` |
| `excluir` | "tira a tomada do meio" | drop the range | same |
| move (hold and drag) | "põe o fecho antes do meio" | reorder `ranges` | same |
| `dividir` | "divide a tomada 3 no 'então'" | two ranges from the same source, meeting at the split point. A split alone changes nothing (render merges consecutive ranges that meet exactly); it only matters together with another change on one half | same |
| `duplicar` | "repete essa frase" | the same span twice | same |
| `volume` | "abaixa a tomada 2 pela metade" | `ranges[i].volume` 0–4 (0.5 = 50%); omit at 1. The user's choice — level fixes are `gain_db` | `render.py` applies it last; Phase 3 with `mixar_final.py` |
| `velocidade` | "acelera a tomada 4 para 2×" | `ranges[i].velocidade` 0.25–4; omit at 1; never with `curva` | `render.py` |
| `velocidade` → Curva | "faz o Herói na tomada 2" | `ranges[i].curva` = `{"nome": ..., "pontos": [[x, y], ...]}` (presets below; x 0–1 along the take in the source, y 0.1–10) | `render.py` |
| `original` | "volta a tomada 2 como estava" | the edges from the previous `edl.json` | same |

`SKILL.md` ("EDL format") has every field's rules; after a render, `jcut_timeline` is the
truth for where each take landed. Proven from a hand-written EDL by
`tests/test_velocidade_render.py` (speed, curves, J-cut), `tests/test_volume_tomada.py`
(volume, measured after the whole chain) and `tests/test_tempo.py` (the clock).

### Speed curve presets (the editor's `CURVAS`)

| `nome` | Editor name | `pontos` |
|---|---|---|
| `montagem` | Montagem | `[[0, 0.9], [0.1, 0.9], [0.5, 6.8], [0.65, 0.3], [0.8, 1], [1, 1]]` |
| `heroi` | Herói | `[[0, 1], [0.05, 1], [0.35, 5.5], [0.45, 0.5], [0.55, 0.5], [0.65, 5.5], [0.95, 1], [1, 1]]` |
| `bala` | Bala | `[[0, 5.2], [0.4, 5.2], [0.46, 0.5], [0.54, 0.5], [0.6, 5.2], [1, 5.2]]` |
| `salto` | Salto | `[[0, 0.6], [0.43, 0.6], [0.5, 6], [0.57, 0.6], [1, 0.6]]` |
| `entrada` | Entrada rápida | `[[0, 5.2], [0.4, 5.2], [0.6, 1], [1, 1]]` |
| `saida` | Saída rápida | `[[0, 1], [0.4, 1], [0.6, 5.2], [1, 5.2]]` |
| `personalizar` | Personalizar | any 2–20 points; starts as `[[0, 1], [0.25, 1], [0.5, 1], [0.75, 1], [1, 1]]` |

Above ~2.5× there is no speech left to caption; say so when a curve peaks there.

## Colour, filters and transitions (`efeitos.json`)

Schema in `helpers/efeitos.py` (validate with `efeitos.normalize`); times in cut seconds.
Run `helpers/efeitos_render.py <edit>` after writing it, then the Phase 2 render
(`references/shortform.md`, "Effects from the editor").

| Editor tool | Chat request | What to write |
|---|---|---|
| `ajustar` | "clareia a tomada 2 e tira um pouco da cor" | `{"tipo": "ajuste", "inicio", "duracao", "ajustes": {...}}` over the take's window in the cut (`tomadas_no_corte`); keys `brilho contraste saturacao exposicao temperatura matiz realces sombras vinheta`, each −100…100, 0 left out; one per take |
| `filtros` | "põe um P&B no começo" | find the id with `pacotes.py listar --tipo filtro --busca pb`, then `{"tipo": "filtro", "pacote": <id>, "inicio", "duracao"}` |
| `intensidade` | "esse filtro mais fraco" | the filter's `intensidade`, 0–1 (absent = the package's own) |
| `transicoes` | "uma transição de zoom entre a 2 e a 3" | `pacotes.py listar --tipo transicao`, then `{"tipo": "transicao", "pacote": <id>, "corte": <cut second where the takes meet>, "duracao"}` (0.1–5 s) |
| `excluir` (on an effect) | "tira o filtro" | drop the item |

A re-cut moves the takes: map every effect time to the new cut before re-running, and
drop (and tell) an effect whose moment was cut out. Proven from hand-written files by
`tests/test_efeitos.py` (the schema) and `tests/test_efeitos_render.py` (the render).

## Images, audio, text and soundtracks (`camadas.json`)

Schema in `helpers/camadas.py` (validate with `camadas.normalize`); files live in
`<edit>/midia/`, times in cut seconds. Images and texts → `camadas_edit_data.py <edit>`
(it also makes the person's cut-out and the face track a text asks for); sound →
`mixar_final.py <edit> --render <render>` (`references/shortform.md`, "Layers from the
editor").

| Editor tool | Chat request | What to do |
|---|---|---|
| `imp-imagem` | "põe esse print aos 12 s por 3 s" | copy the file the user gives into `<edit>/midia/`; a `tipo: "imagem"` track with `{"arquivo": "midia/<name>", "inicio", "duracao"}` |
| `imp-audio` / `do-celular` | "põe esse áudio de fundo" | same, `tipo: "audio"`, with `corte` (where the file starts playing) and `volume` 0–2 |
| `trilhas` | "põe uma trilha animada" | `pacotes.py listar --tipo trilha --busca <mood>`, then `pacotes.py camada <edit> <id> [--inicio s]` (it writes the layer, marked `trilha`, at 15%) |
| `volume` (on a layer) | "a música mais baixa" | the item's `volume` |
| `melhorar` | "limpa o ruído desse áudio" | the item's `melhorar: true` (noise reduction + voice chain in `mixar_final.py`) |
| `texto` | "escreve PROMOÇÃO no meio da tela dos 5 aos 8 s" | a new `tipo: "texto"` track with `{"texto", "inicio", "duracao", "x": 540, "y": 960}` (the CENTRE, frame px; `\n` breaks the line) |
| `texto-editar` | "o texto em Anton amarelo, maior, com contorno preto", "curva o texto pra cima" | the item's `estilo`: `fonte` (a family of `assets/preview/fontes.js`, with its `peso`), `cor`, `tamanho` (× 96 px), `contorno` (px), `corContorno`; `curva` −100 to 100; `x`/`y` to move it |
| `atras` | "põe o texto atrás de mim", "essa imagem atrás de mim" | the item's `atras: true` (text or image); `camadas_edit_data.py` makes the cut-out of that window (`person_matte.py`, ~30 s per 3 s on CPU). An image then becomes the big card behind the person (`behind[]`) instead of the top card |
| `texto-segue` | "o texto acompanhando meu corpo" | the item's `acompanhar: true`; `camadas_edit_data.py` tracks the face (`face_track.py` → `public/rastreio.json`) |
| `duplicar` (on a layer) | "repete esse texto embaixo" | copy the item into a NEW track (new ids), same time; change what differs |
| `excluir` (on a layer) | "tira a imagem" | drop the item (and the track when empty) |
| track header (mute, hide, lock) | "sem o som do vídeo nessa parte" | `mudo` / `oculto` / `travado` on the track; `video.mudo` for the video's own sound |
| `imp-video` | "usa também esse outro vídeo" | it is a new SOURCE, not a layer: copy it next to the others in the videos folder, transcribe, and cut it into `edl.json` like any take |

Files that live only on the user's phone reach you through the editor's import; from the
chat you need a path on this computer. A text behind the person sits on the bare picture:
under a full-frame effect (split screen, a scene) it is covered. Proven by `tests/test_camadas.py`,
`tests/test_camadas_edit_data.py`, `tests/test_mixar_final.py`,
`tests/test_melhorar_audio.py` and `tests/test_pacotes.py` (`pacotes.py camada`).

## Phase 2 blocks, style and captions

| Editor tool | Chat request | What to write |
|---|---|---|
| hook / insert / word blocks (move, trim) | "o gancho até 3 s", "a tela dividida 2 entra mais cedo" | `edit-data.json` directly: `hook.endSec`; `inserts[]`, `splitInserts[]`, `splitVideos[]`, `wordAccents[]` `start`/`end`; `behind[]` `start`/`dur`. Re-render Phase 2 |
| `estilo` / `legenda` | "muda a legenda para empilhado" | when the user NAMES the style, write it in `state.json` `style` and rebuild Phase 2 (`references/shortform.md`). When they only ask "qual fica melhor?", open the Estilo panel instead (`awaitingStyle`): the gate exists so they see each style on their own frame |
| Phase 2 soundtrack (the read-only block under the audio in Final) | "abaixa a trilha", "tira a música" | `soundtrack` in `edit-data.json`: `volume` (linear, 0.0445 when absent) or `enabled: false`; then `mixar_final.py`. The editor only shows it, so this one is always from the chat |
| caption position (`todas`, `padrao`) | "a legenda mais para cima" | `captionPositions` in `state.json` `style` (`all` for every phrase, `phrases[]` anchored on the source moment), then `caption_positions.py --style <edit>/state.json ...` (`references/shortform.md`, "Where each phrase sits"); `padrao` = leave it out |
| `cena-liga` | "tira o efeito do gráfico" | `cenas[i].desligada: true` (false or absent = on). Re-render that effect's window |
| `cena-texto` | "troca GARGALO por GARGALOS", "o GARGALO em Bebas, maior" | `cenas[i]`: the text field itself (`palavra`, `titulo`, `frase`, `pergunta`, `gigante`, `pequeno`, `etiqueta`, `botao`, `nome`; `batidas[k].palavra` in the digital zoom) and `estilo`: `fonte` (a family of `assets/preview/fontes.js`, with its `peso`), `cor`, `tamanho` (× the designed size), `contorno` (px) and `corContorno`. Re-render the window |
| `cena-texto` on the hook or a number block | "o gancho em Anton amarelo", "o 6 MIL menor" | `hook` / `numeros[i]` in `edit-data.json`: `texto`, `estilo` (same keys as the effects) and the text (`hook.text`; `prefixo`, `valor`, `sufixo`, `rotulo`). Re-render the window |
| moving the effect's frame on the video, `cena-lugar` | "o texto do vidro mais para cima" | `cenas[i].texto = {x, y}`: the block's centre in 1080×1920 frame px (`cena-lugar` = `x: 540`); absent = the component's default place. Re-render the window |
| `cena-original` | "volta o efeito como estava" | the previous values of those keys |
| `zoom-valor`, `zoom-sem` | "a tomada 4 sem zoom", "mais zoom na 2" | `camera.zooms`: one base zoom per take (expand the cycle to one per take first, as the editor does); `zoom-sem` = 1. Re-render those takes |
| `zoom-original` | "volta o zoom da 4" | the previous value |
| `leg-texto` | "legenda em Bebas amarela", "a legenda maior, com contorno" | `captions.estilo` in `edit-data.json`: `fonte` + `peso`, `cor`, `tamanho` (×), `contorno` (px), `corContorno` (the karaoke and the three static styles); on `stacked`/`scatter` only `tamanho` counts. Re-render |
| `leg-segue` | "a legenda acompanhando meu corpo" | `captions.acompanhar: true`; then `camadas_edit_data.py <edit>` (it tracks the face into `public/rastreio.json`) and re-render |
| `leg-posicao` | "a legenda mais para cima" | the caption position row above (`captionPositions`) |
| `leg-original` | "volta a legenda como estava" | the previous `captions.estilo` / `captions.acompanhar` |

Phase 2 is short-form only for the style gate; on longform ask the layer questions in
chat (`SKILL.md`, "The Estilo panel"). Caption positions are proven by
`tests/test_caption_positions.py`.

## Editor-only controls (no file behind them)

`voltar`, `cortar` (selects the take under the needle), the A1/A2 caret on the audio track
(shows where each take's sound plays and the J-cut lead; `jcut_timeline` is the data), `importar`, `audio` and `efeitos`
(open their menus), `ouvir` (plays the take), `f2-original` and `pronto` (editor state),
undo/redo, zoom, Descartar, Baixar. `marcar` is how the user talks to you from the
editor (a note on a range, arriving through `watch_edits.py`); from the chat they just
say it.

## What stays with the user

You do not hear: cut breaths, stumbles and silences by the transcript and the level
measures, and leave "does the music fit / is the emphasis right" to them. You see
frames, not motion: extract frames to check a filter or a position (`contact_sheet.py`,
`timeline_view.py`), and for a choice among many looks prefer the editor. Say which of
these was the case when you hand the edit back.
