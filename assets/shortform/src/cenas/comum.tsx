/**
 * Shared pieces of the effects that take the person off the background (`cenas[]` in
 * edit-data.json). An effect owns one window of the cut, usually one take, and redraws the
 * whole frame its own way: a new background, things on it, the person cut out in front.
 * Everything is drawn ABOVE the base video and BELOW the front texts, the hook and the
 * captions, so the captions stay readable over every effect.
 *
 * The camera of the cut does NOT act inside an effect: no zoom steps, no face tracking. The
 * frame is the plain 1080x1920 picture, so the positions helpers/cenas_edit_data.py measured
 * on the person matte (`pessoa`, `layout`) are screen positions as they are. `zoom` (1 to 1.6)
 * scales the person around the top of the head, which stays put.
 *
 * Clocks: inside an effect `useCurrentFrame()` is LOCAL (0 = window start). `a` is the
 * global frame the window starts on; spoken times (cut seconds) become local frames with
 * `local(sec, a, fps)`. The matte (`cena-<frame>-<frames>.mov`) starts on the window start,
 * so it plays on the local clock.
 */
import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, OffthreadVideo, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadPoppins} from '@remotion/google-fonts/Poppins';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadBebas} from '@remotion/google-fonts/BebasNeue';
import {loadFont as loadOswald} from '@remotion/google-fonts/Oswald';
import {loadFont as loadPlayfair} from '@remotion/google-fonts/PlayfairDisplay';
import {loadFont as loadCaveat} from '@remotion/google-fonts/Caveat';
import {loadFont as loadMarker} from '@remotion/google-fonts/PermanentMarker';
import {loadFont as loadElite} from '@remotion/google-fonts/SpecialElite';
import {loadFont as loadInstrument} from '@remotion/google-fonts/InstrumentSerif';
import {loadFont as loadAbril} from '@remotion/google-fonts/AbrilFatface';
import {loadFont as loadOldStd} from '@remotion/google-fonts/OldStandardTT';
import {VIDEO_LAG} from '../videoLag';
import {CATALOGO, familiaCss} from '../fontes';
import editData from '../../public/edit-data.json';

// The effects' own fonts load only when the video has effects: a video without `cenas`
// renders exactly as before, with no font to fetch.
const TEM_CENAS = (((editData as {cenas?: unknown[]}).cenas) ?? []).length > 0;
const L = {subsets: ['latin' as const]};
const carrega = (f: () => {fontFamily: string}, nome: string) => (TEM_CENAS ? f().fontFamily : nome);
export const FONTE = {
  poppins: carrega(() => loadPoppins('normal', {weights: ['400', '500', '600', '700', '800', '900'], ...L}), 'Poppins'),
  anton: carrega(() => loadAnton('normal', {weights: ['400'], ...L}), 'Anton'),
  bebas: carrega(() => loadBebas('normal', {weights: ['400'], ...L}), 'Bebas Neue'),
  oswald: carrega(() => loadOswald('normal', {weights: ['500', '700'], ...L}), 'Oswald'),
  playfair: carrega(() => loadPlayfair('normal', {weights: ['700', '900'], ...L}), 'Playfair Display'),
  caveat: carrega(() => loadCaveat('normal', {weights: ['600', '700'], ...L}), 'Caveat'),
  marker: carrega(() => loadMarker('normal', {weights: ['400'], ...L}), 'Permanent Marker'),
  elite: carrega(() => loadElite('normal', {weights: ['400'], ...L}), 'Special Elite'),
  instrument: carrega(() => loadInstrument('italic', {weights: ['400'], ...L}), 'Instrument Serif'),
  abril: carrega(() => loadAbril('normal', {weights: ['400'], ...L}), 'Abril Fatface'),
  oldstd: carrega(() => loadOldStd('normal', {weights: ['400', '700'], ...L}), 'Old Standard TT'),
};
if (TEM_CENAS) loadPlayfair('italic', {weights: ['700'], ...L});

