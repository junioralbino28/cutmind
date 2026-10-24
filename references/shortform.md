# SHORT-FORM track (Reels / TikTok / Shorts) — Phase 2 + 3 reference

Read this file when the video is vertical short-form and the Phase-1 cut is
approved. Everything here rides on the **data-driven template** at
`assets/shortform/` — the code is immutable; a video is described by ONE JSON.

## The style (the proven default)

- **Frame rate:** render at **30fps when the source is 30fps or higher** (natural
  motion, matches Instagram/TikTok/Shorts capture); only slower sources use 24.
  `render.py` picks this automatically for `cut.mp4` — then set `edit-data.json`
  `fps` to the SAME value as `cut.mp4` (ffprobe it) so the Remotion render matches.
- **Base:** 1080×1920 (fps per the rule above), `<OffthreadVideo src=cut.mp4>` with the **dynamic
  camera**, whose three parts are separate picks on the Estilo panel: hard zoom per
  cut segment (`zoomCuts`, ~1.10–1.22, cycles), slow push-in (`zoomAuto`,
  +0.04/segment), clamped eye-tracking (`tracking`, target upper third, never
  reveals an edge). `zoomCuts` is what makes a talking head feel edited — if the
  user turns everything off, say what they lose and build it anyway.
- **Visual hook (first ~4s):** static copywriting headline, **always two lines**
  with the size fitted to them (see "Headline styles"). On by default, but the
  Estilo panel offers "Nenhum" — respect it and set `hook.enabled: false`.
- **Captions:** six styles — three animated (**karaoke**, **stacked**, **scatter**)
  and three static (**simples**, **serifada**, **classica**) — plus "Nenhum",
  which is `captions.enabled: false` and no caption generation at all. The user already
  picked one on the Estilo panel; see the "Caption style" section.
  Karaoke: one line ≤3 words, words rise from below, Poppins Black, lower third,
  `measureText` fit into **SAFE_WIDTH 720** (~180px each side — clears
  Instagram/TikTok's right action rail; verified on a real screenshot). Never
  rely on `nowrap` alone.
- **Inserts (upper zone):** rounded-card + shadow motif synced to spoken nouns,
  slow Ken-Burns. Pexels for concrete objects; **bespoke motion graphics** when
  a word names something animatable (timeline for "cortes", typewriter sheet
  for "roteiro" — worked examples in `src/CustomGraphics.tsx`).
- **Zones:** inserts/graphics upper third, captions lower third, face clear.
  Minimalist; accent `#33e0a3`.
- **Audio:** whoosh ~0.09 on card entrances, pop ~0.12 on shapes, music ~0.0445,
  and ALWAYS a final loudnorm pass (voice+music+SFX summed will clip). The
  shared sfx pack (`public/sfx/`) also ships `click1`/`click2` (element pops) and
  `tictac` (clocks/countdowns) — trigger any at a local frame by wrapping
  `<Sfx src="click2.mp3" volume={0.7}/>` in a `<Sequence from={frame} layout="none">`.

## Workflow

**Read `<edit>/preview_style.json` first — it IS the brief.** The user chose it on
the Estilo panel at the end of Fase 1; every key maps to something here:

| Pick | What it means |
|---|---|
| `edit: "limpa"` | **the default** — NO split inserts, full frame throughout. See the "Limpa" section |
| `edit: "split" \| "split2"` | the split-screen variant below — every image insert uses it |
| `headline: "outline" \| "card" \| "realce" \| "misto"` | `hook.style` in edit-data.json |
| `headline: "none"` | **no headline at all** — `hook.enabled: false`. The template already gates on that flag, so nothing else changes |
| `captions: "karaoke" \| "stacked" \| "scatter" \| "simples" \| "serifada" \| "classica"` | `captions.style` in edit-data.json (+ the director step for stacked) |
| `captions: "none"` | **no captions at all** — `captions.enabled: false`. Skip `captions_for_remotion.py` too; nothing reads the file |
| `captionPositions` | where the user dragged the caption phrases on the phone → `caption_positions.py` writes `captions.positions`. See "Where each phrase sits" |
| `accent` (hex) | `hook.accent` + `captions.accent`. Only `realce`/`misto`/`stacked` paint it; `accentUsed:false` means the picked styles have none |
| `elements.tracking` | `face_track.py` + `track.json`; OFF → skip it, fixed frame |
| `elements.zoomAuto` | the slow push-in inside each segment (`+0.04/segment`) |
| `elements.zoomCuts` | the hard zoom change ON each cut (~1.10–1.22, cycles) |
| `elements.flashCut` | `transitions[]` in edit-data.json — see "Flash na transição" |
| `elements.musicAI` | Phase 3 via `treblo_music.py`; OFF → deliver with voice only |
| `modelo` (`{id, nome}`) | the user applied a saved style template (Estilo → Modelos). The picks above already ARE the template's. Its filter, transition, colour and soundtrack came in the `preview_edits.json` of the same Salvar (`efeitos`, `camadas`): apply that file too. `modelos.py mostrar <id>` shows the template |
| `legenda` (`{estilo, acompanhar}`) | the template's caption look → `captions.estilo` / `captions.acompanhar` in edit-data.json, the same as `editData.legenda` from a Salvar |
| `note` | free text — read it, it overrides the defaults above |

An unchecked box is an explicit NO, not a silence. Copy the picks into
`state.json` as `style` (`captionPositions` included: it is what the phone shows
when the user reopens Posição), clear `awaitingStyle`, delete `preview_style.json`.

1. **Scaffold (one command, never read the TSX):**
   ```bash
   cp -R <skill>/assets/shortform/. <edit>/remotion/ && cd <edit>/remotion && npm install
   ```
   Only for a NEW `remotion/`: run over an existing one, it overwrites the video's data in
   `public/` and the project's `CustomGraphics.tsx`. A project scaffolded with an older kit
   keeps that kit's template code, and what the kit gained since (the `cenas[]` effects, for
   one) silently stays out of the render: `atualizar_template.py <edit>` replaces only the
   immutable code (`src/` minus `CustomGraphics.tsx`, `scripts/`, the configs; `public/` is
   never touched), keeps the replaced files in `<edit>/.template-anterior/` and runs
   `npm install` when `package.json` changed. `cenas_edit_data.py` stops and says so when
   the project's template cannot draw the effects.
