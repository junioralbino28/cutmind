# Animated graphics as data (`graficos[]`)

Motion graphics the template draws on top of the video, without redrawing the take (that is
`cenas[]`). They are data, not code: one item per graphic in
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
| `pula` | Texto que pula | the sentence word by word, each word jumping in when spoken, the one being said in the accent | the sentence itself is the point and the rhythm carries it |
| `partes` | Texto por partes | big lines entering one at a time, each on its word, leaving together | asks and answers ("IMPOSSÍVEL?" … "NÃO É.") |
| `danca` | Letras dançando | a title whose letters enter one by one and keep dancing | names the topic with energy |
| `glitch` | Glitch | a title breaking into shifted coloured slices, in bursts | says something broke, failed or changed abruptly |
| `marca` | Marca-texto | a white card with the sentence; a highlighter runs over the part that matters | states the one sentence to remember |
| `contador` | Contador | a number climbing to its value at `fimAt`, label under it | says a result, a price, an amount |
| `nome` | Nome e cargo | name and role coming in at the lower corner | the person introduces themselves or quotes someone |
| `chat` | Conversa | message bubbles, one at a time, the other side typing first | tells a conversation |
| `maquina` | Máquina de escrever | mono letters typed on a white sheet, with key sounds | a sentence to read slowly, a title |
| `prompt` | Prompt | a dark AI prompt box typing the request, with key sounds; the send button lights up | says what was asked of an AI |
| `emoji` | Emoji | emoji popping in, each on its word | a reaction, a light moment |

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
  each button, a whoosh on `objecao`, a typing sound during `comenta`. **`maquina` and `prompt` bring
  their key sounds by themselves**: the final mix plays `digitacao` from `digitaAt` to `digitaFimAt`,
  and it moves with the graphic. `som: false` on the item turns it off.
- **Texts that do not wrap** (`grande`, `palavras`, `danca`, `glitch`, `partes`, `contador`) must fit
  880 px: with Poppins 900 a word takes about 0.7 × `tamanho` per letter. The editor's panel reduces
  `tamanho` by itself; in the chat, you do.
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
  `cor?` (white), `contorno?` (`#111`). `troca?` + `trocaAt?`: the word struck at `riscoAt` is swapped
  for `troca` at `trocaAt`, landing in the accent ("word crossed out and replaced").
- **`objecao`**: `usuario` (e.g. `@quem_assiste`), `texto`, `quando?` ("agora"), `cinza?` (true:
  the picture goes black and white).
- **`lista`**: `titulo`, `itens: [{t, at}]` (up to 6; short items, ~22 characters), `icone?` (`x`, the
  default red X, or `check`, a green check, for what is right).
- **`selo`**: `src` (a logo in `public/`, white on transparent reads best), `fundo?` (`#101010`).
- **`ajuste`**: `titulo?` ("linha do tempo"), `src?` (a strip image for the clips; without it, accent
  gradients). The drag happens on its own in the first second.
- **`progresso`**: `titulo`, `fimAt` (when the bar is full and the green word pops), `fim`.
- **`comenta`**: `texto` (the keyword typed), `digitaAt`, `digitaFimAt` (typing span), `dmAt?` + `dm?`
  (the direct pill), `seta?: {x, y}` (where the arrow tip points, e.g. `{x: 820, y: 1380}`, toward
  the comments), `placeholder?`, `publicar?` (the UI words, Portuguese by default: translate them for
  a video in another language).
- **`celular`**: `src` (a screenshot in `public/`), `x?` (550), `w?` (300), `rot?` (7).
- **`pula`**: `itens: [{t, at}]`, ONE WORD per item (up to 12), each `at` on the word as spoken;
  `tamanho?` (92). The lines wrap by themselves.
- **`partes`**: `itens: [{t, at, cor?}]` (one line per item); `tamanho?` (130). Odd lines default to
  the accent. All leave at `end`.
- **`danca`**: `t`, `sub?` (a line under it), `at?`, `tamanho?` (150).
- **`glitch`**: `t`, `at?`, `tamanho?` (170).
- **`marca`**: `texto`, `frase?` (a part of `texto`; without it, the whole text is highlighted),
  `marcaAt`, `marcaFimAt` (the highlighter's run), `cor?` (accent at 50%).
- **`contador`**: `valor` (a number), `fimAt` (when it arrives), `inicio?` (0), `casas?` (0), `prefixo?`
  (`R$ `), `sufixo?` (`%`), `rotulo?` (a line under it), `tamanho?` (190), `local?` (`pt-BR`, the
  number format).
- **`nome`**: `nome`, `cargo?`. Its default place is low (y 1140), left of the button column.
- **`chat`**: `itens: [{t, at, lado?}]` (up to 6; the last 4 stay on screen). `lado`: `outro` (left,
  dark) or `eu` (right, accent); without it, they alternate starting from `outro`.
- **`maquina`**: `texto`, `digitaAt`, `digitaFimAt` (~0.05 s per letter), `som?`.
- **`prompt`**: `texto`, `titulo?` (`Claude`: the name of the AI on the card), `digitaAt`,
  `digitaFimAt` (~0.03 s per letter), `som?`.
- **`emoji`**: `itens: [{t, at, ate?, x?, y?}]`, `tamanho?` (190). Each stays until its `ate` or `end`;
  without `x`/`y`, they take places around the top of the frame.

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
edge), and change its texts (**Editar**) or turn it off (**Desligar**, `desligada: true`). The
Texto and Efeitos menus open **Gráficos**: one card per type, the texts prefilled from the speech
at the needle, each beat on the spoken word when the line starts with one, and the images of `selo`
and `celular` from the project's `midia/` (the Salvar copies them to `public/`). The Salvar writes
all of it straight into `edit-data.json` (`editdata_aplicar.py`), no agent turn, and the Baixar
renders it. **After a user-made graphic, you may improve its texts and move each beat onto the right
word when asked; its place on the timeline is the user's.**