/** The person in the matte, in frame px, already with the effect's `zoom` (cenas_edit_data.py). */
export type Pessoa = {x0: number; x1: number; topo: number; base: number; cabecaX: number; presenca: number};
export type Cena = {
  tipo: string;
  start: number; // window start on the cut timeline (s)
  end: number; // window end (s)
  desligada?: boolean;
  matte?: string; // person matte in public/, frame 0 = start
  pessoa?: Pessoa;
  layout?: any; // default positions per type, computed by helpers/cenas.py
  zoom?: number;
  texto?: {x: number; y: number} | null; // where the user dragged the block, frame px
  estilo?: any;
  [k: string]: any;
};
export type CenaProps = {c: Cena; a: number; n: number};

export const W = 1080;
export const H = 1920;
export const ACCENT = '#ff5200';

/** Centre of an effect's movable block (its text, card or page): edit-data `texto: {x, y}` in
 * frame pixels, which is what the user drags in the editor, or the `layout` default. The editor
 * mirrors each default (CENA_BLOCO in assets/preview/celular.js): change both. */
export const centro = (c: Cena, padrao: [number, number]): [number, number] => {
  const t = c.texto;
  return t && Number.isFinite(+t.x) && Number.isFinite(+t.y) ? [+t.x, +t.y] : padrao;
};

/** Weight each font is loaded with (FONTE): a switched font keeps a real weight, never a faux bold. */
const PESO: Record<string, number> = {
  poppins: 900, anton: 400, bebas: 400, oswald: 700, playfair: 900, caveat: 700, marker: 400, elite: 400, instrument: 400, abril: 400, oldstd: 700,
};
export type EstiloTexto = {fonte: string; cor: string; escala: number; contorno: number; corContorno: string};
/** Look of an effect's highlight text: edit-data `estilo: {fonte, cor, tamanho, contorno, corContorno}`
 * (the editor's Text panel) over the effect's own look. `tamanho` is a multiplier (1 = as designed),
 * `fonte` a key of FONTE or a family of the catalog (fontes.ts), `contorno` the outline in frame px.
 * The editor mirrors each default (CENA_ESTILO in assets/preview/celular.js): change both. */
export const estiloDe = (c: Cena, padrao: EstiloTexto) => {
  const e = c.estilo || {};
  const num = (v: any, lo: number, hi: number, d: number) => (v !== null && v !== '' && Number.isFinite(+v) ? Math.min(hi, Math.max(lo, +v)) : d);
  const legado = typeof e.fonte === 'string' && e.fonte in FONTE;
  const catalogo = !legado && typeof e.fonte === 'string' && e.fonte in CATALOGO;
  const fonte: string = legado || catalogo ? e.fonte : padrao.fonte;
  const contorno = num(e.contorno, 0, 60, padrao.contorno);
  const corContorno = typeof e.corContorno === 'string' && e.corContorno ? e.corContorno : padrao.corContorno;
  return {
    fonte,
    familia: catalogo ? familiaCss(fonte) : (FONTE as Record<string, string>)[fonte],
    peso: catalogo ? num(e.peso, 100, 900, CATALOGO[fonte].peso) : PESO[fonte] ?? 400,
    italico: (!catalogo && fonte === 'instrument' ? 'italic' : 'normal') as 'italic' | 'normal',
    cor: typeof e.cor === 'string' && e.cor ? e.cor : padrao.cor,
    escala: num(e.tamanho, 0.3, 3, padrao.escala),
    contorno,
    corContorno,
    /** CSS for HTML text: the outline drawn under the fill, like the SVG paint-order */
    traco: contorno > 0 ? {WebkitTextStroke: `${contorno}px ${corContorno}`, paintOrder: 'stroke fill' as const} : {},
  };
};

/** Spoken time (cut seconds) → local frame of a window that starts on global frame `a`. */
export const local = (sec: number, a: number, fps: number) => Math.round(sec * fps) + VIDEO_LAG - a;