2. **Generate machine data into `remotion/public/`:**
   - `cp cut.mp4 remotion/public/` — or, when `<edit>/efeitos.json` has items,
     `uv run python -X utf8 helpers/efeitos_render.py <edit>` instead (it writes
     `public/cut.mp4` with the filters and transitions; "Effects from the editor")
   - `transcribe.py cut.mp4 --edit-dir <edit>` → `transcripts/cut.json`
     (cut times are already on the output timeline — never map the source EDL)
   - `captions_for_remotion.py --transcript transcripts/cut.json -o public/captions.json`
   - **Caption style** — from the Estilo panel pick. `stacked` ALSO needs
     `caption_style.py --transcript transcripts/cut.json -o public/caption-cues.json`
     plus `captions.style:"stacked"` (see the "Caption style" section).
   - `face_track.py cut.mp4 -o public/track.json` — **only when
     `elements.tracking` is on.** Off, the frame stays put — but the file must
     still EXIST: the template imports it statically and the bundle fails to
     build without it ("track.json doesn't exist" out of webpack, not a runtime
     warning). Write a neutral one instead: every point pinned to the camera
     target, so the follow has nothing to correct.
     ```bash
     python - <<'EOF'
     import json, pathlib
     ed = json.loads(pathlib.Path('public/edit-data.json').read_text())
     n = round(ed['durationSec'] * ed['fps'])
     tx, ty = ed['camera']['targetX'], ed['camera']['targetY']
     pathlib.Path('public/track.json').write_text(json.dumps(
         {"fps": ed['fps'], "width": ed['width'], "height": ed['height'],
          "count": n, "points": [[tx, ty]] * n, "neutral": True}))
     EOF
     ```
   - `public/segments.json` — cumulative cut boundaries **measured from the
     encoded segments' frame counts, never summed from the EDL's seconds**.
     **Regenerate it after EVERY Phase-1 re-render.** A stale segments.json is
     invisible: the render succeeds, the overlays look plausible, and every cut
     is off by a frame or three. Measured on this project after a re-grade — the
     file still carried EDL-summed times and drifted +1 frame by the 3rd cut and
     +3 by the 20th, while `VIDEO_LAG` quietly absorbed the first frame of it and
     made the error look fixed. The mechanism: ffmpeg quantises each segment to
     whole frames, so EDL arithmetic drifts a fraction of a frame per cut and the
     error ACCUMULATES. Anything that must land on a cut then sits visibly early.
     ```bash
     python - <<'EOF'
     import subprocess, glob, json, math, pathlib, sys
     # TWO assertions, because globbing a directory is only as good as the
     # directory. `_v.mp4` first: the J-cut writes video-only segments and a bare
     # glob also matches butt-join leftovers. Then check the COUNT against the EDL
     # and the SUM against cut.mp4 — a re-render with fewer ranges leaves the old
     # higher-numbered segments behind, and that gave segments.json 9.23s for a
     # 7.57s video. It renders clean and every overlay lands wrong.
     segs = sorted(glob.glob("clips_graded/seg_*_v.mp4")) or sorted(glob.glob("clips_graded/seg_*.mp4"))
     nranges = len(json.loads(pathlib.Path("edl.json").read_text())["ranges"])
     if len(segs) != nranges:
         sys.exit(f"{len(segs)} segments for {nranges} ranges — clips_graded is dirty")
     cum, t = [0], 0
     for f in segs:
         n = int(subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
             "-count_frames","-show_entries","stream=nb_read_frames",
             "-of","default=nw=1:nk=1",f], capture_output=True, text=True).stdout)
         t += n; cum.append(t)
     real = int(subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
         "-count_frames","-show_entries","stream=nb_read_frames",
         "-of","default=nw=1:nk=1","cut.mp4"], capture_output=True, text=True).stdout)
     if t != real:
         sys.exit(f"segments sum {t}f != cut.mp4 {real}f — do not ship this file")
     fps = 30  # match cut.mp4
     # videoLag: how many frames the picture trails the composition in Remotion —
     # the cut's VIDEO start time in frames, rounded UP (OffthreadVideo draws the
     # frame at or before frame/fps). 0 when the video starts at zero.
     st = float(subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
         "-show_entries","stream=start_time","-of","default=nw=1:nk=1","cut.mp4"],
         capture_output=True, text=True).stdout.strip() or 0)
     lag = max(0, math.ceil(st * fps - 1e-3))
     json.dump({"segments": [{"start": round(cum[i]/fps,4),
                              "dur": round((cum[i+1]-cum[i])/fps,4)}
                             for i in range(len(cum)-1)], "videoLag": lag},
               open("remotion/public/segments.json","w"), indent=2)
     EOF
     ```
   - **VERIFY segments.json against the picture — do not trust it.** `scdet`
     scores every frame by how much it differs from the one before, so a hard
     cut is a spike. The spike frame in `cut.mp4` must equal
     `round(segments[i].start * fps)`:
     ```bash
     ffmpeg -v info -i cut.mp4 -vf "select='between(n,344,358)',setpts=N/30/TB,scdet=threshold=0" \
       -an -f null - 2>&1 | grep scd.score
     ```
     In the RENDER the same cut lands `videoLag` frames later (segments.json,
     written above): 0 when cut.mp4's video starts at zero — what the kit's
     render.py writes — and 1 for cut.mp4 files whose video starts a fraction of
     a frame late (0.021s and 0.033s measured on older projects). Everything
     that must change with the picture adds it (`src/videoLag.ts`: zoom steps,
     split windows, the caption seam, mattes) and mixar_final.py delays the
     voice by it. Proof: cut spike at frame F in cut.mp4, at F+videoLag in the
     render, overlay window opening at F+videoLag. With the wrong value the
     camera zoom steps one frame after every cut — a double step that reads as
     a bad zoom.
   - `pexels_search.py "<query>" --out-dir public/pexels --count 3 --orientation portrait`
3. **Write `public/edit-data.json`** — the whole edit in one file (schema in
   `assets/shortform/README.md`): durationSec (exact ffprobe of cut.mp4),
   camera zooms, hook lines/logo/sign, captions config, inserts[], behind[],
   soundtrack (leave `enabled:false` until Phase 3).
4. **Verify with stills, batched:** `npx remotion still Reels --frame=<n> f.png`
   for the hook still (user approval), then ONE contact sheet for spot checks:
   `contact_sheet.py <render> --times t1 t2 t3 -o sheet.png` — one image, not N.
5. **Render:** `npx remotion render Reels out/render.mp4`, then loudnorm →
   `edit/final.mp4` (see Phase 3).

Never edit `src/Main.tsx`. Bespoke graphics go in `src/CustomGraphics.tsx`
(the ONE editable file — read it only when the video needs a custom graphic).

## Headline styles — always two lines

Four looks via `hook.style`, picked by the user on the Estilo panel: **`outline`**
(default, white + thick black stroke), **`card`** (dark rounded card, UPPERCASE,
optional logo row), **`realce`** (each line on a solid accent marker block),
**`misto`** (line 1 light white, line 2 heavy accent).

### The accent colour (`accent` in preview_style.json)

`realce`, `misto` and the `stacked` caption are the only things that paint an
accent; the default is `#ff5200`. The user picks it on the Estilo panel and it
arrives as a hex — set it on **`hook.accent`** and **`captions.accent`** in
edit-data.json so headline and caption stay the same colour. `preview_style.json`
also carries `accentUsed`: when it is `false`, the picked styles have no accent
and the colour is not a request to find somewhere to put one.

Hardcoding `#ff5200` anywhere in the template re-breaks this — the preview will
show the user's colour and the render will show orange, which is worse than not
offering the choice.

**Author `hook.text` as one plain sentence.** Whatever you write — `text`, or a
hand-broken `lines[]` — is joined and re-broken into exactly TWO lines balanced by
MEASURED width, then the size is fitted to the widest one. A third line shrinks
the type and costs the glance the headline exists to win.

- The break is measured, not counted: "É assim que vai" (4 words) and "ficar a sua
  headline" (3 words) are nearly the same width. Counting words breaks it wrong.
- **`fontSizePx` is a CEILING, not a fixed size.** As a hard override it defeats
  the whole feature: at a size the text cannot fit in, the line wraps and you are
  back to three lines. Measured, not guessed — the uppercase `card` style did
  exactly that at an inherited `fontSizePx: 66`.
