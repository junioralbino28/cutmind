# Effects that take the person off the background (`cenas[]`)

Fourteen Phase-2 effects redraw one take of the short-form video: a new background, things on it,
and the person, cut out of the frame, in front. They live in `edit-data.json` `cenas[]`, one item
per effect, and the template draws them (`assets/shortform/src/cenas/`).

| `tipo` | Name in the editor | What the viewer sees |
|---|---|---|
| `fundo` | Fundo | the same take on another background (a ready-made one or the user's image) |
| `vidro` | Vidro | the picture turns icy and one word of frosted glass rises behind the head |
| `capa` | Capa de revista | the frame becomes a magazine cover, the title behind the head |
| `mural` | Mural | newspaper clippings slam on a dark wall around the person |
| `parede` | Parede de fotos | polaroids fill the wall behind the person, a giant word above the head |
| `grafico` | Gráfico | a bar chart grows behind the person, a tag pops at the end |
| `chroma` | Site | the background becomes a web page and the person, smaller, slides into a corner |
| `orbita` | Órbita | cards (images or frames) circle the person: behind the head, then in front |
| `app` | App | the top half becomes an app window: thumbnails fall in, a command is typed; the person below |
| `saindo` | Saindo da tela | the video in a neon post frame; the head and hand break out of it |
| `revelacao` | Revelação | the picture shrinks into the preview of a dark editor, tasks ticking around it |
| `papel` | Recorte de papel | a kraft collage in stop motion, the person a sticker, cut-out letters |
| `rabisco` | Rabisco | a chalkboard, a trembling chalk outline around the person, doodles drawing themselves |
| `vertigem` | Vertigem | dolly zoom: the video's own background grows while the person keeps their size |

The editor knows four more names (`celular`, `checklist`, `zoomDigital`, `corteZoom`). The template
does not draw them as scenes (the first two exist as graphics, `references/graficos.md`):
`cenas_edit_data.py` refuses them with the list above.

## The path

1. **Pick the takes.** One effect per take, on the take whose speech carries the idea (the
   number, the before/after, the big word). The window is the take: `start` and `end` in
   seconds of the cut, from `helpers/tempo.py` (`tomadas_no_corte(edl)`: each take's `out` and
   `out + dur`), which knows speed, curves and the J-cut.
2. **Write the items** with the fields below. **Every text comes from what the person says in
   that take** (`takes_packed.md`, the caption phrase of the window): no invented numbers, no
   claims they did not make. No text has a default: an empty field draws nothing.
3. **Run the helper:** `uv run python -X utf8 helpers/cenas_edit_data.py <edit>`. It validates
   every item (an error names the field and nothing is written), cuts the person out of each
   window, measures them in the cut-out, computes where each thing goes (`layout`) and copies the
   backgrounds and images to `public/cenas/`. Exit 1 = read its `FALTA`/`AVISO`/`ERRO` lines.
   A project scaffolded with an older kit has template code that cannot draw the effects: the
   helper stops before cutting anything and names the files, and
   `uv run python -X utf8 helpers/atualizar_template.py <edit>` brings this kit's template
   code (the video's data and `CustomGraphics.tsx` stay). Then run the helper again.
4. **Render.** The first time, the whole video. After a change to effects that were already
   rendered, only their windows: `uv run python -X utf8 helpers/render_janelas.py <edit>
   --janelas <start>-<end>[,<start>-<end>...]` renders those frames (2 extra on each side),
   splices them into `out/render.mp4` by frame number and keeps its sound; then
   `mixar_final.py` as after a full render. A changed sound (soundtrack, sound effect) needs
   the full render.
5. **Check a still inside each window**, after the elements came in (about 2 s into the take):
   the person whole with no straight edge, the text readable against what is really behind it,
   nothing over the face. `cenas_edit_data.py` prints a warning when it had to leave something
   out.

Run the helper again after ANY change to an effect (window, text, zoom, a new item): the
positions depend on the texts and on the person, and an unchanged window reuses its cut-out and
its measurement, so the run costs seconds.

## The fields every effect has

| Field | Who writes it | What it is |
|---|---|---|
| `tipo` | agent | one of the types above |
| `start`, `end` | agent | the window on the cut, seconds; at least 0.3 s |
| `desligada` | editor | `true` = off |
| `texto` | editor | `{x, y}`: where the user dragged the movable block, frame px; absent = `layout` |
| `estilo` | editor | `fonte`, `peso`, `cor`, `tamanho` (a multiplier), `contorno`, `corContorno` |
| `zoom` | agent | 1 to 1.6: the person larger, around the top of the head (which stays put) |
| `matte`, `pessoa`, `layout` | `cenas_edit_data.py` | never by hand; rewritten on every run |

Inside an effect the camera of the cut does not act (no zoom steps, no face tracking): the
frame is the plain picture, plus the effect's own `zoom`.

## The types

Required fields in **bold**; the others have the default in parentheses. Instants (`at`,
`circuloAt`, `pequenoAt`, `giganteAt`, `manchetes[].at`) are seconds of the cut, inside the window.

### `fundo` — a new background

When the place the video was recorded does not match the message, or to set one take apart
(the turning point of a story, the offer). Coaching video recorded in the kitchen → studio
for the method; a product demo → dark background for the reveal.

- **`fundo`**: `fundos/<id>` (ready-made: `concreto`, `parede`, `kraft`, `lousa`, `estudio`,
  `neon`) or `midia/<file>` (an image the user sent, copied into `<edit>/midia/`).
- `escurecer` 0–0.6 (0.25): a dark veil that seats the person's light on the new background.
- `desfoque` 0–20 px (0); `aproximar` (true): a slow push-in; `sombra` (false): the person's
  shadow on the background.

```json
{"tipo": "fundo", "start": 58.73, "end": 62.30, "fundo": "fundos/estudio", "escurecer": 0.1}
```

### `vidro` — a frosted-glass word behind the head

For THE word of the video, once. A course on productivity → "FOCO"; a store on its best seller →
"ESGOTOU"; a SaaS on its pain → "GARGALO".

- **`palavra`**: 1 word, at most ~10 letters (it is fitted to `largura`; a long word gets smaller).
- `at` (start + 0.5): when it rises; `largura` (1000): the width it is fitted to.

```json
{"tipo": "vidro", "start": 71.23, "end": 74.43, "palavra": "GARGALO", "at": 71.6}
```

### `capa` — magazine cover

When the take presents someone or something as the subject of the moment: a case, a role, a
result. A personal brand → "MENTORA"; a gym → "TREINO"; a finance creator → "FINANCEIRO".

- **`nome`**: the cover's title, 1 word (it is stretched to 1010 px).
- `cor` (#b0101b); `topo`: up to 3 short lines across the top; `esquerda`, `direita`: up to 3
  pairs `[line, line]` each (a short uppercase line and an italic one); `selo`: a round seal
  just under the title, on the side without a list (1–2 short words; it wraps inside the circle).
- The right list ends before the Reels button column (x 930); see "Zona segura" in shortform.md.
- The side lines only go where the person is not. On a close-up with the body touching both
  edges there may be room on one side only: a list whose side has no room moves to the free
  side; with no room at all it stays out and the helper says so. Prefer ONE list of 2 pairs.

```json
{"tipo": "capa", "start": 52.63, "end": 56.63, "nome": "FINANCEIRO",
 "topo": ["EDIÇÃO 2026", "IA NO TRABALHO"], "esquerda": [["ANTES", "horas"], ["AGORA", "minutos"]], "selo": "ESPECIAL"}
```

### `mural` — newspaper headlines on a wall

When the person cites news, a study, a market fact, or a common belief to knock down. Each
clipping slams on its `at`, with a camera shake; a red pen circles one of them.

- **`manchetes`**: 1 to 4 `{"kicker", "t", "at"}`: `t` the headline (≤ 6 words), `kicker` the
  source or section in caps, `at` when it lands (cut seconds; spread them through the take).
- `circulo` (the last one): which headline gets the circle; `circuloAt` (end − 0.9).
- `fundo` (`fundos/parede`): the wall.

```json
{"tipo": "mural", "start": 33.0, "end": 36.43, "circulo": 0, "circuloAt": 35.4,
 "manchetes": [{"kicker": "S&P", "t": "Redução nas grandes empresas", "at": 33.3},
               {"kicker": "PEQUENAS E MÉDIAS", "t": "O impacto continua positivo", "at": 34.3}]}
```

### `parede` — a wall of photos

When the take talks about volume or history: many clients, many posts, years of work. An
e-commerce → product shots; a creator → their own posts; a consultant → client logos.

- `fotos`: up to 14 `{"src": "midia/<file>", "legenda"}` (the user's images). Without them the
  helper uses frames of the video itself, a square around the face from other moments.
- `pequeno` (the yellow tape) and `gigante` (the giant word, 1 word), `pequenoAt`, `giganteAt`
  (start + 2); `cada` (0.1 s between photos); `inicio` (0.15 s); `fundo` (`fundos/concreto`).
- `fundo: "video"`: the photos go on the video's OWN background. The person stays exactly where they
  are (no moving down for the giant word), the photos only take the places they do not cover, and
  there is no shadow. For a take where the place matters: a story told at home, a room full of memories.

```json
{"tipo": "parede", "start": 62.30, "end": 65.93, "pequeno": "CORTAR A", "gigante": "FOLHA", "giganteAt": 63.6}
```

### `grafico` — bars growing behind the person

When the take states growth or a comparison with numbers the person SAID. Sales by month, students
per class, a before/after in steps.

- **`valores`**: 2 to 12 numbers from 0 to 1 (the bar heights, relative); `rotulos`: one short
  label per bar; `etiqueta`: the tag (the number said, "66%", "3x"); `inicio` (0.2 s), `passo`
  (0.16 s between bars).
- On a close-up most bars hide behind the person (the end bars, the line and the tag stay). It
  reads best on a wider take.

```json
{"tipo": "grafico", "start": 15.67, "end": 19.70, "valores": [0.22, 0.4, 0.55, 0.66],
 "rotulos": ["2023", "2024", "2025", "2026"], "etiqueta": "66%"}
```

### `chroma` — the person on a web page (Site)

When the take points to an offer, a page, an app or a sign-up: the page behind becomes the call to
action and the person, smaller, stays in a corner.

- **`titulo`**: the headline (≤ 5 words); `frase`: one line under it; `botao`: the button;
  `marca` and `menu`: the top bar (both optional: without them there is no bar).
- `lado` (`direita`): the corner the person goes to; `entrada` (0.25 s): when they slide in;
  `escala` 0.45–0.85 (0.7).

```json
{"tipo": "chroma", "start": 47.97, "end": 52.63, "titulo": "Menos CRM, mais venda",
 "frase": "As horas preenchendo viram tempo vendendo.", "botao": "Quero isso"}
```

### `orbita` — cards circling the person

When the take shows several things at once (features, results, screens of a product, a portfolio):
cards orbit on a tilted ring, the back ones pass BEHIND the person and the front ones in front. Unlike
the other effects the picture stays as it is (the take's framing and zoom too); only the cards and the
person cut out over them are drawn.

- `cartoes`: 2–10 images of the project (`[{"src": "midia/<file>"}]`), prints and photos work best
  (they show at 300×210, cropped to fill). Without them, 6 frames of the video itself, cropped around
  the face.
- `titulo` (optional): one or two short lines, below the safe-zone line; `voltas` 0.25–3 (0.75): how
  many turns in the window.
- The ring's centre follows the person on screen; it reads best on a waist-up or wider take.

```json
{"tipo": "orbita", "start": 30.5, "end": 33.4, "titulo": "Tudo num lugar só",
 "cartoes": [{"src": "midia/print-editor.png"}, {"src": "midia/print-legenda.png"}, {"src": "midia/print-trilha.png"}]}
```

### `app` — inside an app window

When the take describes something happening on a screen: sending files, asking for something, a
workflow. The top half slides down as a light app window, pushing the picture below it.

- `zona`: the text of the drop area; `etiqueta`: a tag that pops ("4 CLIPES"); `comando`: what gets
  typed in the box, with the send button pressed at the end. All from the speech, and all optional.
- `fotos`: up to 4 `{"src": "midia/<file>"}`. Without them, 4 frames of the video itself.
- `digitaAt`, `digitaFimAt` (45 % and 85 % of the window): when the typing happens. It comes with the
  key sound in the final mix; `som: false` turns it off.

```json
{"tipo": "app", "start": 20.1, "end": 25.3, "zona": "Solte aqui", "etiqueta": "4 CLIPES", "comando": "edita pra mim"}
```

### `saindo` — breaking out of the frame

For a turning point or an "I got out of this" moment: the video sits in a post frame and the person
comes out through the top, with shards and a shake. Best on a take with the head well inside the frame.

- `titulo`: above the frame, 1 to 3 words; `cor` (`#c6ff3d`): border, grid and title; `at` (start + 0.4): when
  they break out.

```json
{"tipo": "saindo", "start": 40.2, "end": 43.0, "titulo": "SAI DO FEED", "at": 40.6}
```

### `revelacao` — the video becomes the preview of an editor

For showing the work behind the video. It needs no person (no cut-out, no measure), so it also works on a
screen recording. Do not use it on a take that depends on seeing the face: the picture ends small.

- `tarefas`: up to 6 short lines, ticked one by one as the window goes on; `at` (start + 0.25): when the
  camera starts pulling back. The colour is the Estilo accent.

```json
{"tipo": "revelacao", "start": 70.0, "end": 75.5, "tarefas": ["Transcrever", "Cortar silêncio", "Legenda", "Efeitos", "Música"]}
```

### `papel` — paper collage

For a lighter or more personal take. Everything moves in stop motion (15 frames per second), including
the person, who is a sticker with a thick white border.

- `frase`: cut-out letters, up to 2 lines (a line break in the text), about 12 letters per line (each letter
  has its own font and paper, so long sentences get small). The person moves down to clear it.

```json
{"tipo": "papel", "start": 12.0, "end": 15.2, "frase": "FEITO\nÀ MÃO"}
```

### `rabisco` — chalk doodles

For an idea being explained or a big claim. A chalk outline trembles around the person, a crown
draws itself on the head and doodles appear where the person is not (those that do not fit stay out, silently).

- `frase`: handwritten at the top, up to ~30 letters.

```json
{"tipo": "rabisco", "start": 30.0, "end": 34.0, "frase": "isso muda tudo"}
```

### `vertigem` — dolly zoom

For a shock or a question that hangs in the air. The background of the video itself, rebuilt without the
person from frames of the same take, grows slowly while the person keeps their size, in black and white
over dark red. It only works when the camera does not move in that take. Where the person never left, the
hole is filled and blurred: the darker colour and the rays hide it.

- `pergunta`: at the top, with a colour shake, up to ~20 letters; `cor` (`#8a0b16`): the background colour.

```json
{"tipo": "vertigem", "start": 50.0, "end": 53.5, "pergunta": "E AGORA?"}
```

## Rules

- **Short text.** The big text is 1 to 3 words (`palavra`, `nome`, `gigante`, `etiqueta`); a
  title at most 5. The viewer reads it in under a second.
- **One effect per take, and not every take.** Two or three effects in a 60 s video; the rest is
  the person talking.
- **Never on a take with a split screen, an insert, or the hook.** The effect redraws the whole
  frame and would hide them.
- **The person has to be in the frame.** When they leave it for a good part of the window
  (`pessoa.presenca` under 0.6) the helper warns: pick another take.
- **No text the person did not say.** Numbers, sources and results come from the speech.

## Limits (say them when the user asks why)

- **The light does not change.** The person keeps the light of the place they recorded in. Dark
  backgrounds and the `escurecer` veil hide it; a bright studio behind a person lit by a warm lamp
  shows it.
- **The edge.** Loose hair against a busy background and fast hands show at the edge. The cut-out
  of the effects takes the person's colour at the soft edge (`person_matte.py --cor misturada`),
  so the old background bleeds less; what the model takes for hair (a green shutter between hair
  strands) still shows.
- **Cost.** The cut-out runs on the CPU at 3 to 4.5 frames per second (a 3.5 s take: ~25 s) and
  takes ~20 MB per second of window in `public/`. The model downloads once (~15 MB).

## In the editor

The effects show on the Efeitos track of the Final view. The user turns them on and off, changes
the text, drags the block and changes the font and colour (`references/pelo-chat.md`, the `cena-`
tools). The Salvar brings those changes by `ref`; write them into `cenas[ref]`, run
`cenas_edit_data.py` and render.

The user can also CREATE effects there, on the take under the needle:

- **Efeitos → Fundo:** each card shows them cut out on the needle's frame over a background, with
  Escurecer and Desfoque. It comes in the Salvar as `nova: true`, without `ref`, with the take's
  window and `campos` (`fundo`, `escurecer`, `desfoque`).
- **Efeitos → Cenas** (since 0.3.6): one card per other type (Vidro, Capa, Mural, Parede, Gráfico,
  Site, Órbita, App, Saindo da tela, Revelação, Recorte de papel, Rabisco, Vertigem), each a sketch of
  the effect around the user cut out on the needle's frame, with the
  texts already taken from the take's speech (no AI: the longest word, the first words, chunks of
  up to 6 words for headlines, a number said for the chart tag). It comes as `nova: true` with the
  texts in `textos` (only the type's own: `palavra`; `nome`, `selo`; `pequeno`, `gigante`;
  `etiqueta`; `titulo`, `frase`, `botao`; `titulo`; `zona`, `etiqueta`, `comando`; `titulo`; `frase`;
  `frase`; `pergunta`) and the lists in `campos` (Mural `manchetes` with `at` spread in the window,
  `circulo`, `circuloAt`; Gráfico `valores`; Revelação `tarefas`; Parede `fundo: "video"` when the user ticks
  "Sobre o fundo do próprio vídeo"). The server checks it
  against this file's rules and writes it into `cenas[]` by itself, so the Baixar draws it with no
  agent at all.
- **`textoAuto: true`** marks texts the panel took from the speech and the user never touched. When
  the user presses "Pronto, Claude segue", improve those texts from the transcript (the word or
  headline that really carries the take) and remove the flag; an item without the flag has the
  user's own words, so never rewrite it. The flag also goes away by itself when the user edits the
  text later (editor and `editdata_aplicar.py`).

Either way: run `cenas_edit_data.py` and render, as for any effect.
