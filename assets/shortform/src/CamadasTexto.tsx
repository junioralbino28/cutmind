/**
 * TEXT LAYERS — the texts the user put on the timeline in the editor. DO NOT EDIT.
 *
 * Data: edit-data.json `textos[]`, written by helpers/camadas_edit_data.py from the
 * project's camadas.json, never by hand. Times in seconds on the cut timeline. Each text:
 *   - sits with its CENTRE on `x`/`y` (frame px), in the look of the editor's Text panel:
 *     `estilo.fonte` (a family of fontes.ts), `peso`, `cor`, `tamanho` (× 96 px),
 *     `contorno` (px) and `corContorno`. Nothing chosen = white Poppins, 96 px, no outline;
 *   - keeps its line breaks ("\n"), each line centred;
 *   - `curva` (−100 to 100) bends the line into an arc: 100 = half a circle arching over
 *     the centre, −100 = the same hanging under it (the lines are joined into one);
 *   - `matte` puts it BEHIND the person: the person's cut-out (person_matte.py, ProRes 4444,
 *     frame 0 = the text's start) is drawn back over it with the camera of the base picture;
 *   - `acompanhar` makes it FOLLOW the person: it moves as much as the face tracked in
 *     public/rastreio.json (face_track.py) moved on screen since the text came in.
 * The editor's preview draws the texts with these same numbers (assets/preview/celular.js).
 * A later text draws over an earlier one, like the layers in the editor.
 */
import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {measureText} from '@remotion/layout-utils';
import editData from '../public/edit-data.json';
import rastreio from '../public/rastreio.json';
import {CATALOGO, carregarFonte, familiaCss, useFontesProntas} from './fontes';
import {DynamicVideo, cameraAt} from './Main';
import {VIDEO_LAG} from './videoLag';

export type Texto = {
  id: string;
  texto: string;
  start: number;
  end: number;
  x: number;
  y: number;
  estilo?: {fonte?: string; peso?: number; cor?: string; tamanho?: number; contorno?: number; corContorno?: string};
  curva?: number;
  matte?: string;
  acompanhar?: boolean;
};

const TEXTOS: Texto[] = (editData as unknown as {textos?: Texto[]}).textos ?? [];
// [cx, cy] per frame of cut.mp4, 0..1 — empty when the person was not tracked
const PONTOS: [number, number][] = (rastreio as unknown as {points?: [number, number][]}).points ?? [];

export const TEXTO_PX = 96; // tamanho 1
export const TEXTO_LH = 1.1;
const PADRAO = {fonte: 'Poppins', cor: '#ffffff', corContorno: '#000000'};

const fonteDe = (t: Texto) => (t.estilo?.fonte && t.estilo.fonte in CATALOGO ? t.estilo.fonte : PADRAO.fonte);
const pesoDe = (t: Texto) => Number(t.estilo?.peso) || CATALOGO[fonteDe(t)].peso;
const curvaDe = (t: Texto) => Math.max(-100, Math.min(100, Number(t.curva) || 0));

// every family the texts use loads before the first frame, the default one too
for (const t of TEXTOS) carregarFonte(fonteDe(t), pesoDe(t));

// a curved text needs its width: it measures only after the fonts loaded (useFontesProntas)
const MEDE = TEXTOS.some((t) => curvaDe(t) !== 0);

/** The baseline arc of a curved text, in frame px. The line covers |curva|/100 of half a
 * circle, and its middle keeps the block's centre (x, y): the baseline runs 0.35 em below it. */
export const arcoDoTexto = (x: number, y: number, size: number, largura: number, curva: number) => {
  const theta = (Math.abs(curva) / 100) * Math.PI;
  const r = Math.max(1, largura) / theta;
  const meio = Math.min(Math.PI * 0.999, theta / 2 + 0.25); // the path runs a little past the line
  const by = y + size * 0.35;
  const sx = r * Math.sin(meio);
  const sy = r * (1 - Math.cos(meio));
  const grande = 2 * meio > Math.PI ? 1 : 0;
  // curva > 0: circle centre below, clockwise over the top; < 0: centre above, under the bottom
  return curva > 0
    ? `M ${x - sx} ${by + sy} A ${r} ${r} 0 ${grande} 1 ${x + sx} ${by + sy}`
    : `M ${x - sx} ${by - sy} A ${r} ${r} 0 ${grande} 0 ${x + sx} ${by - sy}`;
};

