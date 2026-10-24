/**
 * Fundo: the take gets a new background (a ready-made one of the kit or the user's own image)
 * and the person, cut out, stays in front. Data: `layout.fundo` (copied by the helper),
 * `escurecer` 0–0.6 (a dark veil that seats the person's light on it; 0.25), `desfoque` 0–20 px
 * (0), `aproximar` (a slow push-in, true) and `sombra` (the person's shadow on the background, false).
 */
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {CenaProps, Fundo, Recorte} from './comum';

export const FundoNovo: React.FC<CenaProps> = ({c, n}) => {
  const f = useCurrentFrame();
  const desfoque = Math.min(20, Math.max(0, Number(c.desfoque) || 0));
  // a blurred image darkens at its edges: the extra scale keeps them off screen
  const s = 1.02 + desfoque / 400 + (c.aproximar === false ? 0 : 0.04 * (f / Math.max(1, n)));
  const veu = Math.min(0.6, Math.max(0, c.escurecer ?? 0.25));
  return (
    <AbsoluteFill>
      <Fundo src={c.layout?.fundo} reserva="#111" style={{transform: `scale(${s.toFixed(4)})`, filter: desfoque ? `blur(${desfoque}px)` : undefined}} />
      <AbsoluteFill style={{backgroundColor: `rgba(0,0,0,${veu})`}} />
      {c.sombra ? <Recorte c={c} style={{filter: 'brightness(0) blur(16px)', opacity: 0.42, transform: 'translate(38px, 26px)'}} /> : null}
      <Recorte c={c} />
    </AbsoluteFill>
  );
};
