/**
 * Six more effects that redraw a take: Dentro do app, Saindo da tela, Revelação, Recorte de papel,
 * Rabisco vivo and Vertigem. Same rules as fundoNovo.tsx: positions come from `layout`
 * (helpers/cenas.py, from the person measured in the matte), `texto: {x, y}` from the editor over the
 * movable block, and no text has a default: an empty field draws nothing.
 */
import React from 'react';
import {AbsoluteFill, Easing, Freeze, Img, interpolate, random, staticFile} from 'remotion';
import {ZONA_SEGURA} from '../zonaSegura';
import {ACCENT, Base, CenaProps, FONTE, Fundo, H, Recorte, Traco, W, centro, clamp, ease, estiloDe, local, mola, tremida, useJanela} from './comum';

const TOPO = ZONA_SEGURA.topo;

// ============ DENTRO DO APP =====================================================
// The top half becomes a light app window pushing the picture down; thumbnails fall into a drop area,
// a tag pops and the input box types a command, with the send button pressed at the end. The person
// stays below with the caption. Data: zona, etiqueta, comando, digitaAt, digitaFimAt; layout.desce,
// layout.fotos (the user's images, or frames of the video itself).
const PAINEL_H = 900;
const CABE_NA_CAIXA = 40; // letras na caixa de texto, a 36 px

