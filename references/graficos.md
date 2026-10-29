# Animated graphics as data (`graficos[]`)

Ten motion graphics the template draws on top of the video, without redrawing the take (that is
`cenas[]`). They came from a finished Reels and are data, not code: one item per graphic in
`edit-data.json` `graficos[]`, drawn by `assets/shortform/src/graficos/`. **Never** write a graphic
of these kinds in `CustomGraphics.tsx`: a graphic in code is invisible to the editor's timeline and
does not survive a re-cut.

| `tipo` | Name in the editor | What the viewer sees | Use it when the speech… |
|---|---|---|---|
| `palavras` | Palavras | one big word (or phrase) per beat, blurred in and settling; optional selection box around a word, optional pill with an icon | punches a list of words, the opening line, a brand name |
| `botoes` | Botões | accent pill buttons, one at a time, a cursor clicking each | names the actions of a product ("cortar", "legendar") |
| `grande` | Palavra grande | a huge word slams in and shakes; `riscoAt` strikes it in red; optional line above (`sub`) | states a number, a price, the one word to remember, or "not this" |
| `objecao` | Objeção | the picture goes black and white and a viewer's comment card pops | voices the viewer's doubt before answering it |
| `lista` | Lista | a dark card where each item enters with a red X | lists what is wrong with the alternative |
| `selo` | Selo | a logo (image from `public/`) on a dark seal | says the brand or product name |
| `ajuste` | Ajuste | a timeline card where a cursor drags a clip's edge | talks about trimming, adjusting by hand |
| `progresso` | Progresso | a bar fills and closes with a green word at `fimAt` | talks about learning, loading, getting done |
| `comenta` | Comenta | an Instagram-style comment box types the keyword, an arrow points down, a direct pill pops | is the CTA "comment X and I send you…" |
| `celular` | Celular | a screenshot (image from `public/`) inside a drawn phone sliding in | shows an app or a screen |

## The rules

- **Every item has a window**: `start`/`end`, in seconds of the cut (`segments.json`, the same clock
  as `inserts`). The beats inside are `at`, `ate` (until when a list item stays) or a field ending in
  `At` (`fimAt`, `digitaAt`, `digitaFimAt`, `dmAt`, `riscoAt`, `selecao.at`). Those are the ONLY
  names the re-cut (`remapear.py`) and the editor (moving a block) carry along: a time field with
  another name stays behind. Every beat must fall inside the window.
- **Land each beat on a word** of the cut transcript (`takes_packed.md` / `captions.json`): the word
  appears when it is said, never a beat early.
- **Texts come from what the person says.** No invented numbers or claims.
- **Colours follow the Estilo panel** (`hook.accent`). `cor` and `contorno` on a word are optional;
  without them, the default look.
- **Places**: every default sits below the Reels safe zone (y 240) and left of the button column
  (x 930) — see "Zona segura" in `shortform.md`. `y` moves a graphic vertically (frame px); keep it
  ≥ 300 for anything whose top is above its `y`, and a `seta` tip left of x 900.
- **Sound** is not in the template: put an SFX on each beat in the final mix
  (`mixar_final.py --sfx arquivo@segundo:volume`), e.g. a pop on each `palavras` item, a click on
  each button, a whoosh on `objecao`, a typing sound during `comenta`.
- One graphic at a time on screen; leave the face clear (they all sit in the upper zone).
- **Check before rendering**: `uv run python -X utf8 helpers/graficos.py <edit>` lists every missing
  field, beat outside its window, unknown icon and image missing from `public/`, and says when the
  project's template is older than the kit (then `atualizar_template.py <edit>`).

## Fields

`?` = optional. All items also take `y?` and `desligada?` (true = off, the editor's switch).

- **`palavras`**: `itens: [{t, at, ate?, cor?, contorno?, selecao?: {at, palavra}, pilula?}]`,
  `tamanho?` (140), `cor?` (`#111`, dark: on a dark picture pass `cor: "#fff"` or a `contorno`).
  Each item stays until its `ate`, the next item's `at`, or `end`. `selecao` draws the editor's
  selection box around `palavra` (one word of `t`) at `selecao.at`. `pilula: true` (or
  `{cor?, icone?}`) turns the item into a coloured pill with the AI spark (or another icon).
- **`botoes`**: `itens: [{t, icone?, at, ate?}]`. Icons: `rec`, `ia`, `corte`, `cenario`, `trilha`,
  `cc`, `check`, `play`, `mic`, `texto`, `raio`, `estrela`.
- **`grande`**: `t`, `at?` (when it slams; default `start`), `riscoAt?`, `sub?`, `tamanho?` (170),
  `cor?` (white), `contorno?` (`#111`).
- **`objecao`**: `usuario` (e.g. `@quem_assiste`), `texto`, `quando?` ("agora"), `cinza?` (true:
  the picture goes black and white).
- **`lista`**: `titulo`, `itens: [{t, at}]` (up to 6; short items, ~22 characters).
- **`selo`**: `src` (a logo in `public/`, white on transparent reads best), `fundo?` (`#101010`).
- **`ajuste`**: `titulo?` ("linha do tempo"), `src?` (a strip image for the clips; without it, accent
  gradients). The drag happens on its own in the first second.
- **`progresso`**: `titulo`, `fimAt` (when the bar is full and the green word pops), `fim`.
- **`comenta`**: `texto` (the keyword typed), `digitaAt`, `digitaFimAt` (typing span), `dmAt?` + `dm?`
  (the direct pill), `seta?: {x, y}` (where the arrow tip points, e.g. `{x: 820, y: 1380}`, toward
  the comments), `placeholder?`, `publicar?` (the UI words, Portuguese by default: translate them for
  a video in another language).
- **`celular`**: `src` (a screenshot in `public/`), `x?` (550), `w?` (300), `rot?` (7).

## Example (the CTA and an objection)

```json
"graficos": [
  {"tipo": "objecao", "start": 12.4, "end": 14.9, "usuario": "@quem_assiste",
   "texto": "Mas isso não deixa o vídeo com cara de IA?"},
  {"tipo": "comenta", "start": 30.1, "end": 35.2, "texto": "CUTMIND", "digitaAt": 30.5,
   "digitaFimAt": 31.4, "dmAt": 32.0, "dm": "te mando no direct", "seta": {"x": 820, "y": 1380}}
]
```

## In the editor

Each graphic is a block on the Final view's text track, named by its type and text. The user can
move it (every beat goes along) and trim it (beats outside the new window move to the nearest
edge). The Salvar writes it straight into `edit-data.json` (`editdata_aplicar.py`), no agent turn.
