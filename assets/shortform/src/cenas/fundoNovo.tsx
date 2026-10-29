/**
 * Motors A + B: a new background behind the person, things pinned on it, the person (matte) in
 * front. Mural de manchete, Parede de fotos, Capa de revista, Gráfico subindo and Site (`chroma`).
 *
 * Every position comes from `layout` (helpers/cenas.py, from the person measured in the matte),
 * with `texto: {x, y}` from the editor over the movable block. No text has a default: an empty
 * field draws nothing (the agent takes the texts from the speech).
 */
import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, random, staticFile} from 'remotion';
import {ACCENT, CenaProps, FONTE, Fundo, H, Recorte, Traco, W, centro, clamp, ease, estiloDe, local, mola, tremidas, useJanela} from './comum';

type Slot = {x: number; y: number; w: number; h: number; r: number};
type Coluna = {x: number; y: number; w: number; lado: 'esquerda' | 'direita'} | null;

// ============ MURAL DE MANCHETE =================================================
// Dark wall lit from above; newspaper clippings slam on it where the person is not, each with a
// camera shake; a red pen circle closes on one of them. Data: manchetes [{kicker?, t, at}],
// circulo (index, default the last one), circuloAt (s); layout.slots, layout.fundo.
const circuloPath = (cx: number, cy: number, rx: number, ry: number) => {
  const pts: string[] = [];
  for (let i = 0; i <= 70; i++) {
    const t = -Math.PI * 0.62 + (i / 70) * Math.PI * 2.18;
    const k = 1 + 0.035 * Math.sin(3 * t + 1) + 0.02 * Math.cos(5 * t);
    pts.push(`${(cx + rx * k * Math.cos(t)).toFixed(1)},${(cy + ry * k * Math.sin(t)).toFixed(1)}`);
  }
  return 'M' + pts.join(' L');
};

export const Mural: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const ms: {t: string; kicker?: string; at: number}[] = c.manchetes ?? [];
  const slots: Slot[] = c.layout?.slots ?? [];
  const hits = ms.map((m) => local(m.at, a, fps));
  const sh = tremidas(f, hits, 8, 15);
  const ci = Math.min(ms.length - 1, Math.max(0, c.circulo ?? ms.length - 1));
  const cAt = local(c.circuloAt ?? c.end - 0.9, a, fps);
  const pc = ease(f, cAt, cAt + 13, Easing.inOut(Easing.cubic));
  const sc = slots[ci];
  return (
    <AbsoluteFill style={{transform: `translate(${sh.x}px, ${sh.y}px) rotate(${sh.r}deg) scale(1.03)`}}>
      <Fundo src={c.layout?.fundo} reserva="radial-gradient(ellipse at 50% 0%, #4a4a4a, #161616 70%)" />
      {ms.map((m, i) => {
        const p = slots[i];
        const t = f - hits[i];
        if (!p || t < 0) return null;
        const s = interpolate(t, [0, 5], [1.4, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.3))});
        const o = interpolate(t, [0, 2], [0, 1], {extrapolateRight: 'clamp'});
        const largo = p.w > 400;
        return (
          <div
            key={i}
            style={{
              position: 'absolute', left: p.x, top: p.y, width: p.w, height: p.h, boxSizing: 'border-box',
              padding: largo ? '24px 30px' : '22px 24px', background: '#eee6d4',
              backgroundImage: 'linear-gradient(0deg, rgba(60,40,10,.05) 1px, transparent 1px), radial-gradient(circle at 30% 20%, rgba(255,255,255,.5), rgba(0,0,0,.06))',
              backgroundSize: '100% 5px, 100% 100%',
              boxShadow: `0 ${20 * o}px ${44 * o}px rgba(0,0,0,.6)`,
              transform: `rotate(${p.r}deg) scale(${s})`, opacity: o,
            }}
          >
            {m.kicker ? (
              <div style={{fontFamily: FONTE.oldstd, fontWeight: 700, fontSize: 21, letterSpacing: 5, color: '#a3141c', borderBottom: '3px double #1a1a1a', paddingBottom: 8, marginBottom: 14}}>
                {m.kicker}
              </div>
            ) : null}
            <div style={{fontFamily: FONTE.playfair, fontWeight: 900, fontSize: largo ? 50 : 40, lineHeight: 1.04, color: '#141414', letterSpacing: -0.5}}>{m.t}</div>
            {[0, 1, 2, 3].map((k) => (
              <div key={k} style={{height: 8, marginTop: 13, width: `${94 - ((k * 17) % 40)}%`, background: 'rgba(0,0,0,.17)', borderRadius: 2}} />
            ))}
          </div>
        );
      })}
      {sc ? (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
          <g transform={`rotate(${sc.r} ${sc.x + sc.w / 2} ${sc.y + sc.h / 2})`}>
            <Traco d={circuloPath(sc.x + sc.w / 2, sc.y + sc.h / 2, sc.w / 2 + 34, sc.h / 2 + 30)} p={pc} cor="#e11d1d" w={11} />
            <Traco d={circuloPath(sc.x + sc.w / 2 + 4, sc.y + sc.h / 2 - 3, sc.w / 2 + 28, sc.h / 2 + 36)} p={pc * 0.9} cor="#e11d1d" w={5} opacity={0.7} />
          </g>
        </svg>
      ) : null}
      <Recorte c={c} />
    </AbsoluteFill>
  );
};

