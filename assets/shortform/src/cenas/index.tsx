/**
 * Mount point of the effects that take the person off the background: edit-data.json `cenas[]`,
 * prepared by helpers/cenas_edit_data.py (matte, measured person and `layout` per item). Window =
 * start/end on the cut timeline shifted by VIDEO_LAG, so the effect changes on the same frame as
 * the picture, and the matte (frame 0 = start) plays on the window's clock.
 *
 * Drawn in the 1080x1920 frame the helper measured in, scaled to the composition. An item the
 * template does not draw yet (the editor knows 17 names), one switched off in the editor
 * (`desligada`) and one still without its matte are skipped: the plain cut shows there.
 */
import React from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import editData from '../../public/edit-data.json';
import {VIDEO_LAG} from '../videoLag';
import {Cena, CenaProps, H, W} from './comum';
import {FundoNovo} from './fundo';
import {Capa, Chroma, Grafico, Mural, Parede} from './fundoNovo';
import {Vidro} from './vidro';

// the types helpers/cenas.py validates (TIPOS there; tests/test_cenas_contrato.py keeps both equal)
export const TIPOS: Record<string, React.FC<CenaProps>> = {
  fundo: FundoNovo,
  vidro: Vidro,
  capa: Capa,
  mural: Mural,
  parede: Parede,
  grafico: Grafico,
  chroma: Chroma,
};

export const janelaDaCena = (c: Cena, fps: number): [number, number] => [
  Math.round(c.start * fps) + VIDEO_LAG,
  Math.round(c.end * fps) + VIDEO_LAG,
];

const avisados = new Set<string>();
const avisa = (msg: string) => {
  if (avisados.has(msg)) return;
  avisados.add(msg);
  console.warn(msg);
};

export const Cenas: React.FC = () => {
  const {fps, width} = useVideoConfig();
  const lista = ((editData as {cenas?: Cena[]}).cenas ?? []).filter((c) => !c.desligada);
  if (!lista.length) return null;
  return (
    <AbsoluteFill style={width === W ? undefined : {width: W, height: H, transform: `scale(${width / W})`, transformOrigin: '0 0'}}>
      {lista.map((c, i) => {
        const Comp = TIPOS[c.tipo];
        if (!Comp) {
          avisa(`cena ${c.tipo}: o template ainda não desenha esse tipo; ficou fora do vídeo`);
          return null;
        }
        if (!c.matte || !c.layout) {
          avisa(`cena ${c.tipo} em ${c.start}s: sem recorte; rode helpers/cenas_edit_data.py`);
          return null;
        }
        const [a, b] = janelaDaCena(c, fps);
        return (
          <Sequence key={i} from={a} durationInFrames={Math.max(1, b - a)} name={`cena ${c.tipo}`}>
            <Comp c={c} a={a} n={b - a} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
