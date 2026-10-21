/**
 * STACKED caption style — an alternative to the default single-line Karaoke.
 * Selected per-video with `captions.style: "stacked"` in edit-data.json.
 *
 * Look: words stacked vertically, tight, mixing per line — Poppins bold-italic
 * with a white→light-gray gradient, Poppins regular (smaller), Playfair serif
 * bold-italic in ORANGE #ff5200, Poppins bold. Emphasis words appear solo; some
 * get a hand-drawn green "pencil" ellipse. Words rise in one by one.
 *
 * Baked SFX (no Premiere): a click on every solo word, a scratch when a word is
 * circled — from public/sfx/caption-click.mp3 + caption-scratch.mp3.
 *
 * Data: ../public/caption-cues.json (helpers/caption_style.py). Immutable code,
 * data-driven — same contract as Main.tsx.
 */
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont as loadPoppins} from '@remotion/google-fonts/Poppins';
import {loadFont as loadPlayfair} from '@remotion/google-fonts/PlayfairDisplay';
import cues from '../public/caption-cues.json';
import editData from '../public/edit-data.json';
import {PencilOutline} from './PencilOutline';
import {seamAt, spotCentre, spotFor} from './captionPlace';

const poppins = loadPoppins('normal', {weights: ['400', '700', '800', '900']});
loadPoppins('italic', {weights: ['700', '900']});
const POPPINS = poppins.fontFamily;
const playfair = loadPlayfair('italic', {weights: ['700', '900']});
loadPlayfair('normal', {weights: ['700', '900']});
const PLAYFAIR = playfair.fontFamily;

