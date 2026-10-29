/**
 * Shared pieces of the animated graphics (`graficos[]` in edit-data.json): time helpers on the
 * cut's clock, the accent colour, the icon set, the cursor and the selection box.
 *
 * Every item has a window (`start`/`end`, cut seconds) and its inner instants are `at`, `ate` or a
 * field ending in `At` (`fimAt`, `digitaAt`, `riscoAt`...). helpers/remapear.py moves exactly those
 * on a re-cut and helpers/editdata_aplicar.py moves them with the block the user drags: a new time
 * field with any other name stays behind.
 */
import React from 'react';
import {Easing, interpolate} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import editData from '../../public/edit-data.json';
import {VIDEO_LAG} from '../videoLag';

export const {fontFamily: POPPINS} = loadFont('normal', {weights: ['400', '500', '600', '700', '800', '900']});

const D = editData as unknown as {hook?: {accent?: string}; captions?: {accent?: string}};
// the colour the user picked on the Estilo panel (hook.accent + captions.accent), never a literal
export const ACCENT = D.hook?.accent || D.captions?.accent || '#ff5200';
export const TINTA = '#1b0c00';
export const VERMELHO = '#FF3B30';
export const VERDE = '#22C55E';
export const CL = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** The frame of a cut second, shifted like the picture (VIDEO_LAG). */
export const quadro = (fps: number, s: number) => Math.round(s * fps) + VIDEO_LAG;
export const entra = (f: number, a: number, d = 6) => interpolate(f, [a, a + d], [0, 1], {...CL, easing: Easing.out(Easing.cubic)});
export const sai = (f: number, b: number, d = 5) => interpolate(f, [b - d, b], [1, 0], CL);
export const tremor = (f: number, a: number, forca = 12) => {
  const k = f - a;
  if (k < 0 || k > 9) return 0;
  return Math.sin(k * 2.3) * forca * (1 - k / 9);
};

/** `#rrggbb` + alpha → rgba(), for glows in the accent colour. */
export const comAlfa = (hex: string, a: number) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return `rgba(255,82,0,${a})`;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

/** An 8-point spark (a generic "AI" mark). */
export const Faisca: React.FC<{cor: string}> = ({cor}) => (
  <g stroke={cor} strokeWidth={2.6} strokeLinecap="round">
    {[0, 45, 90, 135, 180, 225, 270, 315].map((ang) => {
      const r = (ang * Math.PI) / 180;
      const r0 = ang % 90 === 0 ? 2.2 : 3;
      const r1 = ang % 90 === 0 ? 10.5 : 8.5;
      return <line key={ang} x1={12 + Math.cos(r) * r0} y1={12 + Math.sin(r) * r0} x2={12 + Math.cos(r) * r1} y2={12 + Math.sin(r) * r1} />;
    })}
  </g>
);

// the icons a button (`botoes`) or a pill can carry; an unknown name draws nothing
export const ICONES = ['rec', 'ia', 'corte', 'cenario', 'trilha', 'cc', 'check', 'play', 'mic', 'texto', 'raio', 'estrela'] as const;

export const Icone: React.FC<{nome?: string; px: number; cor?: string}> = ({nome, px, cor = 'white'}) => {
  const s = {fill: 'none', stroke: cor, strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round'} as const;
  if (nome === 'cc') return <div style={{fontWeight: 900, fontSize: px * 0.42, color: cor, letterSpacing: -1}}>CC</div>;
  return (
    <svg width={px * 0.62} height={px * 0.62} viewBox="0 0 24 24">
      {nome === 'rec' ? <circle cx={12} cy={12} r={7} fill={VERMELHO} /> : null}
      {nome === 'ia' ? <Faisca cor={cor} /> : null}
      {nome === 'corte' ? (
        <g {...s}>
          <circle cx={6} cy={6.5} r={3} />
          <circle cx={6} cy={17.5} r={3} />
          <path d="M8.5 8.2 L20 18 M8.5 15.8 L20 6" />
        </g>
      ) : null}
      {nome === 'cenario' ? (
        <g {...s}>
          <rect x={3} y={5} width={18} height={14} rx={2.5} />
          <path d="M3 16.5 L9 11 L13 15 L16 12.5 L21 17" />
          <circle cx={16.5} cy={9} r={1.6} />
        </g>
      ) : null}
      {nome === 'trilha' ? (
        <g {...s}>
          <path d="M9 18 V5.5 L20 3.5 V16" />
          <circle cx={6.5} cy={18} r={2.6} />
          <circle cx={17.5} cy={16} r={2.6} />
        </g>
      ) : null}
      {nome === 'check' ? <path d="M4.5 12.5 L10 18 L19.5 6.5" {...s} strokeWidth={3} /> : null}
      {nome === 'play' ? <path d="M8 5 L19 12 L8 19 Z" fill={cor} /> : null}
      {nome === 'mic' ? (
        <g {...s}>
          <rect x={9} y={3} width={6} height={11} rx={3} />
          <path d="M5.5 11 a6.5 6.5 0 0 0 13 0 M12 17.5 V21" />
        </g>
      ) : null}
      {nome === 'texto' ? <path d="M5 6 H19 M12 6 V19 M9 19 H15" {...s} strokeWidth={2.6} /> : null}
      {nome === 'raio' ? <path d="M13.5 2.5 L5 13.5 H11.5 L10.5 21.5 L19 10.5 H12.5 Z" fill={cor} /> : null}
      {nome === 'estrela' ? <path d="M12 3 L14.6 9 L21 9.4 L16 13.6 L17.6 20 L12 16.6 L6.4 20 L8 13.6 L3 9.4 L9.4 9 Z" fill={cor} /> : null}
    </svg>
  );
};

export const Cursor: React.FC<{x: number | string; y: number | string; apertado: boolean}> = ({x, y, apertado}) => (
  <svg width={74} height={74} viewBox="0 0 24 24" style={{position: 'absolute', left: x, top: y, scale: apertado ? '0.86' : '1', filter: 'drop-shadow(0 6px 10px rgba(0,0,0,.45))'}}>
    <path d="M4 2.5 L4 19 L8.6 14.8 L11.6 21.2 L14.6 19.8 L11.7 13.6 L18 13.4 Z" fill="white" stroke="#111" strokeWidth={1.4} strokeLinejoin="round" />
  </svg>
);

/** The selected-layer box of an editor (accent border, four handles), around a word. */
export const Selecao: React.FC<{f: number}> = ({f}) => {
  if (f < 0) return null;
  const k = entra(f, 0, 4);
  const alca = (pos: React.CSSProperties) => (
    <div style={{position: 'absolute', width: 26, height: 26, background: 'white', border: `5px solid ${ACCENT}`, borderRadius: 6, ...pos}} />
  );
  return (
    <div style={{position: 'absolute', left: -22, right: -22, top: -4, bottom: -10, border: `6px solid ${ACCENT}`, borderRadius: 10, opacity: k, scale: String(1.12 - 0.12 * k)}}>
      {alca({left: -16, top: -16})}
      {alca({right: -16, top: -16})}
      {alca({left: -16, bottom: -16})}
      {alca({right: -16, bottom: -16})}
    </div>
  );
};