export const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
export const ease = (f: number, f0: number, f1: number, e = Easing.out(Easing.cubic)) =>
  interpolate(f, [f0, f1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: e});

/** Spring 0→1 starting at local frame `de`. */
export const mola = (f: number, de: number, fps: number, cfg: {damping?: number; stiffness?: number; mass?: number} = {}) =>
  spring({frame: f - de, fps, config: {damping: 12, stiffness: 140, mass: 0.9, ...cfg}});

/** Decaying camera shake that starts at `de` and lasts `dur` frames. */
export const tremida = (f: number, de: number, dur = 8, amp = 16, seed = 'tremida') => {
  const t = f - de;
  if (t < 0 || t >= dur) return {x: 0, y: 0, r: 0};
  const k = 1 - t / dur;
  return {
    x: (random(`${seed}x${t}`) * 2 - 1) * amp * k,
    y: (random(`${seed}y${t}`) * 2 - 1) * amp * k,
    r: (random(`${seed}r${t}`) * 2 - 1) * 0.6 * k,
  };
};

/** Sum of several shakes (one per hit). */
export const tremidas = (f: number, hits: number[], dur = 8, amp = 16) =>
  hits.reduce(
    (acc, h, i) => {
      const s = tremida(f, h, dur, amp, `h${i}`);
      return {x: acc.x + s.x, y: acc.y + s.y, r: acc.r + s.r};
    },
    {x: 0, y: 0, r: 0},
  );

/** The effect's `zoom`: the picture scaled around the top of the head, which stays put. */
const zoomDe = (c: Cena): React.CSSProperties => {
  const z = Math.min(1.6, Math.max(1, Number(c.zoom) || 1));
  return z > 1 && c.pessoa ? {transform: `scale(${z})`, transformOrigin: `${c.pessoa.cabecaX}px ${c.pessoa.topo}px`} : {};
};

/** The person, cut out (the window's matte), at the effect's zoom. At 100 % or more the edges
 * where the original frame cut the body stay on the edges of the screen. */
export const Recorte: React.FC<{c: Cena; style?: React.CSSProperties}> = ({c, style}) =>
  c.matte ? (
    <AbsoluteFill style={style}>
      <AbsoluteFill style={zoomDe(c)}>
        <OffthreadVideo src={staticFile(c.matte)} transparent muted style={{width: '100%', height: '100%'}} />
      </AbsoluteFill>
    </AbsoluteFill>
  ) : null;

/** A silent copy of the plain picture for this window (same frame as the matte, same zoom). */
export const Base: React.FC<{c: Cena; a: number; style?: React.CSSProperties}> = ({c, a, style}) => (
  <AbsoluteFill style={style}>
    <AbsoluteFill style={zoomDe(c)}>
      <OffthreadVideo src={staticFile('cut.mp4')} trimBefore={Math.max(0, a - VIDEO_LAG)} muted style={{width: '100%', height: '100%'}} />
    </AbsoluteFill>
  </AbsoluteFill>
);

/** A background image from public/ (the helper copies it to cenas/), or `reserva` without one. */
export const Fundo: React.FC<{src?: string; reserva: string; style?: React.CSSProperties}> = ({src, reserva, style}) => (
  <AbsoluteFill style={{overflow: 'hidden', background: reserva}}>
    {src ? <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover', ...style}} /> : null}
  </AbsoluteFill>
);

export const useJanela = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return {f, fps};
};

/** SVG path drawn on like a pen: pathLength="1" + dashoffset 1→0. */
export const Traco: React.FC<{
  d: string;
  p: number;
  cor: string;
  w: number;
  filtro?: string;
  opacity?: number;
}> = ({d, p, cor, w, filtro, opacity = 1}) =>
  p <= 0 ? null : (
    <path
      d={d}
      pathLength={1}
      fill="none"
      stroke={cor}
      strokeWidth={w}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="1 1"
      strokeDashoffset={1 - clamp(p)}
      filter={filtro}
      opacity={opacity}
    />
  );