const ORANGE = '#ff5200';
const WHITE_GRAD: React.CSSProperties = {
  backgroundImage: 'linear-gradient(180deg, #ffffff 0%, #ffffff 46%, #cfcfcf 100%)',
  WebkitBackgroundClip: 'text',
  backgroundClip: 'text',
  WebkitTextFillColor: 'transparent',
  color: 'transparent',
};
// 0=bold-italic, 1=regular(small), 2=serif-orange, 3=bold
const LINE_STYLES: React.CSSProperties[] = [
  {fontFamily: POPPINS, fontWeight: 900, fontStyle: 'italic', ...WHITE_GRAD},
  {fontFamily: POPPINS, fontWeight: 400, fontStyle: 'normal', ...WHITE_GRAD},
  {fontFamily: PLAYFAIR, fontWeight: 900, fontStyle: 'italic', color: ORANGE},
  {fontFamily: POPPINS, fontWeight: 800, fontStyle: 'normal', ...WHITE_GRAD},
];
const SHADOW = 'drop-shadow(0 5px 9px rgba(0,0,0,0.5))';
const SHADOW_STRONG =
  'drop-shadow(0 5px 10px rgba(0,0,0,0.55)) drop-shadow(0 2px 3px rgba(0,0,0,0.55))';

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const stripPunct = (t: string) => t.replace(/[.,!?;:…"'-]/g, '');
const fitFont = (text: string, base: number, avail = 900, factor = 0.59): number => {
  const n = Math.max(1, text.trim().length);
  const est = n * base * factor;
  return est > avail ? Math.floor(avail / (n * factor)) : base;
};

// -------- config (optional overrides in edit-data.json → captions) --------
type SfxCfg = {enabled?: boolean; clickVolume?: number; scratchVolume?: number};
type CapCfg = {stackedOffsetY?: number; fontScale?: number; sfx?: SfxCfg};
const CAP = ((editData as {captions?: CapCfg}).captions ?? {}) as CapCfg;
const OFFSET_Y = CAP.stackedOffsetY ?? 0.156; // fraction of height, below center
const FONT_SCALE = CAP.fontScale ?? 0.8;
const SFX = CAP.sfx ?? {};
const SFX_ON = SFX.enabled !== false;
const CLICK_VOL = SFX.clickVolume ?? 0.45;
const SCRATCH_VOL = SFX.scratchVolume ?? 0.16;

type Word = {text: string; fromMs: number; toMs: number};
type CueData = {
  i: number;
  startMs: number;
  endMs: number;
  preset: 'STACK_MIXED' | 'SOLO_BIG' | 'SOLO_OUTLINE';
  exit: 'blur_up' | 'abrupt';
  styleOffset: number;
  lineStyles?: number[];
  lineBoost?: boolean[];
  lineEmph?: boolean[];
  lines: Word[][];
};

// Rough size of a cue on screen — the same estimate fitFont sizes the lines with.
// Good enough to keep a dragged cue inside the frame; nothing else uses it.
function cueBox(cue: CueData, scale: number, avail: number): {w: number; h: number} {
  if (cue.preset !== 'STACK_MIXED') {
    const t = cue.lines[0][0].text;
    const size = fitFont(t, cue.preset === 'SOLO_BIG' ? 150 : 118, avail / scale, 0.6) * scale;
    return {w: Math.min(avail, t.length * size * 0.6), h: size * 1.12};
  }
  let w = 0;
  let h = 0;
  cue.lines.forEach((line, li) => {
    const text = line.map((x) => x.text).join(' ');
    const size = fitFont(text, 86, avail / scale, 0.58) * scale;
    w = Math.max(w, Math.min(avail, text.length * size * 0.58));
    h += size * (li === 0 ? 1.12 : 1.12 - 0.34);
  });
  return {w, h};
}

const Cue: React.FC<{cue: CueData; cueDurationFrames: number; fromFrame: number}> = ({cue, cueDurationFrames, fromFrame}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();

  const scale = (width / 1080) * FONT_SCALE;
  const avail = width - 180;
  const baseY = Math.round(height * OFFSET_Y);
  // the user's spot for this cue → the split seam → the style's own offset
  const spot = spotFor(cue.startMs / 1000, cue.endMs / 1000);
  const seam = spot ? null : seamAt(fromFrame + frame, fps);

  const ENTER = Math.max(3, Math.min(8, Math.floor(cueDurationFrames * 0.45)));
  const EXIT = Math.max(2, Math.min(7, Math.floor(cueDurationFrames * 0.35)));
  const lastLocalStart = Math.max(
    ...cue.lines.flat().map((w) => ((w.fromMs - cue.startMs) / 1000) * fps),
  );
  const exitStart = Math.max(
    cueDurationFrames - EXIT,
    Math.min(lastLocalStart + ENTER, cueDurationFrames - 2),
  );
  const exitProg = interpolate(frame, [exitStart, cueDurationFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  let cOpacity = 1;
  let cTranslateY = 0;
  let cBlur = 0;
  if (cue.exit === 'blur_up') {
    cOpacity = 1 - exitProg;
    cTranslateY = -55 * exitProg;
    cBlur = 14 * exitProg;
  } else {
    cOpacity = frame >= cueDurationFrames - 2 ? 0 : 1;
  }

  const wordAnim = (w: Word, strong: boolean) => {
    const localStart = ((w.fromMs - cue.startMs) / 1000) * fps;
    const enter = Math.max(2, Math.min(ENTER, Math.floor(exitStart - localStart - 1)));
    const p = interpolate(frame, [localStart, localStart + enter], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: easeOut,
    });
    const eb = (1 - p) * 5;
    return {
      opacity: p,
      translate: `0px ${interpolate(p, [0, 1], [46, 0])}px`,
      filter: `${eb > 0.3 ? `blur(${eb}px) ` : ''}${strong ? SHADOW_STRONG : SHADOW}`,
      localStart,
    };
  };

  let dx = 0;
  let dy = seam == null ? baseY : 0;
  if (spot) {
    const box = cueBox(cue, scale, avail);
    const c = spotCentre(spot, box.w, box.h, width, height);
    dx = c.x - width / 2;
    dy = c.y - height / 2;
  }
  const container: React.CSSProperties = {
    opacity: cOpacity,
    translate: `${dx}px ${dy + cTranslateY}px`,
    filter: cBlur > 0.25 ? `blur(${cBlur}px)` : undefined,
    textAlign: 'center',
  };

  let inner: React.ReactNode = null;
  if (cue.preset === 'STACK_MIXED') {
    inner = (
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        {cue.lines.map((line, li) => {
          const styleIdx = cue.lineStyles?.[li] ?? (li + cue.styleOffset) % LINE_STYLES.length;
          const ls = LINE_STYLES[styleIdx];
          const lineText = line.map((w) => w.text).join(' ');
          let size = fitFont(lineText, 86, avail / scale, 0.58);
          if (styleIdx === 1) size = Math.round(size * 0.72);
          if (styleIdx === 2) size = Math.round(size * 0.95);
          if (cue.lineEmph?.[li]) size = Math.round(size * 1.12);
          if (cue.lineBoost?.[li]) size = Math.round(size * 1.35);
          return (
            <div
              key={li}
              style={{
                fontSize: size * scale,
                letterSpacing: -1.5,
                lineHeight: 1.12,
                marginTop: li === 0 ? 0 : '-0.34em',
                whiteSpace: 'pre',
              }}
            >
              {line.map((w, wi) => {
                const a = wordAnim(w, styleIdx === 1);
                return (
                  <span
                    key={wi}
                    style={{
                      ...ls,
                      display: 'inline-block',
                      padding: '0 0.06em',
                      opacity: a.opacity,
                      translate: a.translate,
                      filter: a.filter,
                    }}
                  >
                    {w.text + (wi < line.length - 1 ? ' ' : '')}
                  </span>
                );
              })}
            </div>
          );
        })}
      </div>
    );
  } else if (cue.preset === 'SOLO_BIG') {
    const w = cue.lines[0][0];
    const a = wordAnim(w, false);
    inner = (
      <div
        style={{
          ...WHITE_GRAD,
          fontFamily: POPPINS,
          fontWeight: 900,
          fontStyle: 'italic',
          fontSize: fitFont(w.text, 150, avail / scale, 0.6) * scale,
          letterSpacing: -3,
          lineHeight: 1.12,
          padding: '0 0.14em',
          opacity: a.opacity,
          translate: a.translate,
          scale: String(interpolate(a.opacity, [0, 1], [0.88, 1])),
          filter: a.filter,
        }}
      >
        {w.text}
      </div>
    );
  } else {
    const w = cue.lines[0][0];
    const a = wordAnim(w, false);
    const oStart = a.localStart + 2;
    const oEnd = Math.min(oStart + 10, exitStart - 1, cueDurationFrames - 2);
    const outlineProg = interpolate(frame, [oStart, Math.max(oEnd, oStart + 3)], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    inner = (
      <div style={{position: 'relative', display: 'inline-block'}}>
        <PencilOutline progress={outlineProg} />
        <span
          style={{
            ...WHITE_GRAD,
            fontFamily: POPPINS,
            fontWeight: 900,
            fontSize: fitFont(w.text, 118, (avail - 80) / scale, 0.6) * scale,
            letterSpacing: -2,
            lineHeight: 1.12,
            padding: '0 0.1em',
            opacity: a.opacity,
            translate: a.translate,
            filter: a.filter,
            display: 'inline-block',
          }}
        >
          {w.text}
        </span>
      </div>
    );
  }

  // on the seam the stack stands on the karaoke's baseline and grows upward
  return (
    <AbsoluteFill
      style={
        seam == null
          ? {justifyContent: 'center', alignItems: 'center', padding: '0 90px'}
          : {justifyContent: 'flex-end', alignItems: 'center', padding: '0 90px', paddingBottom: seam}
      }
    >
      <div style={container}>{inner}</div>
    </AbsoluteFill>
  );
};

export const StackedCaptions: React.FC = () => {
  const {fps, durationInFrames} = useVideoConfig();
  const CUES = cues as unknown as CueData[];
  return (
    <AbsoluteFill>
      {CUES.map((cue) => {
        const from = Math.round((cue.startMs / 1000) * fps);
        const end = Math.round((cue.endMs / 1000) * fps);
        const dur = Math.max(2, Math.min(end, durationInFrames) - from);
        if (dur <= 0) return null;
        const isSolo = cue.preset === 'SOLO_BIG' || cue.preset === 'SOLO_OUTLINE';
        const isCircled = cue.preset === 'SOLO_OUTLINE';
        return (
          <Sequence key={cue.i} from={from} durationInFrames={dur} layout="none">
            <Cue cue={cue} cueDurationFrames={dur} fromFrame={from} />
            {SFX_ON && isSolo ? (
              <Audio src={staticFile('sfx/caption-click.mp3')} volume={CLICK_VOL} />
            ) : null}
            {SFX_ON && isCircled ? (
              <Sequence from={2} layout="none">
                <Audio src={staticFile('sfx/caption-scratch.mp3')} volume={SCRATCH_VOL} />
              </Sequence>
            ) : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
