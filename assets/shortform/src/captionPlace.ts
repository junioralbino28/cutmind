/**
 * Where each caption phrase goes — one rule for all six caption styles.
 *
 * The user drags phrases on the phone editor ("Posição das frases"); the skill
 * turns that into `captions.positions` with helpers/caption_positions.py,
 * already on the cut.mp4 timeline:
 *
 *   "positions": {
 *     "all": {"x": 0.5, "y": 0.62},                     // every phrase without its own
 *     "phrases": [{"at": 12.48, "x": 0.5, "y": 0.3}]    // `at` = the phrase's first word
 *   }
 *
 * x and y are fractions of the frame and mark the CENTRE of the phrase block.
 * Order: the phrase's own spot → the spot for all → the split-screen seam
 * (`captions.windows`, now honoured by every style) → the style's own place.
 * What the user set always wins over what the layout would do on its own.
 */
import editData from '../public/edit-data.json';

export type Spot = {x: number; y: number};
type Positions = {all?: Spot | null; phrases?: {at: number; x: number; y: number}[]};
type Win = {start: number; end: number; paddingBottom: number};

const C = (editData as any).captions ?? {};
const P: Positions = C.positions ?? {};
const WINDOWS: Win[] = C.windows ?? [];

// A phrase owns the spot whose `at` falls inside it. `at` is the start of its
// first word, and a cue's bounds are rounded (to the ms, or to the frame for the
// karaoke) — so BOTH bounds take the same slack. With the slack only on the start,
// the next phrase's `at` (2.132) sits just under this phrase's rounded end (2.1333)
// and the spot lands on two phrases at once.
export function spotFor(startSec: number, endSec: number): Spot | null {
  const own = (P.phrases ?? []).find((p) => p.at >= startSec - 0.05 && p.at < endSec - 0.05);
  if (own) return {x: own.x, y: own.y};
  return P.all ?? null;
}

// The seam window up at this GLOBAL frame, as the karaoke's CaptionShell reads it:
// compared in frames, +1 for the split layout's VIDEO_LAG.
export function seamAt(frame: number, fps: number): number | null {
  const w = WINDOWS.find((x) => frame >= Math.round(x.start * fps) + 1 && frame < Math.round(x.end * fps) + 1);
  return w ? w.paddingBottom : null;
}

// A dragged phrase never leaves the frame: its centre is pulled in so a w×h block
// keeps MARGIN px from every edge (and sits centred if it is wider than that).
const MARGIN = 40;
export function spotCentre(spot: Spot, w: number, h: number, W: number, H: number): {x: number; y: number} {
  const x = w + 2 * MARGIN >= W ? W / 2 : Math.min(Math.max(spot.x * W, w / 2 + MARGIN), W - w / 2 - MARGIN);
  const y = h + 2 * MARGIN >= H ? H / 2 : Math.min(Math.max(spot.y * H, h / 2 + MARGIN), H - h / 2 - MARGIN);
  return {x, y};
}