// ============ PAREDE DE FOTOS ===================================================
// The wall behind the person fills with polaroids, one every `cada` seconds, falling on a spring
// with a coloured pin; the person casts a shadow on it; a tape strip and a giant word sit above
// the head, below the Reels safe zone (the person moves down `layout.desce` px to make room). Data:
// cada (s), inicio (s), pequeno, pequenoAt, gigante, giganteAt; layout.fotos (the user's images, or
// frames of the video itself), layout.bloco, layout.desce, layout.fundo.
const SLOTS_PAREDE = [
  {x: 24, y: 120, r: -6}, {x: 286, y: 80, r: 4}, {x: 548, y: 128, r: -3}, {x: 806, y: 92, r: 7},
  {x: -6, y: 470, r: 5}, {x: 818, y: 452, r: -4}, {x: 258, y: 420, r: -5}, {x: 574, y: 462, r: 6},
  {x: 14, y: 820, r: -3}, {x: 822, y: 812, r: 4}, {x: 36, y: 1160, r: 6}, {x: 800, y: 1150, r: -6},
  {x: 290, y: 760, r: 3}, {x: 560, y: 790, r: -5},
];
const PINOS = ['#e63946', '#2a9df4', '#f4c430', '#2ecc71', '#9b5de5', '#ff7f11'];