export const App: React.FC<CenaProps> = ({c, a, n}) => {
  const {f, fps} = useJanela();
  const m = mola(f, 0, fps, {damping: 17, stiffness: 120});
  const desce = (Number(c.layout?.desce) || 0) * m;
  const fotos: {src: string}[] = (c.layout?.fotos ?? []).slice(0, 4);
  const ini = Math.round(0.35 * fps);
  const cada = Math.round(0.18 * fps);
  const eAt = ini + fotos.length * cada + 3;
  const dAt = c.digitaAt != null ? local(c.digitaAt, a, fps) : Math.round(n * 0.45);
  const dFim = c.digitaFimAt != null ? local(c.digitaFimAt, a, fps) : Math.round(n * 0.85);
  const cmd = String(c.comando ?? '');
  const k = Math.round(cmd.length * ease(f, dAt, dFim, Easing.linear));
  const digitado = cmd.slice(0, k).slice(-CABE_NA_CAIXA); // a frase longa anda: aparece o fim do que está sendo digitado
  const aperto = f >= dFim + 1 ? 1 - 0.18 * Math.sin(clamp((f - dFim - 1) / 6) * Math.PI) : 1;
  return (
    <AbsoluteFill style={{background: '#101012'}}>
      <Base c={c} a={a} style={{transform: `translateY(${desce}px)`}} />
      <div style={{position: 'absolute', left: 0, top: -PAINEL_H * (1 - m), width: W, height: PAINEL_H, background: '#efece6', boxShadow: '0 16px 44px rgba(0,0,0,.4)'}}>
        <div style={{position: 'absolute', left: 40, top: TOPO + 6, width: 1000, height: PAINEL_H - TOPO - 26, background: '#fff', borderRadius: 30, overflow: 'hidden', boxShadow: '0 10px 30px rgba(0,0,0,.14)', fontFamily: FONTE.poppins}}>
          <div style={{height: 58, background: '#f6f4ef', display: 'flex', alignItems: 'center', gap: 12, paddingLeft: 26, borderBottom: '2px solid #e6e2d9'}}>
            {['#ff6159', '#ffbd2e', '#28c93f'].map((cor) => (
              <div key={cor} style={{width: 18, height: 18, borderRadius: 99, background: cor}} />
            ))}
          </div>
          <div style={{position: 'absolute', left: 30, right: 30, top: 84, height: 330, border: '4px dashed #c9c3b6', borderRadius: 24, boxSizing: 'border-box', background: '#fbfaf7'}}>
            {c.zona ? <div style={{position: 'absolute', top: 26, left: 0, right: 0, textAlign: 'center', fontWeight: 600, fontSize: 36, color: '#8b8678'}}>{c.zona}</div> : null}
            {fotos.map((ft, i) => {
              const de = ini + i * cada;
              if (f < de) return null;
              const q = mola(f, de, fps, {damping: 11, stiffness: 190});
              return (
                <div key={i} style={{position: 'absolute', left: 24 + i * 222, top: 96 - 260 * (1 - q), width: 204, height: 190, borderRadius: 14, overflow: 'hidden', boxShadow: '0 8px 18px rgba(0,0,0,.28)', transform: `rotate(${(i % 2 ? 2 : -2) + 12 * (1 - q)}deg)`, opacity: clamp(q * 3)}}>
                  <Img src={staticFile(ft.src)} style={{width: '100%', height: '100%', objectFit: 'cover', display: 'block'}} />
                </div>
              );
            })}
          </div>
          {c.etiqueta && f >= eAt ? (
            <div style={{position: 'absolute', right: 52, top: 66, background: ACCENT, color: '#fff', fontWeight: 800, fontSize: 32, letterSpacing: 1, padding: '10px 26px', borderRadius: 99, transform: `scale(${mola(f, eAt, fps, {damping: 9, stiffness: 240})}) rotate(3deg)`, boxShadow: '0 8px 18px rgba(0,0,0,.22)'}}>
              {c.etiqueta}
            </div>
          ) : null}
          <div style={{position: 'absolute', left: 30, right: 30, bottom: 26, height: 112, borderRadius: 24, border: '3px solid #dcd7cb', background: '#fff', display: 'flex', alignItems: 'center', padding: '0 20px 0 30px', boxSizing: 'border-box'}}>
            <div style={{flex: 1, fontWeight: 500, fontSize: 36, color: '#26241f', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'clip'}}>
              {digitado}
              {f >= dAt && f < dFim + 2 && f % 16 < 10 ? <span style={{color: ACCENT}}>|</span> : null}
            </div>
            <div style={{width: 76, height: 76, borderRadius: 99, background: f >= dFim ? ACCENT : '#d9d5cb', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 44, fontWeight: 800, transform: `scale(${aperto})`}}>↑</div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ============ SAINDO DA TELA ====================================================
// The video sits in a post frame with a neon border on a black grid. At `at` the head and the hand break
// out of the top (the cut-out over it, held only at the bottom), with shards, a shake and the border
// flashing. Data: titulo, cor, at; layout.quadro (the frame), layout.foto (x, y, escala of the picture),
// layout.bloco.
const CACOS = Array.from({length: 18}, (_, i) => i);

export const Saindo: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const q = c.layout?.quadro ?? {x: 90, y: 560, w: 900, h: 980};
  const ft = c.layout?.foto ?? {x: 90, y: 400, escala: 0.9};
  const b = c.layout?.bloco ?? {x: W / 2, y: TOPO + 85};
  const [tx, ty] = centro(c, [b.x, b.y]);
  const est = estiloDe(c, {fonte: 'bebas', cor: c.cor ?? '#c6ff3d', escala: 1, contorno: 0, corContorno: '#000000'});
  const cor: string = c.cor ?? '#c6ff3d';
  const at = local(c.at ?? c.start + 0.4, a, fps);
  const saiu = f >= at;
  const m = saiu ? mola(f, at, fps, {damping: 11, stiffness: 150}) : 0;
  const s = 1 + 0.14 * m;
  const sh = tremida(f, at, 12, 20);
  const flash = saiu ? Math.max(0, 1 - (f - at) / 10) : 0;
  const px = q.x + q.w / 2;
  const py = q.y + q.h;
  const foto: React.CSSProperties = {position: 'absolute', left: ft.x, top: ft.y, width: W, height: H, transform: `scale(${ft.escala})`, transformOrigin: '0 0'};
  const escala: React.CSSProperties = {position: 'absolute', left: 0, top: 0, width: W, height: H, transform: `translate(${px}px, ${py}px) scale(${s}) translate(${-px}px, ${-py}px)`};
  const cx = c.pessoa ? ft.x + c.pessoa.cabecaX * ft.escala : px;
  return (
    <AbsoluteFill style={{background: '#050505', overflow: 'hidden'}}>
      <AbsoluteFill style={{backgroundImage: `linear-gradient(${cor}22 2px, transparent 2px), linear-gradient(90deg, ${cor}22 2px, transparent 2px)`, backgroundSize: '72px 72px'}} />
      <AbsoluteFill style={{transform: `translate(${sh.x}px, ${sh.y}px) rotate(${sh.r}deg)`}}>
        <div style={{position: 'absolute', left: q.x, top: q.y, width: q.w, height: q.h, overflow: 'hidden', background: '#000'}}>
          <div style={{position: 'absolute', left: -q.x, top: -q.y, width: W, height: H}}>
            <div style={escala}>
              <div style={foto}>
                <Base c={c} a={a} />
              </div>
            </div>
          </div>
        </div>
        <div style={{position: 'absolute', left: q.x, top: q.y, width: q.w, height: q.h, boxSizing: 'border-box', border: `9px solid ${cor}`, borderRadius: 6, boxShadow: `0 0 ${34 + 70 * flash}px ${cor}, inset 0 0 ${18 + 30 * flash}px ${cor}88`}} />
        {saiu ? (
          <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, clipPath: `inset(0 0 ${H - py}px 0)`}}>
            <div style={escala}>
              <div style={foto}>
                <Recorte c={c} />
              </div>
            </div>
          </div>
        ) : null}
        {saiu
          ? CACOS.map((i) => {
              const t = f - at;
              if (t > 24) return null;
              const ang = -Math.PI * (0.08 + 0.84 * random(`ca${i}`));
              const v = 16 + 26 * random(`cv${i}`);
              const tam = 14 + 34 * random(`ct${i}`);
              const x = cx + (random(`cx${i}`) - 0.5) * 300 + Math.cos(ang) * v * t;
              const y = q.y + Math.sin(ang) * v * t + 1.1 * t * t;
              return <div key={i} style={{position: 'absolute', left: x, top: y, width: tam, height: tam, background: i % 3 ? cor : '#ffffff', opacity: clamp(1.4 - t / 20), clipPath: 'polygon(50% 0, 100% 72%, 18% 100%)', transform: `rotate(${(random(`cr${i}`) * 720 - 360) * (t / 24)}deg)`}} />;
            })
          : null}
      </AbsoluteFill>
      {c.titulo ? (
        <div style={{position: 'absolute', left: tx, top: ty, transform: 'translate(-50%, -50%)', whiteSpace: 'nowrap', fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: 150 * est.escala, lineHeight: 1, letterSpacing: 2, color: est.cor, textShadow: `0 0 26px ${est.cor}aa`, ...est.traco, opacity: ease(f, 0, 6)}}>
          {c.titulo}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

// ============ REVELAÇÃO =========================================================
// Starts as the plain picture; at `at` the camera pulls back until it is the preview window of a dark
// editor: tasks being ticked on the side, tracks and a sound wave below, the cursor walking. Data:
// tarefas (up to 6), at. No cut-out and no measure of the person: it also works on a screen recording.
const PV = {x: 60, y: TOPO + 62, w: 470};
const PV_H = (PV.w * 16) / 9;
const TL = {x: 60, y: PV.y + PV_H + 28, w: 860, h: 300};

export const Revelacao: React.FC<CenaProps> = ({c, a, n}) => {
  const {f, fps} = useJanela();
  const at = local(c.at ?? c.start + 0.25, a, fps);
  const dur = Math.round(0.9 * fps);
  const p = ease(f, at, at + dur, Easing.inOut(Easing.cubic));
  const esc = 1 + (PV.w / W - 1) * p;
  const tarefas: string[] = (c.tarefas ?? []).slice(0, 6);
  const tIni = at + dur;
  const tPasso = Math.max(4, (n - tIni - 6) / Math.max(1, tarefas.length));
  const cursor = interpolate(f, [at, n], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const faixas = [
    {cor: ACCENT, y: 0, pedacos: 5},
    {cor: '#3aa0ff', y: 56, pedacos: 7},
    {cor: '#a06bff', y: 112, pedacos: 4},
  ];
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={{background: '#14161b', opacity: p, fontFamily: FONTE.poppins}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: TOPO - 6, height: 54, display: 'flex', alignItems: 'center', gap: 12, paddingLeft: 60}}>
          {['#ff6159', '#ffbd2e', '#28c93f'].map((cor) => (
            <div key={cor} style={{width: 16, height: 16, borderRadius: 99, background: cor}} />
          ))}
        </div>
        <div style={{position: 'absolute', left: PV.x + PV.w + 28, top: PV.y, width: TL.x + TL.w - (PV.x + PV.w + 28), height: PV_H, background: '#1c1f26', borderRadius: 20, padding: '40px 24px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: 54}}>
          {tarefas.map((tx, i) => {
            const de = tIni + i * tPasso;
            const q = f < de ? 0 : mola(f, de, fps, {damping: 11, stiffness: 220});
            return (
              <div key={i} style={{display: 'flex', alignItems: 'center', gap: 16, fontSize: 32, fontWeight: 600, lineHeight: 1.15, color: q > 0.5 ? '#ffffff' : '#7d8290'}}>
                <div style={{flex: '0 0 46px', width: 46, height: 46, borderRadius: 99, border: `4px solid ${q > 0.5 ? ACCENT : '#4a4e5a'}`, background: q > 0.5 ? ACCENT : 'transparent', boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 28, fontWeight: 800, transform: `scale(${0.8 + 0.2 * q})`}}>
                  {q > 0.5 ? '✓' : ''}
                </div>
                <span>{tx}</span>
              </div>
            );
          })}
        </div>
        <div style={{position: 'absolute', left: TL.x, top: TL.y, width: TL.w, height: TL.h, background: '#1c1f26', borderRadius: 20, overflow: 'hidden'}}>
          <div style={{position: 'absolute', left: 16, right: 16, top: 18, height: 160}}>
            {faixas.map((fx) => {
              let x = 0;
              return Array.from({length: fx.pedacos}, (_, i) => {
                const w = (100 / fx.pedacos) * (0.65 + 0.3 * random(`w${fx.y}-${i}`));
                const el = <div key={`${fx.y}-${i}`} style={{position: 'absolute', top: fx.y, left: `${x}%`, width: `${w}%`, height: 46, borderRadius: 10, background: fx.cor, opacity: 0.85}} />;
                x += 100 / fx.pedacos;
                return el;
              });
            })}
          </div>
          <div style={{position: 'absolute', left: 16, right: 16, bottom: 18, height: 84, display: 'flex', alignItems: 'center', gap: 3}}>
            {Array.from({length: 96}, (_, i) => (
              <div key={i} style={{flex: 1, height: `${18 + 80 * random(`o${i}`) * (0.5 + 0.5 * Math.sin(i * 0.33 + 1))}%`, background: '#5e6472', borderRadius: 2}} />
            ))}
          </div>
          <div style={{position: 'absolute', top: 0, bottom: 0, left: 16 + cursor * (TL.w - 32), width: 5, background: ACCENT, boxShadow: `0 0 14px ${ACCENT}`}} />
        </div>
      </AbsoluteFill>
      <Base c={c} a={a} style={{transform: `translate(${PV.x * p}px, ${PV.y * p}px) scale(${esc})`, transformOrigin: '0 0', borderRadius: (22 * p) / esc, overflow: 'hidden', outline: p > 0.5 ? `${4 / esc}px solid ${ACCENT}` : undefined}} />
    </AbsoluteFill>
  );
};

// ============ RECORTE DE PAPEL ==================================================
// A kraft collage in stop motion (15 fps): torn paper, tape, a blue pen scribble and a red X; the person
// is a sticker with a thick white border, a bit crooked; the sentence is made of cut-out letters, each
// with its own font and paper. Data: frase (a text, one line per \n, up to 2); layout.fundo, layout.bloco,
// layout.desce.
const FONTES_PAPEL = ['anton', 'playfair', 'elite', 'marker', 'bebas', 'abril', 'oldstd', 'oswald'] as const;
const PAPEIS = [['#fff7e6', '#111111'], ['#141414', '#ffffff'], ['#d7263d', '#ffffff'], ['#f4d35e', '#111111'], ['#1b4965', '#ffffff'], ['#ffffff', '#d7263d'], ['#2a9d8f', '#ffffff']];
const PEDACOS = [
  {x: -40, y: 420, w: 430, h: 560, r: -7, cor: '#f5efe2'},
  {x: 690, y: 520, w: 450, h: 500, r: 6, cor: '#c9d6df'},
  {x: -30, y: 1120, w: 480, h: 420, r: 4, cor: '#e9d8a6'},
  {x: 660, y: 1160, w: 480, h: 460, r: -5, cor: '#f2c5a0'},
];
const rasgado = (seed: string) => {
  const pts: string[] = [];
  const lado = 11;
  for (let i = 0; i <= lado; i++) pts.push(`${(i / lado) * 100}% ${random(`${seed}t${i}`) * 3.5}%`);
  for (let i = 0; i <= lado; i++) pts.push(`${100 - random(`${seed}r${i}`) * 3.5}% ${(i / lado) * 100}%`);
  for (let i = lado; i >= 0; i--) pts.push(`${(i / lado) * 100}% ${100 - random(`${seed}b${i}`) * 3.5}%`);
  for (let i = lado; i >= 0; i--) pts.push(`${random(`${seed}l${i}`) * 3.5}% ${(i / lado) * 100}%`);
  return `polygon(${pts.join(',')})`;
};

export const Papel: React.FC<CenaProps> = ({c, a}) => {
  const {f, fps} = useJanela();
  const passo = Math.max(1, Math.round(fps / 15));
  const g = Math.floor(f / passo);
  const est = estiloDe(c, {fonte: 'anton', cor: '#ffffff', escala: 1, contorno: 0, corContorno: '#000000'});
  const b = c.layout?.bloco ?? {x: W / 2, y: TOPO + 170};
  const [tx, ty] = centro(c, [b.x, b.y]);
  const desce = Number(c.layout?.desce) || 0;
  const linhas = String(c.frase ?? '').split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 2);
  const maior = Math.max(1, ...linhas.map((s) => s.length));
  const tam = Math.min(118, 930 / (maior * 0.74)) * est.escala;
  const giro = -2.4 + 1.3 * (random(`pg${g}`) * 2 - 1);
  const dx = (random(`px${g}`) * 2 - 1) * 4;
  const dy = (random(`py${g}`) * 2 - 1) * 4;
  const risco = clamp(g / 14);
  const xis = clamp((g - 8) / 7);
  let conta = 0;
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Fundo src={c.layout?.fundo} reserva="#b08d5e" />
      {PEDACOS.map((pd, i) => {
        const j = random(`pd${i}${Math.floor(g / 2)}`) * 1.4 - 0.7;
        return (
          <div key={i} style={{position: 'absolute', left: pd.x, top: pd.y, width: pd.w, height: pd.h, transform: `rotate(${pd.r + j}deg)`, filter: 'drop-shadow(4px 7px 5px rgba(0,0,0,.35))'}}>
            <div style={{width: '100%', height: '100%', background: pd.cor, clipPath: rasgado(`pd${i}`)}} />
          </div>
        );
      })}
      <div style={{position: 'absolute', left: 300, top: 470, width: 250, height: 62, background: 'rgba(255,240,175,.62)', transform: `rotate(-14deg)`, boxShadow: '0 2px 5px rgba(0,0,0,.2)'}} />
      <div style={{position: 'absolute', left: 620, top: 1150, width: 220, height: 58, background: 'rgba(255,240,175,.62)', transform: `rotate(9deg)`, boxShadow: '0 2px 5px rgba(0,0,0,.2)'}} />
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        <Traco d="M 40 1230 C 130 1160, 170 1320, 250 1230 S 370 1180, 410 1290 S 240 1400, 120 1340" p={risco} cor="#1f5fd1" w={9} />
        <Traco d="M 830 640 L 990 800" p={xis * 2} cor="#d7263d" w={22} />
        <Traco d="M 990 640 L 830 800" p={xis * 2 - 1} cor="#d7263d" w={22} />
      </svg>
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <filter id={`adesivo-${a}`} x="-4%" y="-4%" width="108%" height="108%" colorInterpolationFilters="sRGB">
          <feMorphology in="SourceAlpha" operator="dilate" radius="12" result="d" />
          <feFlood floodColor="#ffffff" />
          <feComposite in2="d" operator="in" result="borda" />
          <feMerge>
            <feMergeNode in="borda" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </svg>
      <AbsoluteFill style={{transform: `translate(${dx}px, ${dy + desce}px) rotate(${giro}deg)`, transformOrigin: '50% 100%', filter: 'drop-shadow(9px 12px 0 rgba(0,0,0,.33))'}}>
        <Freeze frame={g * passo}>
          <Recorte c={c} style={{filter: `url(#adesivo-${a})`}} />
        </Freeze>
      </AbsoluteFill>
      <div style={{position: 'absolute', left: tx, top: ty, transform: 'translate(-50%, -50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12}}>
        {linhas.map((s, li) => (
          <div key={li} style={{display: 'flex', gap: 5, whiteSpace: 'nowrap'}}>
            {Array.from(s).map((ch, i) => {
              const ordem = conta++;
              if (ch === ' ') return <div key={i} style={{width: tam * 0.32}} />;
              if (g < ordem) return null;
              const [fundo, tinta] = PAPEIS[Math.floor(random(`pl${li}${i}`) * PAPEIS.length)];
              const fonte = FONTES_PAPEL[Math.floor(random(`pf${li}${i}`) * FONTES_PAPEL.length)];
              const r = (random(`pr${li}${i}`) * 2 - 1) * 7 + (random(`pj${li}${i}${Math.floor(g / 3)}`) * 2 - 1) * 1.4;
              return (
                <div key={i} style={{background: fundo, color: tinta, fontFamily: FONTE[fonte], fontWeight: 700, fontSize: tam, lineHeight: 1.08, padding: `${tam * 0.05}px ${tam * 0.1}px`, transform: `rotate(${r}deg) translateY(${(random(`pv${li}${i}`) * 2 - 1) * tam * 0.07}px)`, boxShadow: '3px 5px 0 rgba(0,0,0,.32)'}}>
                  {ch}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// ============ RABISCO VIVO ======================================================
// A dark chalkboard, a white hand-drawn contour around the person that trembles (new noise every 3
// frames) and chalk doodles drawing themselves: a crown on the head, then a star, a heart, a spiral, a
// clapperboard and an arrow, where the person is not, and a handwritten sentence. Data: frase;
// layout.fundo, layout.coroa (x, y, w), layout.desenhos (name → x, y, w, h, or null when it does not
// fit), layout.bloco.
const espiralPath = () => {
  const pts: string[] = [];
  for (let i = 0; i <= 70; i++) {
    const t = (i / 70) * Math.PI * 5.4;
    const r = 3 + (i / 70) * 45;
    pts.push(`${(50 + r * Math.cos(t)).toFixed(1)} ${(50 + r * Math.sin(t)).toFixed(1)}`);
  }
  return 'M' + pts.join(' L');
};
const DESENHOS: Record<string, {d: string; cor: string}> = {
  estrela: {d: 'M50 5 L62 38 L97 38 L68 60 L79 95 L50 73 L21 95 L32 60 L3 38 L38 38 Z', cor: '#fdfdf8'},
  coracao: {d: 'M50 88 C10 60 0 30 20 15 C35 5 48 18 50 30 C52 18 65 5 80 15 C100 30 90 60 50 88 Z', cor: '#ff7ab8'},
  espiral: {d: espiralPath(), cor: '#7fe0ff'},
  claquete: {d: 'M6 40 H94 V94 H6 Z M6 40 L90 12 L96 32 L12 58 M26 33 L36 52 M48 26 L58 45 M70 19 L80 38', cor: '#fdfdf8'},
  seta: {d: 'M4 62 C28 30 62 28 90 52 M68 28 L92 54 L60 70', cor: '#9dff8a'},
};
const COROA = 'M5 90 L12 25 L32 60 L50 10 L68 60 L88 25 L95 90 Z';

export const Rabisco: React.FC<CenaProps> = ({c, a, n}) => {
  const {f, fps} = useJanela();
  const sem = 1 + Math.floor(f / 3);
  const est = estiloDe(c, {fonte: 'caveat', cor: '#fdfdf8', escala: 1, contorno: 0, corContorno: '#000000'});
  const b = c.layout?.bloco ?? {x: W / 2, y: TOPO + 80};
  const [tx, ty] = centro(c, [b.x, b.y]);
  const coroa = c.layout?.coroa;
  const lugares: Record<string, {x: number; y: number; w: number; h: number} | null> = c.layout?.desenhos ?? {};
  const nomes = Object.keys(DESENHOS).filter((k) => lugares[k]);
  const passo = Math.max(6, Math.min(14, (n - 24) / Math.max(1, nomes.length + 1)));
  const frase = String(c.frase ?? '');
  const tam = Math.min(112, 980 / Math.max(1, frase.length * 0.42)) * est.escala;
  const fp = ease(f, 8, 8 + Math.max(10, frase.length), Easing.linear);
  const desce = Number(c.layout?.desce) || 0;
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Fundo src={c.layout?.fundo} reserva="#1d2a26" />
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <filter id={`giz-${a}-${sem}`} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feMorphology in="SourceAlpha" operator="dilate" radius="19" result="fora" />
          <feMorphology in="SourceAlpha" operator="dilate" radius="13" result="dentro" />
          <feComposite in="fora" in2="dentro" operator="out" />
          {/* the cut-out has soft edges: without this the ring comes out grey and blurred */}
          <feComponentTransfer result="anel">
            <feFuncA type="linear" slope="6" />
          </feComponentTransfer>
          <feTurbulence type="fractalNoise" baseFrequency="0.016" numOctaves="2" seed={sem} result="ruido" />
          <feDisplacementMap in="anel" in2="ruido" scale="26" xChannelSelector="R" yChannelSelector="G" result="tremido" />
          <feFlood floodColor="#fdfdf8" />
          <feComposite in2="tremido" operator="in" />
        </filter>
        <filter id={`tremor-${a}-${sem}`} x="-2%" y="-2%" width="104%" height="104%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed={sem + 40} result="ruido" />
          <feDisplacementMap in="SourceGraphic" in2="ruido" scale="9" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </svg>
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}} filter={`url(#tremor-${a}-${sem})`}>
        {nomes.map((k, i) => {
          const l = lugares[k]!;
          const de = 10 + i * passo;
          return (
            <g key={k} transform={`translate(${l.x} ${l.y}) scale(${l.w / 100} ${l.h / 100})`}>
              <path d={DESENHOS[k].d} pathLength={1} fill="none" stroke={DESENHOS[k].cor} strokeWidth={5.5} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1 1" strokeDashoffset={1 - ease(f, de, de + 12, Easing.linear)} vectorEffect="none" />
            </g>
          );
        })}
      </svg>
      <Recorte c={c} style={{filter: `url(#giz-${a}-${sem})`, opacity: ease(f, 0, 5), transform: `translateY(${desce}px)`}} />
      <Recorte c={c} style={{transform: `translateY(${desce}px)`}} />
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}} filter={`url(#tremor-${a}-${sem})`}>
        {coroa ? (
          <g transform={`translate(${coroa.x - coroa.w / 2} ${coroa.y - coroa.w * 0.45}) scale(${coroa.w / 100} ${(coroa.w * 0.75) / 100})`}>
            <path d={COROA} pathLength={1} fill="none" stroke="#ffd84d" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1 1" strokeDashoffset={1 - ease(f, 2, 14, Easing.linear)} />
          </g>
        ) : null}
        {frase ? (
          <g style={{clipPath: `inset(0 ${(1 - fp) * 100}% 0 0)`}}>
            <text x={tx} y={ty} textAnchor="middle" dominantBaseline="central" fontFamily={est.familia} fontWeight={est.peso} fontStyle={est.italico} fontSize={tam} fill={est.cor} stroke={est.contorno > 0 ? est.corContorno : 'none'} strokeWidth={est.contorno} paintOrder="stroke fill">
              {frase}
            </text>
          </g>
        ) : null}
      </svg>
    </AbsoluteFill>
  );
};

// ============ VERTIGEM ==========================================================
// Dolly zoom: the background of the video itself (rebuilt without the person from several frames, the
// hole filled) grows slowly while the person keeps their size. Dark red background, the person in black
// and white, rays from the centre, a question with a colour shake. Data: pergunta, cor; layout.limpo,
// layout.bloco.
export const Vertigem: React.FC<CenaProps> = ({c, n}) => {
  const {f} = useJanela();
  const s = 1 + 0.42 * ease(f, 0, n, Easing.inOut(Easing.sin));
  const cor: string = c.cor ?? '#8a0b16';
  const est = estiloDe(c, {fonte: 'oswald', cor: '#ffffff', escala: 1, contorno: 0, corContorno: '#000000'});
  const b = c.layout?.bloco ?? {x: W / 2, y: TOPO + 90};
  const [tx, ty] = centro(c, [b.x, b.y]);
  const g = Math.floor(f / 2);
  const dx = (random(`vx${g}`) * 2 - 1) * 7;
  const dy = (random(`vy${g}`) * 2 - 1) * 3;
  return (
    <AbsoluteFill style={{overflow: 'hidden', background: '#1a0205'}}>
      <Fundo src={c.layout?.limpo} reserva="#2a0408" style={{transform: `scale(${s.toFixed(4)})`, filter: 'grayscale(1) contrast(1.12) brightness(.92)'}} />
      <AbsoluteFill style={{background: cor, mixBlendMode: 'multiply'}} />
      <AbsoluteFill style={{background: 'repeating-conic-gradient(from 0deg at 50% 42%, rgba(255,70,60,.15) 0deg 5deg, transparent 5deg 15deg)', transform: `rotate(${f * 0.22}deg) scale(1.6)`, mixBlendMode: 'screen'}} />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse 75% 60% at 50% 42%, transparent 40%, rgba(0,0,0,.72) 100%)'}} />
      <Recorte c={c} style={{filter: 'grayscale(1) contrast(1.18)', transform: `translateY(${Number(c.layout?.desce) || 0}px)`}} />
      {c.pergunta ? (
        <div style={{position: 'absolute', left: tx, top: ty, transform: `translate(-50%, -50%) translate(${dx * 0.3}px, ${dy * 0.3}px)`, whiteSpace: 'nowrap', fontFamily: est.familia, fontWeight: est.peso, fontStyle: est.italico, fontSize: 132 * est.escala, lineHeight: 1, letterSpacing: 1, color: est.cor, textShadow: `${dx}px ${dy}px 0 rgba(255,30,60,.85), ${-dx}px ${-dy}px 0 rgba(40,220,255,.75)`, ...est.traco, opacity: ease(f, 2, 9)}}>
          {c.pergunta}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