- Per-style geometry (weights, cap, safeWidth, lineHeight, paddingTop) lives in
  `HL_STYLES` in `src/Main.tsx` **and is mirrored in the editor's `assets/preview/estilos.js`** so
  the Estilo panel shows the real break at the real size. Change one, change both.
- In a split layout, `paddingTop` still has to follow the seam — see the split
  section.

## Caption style — six of them

Three are animated (karaoke, stacked, scatter) and three are STATIC
(`simples`, `serifada`, `classica`) — no animation at all, a cue just replaces
the previous one. All three static ones live in `SimpleCaptions.tsx`, read
`captions.json` alone, and share one rule that is the whole point:

**Lines group by MEASURED WIDTH, capped at `maxWords` — never by word count.**
"inteligência" and "de" cannot obey the same rule: the long word takes the line
alone and the short ones ride together. A fixed 3-words-per-line gets this
backwards on every long word.

- `simples` — Poppins 600 at 66, squeezed to 0.9 on BOTH axes, one line, ≤3 words.
  Poppins ships no condensed cut, so this is a distorted regular: it thins the
  stems in both directions. If it ever reads too light, raise the weight to 700
  rather than compressing further.
- `serifada` — Libre Baskerville 700 at 67, same rules, no distortion.
- `classica` — Inter 500 at 42, TWO lines, classic subtitle. The split is width
  balance PLUS a penalty for ending a line on a short function word ("o", "de"),
  which a pure balance does constantly and no real subtitle ever does.
- **The horizontal squeeze changes the line grouping** (narrower glyphs → more
  words fit); the vertical one does not (grouping is measured on width). Worth
  knowing before "just squashing it a bit".
- All three sit at `bottom: 430`, the same band as the others. Lower than that
  and a 9:16 caption lands under the platform's own UI.
- **Over light clothing or a bright background the off-white text vanishes** — the
  soft shadow is all it has. `captions.strokePx` in edit-data.json adds a dark outline
  painted under the fill (only the outer half shows): **6** held over a white shirt
  and still read as the same style; 9 already looked heavy. Absent or 0 = no
  outline, the look the Estilo panel previews. Check a still over the lightest part
  of the frame before the full render.
- **The user's own font, colour, size and outline** (the captions' Text panel in the
  editor) arrive as `captions.estilo`: `fonte` (a family of `src/fontes.ts`) + `peso`,
  `cor`, `tamanho` (×), `contorno` (px, over `strokePx`), `corContorno`. The karaoke and
  the three static styles take all of it, and the grouping by width follows the new
  font and size (a narrower font fits more words per cue); `stacked` and `scatter` take
  only `tamanho` — their fonts and colours ARE the style. Absent = each style as drawn.
- **`captions.acompanhar: true`** moves the whole caption layer with the person: by how
  far the face (`public/rastreio.json` through the camera) is from where it usually sits
  on screen (the median), capped at ±160 px sideways and ±300 px up and down so the
  action rail stays clear. Every style follows, the hand-placed phrases included.

### karaoke (default), STACKED or SCATTER

Short-form ships two caption styles. **The user already picked one on the Estilo
tab**, where both previews run the real animation — do not ask again, just set
`captions.style` from `preview_style.json`. (`caption-styles/stacked.png` is
still there as a montage over real footage if a still is useful.)

- **`"karaoke"`** (default): one line ≤3 words, Poppins Black, lower third.
- **`"scatter"`** ("Disperso"): Lora serif, lowercase, off-white with a slight
  darkening toward the baseline, one word at a time in short ragged lines. Reads
  `captions.json` alone — no extra generation step. Ordinary words FADE only; one
  word per cue (the longest, ≥7 chars) resolves out of a heavy blur at 1.62× and
  dissolves back into blur on the way out. Tunables in `captions`:
  `scatterOffsetY` (block centre, default 0.72), `scatterFontSize` (58),
  `scatterSafeWidth` (820); `SPREAD` in the component caps how far a line wanders.
  Three things it took real footage to learn:
  - **Never `Math.random()`.** Remotion renders frames independently, so a true
    random re-rolls the layout every frame and the text shakes. Positions are
    hashed off the cue index.
  - **The middle of the frame is the FACE.** The reference look lives over B-roll;
    on a talking head the block belongs on the chest (`scatterOffsetY` 0.72).
    Raise it only when the shot behind is not a face.
  - **Motion on every word is motion on nothing.** Ordinary words used to drop in
    from above too, and at one word per ~200ms the screen read as frantic. The
    blur on the highlighted word only reads because everything else is still.
- **`"stacked"`**: words stacked tight, mixing per line — Poppins bold-italic
  (white→gray gradient) / Poppins regular (smaller) / Playfair serif bold-italic
  in ORANGE `#ff5200` / Poppins bold. Emphasis words appear solo; key ones get a
  hand-drawn green pencil ellipse. **Baked SFX** (no extra step, no Premiere): a
  **click** on every solo word, a **scratch** when a word is circled.

For stacked, the ONE extra data step is the director (reads the same cut
transcript as `captions_for_remotion.py`):
```bash
uv run python helpers/caption_style.py --transcript <edit>/transcripts/cut.json \
    -o remotion/public/caption-cues.json
```
Then set `captions.style:"stacked"` in edit-data.json (keep the other caption
fields — they stay valid). Defaults match the user-approved look: the stack sits
~15.6% of the height below center and SFX play from `public/sfx/caption-click.mp3`
+ `caption-scratch.mp3` (both already in the template). Optional overrides inside
`captions`: `stackedOffsetY` (0–1 of height), `fontScale`, and
`sfx:{enabled,clickVolume(0.45),scratchVolume(0.16)}`. The director groups words
into short cues, gives the orange serif accent to the content word (never a
connective), keeps 1-letter/short connectors from standing alone, and flags
solo/circled words. It is language-tuned for pt-BR (`--lang`); for other
languages it falls back to length heuristics.

A solo word also needs DURATION, not just weight — a word spoken in under
`MIN_SOLO_MS` (340ms) renders as a one-frame flash and reads as a glitch, so the
director folds it into a neighbouring stack instead. Fast connective speech hits
this often. After generating cues, sanity-check the plan (it prints a summary):
every non-`STACK_MIXED` cue should span ≥0.34s, and the word list across all
cues must match the transcript exactly, in order.

### Where each phrase sits (`captionPositions`)

On the phone the user can drag the caption over the video (Estilo → Legenda →
**Posição**), phrase by phrase, as each of the six styles groups its own phrases:
the drag moves only the phrase on screen; with **Todas** on, one drag moves every
phrase; **Padrão** sends it back to the style's place.

The save carries `captionPositions` in `preview_style.json`. Each phrase is
anchored on the SOURCE moment of its first word (`source` + `at`), so a later
re-cut does not shift it. Convert it to the cut timeline:

```bash
uv run python helpers/caption_positions.py --style <edit>/preview_style.json \
    --edl <edit>/edl.json --edit-data <edit>/remotion/public/edit-data.json
```