export const Parede: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const fotos: {src: string; legenda?: string}[] = c.layout?.fotos ?? [];
  const cada = Math.max(1, Math.round((c.cada ?? 0.1) * fps));
  const ini = Math.round((c.inicio ?? 0.15) * fps);
  const gAt = local(c.giganteAt ?? c.start + 2, a, fps);
  const pAt = local(c.pequenoAt ?? c.start + 0.3, a, fps);
  const gp = mola(f, gAt, fps, {damping: 10, stiffness: 160});
  const pp = ease(f, pAt, pAt + 8);
  const b = c.layout?.bloco ?? {x: W / 2, y: 400};
  const [tx, ty] = centro(c, [b.x, b.y]);
  const desce = Number(c.layout?.desce) || 0;
  const est = estiloDe(c, {fonte: 'anton', cor: ACCENT, escala: 1, contorno: 10, corContorno: '#ffffff'});
  return (
    <AbsoluteFill>
      <Fundo src={c.layout?.fundo} reserva="#c8c4be" />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 35%, rgba(255,255,255,.18), rgba(0,0,0,.28))'}} />
      {fotos.slice(0, SLOTS_PAREDE.length).map((ft, i) => {
        const s = SLOTS_PAREDE[i];
        const de = ini + i * cada;
        if (f < de) return null;
        const m = mola(f, de, fps, {damping: 11, stiffness: 170});
        const y = s.y - 170 * (1 - m);
        const r = s.r + 14 * (1 - m);
        const pino = m > 0.85;
        return (
          <div key={i} style={{position: 'absolute', left: s.x, top: y, width: 250, height: 296, transform: `rotate(${r}deg) scale(${1.12 - 0.12 * m})`, opacity: clamp(m * 3)}}>
            <div style={{position: 'absolute', inset: 0, background: '#fbfaf6', boxShadow: `0 ${10 + 12 * m}px ${22 + 14 * m}px rgba(0,0,0,.32)`, padding: '14px 14px 0'}}>
              <Img src={staticFile(ft.src)} style={{width: 222, height: 214, objectFit: 'cover', display: 'block', filter: 'saturate(1.05) contrast(1.04)'}} />
              <div style={{fontFamily: FONTE.caveat, fontWeight: 700, fontSize: 38, color: '#2b2b2b', textAlign: 'center', marginTop: 6, lineHeight: 1}}>{ft.legenda ?? ''}</div>
            </div>
            {pino ? (
              <div
                style={{
                  position: 'absolute', left: 113, top: -10, width: 26, height: 26, borderRadius: 999,
                  background: `radial-gradient(circle at 35% 30%, #fff 0 12%, ${PINOS[i % PINOS.length]} 13% 70%, rgba(0,0,0,.4) 100%)`,
                  boxShadow: '2px 5px 6px rgba(0,0,0,.45)',
                }}
              />
            ) : null}
          </div>
        );
      })}
      {/* the person's shadow on the wall, then the person */}
      <Recorte c={c} style={{filter: 'brightness(0) blur(16px)', opacity: 0.42, transform: `translate(38px, ${26 + desce}px)`}} />
      <Recorte c={c} style={desce ? {transform: `translateY(${desce}px)`} : undefined} />
      {/* tape + giant word: one block, centred on `texto` or on layout.bloco */}
      <div style={{position: 'absolute', left: tx, top: ty, width: W, transform: 'translate(-50%, -50%)', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        {c.pequeno ? (
          <div style={{opacity: pp, transform: `translateY(${(1 - pp) * -20}px)`}}>
            <div style={{background: '#ffe14d', padding: '10px 26px', transform: 'rotate(-2deg)', fontFamily: FONTE.poppins, fontWeight: 800, fontSize: 40, letterSpacing: 2, color: '#1b1b1b', boxShadow: '0 8px 18px rgba(0,0,0,.25)'}}>
              {c.pequeno}
            </div>
          </div>
        ) : null}
        {c.gigante ? (
          <div
            style={{
              marginTop: 6, whiteSpace: 'nowrap', fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: 230 * est.escala, lineHeight: 1,
              color: est.cor, ...est.traco, letterSpacing: 2,
              textShadow: '0 16px 34px rgba(0,0,0,.35)', transform: `scale(${0.7 + 0.3 * gp})`, opacity: f >= gAt ? clamp(gp * 2) : 0,
            }}
          >
            {c.gigante}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// ============ CAPA DE REVISTA ===================================================
// The frame becomes a magazine cover: studio cream, the masthead huge behind the head (the person
// covers its foot), the side lines outside the person, an optional round seal just under the
// masthead (layout.selo: centre and diameter), a barcode and a gloss sweep. Data: nome, cor, topo [], esquerda [[a, b]], direita [[a, b]], selo; layout.baseline,
// layout.tamanho, layout.colunas (where each list sits: a list whose side has no room moves to the
// free side and keeps its own look, aligned to the side it landed on).
const ColunaCapa: React.FC<{col: Coluna; linhas: [string, string][]; estilo: 'esquerda' | 'direita'; entra: (d: number) => number}> = ({col, linhas, estilo, entra}) => {
  if (!col || !linhas.length) return null;
  const naDireita = col.lado === 'direita';
  const dir = estilo === 'direita';
  return (
    <div style={{position: 'absolute', left: col.x, top: col.y, width: col.w, textAlign: naDireita ? 'right' : 'left'}}>
      {linhas.map(([t1, t2], i) => {
        const e = entra((dir ? 9 : 6) + i * 5);
        return (
          <div key={i} style={{marginBottom: 40, opacity: e, transform: `translateX(${(1 - e) * (naDireita ? 40 : -40)}px)`}}>
            {dir ? (
              <div style={{display: 'inline-block', background: i === 0 ? '#c1121f' : 'transparent', color: i === 0 ? '#fff' : '#161616', padding: i === 0 ? '4px 12px' : 0, fontFamily: FONTE.poppins, fontWeight: 800, fontSize: 30, letterSpacing: 1, textTransform: 'uppercase'}}>{t1}</div>
            ) : (
              <div style={{fontFamily: FONTE.poppins, fontWeight: 800, fontSize: 34, lineHeight: 1.05, color: '#161616', textTransform: 'uppercase'}}>{t1}</div>
            )}
            <div style={{fontFamily: FONTE.playfair, fontStyle: 'italic', fontWeight: 700, fontSize: dir ? 38 : 40, lineHeight: 1.05, color: !dir && i === 0 ? '#c1121f' : dir ? '#2a2a2a' : '#3a3a3a', marginTop: dir ? 8 : 6}}>{t2}</div>
          </div>
        );
      })}
    </div>
  );
};

export const Capa: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const entra = (d: number) => ease(f, d, d + 9);
  const brilho = interpolate(f, [16, 40], [-0.6, 1.6], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const m = mola(f, 0, fps, {damping: 14, stiffness: 120});
  const barras = Array.from({length: 34}, (_, i) => 2 + Math.floor(random(`bar${i}`) * 5));
  const est = estiloDe(c, {fonte: 'playfair', cor: c.cor ?? '#b0101b', escala: 1, contorno: 0, corContorno: '#000000'});
  const tam0 = c.layout?.tamanho ?? 330;
  const tam = tam0 * est.escala; // grows around the centre: the default centre is the computed one
  const [mx, my] = centro(c, [W / 2, (c.layout?.baseline ?? 690) - tam0 * 0.355]);
  const colunas = c.layout?.colunas ?? {};
  const selo: {x: number; y: number; d: number} = c.layout?.selo ?? {x: 830, y: 790, d: 200};
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse 80% 60% at 50% 38%, #f8f1e6 0%, #ece1cd 55%, #cdbd9f 100%)'}} />
      {c.nome ? (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity: clamp(m * 1.5)}}>
          <text
            x={mx} y={my + tam * 0.355} textAnchor="middle" textLength={(c.largura ?? 1010) * est.escala} lengthAdjust="spacingAndGlyphs"
            fontFamily={est.familia} fontWeight={est.peso} fontStyle={est.italico} fontSize={tam} fill={est.cor}
            stroke={est.contorno > 0 ? est.corContorno : 'none'} strokeWidth={est.contorno} paintOrder="stroke fill"
            transform={`translate(0 ${(1 - m) * -40})`}
          >
            {c.nome}
          </text>
        </svg>
      ) : null}
      {(c.topo ?? []).length ? (
        <div style={{position: 'absolute', top: 252, left: 40, right: 40, display: 'flex', justifyContent: 'space-between', fontFamily: FONTE.poppins, fontWeight: 700, fontSize: 24, letterSpacing: 3, color: '#2a2a2a', opacity: entra(2)}}>
          {(c.topo as string[]).map((t, i) => (
            <span key={i}>{t}</span>
          ))}
        </div>
      ) : null}
      <Recorte c={c} />
      <ColunaCapa col={colunas.esquerda ?? null} linhas={c.esquerda ?? []} estilo="esquerda" entra={entra} />
      <ColunaCapa col={colunas.direita ?? null} linhas={c.direita ?? []} estilo="direita" entra={entra} />
      {c.selo ? (
        <div
          style={{
            position: 'absolute', left: selo.x - selo.d / 2, top: selo.y - selo.d / 2, width: selo.d, height: selo.d, borderRadius: 999, boxSizing: 'border-box', background: '#d4141c',
            border: '5px dashed rgba(255,255,255,.6)', boxShadow: '0 10px 24px rgba(0,0,0,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            transform: `rotate(-12deg) scale(${mola(f, 4, fps, {damping: 9, stiffness: 180})})`,
          }}
        >
          <span style={{fontFamily: FONTE.anton, fontSize: selo.d * 0.18, lineHeight: 1.05, letterSpacing: 2, color: '#fff', textAlign: 'center', maxWidth: selo.d * 0.8}}>{c.selo}</span>
        </div>
      ) : null}
      {/* barcode */}
      <div style={{position: 'absolute', left: 56, top: 1600, padding: '12px 14px 8px', background: '#fff', opacity: entra(12)}}>
        <div style={{display: 'flex', gap: 3, height: 86, alignItems: 'stretch'}}>
          {barras.map((w, i) => (
            <div key={i} style={{width: w, background: i % 3 === 2 ? 'transparent' : '#111'}} />
          ))}
        </div>
        <div style={{fontFamily: FONTE.oldstd, fontSize: 20, letterSpacing: 4, color: '#111', textAlign: 'center', marginTop: 4}}>7 891234 567890</div>
      </div>
      {/* gloss sweep, like coated paper */}
      <AbsoluteFill style={{background: `linear-gradient(115deg, transparent ${(brilho - 0.18) * 100}%, rgba(255,255,255,.55) ${brilho * 100}%, transparent ${(brilho + 0.18) * 100}%)`, mixBlendMode: 'soft-light'}} />
    </AbsoluteFill>
  );
};

// ============ GRÁFICO SUBINDO ===================================================
// Emerald background with a grid; a bar chart grows behind the person, bar by bar on springs; a
// line joins the tops and a tag pops at the end. The person gets a green glow on the outline.
// Data: valores [] (0-1), rotulos [], etiqueta, inicio (s), passo (s); layout.base, layout.altura,
// layout.bloco.
export const Grafico: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const val: number[] = c.valores ?? [];
  const rot: string[] = c.rotulos ?? [];
  const n = Math.max(1, val.length);
  const x0 = 60;
  const x1 = 1020;
  const gap = 22;
  const bw = (x1 - x0 - gap * (n - 1)) / n;
  const base = c.layout?.base ?? 1270;
  const alt = c.layout?.altura ?? 760;
  const passo = Math.round((c.passo ?? 0.16) * fps);
  const ini = Math.round((c.inicio ?? 0.2) * fps);
  const fimBarras = ini + passo * (n - 1) + 12;
  const pl = ease(f, fimBarras, fimBarras + 14, Easing.inOut(Easing.cubic));
  const tagAt = fimBarras + 16;
  const tg = mola(f, tagAt, fps, {damping: 9, stiffness: 180});
  const topos = val.map((v, i) => [x0 + i * (bw + gap) + bw / 2, base - alt * v * mola(f, ini + i * passo, fps, {damping: 10, stiffness: 150})]);
  const linha = 'M' + topos.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L');
  const b = c.layout?.bloco ?? {x: 751, y: 411};
  const [gx, gy] = centro(c, [b.x, b.y]);
  const est = estiloDe(c, {fonte: 'poppins', cor: '#063322', escala: 1, contorno: 0, corContorno: '#ffffff'});
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 30%, #0f5a43 0%, #08402f 55%, #032118 100%)'}} />
      <AbsoluteFill
        style={{
          backgroundImage: 'linear-gradient(rgba(190,255,220,.08) 2px, transparent 2px), linear-gradient(90deg, rgba(190,255,220,.08) 2px, transparent 2px)',
          backgroundSize: '90px 90px', backgroundPosition: '0 40px',
        }}
      />
      {val.map((v, i) => {
        const g = mola(f, ini + i * passo, fps, {damping: 10, stiffness: 150});
        const h = Math.max(0, alt * v * g);
        const x = x0 + i * (bw + gap);
        return (
          <React.Fragment key={i}>
            <div style={{position: 'absolute', left: x, top: base - h, width: bw, height: h, borderRadius: '16px 16px 4px 4px', background: 'linear-gradient(180deg, #e8ff5a 0%, #9be33a 55%, #4fae2a 100%)', boxShadow: '0 0 30px rgba(200,255,90,.25)'}} />
            {rot[i] ? (
              <div style={{position: 'absolute', left: x, top: base + 14, width: bw, textAlign: 'center', fontFamily: FONTE.poppins, fontWeight: 800, fontSize: 36, color: 'rgba(230,255,240,.8)'}}>{rot[i]}</div>
            ) : null}
          </React.Fragment>
        );
      })}
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        <Traco d={linha} p={pl} cor="#f6ffc8" w={7} />
        {topos.map(([x, y], i) => (pl > i / n ? <circle key={i} cx={x} cy={y} r={11} fill="#f6ffc8" /> : null))}
      </svg>
      <Recorte c={c} style={{filter: 'drop-shadow(0 0 8px rgba(170,255,120,.95)) drop-shadow(0 0 26px rgba(90,240,120,.65))'}} />
      {c.etiqueta && f >= tagAt ? (
        <div
          style={{
            position: 'absolute', left: gx, top: gy, transform: `translate(-50%, -50%) scale(${(0.4 + 0.6 * tg) * est.escala}) rotate(${-4 * tg}deg)`, transformOrigin: 'center', whiteSpace: 'nowrap',
            background: '#e8ff5a', color: est.cor, ...est.traco, padding: '18px 34px', borderRadius: 999, fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: 52,
            boxShadow: '0 14px 34px rgba(0,0,0,.35)', display: 'flex', alignItems: 'center', gap: 14,
          }}
        >
          {c.etiqueta}
          <svg width={46} height={46} viewBox="0 0 46 46">
            <path d="M8 38 L36 10 M16 10 H36 V30" stroke={est.cor} strokeWidth={7} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

// ============ SITE (`chroma`) ===================================================
// The background becomes a web page (gradient, moving light blobs, a menu, a big title, a line and
// a button) and the person, whole and scaled down, slides in at a lower corner. Data: titulo, marca,
// menu [], frase, botao, lado ('direita' | 'esquerda'), entrada (s); layout.escala, layout.x,
// layout.y (the corner of the scaled frame) and layout.bloco (the text, around the designed 514, 640).
// The menu and the title sit below the Reels safe zone.
export const Chroma: React.FC<CenaProps> = ({c}) => {
  const {f, fps} = useJanela();
  const entra = (d: number) => ease(f, d, d + 10);
  const sl = mola(f, Math.round((c.entrada ?? 0.25) * fps), fps, {damping: 15, stiffness: 110});
  const L = c.layout ?? {};
  const esc = L.escala ?? 0.7;
  const direita = (c.lado ?? 'direita') === 'direita';
  const pw = W * esc;
  const ph = H * esc;
  const px = L.x ?? (direita ? W - pw + 90 : -90);
  const py = L.y ?? H - ph;
  const b = L.bloco ?? {x: 514, y: 640};
  const [bx, by] = centro(c, [b.x, b.y]);
  const est = estiloDe(c, {fonte: 'poppins', cor: '#ffffff', escala: 1, contorno: 0, corContorno: '#3a0ca3'});
  // scaled down, the side of the original frame that faces the page (a straight cut through the
  // shoulder) would show: that side fades into the page
  const lado = direita ? '90deg' : '270deg';
  const mascara = `linear-gradient(${lado}, transparent 0%, rgba(0,0,0,.55) 12%, #000 30%)`;
  const blobs = [
    {c: 'rgba(255,255,255,.35)', r: 520, x: 200, y: 520, sx: 0.013, sy: 0.009},
    {c: 'rgba(255,120,200,.45)', r: 620, x: 860, y: 900, sx: 0.009, sy: 0.012},
    {c: 'rgba(120,160,255,.45)', r: 560, x: 300, y: 1500, sx: 0.011, sy: 0.007},
  ];
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: 'linear-gradient(160deg, #3a0ca3 0%, #7209b7 48%, #f72585 100%)'}} />
      {blobs.map((bl, i) => (
        <div
          key={i}
          style={{
            position: 'absolute', width: bl.r, height: bl.r, borderRadius: 999, background: `radial-gradient(circle, ${bl.c}, transparent 70%)`,
            left: bl.x - bl.r / 2 + Math.sin(f * bl.sx * 6 + i) * 90, top: bl.y - bl.r / 2 + Math.cos(f * bl.sy * 6 + i * 2) * 70, filter: 'blur(30px)',
          }}
        />
      ))}
      {c.marca || (c.menu ?? []).length ? (
        <div style={{position: 'absolute', left: 56, right: 56, top: 250, height: 84, display: 'flex', alignItems: 'center', justifyContent: 'space-between', opacity: entra(0)}}>
          <div style={{fontFamily: FONTE.poppins, fontWeight: 800, fontSize: 36, color: '#fff', display: 'flex', alignItems: 'center', gap: 12}}>
            {c.marca ? <div style={{width: 30, height: 30, background: '#fff', transform: 'rotate(45deg)', borderRadius: 6}} /> : null}
            {c.marca ?? ''}
          </div>
          <div style={{display: 'flex', gap: 26, alignItems: 'center', fontFamily: FONTE.poppins, fontWeight: 500, fontSize: 26, color: 'rgba(255,255,255,.88)'}}>
            {((c.menu ?? []) as string[]).map((m, i) => (
              <span key={i}>{m}</span>
            ))}
          </div>
        </div>
      ) : null}
      <AbsoluteFill style={{transform: `translate(${bx - 514}px, ${by - 640}px)`}}>
        <div style={{position: 'absolute', left: 64, top: 350, width: 900, fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: 94 * est.escala, lineHeight: 1.0, color: est.cor, ...est.traco, letterSpacing: -2, opacity: entra(4), transform: `translateY(${(1 - entra(4)) * 30}px)`}}>
          {c.titulo}
        </div>
        {c.frase ? (
          <div style={{position: 'absolute', left: 66, top: 640, width: 560, fontFamily: FONTE.poppins, fontWeight: 500, fontSize: 36, lineHeight: 1.25, color: 'rgba(255,255,255,.92)', opacity: entra(9)}}>
            {c.frase}
          </div>
        ) : null}
        {c.botao ? (
          <div style={{position: 'absolute', left: 64, top: 830, opacity: entra(13), transform: `scale(${0.9 + 0.1 * entra(13)})`, transformOrigin: 'left center'}}>
            <div style={{background: '#fff', color: '#3a0ca3', borderRadius: 999, padding: '24px 40px', fontFamily: FONTE.poppins, fontWeight: 800, fontSize: 34, boxShadow: '0 16px 40px rgba(40,0,90,.4)'}}>{c.botao}</div>
          </div>
        ) : null}
      </AbsoluteFill>
      <div style={{position: 'absolute', left: px + (direita ? 1 : -1) * (1 - sl) * 760, top: py, width: pw, height: ph}}>
        <div style={{width: W, height: H, transform: `scale(${esc})`, transformOrigin: '0 0', position: 'relative'}}>
          <Recorte c={c} style={{filter: 'drop-shadow(0 20px 40px rgba(30,0,60,.45))', WebkitMaskImage: mascara, maskImage: mascara}} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
