# Effects that take the person off the background (`cenas[]`)

Seven Phase-2 effects redraw one take of the short-form video: a new background, things on it,
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

The editor knows ten more names (`papel`, `rabisco`, `orbita`, `saindo`, `vertigem`, `app`,
`celular`, `checklist`, `revelacao`, `zoomDigital`, plus `corteZoom`). The template does not draw
them yet: `cenas_edit_data.py` refuses them with the list above.

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
4. **Render.**
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
| `tipo` | agent | one of the seven |
| `start`, `end` | agent | the window on the cut, seconds; at least 0.3 s |
| `desligada` | editor | `true` = off |
| `texto` | editor | `{x, y}`: where the user dragged the movable block, frame px; absent = `layout` |
| `estilo` | editor | `fonte`, `peso`, `cor`, `tamanho` (a multiplier), `contorno`, `corContorno` |
| `zoom` | agent | 1 to 1.6: the person larger, around the top of the head (which stays put) |
| `matte`, `pessoa`, `layout` | `cenas_edit_data.py` | never by hand; rewritten on every run |

Inside an effect the camera of the cut does not act (no zoom steps, no face tracking): the
frame is the plain picture, plus the effect's own `zoom`.

## The seven types

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
  pairs `[line, line]` each (a short uppercase line and an italic one); `selo`: the corner ribbon.
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
