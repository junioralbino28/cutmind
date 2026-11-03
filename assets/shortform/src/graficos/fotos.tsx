/**
 * The photo graphics of `graficos[]` (references/graficos.md): a polaroid with a handwritten caption,
 * the white flash of a camera and the closing card with the call to action. Same rules as index.tsx.
 * The camera click goes in the final mix (sons_entrada.py puts one on each photo).
 */
import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, staticFile} from 'remotion';
import editData from '../../public/edit-data.json';
import {carregarFonte, familiaCss} from '../fontes';
import {ZONA_SEGURA} from '../zonaSegura';
import {ACCENT, Base, CL, POPPINS, TINTA, comAlfa, entra, quadro, sai, useJanela} from './comum';

const TOPO = ZONA_SEGURA.topo;
const MANUSCRITA = 'Caveat';

export type GraficoFoto = Base &
  (
    | {tipo: 'polaroide'; src: string; legenda?: string; x?: number; w?: number; h?: number; rot?: number; alfinete?: string; flash?: boolean}
    | {tipo: 'flash'}
    | {tipo: 'cta'; frase: string; botao?: string; src?: string}
  );
type De<T extends GraficoFoto['tipo']> = Extract<GraficoFoto, {tipo: T}>;

// the font only downloads when a video has a captioned polaroid
const PEDE_MANUSCRITA = ((editData as unknown as {graficos?: GraficoFoto[]}).graficos ?? []).some((g) => g?.tipo === 'polaroide' && g.legenda);
if (PEDE_MANUSCRITA) carregarFonte(MANUSCRITA, 700);

/** A white radial flash of 7 frames, starting 1 frame before `a` so it covers the photo coming in. */
const Clarao: React.FC<{f: number; a: number}> = ({f, a}) => {
  const k = interpolate(f, [a - 1, a, a + 1, a + 6], [0, 0.85, 1, 0], CL);
  if (k <= 0) return null;
  return <AbsoluteFill style={{background: 'radial-gradient(circle at 50% 42%, rgba(255,255,255,1) 0%, rgba(255,255,255,.92) 45%, rgba(255,255,255,.55) 100%)', opacity: k}} />;
};

// ---- a polaroid dropping in, tilted, with a caption and an optional pin; a flash takes it unless `flash: false`
export const Polaroide: React.FC<{g: De<'polaroide'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a - 1 || f >= b) return null;
  const w = g.w ?? 620;
  const h = g.h ?? w;
  const borda = w * 0.05;
  const pe = g.legenda ? w * 0.18 : borda;
  const m = spring({frame: f - a, fps, config: {damping: 13, stiffness: 210, mass: 0.7}});
  const rot = g.rot ?? -3;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {f >= a ? (
        <div style={{position: 'absolute', left: g.x ?? 500, top: g.y ?? TOPO + 60, translate: '-50% 0', width: w + 2 * borda, boxSizing: 'border-box', padding: `${borda}px ${borda}px 0`, background: '#fbf8f1', borderRadius: 4, boxShadow: '0 26px 54px rgba(0,0,0,.5), 0 4px 10px rgba(0,0,0,.28)', rotate: `${rot + (1 - m) * rot * 2.2}deg`, scale: String(1.18 - 0.18 * m), opacity: Math.min(1, m * 2) * sai(f, b, 4)}}>
          {g.alfinete ? <div style={{position: 'absolute', top: -w * 0.03, left: '50%', width: w * 0.07, height: w * 0.07, marginLeft: -w * 0.035, borderRadius: 999, background: `radial-gradient(circle at 34% 32%, rgba(255,255,255,.85) 0 14%, ${g.alfinete} 38%, rgba(0,0,0,.55) 100%)`, boxShadow: '0 8px 8px rgba(0,0,0,.38)'}} /> : null}
          <Img src={staticFile(g.src)} style={{display: 'block', width: w, height: h, objectFit: 'cover'}} />
          <div style={{height: pe, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: familiaCss(MANUSCRITA), fontWeight: 700, fontSize: w * 0.085, lineHeight: 1, color: '#14233a', whiteSpace: 'nowrap', overflow: 'hidden'}}>{g.legenda ?? ''}</div>
        </div>
      ) : null}
      {g.flash === false ? null : <Clarao f={f} a={a} />}
    </AbsoluteFill>
  );
};

// ---- only the flash, for a photo or a cut that is already there
export const Flash: React.FC<{g: De<'flash'>}> = ({g}) => {
  const {f, a} = useJanela(g);
  return <Clarao f={f} a={a} />;
};

// ---- the closing card: the picture goes dark, with the logo, the sentence and the button
export const Cta: React.FC<{g: De<'cta'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const k = entra(f, a, 8);
  const m = spring({frame: f - a - 4, fps, config: {damping: 13, stiffness: 180, mass: 0.7}});
  const bt = spring({frame: f - a - 12, fps, config: {damping: 11, stiffness: 200, mass: 0.6}});
  const pulso = 1 + 0.025 * Math.sin((f - a) * 0.22);
  return (
    <AbsoluteFill style={{pointerEvents: 'none', opacity: sai(f, b, 5)}}>
      <AbsoluteFill style={{background: 'rgba(8,8,12,.62)', backdropFilter: 'blur(14px)', opacity: k}} />
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 360, width: 860, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 44, fontFamily: POPPINS, textAlign: 'center', scale: String(0.92 + 0.08 * m), opacity: Math.min(1, m * 1.5), translate: `0px ${(1 - m) * 30}px`}}>
        {g.src ? <Img src={staticFile(g.src)} style={{height: 170, maxWidth: 620, objectFit: 'contain', display: 'block'}} /> : null}
        <div style={{fontWeight: 800, fontSize: 76, lineHeight: 1.14, letterSpacing: -1.5, color: 'white', textShadow: '0 6px 24px rgba(0,0,0,.45)'}}>{g.frase}</div>
        {g.botao ? (
          <div style={{background: ACCENT, color: TINTA, fontWeight: 800, fontSize: 56, letterSpacing: -0.5, lineHeight: 1, borderRadius: 999, padding: '28px 62px 32px', boxShadow: `0 0 0 8px ${comAlfa(ACCENT, 0.2)}, 0 0 70px ${comAlfa(ACCENT, 0.55)}`, scale: String((0.6 + 0.4 * bt) * pulso), opacity: Math.min(1, bt * 1.6)}}>
            {g.botao}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