It writes `captions.positions` — `all` plus `phrases[]` with `at` in cut.mp4
seconds, x/y the block CENTRE as fractions of the frame — and lists every phrase
whose moment was cut out. Those fall back to the style's place; tell the user
which. **Re-run it after every Phase-1 re-render**, like `segments.json`: the
anchors survive a re-cut, the cut-timeline seconds do not. `--style` also takes
`state.json` (the copy under `style`).

Order, in every style: the phrase's own spot → the spot for all → the split seam
(`captions.windows`) → the style's own place. A dragged phrase is kept 40 px
inside the frame. Nothing to tune in the template: `captionPlace.ts` reads it.

## Visual hook — static headline, first ~4s (always on)

The first 1–2 seconds decide the swipe. Write `hook.lines` like a
social-media/copywriting/virality specialist, not a summarizer: read the cut
transcript, find the core promise/tension, and craft a scroll-stopper. Levers:
**curiosity gap · high stakes/bold claim · specificity/number · urgency ·
pattern interrupt**. Match the video's language; never clickbait it can't pay off.

**Two locked styles via `hook.style`** (both user-approved, encoded in the
template):
- **`"card"`** (default): Poppins Black white UPPERCASE on a dark-gray `#232326`
  rounded card, **every line the same font size (~54)** — never a big hero line +
  smaller kicker. Optional row above the card: real brand logo (rounded card,
  w300) + transparent symbol (drop-shadow, w128) — prefer real assets in
  `public/brand/` over drawn SVG; pick a symbol that frames the angle (danger,
  money, trophy…).
- **`"outline"`**: white text + thick black stroke (`WebkitTextStroke` +
  `paintOrder:'stroke fill'`), **no card**, **sentence-case** (write `lines[]`
  normally, not caps), sits lower (`paddingTop` ~330 — may overlap the top of the
  head, which is fine). The TikTok/MrBeast headline look. Tune `fontSizePx` (51),
  `strokePx` (7), `paddingTop` (330), `lineHeight` (1.06). Drop logo/sign.

Both are static hold, fade+rise at the edges, soft whoosh.

Example (Claude Fable video): "A IA MAIS / PERIGOSA DO MUNDO / ACABOU DE SER
LIBERADA". Draft 2–3 copy candidates in chat (text — no renders), let the user
pick, then render ONE still for design approval before the full render.

**De-conflict:** the hook owns the upper zone for its window — push any insert
that wants the same zone to after `hook.endSec` (e.g. move a 2.5s cutaway to
~4.1s).

## Flash na transição (`elements.flashCut`)

A light beam whips across the frame with a bloom and a dry click. Data-driven:
one entry per cut in `transitions[]`, `at` being the cut time **exactly as
segments.json states it** — `VIDEO_LAG` lines it up with the frame the picture
changes on, same as the split windows. Never index it off its own clock.

```json
"transitions": [{"at": 11.7}]
```

Default placement when the element is ON: **one per split-insert entry, not per
cut.** The video has ~27 cuts; a flash on each one stops reading as an accent and
starts reading as a strobe. Put it where the layout changes, which is where the
transition means something. Optional per entry: `intensity` (default 1), `sfx`,
`volume`.

- **The beam LEADS the cut by 2 frames.** Starting it on the cut frame reads as a
  flash after the fact — the eye sees the picture change, then the light. Leading
  it makes the light look like the cause.
- **Blur is what separates a beam from a wash.** At 26px it read as a general
  brightening; 16px reads as a beam. Raise opacity and lower blur together.
- **CHECK THE SFX FILE BEFORE TRUSTING IT.** The pack's `click2.mp3` peaks at
  −25 dB — it is inaudible under speech at any sane volume, and the mix looks
  fine while nothing is heard. `ffmpeg -i <sfx> -af volumedetect -f null -` is
  the check. `cut-click.mp3` (−2 dB, 57ms) is the one that reads.
- **And check WHERE the transient sits inside the file.** The source this click
  came from had 180ms of silence before the hit; delayed to the cut it would have
  landed 180ms late — after a 230ms effect had already finished. Trim the lead-in
  so the transient is at t=0, then delay by the cut time.
- **The delivered click is mixed by ffmpeg, not by Remotion.** The delivery
  re-mux discards Remotion's audio (it drifts), so add the SFX as another input
  with `adelay=<frame/fps*1000>`. The `<Sfx>` in the component only sounds in a
  plain `remotion render`.

## Style: "Limpa" (`edit: "limpa"`) — no split inserts

The whole frame stays on the speaker. **Leave `splitInserts` out of
`edit-data.json` entirely** (an empty array is fine; a populated one is not) and
skip the split director step. Everything else is unchanged — captions, hook,
zoom, tracking, soundtrack and behind-the-subject all still apply, and they are
where the edit gets its life when there is no art on screen.

Two consequences of the frame never being split, both easy to miss:

- **The hook keeps its full-frame padding.** `hook.paddingTop` is tuned per split
  layout (738 / ~920 for a seam that does not exist here). Under `limpa` the
  headline places against the frame, not a seam — start from the template default
  and render one still, rather than carrying a split value over.
- **`captions.windows` has nothing to dodge.** Those entries only exist to move
  the caption off a split seam. Leave the array empty; a stale window from a
  previous render shoves the caption up for no reason.

**This is the default** (`STYLE_CATALOG.edits[0]`), so it is also what a user who
never opens the Estilo panel gets. Split inserts are opted INTO, not out of. It is a
legitimate final look — a talking-head cut, images to be placed by hand later, or
simply no B-roll worth showing — not a placeholder.

## Style: "tela dividida" (split screen) — two variants

Both pin the FACE to a fixed region and give the rest of the frame to the image.
Data lives in `edit-data.json` `splitInserts[]` (`layout: "top" | "bottom"`); the
component is already in the template's `CustomGraphics.tsx`. Hard cut (no fade),
every window snapped to a take cut, consecutive images contiguous, and
`captions.windows` moves the caption to the seam while a window is up — any of
the six styles; a phrase the user placed by hand stays where it was put. Full
rules in `assets/shortform/README.md`.

`splitInserts[].src` accepts images and `.mp4`/`.mov`/`.webm` video. Each video
starts at frame zero of its own window and loops when necessary. Never use the
window's absolute timeline frame as the insert's `startFrom`; that seeks beyond
short clips and freezes them. The re-framed `cut.mp4` is the opposite: it receives
the window start as its offset so its local clock stays aligned with the global
talking-head picture.

| | **Tela dividida** (`top`) | **Tela dividida 2** (`bottom`) |
|---|---|---|
| Art | top band (750) | bottom band (750) |
| Head | raised underneath, `zoom 1.25 / focusY 400` | held high above, `zoom 1.0 / focusY 225` |
| Caption | ON the seam (`paddingBottom` 1074) | just ABOVE the seam (`paddingBottom` 790) |
| Seam gradient | yes — the caption sits over the art | **no** — it only greys the top of the photo |

**`focusY` is a SOURCE y that lands at the top of the video window** — a point
`y_src` renders at `(y_src - focusY) * zoom`. **Measure before trusting the
numbers:** pull a frame out of `cut.mp4`, read the hair-top and chin y, and set
`focusY` so the head lands where the user asked. The defaults fit a head ~660px
tall starting at y 455.

The two are opposites in one specific way, and it is the whole trick: the source
has a lot of headroom above the head. `top` has to zoom in to throw that headroom
away; `bottom` **keeps** it, and that is what puts the face under the frame edge
instead of in the middle. Swapping the zoom/focus pair between them breaks both.

