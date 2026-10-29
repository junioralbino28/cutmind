/**
 * Órbita: cards (the user's images, or frames of the video) circle the person on a tilted ring.
 * The back half passes BEHIND the person (the matte is drawn over them, in the same framing as the
 * picture under it, the take's enquadre or camera zoom included) and the front half in front. The
 * picture is not redrawn: the main video keeps playing underneath. Optional `titulo` (one or two
 * lines) sits below the Reels safe zone.
 *
 * Data: titulo?, voltas? (turns over the window, 0.75), cartoes? (the helper fills layout.cartoes);
 * layout: cartoes [{src}], raio {rx, ry} and the ring's centre comes from the person ON SCREEN
 * (cameraAt), so it follows the framing of the take.
 */
import React from 'react';
import {AbsoluteFill, Easing, Img, OffthreadVideo, interpolate, staticFile} from 'remotion';
import {cameraAt} from '../Main';
import {ZONA_SEGURA} from '../zonaSegura';
import {ACCENT, CenaProps, H, W, centro, clamp, ease, estiloDe, useJanela} from './comum';

const CL = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
export const ORBITA_TITULO_TOPO = ZONA_SEGURA.topo + 30; // the title's top, below the safe-zone line (the editor mirrors it)

export const Orbita: React.FC<CenaProps> = ({c, a, n}) => {
  const {f, fps} = useJanela();
  const cam = cameraAt(a + f, W, H, fps);
  const p = c.pessoa ?? {x0: 300, x1: 780, topo: 500, base: H, cabecaX: 540};
  const cartoes: {src: string}[] = c.layout?.cartoes ?? [];
  // the person on screen: the picture under the effect is the cut seen through the camera
  const cabecaX = cam.tx + p.cabecaX * cam.S;
  const topo = cam.ty + p.topo * cam.S;
  const largura = (p.x1 - p.x0) * cam.S;
  const cx = clamp(cabecaX, 360, 720);
  // the ring passes below the chin, never across the face: the chin sits ~400 px of the cut below the
  // top of the head, times the take's zoom (a 1.84x close-up put a front card on the mouth at topo + 560)
  const cy = clamp(topo + 400 * cam.S + 60, 900, 1300);
  const rx = clamp(largura / 2 + 170, 380, 500);
  const ry = c.layout?.raio?.ry ?? 190;
  const k = ease(f, 0, 10, Easing.out(Easing.cubic));
  const q = interpolate(f, [n - 7, n], [0, 1], {...CL, easing: Easing.in(Easing.cubic)});
  const R = (0.3 + 0.7 * k) * (1 + 0.8 * q);
  const giro = 2 * Math.PI * (c.voltas ?? 0.75) * (f / Math.max(1, n));
  const cw = 300;
  const ch = 210;
  const lista = cartoes.map((cd, i) => {
    const th = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, cartoes.length) + giro;
    const d = Math.sin(th);
    return {cd, i, d, x: cx + rx * R * Math.cos(th), y: cy + ry * R * d, rot: -Math.cos(th) * 30};
  });
  const desenha = (frente: boolean) =>
    lista
      .filter((x) => (x.d >= 0) === frente)
      .sort((u, v) => u.d - v.d)
      .map(({cd, i, d, x, y, rot}) => (
        <div
          key={i}
          style={{
            position: 'absolute', left: x - cw / 2, top: y - ch / 2, width: cw, height: ch, borderRadius: 20, overflow: 'hidden',
            border: `4px solid ${ACCENT}`, boxShadow: '0 22px 45px rgba(0,0,0,.5)', background: '#101010',
            transform: `scale(${(0.8 + 0.25 * d).toFixed(3)}) rotateY(${rot.toFixed(1)}deg)`,
            filter: `brightness(${(0.82 + 0.18 * d).toFixed(2)})`, opacity: Math.min(1, k * 1.4) * (1 - q),
          }}
        >
          <Img src={staticFile(cd.src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </div>
      ));
  const clip = cam.clip;
  const px = (v: number) => `${Math.max(0, v).toFixed(2)}px`;
  const est = estiloDe(c, {fonte: 'instrument', cor: '#ffffff', escala: 1, contorno: 0, corContorno: '#000000'});
  const linhas = (Array.isArray(c.titulo) ? c.titulo : c.titulo ? [c.titulo] : []).map(String);
  const hT = 104 * est.escala * linhas.length;
  const [tx, ty] = centro(c, [W / 2, ORBITA_TITULO_TOPO + hT / 2]);
  return (
    <AbsoluteFill style={{perspective: 1600}}>
      {desenha(false)}
      {c.matte ? (
        <AbsoluteFill style={clip ? {clipPath: `inset(${px(clip.top)} ${px(W - clip.right)} ${px(H - clip.bottom)} ${px(clip.left)})`} : undefined}>
          <div style={{width: W, height: H, transformOrigin: '0 0', transform: `translate(${cam.tx.toFixed(2)}px, ${cam.ty.toFixed(2)}px) scale(${cam.S.toFixed(4)})`}}>
            <OffthreadVideo src={staticFile(c.matte)} transparent muted style={{width: W, height: H}} />
          </div>
        </AbsoluteFill>
      ) : null}
      {desenha(true)}
      {linhas.length ? (
        <div style={{position: 'absolute', left: tx, top: ty, transform: 'translate(-50%, -50%)', textAlign: 'center', whiteSpace: 'nowrap',
          fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: 104 * est.escala, lineHeight: 1.0, color: est.cor,
          ...est.traco, textShadow: '0 8px 30px rgba(0,0,0,.45)', opacity: k * (1 - q)}}>
          {linhas.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
