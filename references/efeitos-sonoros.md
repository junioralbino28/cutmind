# Sound effects — the kit's library and where to find the viral ones

The kit ships ten sound effects it **synthesizes itself** (`helpers/efeitos_sonoros.py`, files in
`assets/sfx/`): no recording, no one's license, safe in a paid ad. They play the roles of the sounds
that show up most in Reels.

| `id` | Name | Use it for | Golpe | Suggested volume |
|---|---|---|---|---|
| `impacto` | Impacto | the big word or number that lands (`grande`) | 0 | 0.42 |
| `notificacao` | Notificação | a comment, a message, a direct popping (`objecao`, `comenta`) | 0 | 0.25 |
| `dinheiro` | Dinheiro | price, revenue, savings | 0 | 0.34 |
| `brilho` | Brilho mágico | AI, the transformation, before/after | 0 | 0.34 |
| `ding` | Ding | a right answer, an item entering a list | 0 | 0.27 |
| `whoosh` | Whoosh | a card or text passing by | **0.25** | 0.51 |
| `clique` | Clique | a button clicked, the cursor (`botoes`) | 0 | 1.0 |
| `pop` | Pop | each word that appears (`palavras`) | 0 | 0.55 |
| `risco` | Risco de disco | the objection, the "wait", a strike-through (`riscoAt`) | 0 | 0.37 |
| `digitacao` | Digitação | a comment being typed (`comenta`, from `digitaAt`) | 0 | 1.0 |

`listar` prints the same table from `assets/sfx/catalogo.json` (the source of truth).

## The rules

- **The hit is at the start of the file** (`golpe` 0): placed at second *t*, it sounds AT *t*. Put it
  on the frame of the event (the word appearing, the click, the strike), never "a bit before". The
  whoosh grows until its middle: start it at *t* − 0.25 so its peak lands on *t*.
- **Volume**: the catalog's `volume` puts every effect at the same level under the voice (measured on
  the 300 ms after the hit). Start there and go down, not up: an effect louder than the voice reads
  as a mistake.
- **One per beat.** Two effects on the same instant blur; ten in a row tire. In a 30 s Reels, 6–15
  effects is the range that reads as "edited", above that as noise.
- **Never on top of a word that matters**: a pop or a ding over the key word of the sentence eats it.

## How they get into the video

- **The user, in the editor**: Áudio → Efeitos sonoros → listen → **Usar**. It becomes an audio layer
  at the needle (`camadas.json`) with the suggested volume; the user moves and trims it like any layer.
- **The agent**:
  - as a layer (visible and editable in the editor):
    `uv run python -X utf8 helpers/efeitos_sonoros.py usar <edit> <id>` copies it to
    `<edit>/midia/sfx-<id>.mp3`; then add the layer to `camadas.json` (`references/shortform.md`,
    "Layers from the editor");
  - or only in the final mix: `mixar_final.py ... --sfx assets/sfx/<id>.mp3@<second>:<volume>`
    (repeatable; the second is on the FINAL video's clock). Faster, but the user does not see them
    in the editor.

## The viral ones (Taco Bell bong, Discord ping, meme sounds…)

They are not in the kit: they belong to brands, series and their authors. Tell the user where to
find them for their own videos:

- **Inside the app when posting** (Instagram, TikTok): the sound library and the trending audios.
  For a sound that must sync with the cut, prefer the file.
- **Sites, free and without credit**: [Pixabay — efeitos sonoros](https://pixabay.com/sound-effects/),
  [Mixkit — efeitos sonoros](https://mixkit.co/free-sound-effects/).
- **[Freesound](https://freesound.org/)**: the license is per sound — filter by CC0 (no credit);
  CC-BY needs credit in the description; CC-BY-NC can't go in an ad.
- **Meme buttons** ([Myinstants](https://www.myinstants.com/)): uploaded by users, no license behind
  them.

Brought in by the editor (Áudio → Do celular / Do computador) or sent in the chat, they are layers
like any other.

**Paid ad:** a brand or series sound (and any meme-site file) can get the ad rejected and the video
claimed. For an ad, use the kit's effects or the no-credit sites above.