**The hook does not transfer for free.** `hook.paddingTop` is tuned to the seam of
whichever layout is up: 738 for `top` (text on the seam under the art), ~920 for
`bottom` (text in the gap between chin and seam). Left at the `top` value, the
headline lands across the speaker's mouth. Render one hook still after switching.

## Behind-the-subject (element between person and background)

Puts an image or giant word(s) BEHIND the person. Great on medium/wide shots;
on tight close-ups anchor elements to the TOP (template already does). The cut-out
runs on ONNX Runtime, part of the base install; the model (~15 MB) downloads on
first use. For a whole new background, a magazine cover, a headline wall and the
other effects that redraw the take, use `cenas[]` instead (next section).

```bash
uv run python helpers/person_matte.py cut.mp4 -o remotion/public/fg_<name>.mov --start <s> --duration <d>
```

Then describe each window in `edit-data.json` `behind[]` (kind image/words,
matte file, start, dur, words with per-word `at` times). Gotchas the template
already encodes — do not re-learn them:
- ProRes 4444 `.mov` (libvpx silently drops alpha on some builds)
- source RGB composited with alpha, not RVM's `fgr` (halo otherwise)
- `<OffthreadVideo transparent>` or the matte renders opaque
- matte gets the same camera via `frameOffset` or the person drifts

Matte ONLY the windows you need — each file's frame 0 = its window start.

## Effects that take the person off the background (`cenas[]`)

Seven effects redraw a whole take with the person cut out in front: a new background
(`fundo`), a frosted-glass word (`vidro`), a magazine cover (`capa`), a headline wall
(`mural`), a wall of photos (`parede`), a growing chart (`grafico`) and a web page with the
person in a corner (`chroma`). Two or three per video, on the takes whose speech carries the
idea, with the texts taken from that speech. Write the items in `edit-data.json` `cenas[]`,
run `cenas_edit_data.py <edit>` (it cuts the person out of each window, measures them and
places everything around them) and render. Types, fields, examples and limits:
**`references/cenas.md`** — read it before the first effect.

## Illustrative images

Pexels for generic concepts (key: `PEXELS_API_KEY`). For brands/people/specific
things, **Wikimedia Commons first** (`wikimedia_images.py` — no key, clean
licensing, prints license+author), then `google_images.py` (needs
`GOOGLE_API_KEY`+`GOOGLE_CSE_ID`, mind rights — pass `--rights cc`, flag
licensing to the user for logos/celebrities). Keep photographer credits.

## Phase 3 — soundtrack (short-form)

Ask: **no soundtrack** (for Reels, TikTok and Shorts the music can go in inside the
app when posting), **a file of theirs** (free sites in `references/trilhas-gratis.md`;
relay that list) or **AI-generated** (Treblo). The kit hosts no music.

