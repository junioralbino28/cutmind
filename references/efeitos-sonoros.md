# Sound effects — the kit's own and the viral ones

Two groups, side by side in the editor (Áudio → Efeitos sonoros) and in `listar`:

- ten sound effects the kit **synthesizes itself** (`helpers/efeitos_sonoros.py`, files in
  `assets/sfx/`): no recording, no one's license, safe in a paid ad. They play the roles of the
  sounds that show up most in Reels;
- eleven **viral** ones (meme, brand, series), further down: what everybody uses, not for a paid ad.

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

## The viral ones (Taco Bell bong, Discord ping, cha-ching, Dexter, meme sounds…)

The sounds that show up in every Reels. The list ships with the kit (`assets/sfx/virais.json`); the
audio lives in a Release of the packages repository and downloads the first time someone listens or
uses one (checked by size and sha256, kept in `~/.cutmind/pacotes/sons`). Every id starts with `v-`.

| `id` | Name | Use it for | Golpe | Suggested volume |
|---|---|---|---|---|
| `v-cha-ching` | Cha-ching | price, a monthly fee, money in or out | 0.13 | 0.36 |
| `v-taco-bell` | Bong do Taco Bell | the punchline, the number that lands | 0.014 | 0.42 |
| `v-discord` | Notificação do Discord | a comment, a message, a direct arriving | 0.023 | 0.32 |
| `v-revelacao` | Revelação mágica | the background changing, AI at work, before/after | 0.008 | 0.23 |
| `v-ding` | Ding (viral) | a right answer, an item entering, the idea | 0.02 | 0.21 |
| `v-whoosh` | Whoosh (viral) | a card or text passing by | 0.049 | 0.19 |
| `v-clique` | Clique (viral) | a button clicked, the cursor | 0.01 | 0.2 |
| `v-core` | Core (TikTok) | the end of a block, the turn to the next one | 0.005 | 0.25 |
| `v-faah` | Faah (meme) | the scare, the mistake, the "uh-oh" | 0.164 | 0.28 |
| `v-dexter-curto` | Dexter (curto) | the objection, the "ok, but…" | 0.013 | 0.11 |
| `v-dexter` | Dexter (completo) | suspense, the doubt left hanging (10.6 s) | 0.013 | 0.13 |

- **Golpe**: a viral sound can breathe before its hit (the cha-ching's "cha", the faah's intake).
  Start it at *t* − `golpe`; the editor's **Usar** already does.
- **Volume**: these came from a mix approved by ear, converted to the trimmed files; start there.
- They are used exactly like the kit's: `usar <edit> <id>` (it downloads), then a layer or
  `mixar_final --sfx midia/sfx-<id>.mp3@<second>:<volume>`.
- **No connection**: the first use needs the internet; after that it plays from the cache.

**Paid ad:** a brand or series sound (and any meme-site file) can get the ad rejected and the video
claimed. For an ad, use the kit's own effects above. In an organic post they are what everybody uses.

### Others, for the user's own videos

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
