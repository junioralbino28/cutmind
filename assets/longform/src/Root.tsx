import {Composition} from 'remotion';
import {Main} from './Main';
import {EfeitosBase, type EfeitosProps} from './EfeitosBase';
import editData from '../public/edit-data.json';

// Composition size/fps/duration come from edit-data.json — MATCH cut.mp4
// exactly (e.g. 1920×1080 @ 30, or 3840×2160 @ 23.976 → use the precise fps).
// EfeitosBase is driven by helpers/efeitos_render.py (filters and transitions
// from the editor); its size and length come from the props it passes.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Longform"
        component={Main}
        durationInFrames={Math.max(1, Math.round(editData.durationSec * editData.fps))}
        fps={editData.fps}
        width={editData.width}
        height={editData.height}
      />
      <Composition
        id="EfeitosBase"
        component={EfeitosBase}
        defaultProps={{largura: 1920, altura: 1080, receitas: []} as EfeitosProps}
        calculateMetadata={({props}) => ({
          durationInFrames: Math.max(1, props.receitas.length),
          width: props.largura,
          height: props.altura,
        })}
        durationInFrames={1}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