**From the kit library (only if it lists something).** `uv run python -X utf8 helpers/pacotes.py listar --tipo trilha
--busca <mood>` lists the soundtracks with mood (`calma`, `animada`…), length and name;
pick by the energy of the cut transcript, then:
```bash
uv run python -X utf8 helpers/pacotes.py camada <edit> <id> [--inicio 0]
```
It downloads the track once (local cache, sha256 checked), copies it to
`<edit>/midia/` and appends an audio layer marked `"trilha": "<id>"` to
`camadas.json`, from `--inicio` to the end of the track or of the video, at volume
**15%**. Library tracks are normalized to −14 LUFS, so 15% sits ~16 dB under the
voice (measured in the proof mix: −20.6 dB of the total). It is a layer like any
other: the user sees it on the phone (Áudio → Trilhas does the same thing there),
can move, trim or change its volume, and `mixar_final.py` mixes it ("Layers from the
editor") with a music fade: 0.4 s in, 1.5 s out. Do **not** also enable `soundtrack`
in edit-data for the same music — it would play twice. Library empty or no internet
(`erro: … não está no servidor de pacotes` / `sem conexão`) → fall back to Treblo or
a local file.

**Writing the Treblo prompt — derive it from the video's context, and ask for
MUSIC, not a texture.** Read the cut transcript: what's the topic, energy and
emotional arc? Then describe a real **composed instrumental piece** — name a
**genre + key instruments + tempo/BPM + mood**, and (optionally) a reference
artist/style. Match the content: a hype tech/AI reel wants upbeat modern
electronic with a catchy synth melody; a calm tutorial wants warm lo-fi keys; a
luxury/story piece wants cinematic strings. **Avoid SFX-y phrasing** ("bed",
bare "beat", "sound design", "drones", "risers") — that's what makes Treblo
return sound effects instead of a song. `treblo_music.py` auto-frames the vibe
as a composed instrumental and bans SFX/vocals, but the vibe you pass still has
to read musical.
```bash
uv run python helpers/treblo_music.py "upbeat modern electronic, catchy synth melody, warm analog bass, crisp light drums, ~110 BPM, bright and motivational" -o public/trilha.mp3 --length-min 30 --length-max 60
```
Then flip `soundtrack.enabled: true` in edit-data.json. **Volume:** start at
`0.0445`. This is the approved reference level: **−15 dB** from the former
`0.25` default (`0.25 × 10^(−15/20) ≈ 0.0445`). Confirm by listening, not just
by the meter, and only deviate when the source voice or composition clearly
demands it. Re-render. Finish with the mandatory loudnorm:

**Take the PICTURE from Remotion and the AUDIO from `cut.mp4`.** Remotion's own
audio track drifts against the source — measured on a 95s edit: the voice is
+90ms late by 8s and +660ms by 78s, i.e. it slides progressively out of lip sync,
unnoticeable at the start and obvious by the end. Its audio track also comes out
~0.7s longer than its video. So never re-encode Remotion's audio; re-mux the
approved master instead and mix the soundtrack here:

**Remotion's picture is FULL-RANGE and mis-tagged — never `-c:v copy` it.** Its
output is `yuvj420p`, `color_range=pc`, `color_primaries=bt470bg` (PAL!), transfer
unknown. Measured: luma 0–255 where `cut.mp4` sits at 16–235. Copying the stream
carries all of that into the delivery, so a compliant player shifts the hue off the
PAL primaries and a player that ignores the range tag crushes the blacks — the
Phase-1 grade the user approved drifts at the very last step. Convert the range and
stamp the tags. `setparams` is what makes them stick: the bare `-color_primaries` /
`-color_trc` output flags silently leave both `unknown` here.

```bash
VD=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 out/render.mp4)
FADE=$(python3 -c "print(f'{$VD-1.5:.3f}')")
ffmpeg -y -i out/render.mp4 -i ../cut.mp4 -i public/trilha.mp3 \
  -filter_complex "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,\
setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid];\
                   [1:a]adelay=33:all=1[v];\
                   [2:a]volume=0.0445,afade=t=in:st=0:d=0.4,afade=t=out:st=$FADE:d=1.5[m];\
                   [v][m]amix=inputs=2:duration=first:normalize=0[mix];\
                   [mix]loudnorm=I=-14:TP=-1:LRA=11[out]" \
  -map "[vid]" -map "[out]" -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 192k -ar 48000 -t "$VD" -movflags +faststart ../final.mp4
```

**Verify the delivery carries the same tags as the cut** — `bt709 / bt709 / bt709 /
tv`, exactly what left Phase 1:
```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=color_space,color_primaries,color_transfer,color_range \
  -of default=nw=1 ../final.mp4
```

**Keeping Remotion's audio is sometimes the right call — measure, don't assume.**
The re-mux above exists because Remotion's audio drifts, and on a 95s edit it does
(+660ms by 78s). But the `stacked` caption bakes a click on nearly every word plus
the flash clicks, and the re-mux throws all of that away — reconstructing ~20 SFX
by hand from the cue file is guesswork. Correlate first (15s+ windows, or the whole
clip when it is short): if the offset is CONSTANT across start/middle/end there is
no drift, and Remotion's own audio keeps the SFX with the sync intact. Measured on
a 7.6s edit: +42.7ms at the head, the tail and the whole — constant, and only ~10ms
from the picture's own +33ms lag. There, `-map 0:a` through the same loudnorm beats
the re-mux. Say which one you used and why.

`adelay` is the picture's lag in ms (`videoLag` frames, 33 per frame at 30fps;
`mixar_final.py` reads it from edit-data.json or segments.json): when cut.mp4's
video starts late, OffthreadVideo draws every frame one composition frame late,
the picture sits behind cut.mp4's timeline and the voice must follow it. With
`videoLag` 0 there is nothing to follow and the delay is zero.
`-t "$VD"` keeps the audio from outliving the video. **Verify** by correlating the
delivered voice against `cut.mp4` at three points — the offset must be CONSTANT
(≈+33ms). Use 15s windows: short windows lock onto the wrong syllable and report
a drift that is not there. Drop this re-mux ONLY if Phase 2 baked SFX into the
audio (stacked captions' click/scratch), and then verify sync by hand.

**A take with its own `volume` in `edl.json` (the phone editor's Volume) → use
`mixar_final.py`, not these hand re-muxes** (it works with no layers). The one-pass
`loudnorm` here is dynamic: it lifts a take the user lowered back up (measured on 21/10:
a take at 50% came back to 0.0 dB). `mixar_final.py` sees the volume and normalizes
linearly instead: it measures the mix, applies one fixed gain to −14 LUFS and a −1 dBFS
limiter, so every take keeps the level the user chose.

If the video has no soundtrack, the same shape without input 2:

```bash
ffmpeg -y -i out/render.mp4 -i ../cut.mp4 -filter_complex "[1:a]adelay=33:all=1,loudnorm=I=-14:TP=-1:LRA=11[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k -ar 48000 -t "$VD" -movflags +faststart ../final.mp4
```

Verify `max_volume ≤ -1 dB` (`-af volumedetect`). Copy to `edit/final.mp4`.

## Layers from the editor (`camadas.json`)

The user can put images, audio and texts on the timeline (editor: **Áudio** /
**Imagem** / **Texto**, with **Modelos** for two or three texts in mixed fonts at once;
`references/celular.md`). The project file is `<edit>/camadas.json`, times in
cut.mp4 seconds, schema in `helpers/camadas.py`; every save also carries it in
`preview_edits.json`, and `watch_edits.py` lists each item.

1. **Images and texts** → `uv run python -X utf8 helpers/camadas_edit_data.py <edit>`.
   Each visible image becomes an `inserts[]` card (the upper-zone card above, marked
   `"camada": <id>`) and is copied to `public/midia/camada-<id>.<ext>` — a name with
   no spaces or accents for `staticFile`. Only those inserts are touched, and they
   go last (on top, as in the editor). An image with `atras` becomes the big card
   behind the person instead (`behind[]`, marked the same way). Each visible text
   becomes a `textos[]` item, drawn by `src/CamadasTexto.tsx` exactly as the editor
   showed it: centre `x`/`y`, the Text panel's `estilo`, `curva` (an arc). For a text
   or image with `atras` the helper makes the person's cut-out of that window
   (`public/pessoa-<id>-<first frame>-<frames>.mov`, `person_matte.py`, ~30 s per 3 s
   on CPU); for a text with `acompanhar` (and for `captions.acompanhar`) it tracks the
   face into `public/rastreio.json` (`face_track.py`, its own file — the camera's
   `track.json` stays as it is). Both are redone when the window or `cut.mp4` change;
   `--sem-recorte` only prints the commands. Re-run after every save: hidden or deleted
   layers leave the edit-data. Then re-render. Something behind the person sits on the
   bare picture: a full-frame effect in the same window (split screen, a scene that
   redraws the frame) covers it — the editor warns when the user turns it on there.
2. **Sound** → `uv run python -X utf8 helpers/mixar_final.py <edit> --render out/render.mp4`
   replaces the hand-written re-mux above, same rules: picture range/tags fixed,
   voice from cut.mp4 with the 1-frame delay — left **out** when the user turned the
   video's sound off —, the soundtrack when enabled, then every audio layer that
   plays (trim `corte`/`duracao`, volume 0–200%, `melhorar` → the
   `melhorar_audio.py` chain: noise reduction + the voice chain), delayed like the
   voice so it stays where the user heard it. A layer marked `trilha` (library
   soundtrack) fades like music, 0.4 s in and 1.5 s out; the others keep 15 ms. Effects go in composition time with
   `--sfx <file>@<seconds>[:volume]`. Sum without normalizing, then loudnorm (linear
   when a take has its own `volume`, see above).
   `--base render` keeps Remotion's own audio (the stacked captions' SFX, see
   above) and only adds the layers; it refuses when the video's sound is off,
   because voice and SFX come mixed there. `--mostrar` prints the command. It
   prints the colour tags and the peak when done.
3. **Verify** like any delivery: a still inside each image and text window, the layer
   audible in its window, a silenced layer and a hidden image or text absent, and a
   text behind the person actually cut by the head.

**Same save re-cuts?** The layer times belong to the cut that was on screen. When
`preview_edits.json` also carries `edl`, map every `inicio` before step 1: find the
old range it falls in (old `edl.json`), its source time, and where that source time
lands in the new ranges; rewrite `camadas.json` with the new times. A layer whose
moment was cut out has nowhere to go — leave it out and tell the user.

The image card's whoosh is a Remotion `<Sfx>`: with the default `--base cut` it is
not in the delivery. Pass `--sfx <public>/sfx/whoosh.mp3@<start>:0.09` per image
when the card should sound.

## Effects from the editor (`efeitos.json`)

Filters and transitions come from the kit library (editor: **Efeitos → Filtros /
Transições**; `references/celular.md`). The project file is `<edit>/efeitos.json`,
times in cut.mp4 seconds, schema in `helpers/efeitos.py`: a filter covers
`inicio`…`inicio+duracao` with an optional `intensidade` (0–1, the package's own
when absent); a transition is centred on `corte`, the frame where two takes meet,
for `duracao`; an `ajuste` (the take's **Ajustar**: brilho, contraste, saturacao,
exposicao, temperatura, matiz, realces, sombras, vinheta, each −100…100) covers its
take like a filter, has no package (it is a shader inside `motor.js`), and one take
holds one. Every save also carries it in `preview_edits.json`.

```bash
uv run python -X utf8 helpers/efeitos_render.py <edit> [--remotion <edit>/remotion]
```

It replaces `cp cut.mp4 remotion/public/`, before the Phase 2 render, and runs again
after every save that touches `efeitos`. It draws each frame of each window with the
**same engine as the phone preview** (`assets/efeitos/motor.js`, through the
`EfeitosBase` composition of the Remotion project), in blocks of 90 frames, and
writes a new `public/cut.mp4`: the windows replaced, everything else re-encoded at
crf 8 (measured: PSNR 54 dB against the cut, ~0.3 luma level), sound copied. The
original `<edit>/cut.mp4` is never touched. With no items it just copies the cut.

Frame rules, shared with the preview: frame n is in an effect when
`start − 1 ms ≤ n/fps < end − 1 ms`. In a transition, `k = ⌊corte·fps + 0.5⌋`. Before
`k`, side A is frame n and side B is frozen on frame `k`. From `k` on, A is frozen on
`k−1` and B is frame n. A frame with several gets the transition first, then the
filter, then the ajuste.

Measured on the test cut, frame by frame, the phone preview against the final frame
is 0.5–1.0 level apart on average, while the effect itself is 25–100 levels against
the cut. Frames outside the windows only change by the re-encode.

**Same save re-cuts?** As with layers, the times belong to the cut on screen: map
them to the new cut before running it, and drop (and tell) an effect whose moment
was cut out.

---

## Melhorar voz (the video's own voice)

The editor's **Áudio → Melhorar voz** (and the tag on the audio track once something
is chosen) opens two dials, like Adobe Podcast's enhancer: **Voz**, from the voice
only cleaned (0) to a studio timbre (100), and **Fundo**, from the voice alone (0) to
the original room (100). Fundo 100 with Voz 0 is the original. The panel plays the
choice live over the video; **Pronto** keeps it in the draft and **Salvar** sends
`melhorar` (`{voz, fundo}` or `{desligar: true}`).

