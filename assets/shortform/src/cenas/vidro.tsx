/**
 * Letra de vidro: the picture turns icy, bubbles rise, and one word of frosted glass stands up
 * behind the person (only the foot of the letters hides behind the head). Data: `palavra`, `at`
 * (cut seconds, when it rises), `largura` (the width the word is fitted to, 1000); `layout.y` (the
 * centre of the word) and `layout.tamanho` come from the helper.
 */
import React from 'react';
import {AbsoluteFill, Easing, interpolate, random} from 'remotion';
import {Base, CenaProps, H, Recorte, W, centro, clamp, ease, estiloDe, local, useJanela} from './comum';

const Bolhas: React.FC<{f: number}> = ({f}) => (
  <>
    {Array.from({length: 16}, (_, i) => {
      const r = 10 + random(`br${i}`) * 26;
      const vel = 3 + random(`bv${i}`) * 5;
      const x0 = random(`bx${i}`) * W;
      const y = H + 80 - ((f * vel + random(`bp${i}`) * H) % (H + 160));
      const x = x0 + Math.sin(f * 0.07 + i) * 18;
      return (
        <div
          key={i}
          style={{
            position: 'absolute', left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: 999,
            background: 'radial-gradient(circle at 34% 30%, rgba(255,255,255,.95) 0 10%, rgba(255,255,255,.18) 34%, rgba(190,225,255,.10) 70%, rgba(255,255,255,.35) 100%)',
            border: '1.5px solid rgba(255,255,255,.55)', boxShadow: '0 4px 12px rgba(40,90,140,.18)',
          }}
        />
      );
    })}
  </>
);

export const Vidro: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const at = local(c.at ?? c.start + 0.5, a, fps);
  const p = ease(f, at, at + 18, Easing.out(Easing.cubic));
  // the glass has no fill colour: the style picks font, size and the outline that draws the letters
  const est = estiloDe(c, {fonte: 'poppins', cor: '#ffffff', escala: 1, contorno: 6, corContorno: 'rgba(255,255,255,.98)'});
  const size = (c.layout?.tamanho ?? 300) * est.escala;
  const largura = (c.largura ?? 1000) * est.escala;
  const [vx, vy] = centro(c, [W / 2, c.layout?.y ?? 700]);
  const baseline = vy + size * 0.36;
  const brilho = interpolate(f, [at + 20, at + 44], [-0.2, 1.25], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const txt = {x: vx, y: baseline, textAnchor: 'middle' as const, textLength: largura, lengthAdjust: 'spacingAndGlyphs' as const, fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: size};
  const palavra = String(c.palavra ?? '');
  return (
    <AbsoluteFill>
      <Base c={c} a={a} style={{filter: 'saturate(.22) brightness(1.2) contrast(.9)'}} />
      <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(214,236,255,.62), rgba(176,212,240,.46))', mixBlendMode: 'screen'}} />
      <Bolhas f={f} />
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <defs>
          <clipPath id={`vidro-letra-${a}`} clipPathUnits="userSpaceOnUse">
            <text {...txt}>{palavra}</text>
          </clipPath>
        </defs>
      </svg>
      {f >= at && palavra ? (
        <AbsoluteFill style={{perspective: 1500, perspectiveOrigin: `${vx}px ${baseline}px`}}>
          <AbsoluteFill
            style={{
              transformOrigin: `${vx}px ${baseline}px`, transform: `translateY(${(1 - p) * 150}px) rotateX(${(1 - p) * 80}deg)`,
              filter: `blur(${(1 - p) * 14}px) drop-shadow(0 18px 30px rgba(40,80,120,.25))`, opacity: clamp(p * 1.8),
            }}
          >
            <AbsoluteFill style={{clipPath: `url(#vidro-letra-${a})`}}>
              {/* the same icy picture, shifted and blurred: that is what reads as glass */}
              <Base c={c} a={a} style={{filter: 'saturate(.22) brightness(1.3) contrast(.88) blur(12px)', transform: 'translate(28px, -20px) scale(1.08)'}} />
              <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(214,236,255,.62), rgba(176,212,240,.46))', mixBlendMode: 'screen'}} />
              <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(255,255,255,.5), rgba(255,255,255,.22) 46%, rgba(60,100,140,.3))'}} />
              <AbsoluteFill style={{background: 'linear-gradient(116deg, transparent 36%, rgba(255,255,255,.6) 45%, transparent 53%)'}} />
              <AbsoluteFill style={{background: `linear-gradient(116deg, transparent ${(brilho - 0.05) * 100}%, rgba(255,255,255,.95) ${brilho * 100}%, transparent ${(brilho + 0.05) * 100}%)`}} />
            </AbsoluteFill>
            <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
              {est.contorno > 0 ? (
                <>
                  {/* a dark rim under the light outline: the word reads on the icy background */}
                  <text {...txt} fill="none" stroke="rgba(25,55,85,.55)" strokeWidth={est.contorno + 8}>
                    {palavra}
                  </text>
                  <text {...txt} fill="none" stroke={est.corContorno} strokeWidth={est.contorno}>
                    {palavra}
                  </text>
                </>
              ) : null}
            </svg>
          </AbsoluteFill>
        </AbsoluteFill>
      ) : null}
      <Recorte c={c} />
    </AbsoluteFill>
  );
};