// where the tracked face is on screen at a GLOBAL frame: the picture shown there is cut.mp4's
// frame (g − VIDEO_LAG), drawn through the camera of frame g. The captions that follow the
// person (Main.tsx) use it too
export const rostoNaTela = (g: number, width: number, height: number, fps: number) => {
  if (!PONTOS.length) return null;
  const [cx, cy] = PONTOS[Math.max(0, Math.min(PONTOS.length - 1, g - VIDEO_LAG))];
  const {S, tx, ty} = cameraAt(g, width, height, fps);
  return [tx + cx * width * S, ty + cy * height * S] as const;
};

const traco = (px: number, cor: string): React.CSSProperties =>
  px > 0 ? {WebkitTextStroke: `${px}px ${cor}`, paintOrder: 'stroke fill'} : {};

const TextoEl: React.FC<{t: Texto; from: number; prontas: boolean}> = ({t, from, prontas}) => {
  const f = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const E = t.estilo ?? {};
  const fam = familiaCss(fonteDe(t));
  const peso = pesoDe(t);
  const size = TEXTO_PX * Math.max(0.2, Math.min(5, Number(E.tamanho) || 1));
  const cor = E.cor || PADRAO.cor;
  const contorno = Math.max(0, Number(E.contorno) || 0);
  const corContorno = E.corContorno || PADRAO.corContorno;
  let dx = 0;
  let dy = 0;
  if (t.acompanhar) {
    const a = rostoNaTela(from, width, height, fps);
    const b = rostoNaTela(from + f, width, height, fps);
    if (a && b) {
      dx = b[0] - a[0];
      dy = b[1] - a[1];
    }
  }
  const casca: React.CSSProperties = {translate: `${dx}px ${dy}px`, filter: 'drop-shadow(0 4px 14px rgba(0,0,0,0.45))'};
  const curva = curvaDe(t);

  if (curva !== 0) {
    if (!prontas) return null;
    const linha = t.texto.split('\n').map((s) => s.trim()).filter(Boolean).join(' ');
    const largura = measureText({text: linha, fontFamily: fam, fontSize: size, fontWeight: peso}).width;
    return (
      <AbsoluteFill style={casca}>
        <svg width={width} height={height} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
          <defs>
            <path id={`curva-${t.id}`} d={arcoDoTexto(t.x, t.y, size, largura, curva)} />
          </defs>
          <text
            fontFamily={fam}
            fontWeight={peso}
            fontSize={size}
            fill={cor}
            stroke={contorno > 0 ? corContorno : 'none'}
            strokeWidth={contorno}
            strokeLinejoin="round"
            paintOrder="stroke"
            textAnchor="middle"
          >
            <textPath href={`#curva-${t.id}`} startOffset="50%">
              {linha}
            </textPath>
          </text>
        </svg>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={casca}>
      <div
        style={{
          position: 'absolute',
          left: t.x,
          top: t.y,
          translate: '-50% -50%',
          whiteSpace: 'pre',
          textAlign: 'center',
          fontFamily: fam,
          fontWeight: peso,
          fontSize: size,
          lineHeight: TEXTO_LH,
          color: cor,
          ...traco(contorno, corContorno),
        }}
      >
        {t.texto}
      </div>
    </AbsoluteFill>
  );
};

// `atras`: only the texts behind the person (Main.tsx mounts this right over the bare
// picture); without it, the others, over the effects and under the hook and captions
export const CamadasTexto: React.FC<{atras?: boolean}> = ({atras = false}) => {
  const {fps} = useVideoConfig();
  const prontas = useFontesProntas(MEDE);
  return (
    <>
      {TEXTOS.map((t, i) => {
        if (Boolean(t.matte) !== atras) return null;
        // a text with the cut-out starts where the matte's frame 0 meets the picture
        const from = Math.round(t.start * fps) + (t.matte ? VIDEO_LAG : 0);
        const dur = Math.max(1, Math.round(t.end * fps) - Math.round(t.start * fps));
        return (
          <Sequence key={t.id || i} from={from} durationInFrames={dur} layout="none">
            <TextoEl t={t} from={from} prontas={prontas} />
            {t.matte ? <DynamicVideo src={t.matte} frameOffset={from} transparent muted /> : null}
          </Sequence>
        );
      })}
    </>
  );
};