How it works (`helpers/melhorar_voz.py`, approved by ear on 23/10):
- **Prepare**, once per cut, from the cut's own sound (`<edit>/.melhorar/`): the clean
  voice (DeepFilterNet, a mask: same voice, same timing, noise removed), the room
  (original − clean), the studio timbre (Sidon fp32, generative) and five Voz steps.
  The steps mix only the MAGNITUDE of the spectrum (log interpolation) over the clean
  voice's phase; mixing waveforms sounds doubled. The editor's server runs it in a
  separate process when the panel opens (progress in `.melhorar/andamento.json`); from
  the chat `aplicar` prepares by itself. Cost on an i3: ~1.3 s per second of audio;
  peak memory ~3.9 GB with 12 GB of RAM or more (Sidon in 30 s pieces with 3 s of
  context), ~2 GB below that (15 s pieces). Models, ~1 GB, download once into
  `~/.cutmind/voz` (`CUTMIND_VOZ_DIR`), or ahead of time with `melhorar_voz.py baixar`.
- **Apply**: `melhorar_voz.py aplicar <edit> --voz N --fundo M` computes the exact
  mix (not the editor's blend of two steps), swaps only the sound of `cut.mp4` (same
  samples count, same timing, the kit's −14 LUFS) and of `remotion/public/cut.mp4`
  when that copy is of the same cut. With a final video, rebuild its sound:
  `mixar_final.py` takes the voice from `cut.mp4` (with `--base render`, re-render
  first: the voice then comes from Remotion's audio).
- **Remove**: `melhorar_voz.py restaurar <edit>` (the original stream, byte for byte).
- **State**: `melhorar_voz.py estado <edit>` prints JSON — `preparo` (`nenhum`,
  `preparando`, `pronto`, `velho` = the cut changed), `aplicado`, `escolha`,
  `reaplicar`. **A re-render of the cut brings the original sound back**: after
  `render.py`, `reaplicar: true` means run `aplicar <edit>` with no numbers.
- Limits: the editor previews up to 3 min of video (longer: the dials still work, the
  user just does not hear them first); `preparar` refuses past 10 min.

---

## Speed of the finished video (`velocidade.json`)

On the Final view the user selects everything (Ctrl+A or **Selecionar**) or a span
(dragging the empty part of the timeline; the orange edges adjust it) and changes its
**Velocidade** — CapCut's "select all and speed it up". It is applied to the video
that is already assembled, so picture, voice, captions, effects, layers and soundtrack
move together and nothing drifts. A take's own speed (the Corte view, `edl.json`) is a
different thing: it changes the cut, and whatever sits on the cut's clock must follow.

The project file is `<edit>/velocidade.json` (schema in `helpers/velocidade.py`):
`trechos` with `inicio`/`fim` in **final.mp4 seconds** and `fator` 0.25–4, plus
`duracao`, the final's length when the user marked them. Delivery:

1. `uv run python -X utf8 helpers/velocidade_final.py <edit>` — after `mixar_final.py`
   whenever the final is redone, and on its own when only the speed changed. It writes
   `final-entrega.mp4` (each span by `setpts` + `atempo`, one filtergraph so the audio
   stays continuous; atempo's own lead, 10–62 ms by factor, is measured and given back)
   and records `entregaVideo` in `state.json`: the editor's **Baixar** delivers that file
   when it is newer than the spans and the final. With no spans it removes both, and
   the final is the delivery again.
2. It **refuses** (exit 2) when the final's length differs from `duracao` by more than
   0.1 s: the cut was redone after the spans were marked, and they may sit on other
   words now. Carry each span to the new cut (as with layers) and write the new
   `duracao`, or clear them and say so; `--forcar` applies anyway.
3. **Verify** the reported length (`esperado` = what the spans promise) and watch a
   boundary: the voice keeps its pitch.

---

## The Estilo panel (between Fase 1 and Fase 2)

The cut is approved and nothing about the LOOK of Fase 2 is decided yet. **Do not
ask the style questions in chat** — set `"awaitingStyle": true` in `state.json`
and the UI opens its own tab, sitting between FASE 1 and FASE 2:

- **Tipo de edição** — `limpa` ("Limpa": no split inserts, full frame throughout —
  **the default**, and the right pick for a talking-head cut or when the user will
  place images by hand later), `split` ("Tela dividida"), `split2` ("Tela
  dividida 2").
- **Cor de destaque** — `accent`, a hex. Sits BEFORE the text styles, because it
  is what they paint with. One spectral swatch (the OS picker) plus a hex field,
  synced both ways — no preset row. Only `realce`/`misto` headlines and the
  `stacked` caption paint an accent, so the save also carries **`accentUsed`**;
  when it is `false` the picked styles have none and the colour is not an
  instruction to invent a place for one.
- **Estilo de headline** — `outline`, `card`, `realce`, `misto`. Always two
  lines, size fitted to the text (see the track reference).
- **Estilo de legenda** — three animated (`karaoke`, `stacked`/"Empilhado",
  `scatter`/"Disperso") and three static (`simples`, `serifada`, `classica`).
- **Elementos da edição** — checkboxes: `tracking` (movimento de tracking),
  `zoomAuto` (automação de zoom in), `zoomCuts` (zoom in/out nos cortes),
  `flashCut` (flash na transição), `musicAI` (trilha sonora com IA), plus a
  free-text observation field.
- **Modelos** — the look of a video kept under a name (`helpers/modelos.py`,
  `~/.cutmind/modelos`). The first card saves this video's look; every other card is
  a template drawn over this video's own frame, with its filter, colour, headline and
  caption. Tapping one previews it; Aplicar puts its filter and colour on every take,
  its transition on every cut and its soundtrack from start to end (the same Salvar),
  then saves the style with `modelo` and `legenda`.

Saving writes `<edit>/preview_style.json` (its OWN file — a style pick and a
timeline correction are different screens at different moments, and one shared
file would clobber the other) and `watch_edits.py` notifies you with the picks,
**what was left out**, and the observation. Then: build Fase 2 from exactly those
choices, **copy them into `state.json` as `style`**, clear `awaitingStyle`, and
delete `preview_style.json`.

Writing `style` back is not bookkeeping — it is what keeps the tab open. The tab
is enabled while `awaitingStyle` OR `style` is set, so the user can return, change
a caption style or tick one more element, and save again. That save arrives with
`"rerender": true` and the watcher says **REFAÇA a Fase 2** — re-render with the
new choices, don't treat it as a first pick. When the picks are exactly the ones the
video already has (Aplicar without changing anything, or a template equal to the video),
it says **SEM MUDANÇA** instead: delete `preview_style.json` and re-render nothing.

**The catalog lives in `STYLE_CATALOG` (`assets/preview/estilos.js`), not in a session.** A new editing
or caption style is one entry there plus its implementation in the track
reference; adding it in chat only, for one project, makes it invisible to every
other project. What is in it today is the **short-form** vocabulary (tela
dividida, karaokê/empilhado) — on a longform job the gate has nothing to offer
yet, so skip `awaitingStyle` and ask the layer questions in chat until longform
entries exist here.

---

## Anti-patterns (Fase 2/3)

These moved out of SKILL.md: they only bite after the phase gate, and the
skill prompt is resent every turn.

- Asking the style questions in chat, or starting Phase 2 before the pick lands.
  The gate screen exists so the user SEES what each style does — a chat list of
  names asks them to choose blind. Set `awaitingStyle` and wait for
  `preview_style.json`.
- Treating an unchecked element as "não pediu". It is an explicit NO: the user
  looked at "Movimento de tracking" and left it off. `watch_edits.py` prints the
  `fora:` line for exactly this reason.
- Hardcoding `#ff5200` (or any accent) in the template. The Estilo panel lets the
  user pick it, so a literal makes the preview show their colour and the render
  show orange — worse than not offering the choice. Feed `accent` into
  `hook.accent` + `captions.accent`.
- Changing a caption's look in the template without changing its preview in
  `estilos.js` (`buildKaraokeDemo` / `buildStackedDemo`). The gate's previews render
  the real faces, sizes and motion, scaled from 1080-wide — that is the whole
  reason the user can choose by looking. A preview that lies about the style is
  worse than no preview.
- Hardcoding a bespoke graphic's timings inside `CustomGraphics.tsx`. Put the
  windows in an `edit-data.json` array (a key the template ignores, e.g.
  `splitInserts`) and map over it — otherwise the graphic is invisible to the
  preview timeline and the user cannot see or retime it.
- Re-rendering Phase 1 without regenerating `segments.json`. Every Phase-2
  overlay that must land on a cut is indexed off that file; stale, it is off by
  frames and nothing errors. Worse, a `VIDEO_LAG`-style constant can absorb the
  first frame of the drift and make a broken file look correct at the one
  boundary you happen to check.
- Delivering Phase 2 with Remotion's own audio track — it drifts progressively against the source (+0.66s by 78s on a 95s edit). Re-mux `cut.mp4`'s audio and mix the soundtrack in ffmpeg (recipe in the track reference).
- Judging A/V sync with short correlation windows — speech is quasi-periodic and a 2–3s window happily locks onto the wrong syllable, inventing a drift. Use 15s+ windows, and remember a PARTIAL render cannot show drift that accumulates over the full timeline.
- Indexing Phase 2 off `Σ(end−start)` when a `jcut_timeline` exists — the J-cut output is shorter, so everything after the first take lands late.

---

## Helpers de Fase 2/3

- **`captions_for_remotion.py`** (karaoke JSON) · **`face_track.py`** (eye-track JSON) · **`person_matte.py`** (RVM alpha matte, ONNX Runtime; `--motor torch` and resnet50 need `uv sync --extra matting`) · **`cenas_edit_data.py`** (prepares `cenas[]`: cut-out, measurement, `layout`, backgrounds; `references/cenas.md`) · **`render_janelas.py`** (re-renders only some windows and splices them into `out/render.mp4`; then `mixar_final.py`) · **`atualizar_template.py`** (a project scaffolded with an older kit gets this kit's template code; `public/` and `CustomGraphics.tsx` stay) · **`pexels_search.py`** · **`wikimedia_images.py`** (no key, brands/people first choice) · **`google_images.py`** (fallback, mind rights) · **`pacotes.py`** (kit library: `listar --tipo trilha`, `camada <edit> <id>`, `abrir <id>`) · **`efeitos_render.py`** (filters and transitions from the editor into `public/cut.mp4`) · **`velocidade_final.py`** (the editor's speed spans on the finished video → `final-entrega.mp4`) · **`legenda_tempos.py`** (caption pieces the user dragged in time → `captions.json`) · **`captions_srt.py`** (longform .srt) · **`chapters.py`** (YouTube chapters) · **`treblo_music.py`** (AI soundtrack — pass a context-driven MUSICAL vibe: genre + instruments + tempo + mood, not SFX-y phrasing; auto-framed as a composed instrumental).

---

## Chaves opcionais (nunca pedidas na instalação)

Nada aqui é necessário para instalar ou para a Fase 1. Peça UMA chave só no
momento em que o recurso for de fato usado, explique para quê, e escreva em
`.env` na raiz da skill — nunca em `<videos_dir>`. Se o usuário não quiser, siga
pelo caminho sem chave e diga o que muda.

| Chave | Recurso | Sem ela |
|---|---|---|
| `PEXELS_API_KEY` | imagens/vídeos ilustrativos | Wikimedia Commons cobre a maioria |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | marcas, pessoas e logos específicos | Wikimedia é o fallback |
| `TREBLO_API_KEY` | trilha sonora composta por IA (Fase 3) | trilha só a partir de arquivo local |

### Como o usuário cria a chave do Treblo (trilha com IA)

Quando ele escolher `musicAI` e não houver `TREBLO_API_KEY`, dite estes passos —
são a interface real do site, não um resumo:

1. Acessar **https://treblo.com/** e fazer login.
2. Clicar no **perfil**, no canto superior direito.
3. Abrir a seção **Developers**.
4. Clicar em **Get Started for Free**.
5. Clicar em **API Keys**.
6. Clicar em **Create Key**, escrever o nome **CutMind** e confirmar em **Create**.
7. Copiar a chave e colar na conversa.

Ao receber a chave: escreva `TREBLO_API_KEY=<chave>` no `.env` da raiz da skill,
confirme em uma linha que gravou, e **nunca repita a chave de volta** na conversa
nem em saída de ferramenta. Se ele preferir não criar conta, siga com trilha de
arquivo local — a Fase 3 funciona assim, só não compõe.

A instalação não menciona nenhuma delas de propósito: o CutMind não precisa de
chave para funcionar, e listar chaves no primeiro contato faz parecer que precisa.
