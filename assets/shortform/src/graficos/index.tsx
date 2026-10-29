/**
 * Animated graphics as data: edit-data.json `graficos[]` (references/graficos.md has every type,
 * when to use it and its fields). Nothing about time lives here: each item carries its window
 * (`start`/`end`, cut seconds) and its beats (`at`, `ate`, `*At`), so the editor shows each one as
 * a Phase 2 block and a re-cut moves them (helpers/remapear.py).
 *
 * Default places start below the Reels safe zone (zonaSegura.ts) and stay left of the button
 * column. Colours follow the accent the user picked (hook.accent). The sound of a graphic goes in
 * the final mix (mixar_final.py --sfx), not here.
 */
import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import editData from '../../public/edit-data.json';
import {ZONA_SEGURA} from '../zonaSegura';
import {ACCENT, CL, Cursor, Faisca, Icone, POPPINS, Selecao, TINTA, VERDE, VERMELHO, comAlfa, entra, quadro, sai, tremor} from './comum';

const TOPO = ZONA_SEGURA.topo;

type Base = {start: number; end: number; desligada?: boolean; y?: number};
type ItemPalavra = {t?: string; at: number; ate?: number; cor?: string; contorno?: string; selecao?: {at: number; palavra: string}; pilula?: {cor?: string; icone?: string} | boolean};
type Botao = {t: string; icone?: string; at: number; ate?: number};
export type Grafico = Base &
  (
    | {tipo: 'palavras'; tamanho?: number; cor?: string; itens: ItemPalavra[]}
    | {tipo: 'botoes'; itens: Botao[]}
    | {tipo: 'celular'; src: string; x?: number; w?: number; rot?: number}
    | {tipo: 'objecao'; usuario: string; texto: string; quando?: string; cinza?: boolean}
    | {tipo: 'grande'; t: string; at?: number; tamanho?: number; cor?: string; contorno?: string; riscoAt?: number; sub?: string}
    | {tipo: 'lista'; titulo: string; itens: {t: string; at: number}[]}
    | {tipo: 'selo'; src: string; fundo?: string}
    | {tipo: 'ajuste'; titulo?: string; src?: string}
    | {tipo: 'progresso'; titulo: string; fimAt: number; fim: string}
    | {tipo: 'comenta'; texto: string; digitaAt: number; digitaFimAt: number; dmAt?: number; dm?: string; placeholder?: string; publicar?: string; seta?: {x: number; y: number}}
  );
type De<T extends Grafico['tipo']> = Extract<Grafico, {tipo: T}>;

/** The item showing now in a list of beats: each one lasts until its `ate`, the next `at` or the end. */
const daVez = <T extends {at: number; ate?: number}>(itens: T[], fim: number, f: number, fps: number): T | null => {
  for (let i = 0; i < itens.length; i++) {
    const a = quadro(fps, itens[i].at);
    const b = quadro(fps, itens[i].ate ?? itens[i + 1]?.at ?? fim);
    if (f >= a && f < b) return itens[i];
  }
  return null;
};

const useJanela = (g: Base) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return {f, fps, a: quadro(fps, g.start), b: quadro(fps, g.end)};
};

// ---- one word per beat of the speech, coming in blurred and settling; a pill (icon + name) or a
// selection box around a word are options of the item
const Palavras: React.FC<{g: De<'palavras'>}> = ({g}) => {
  const {f, fps, b} = useJanela(g);
  const it = daVez(g.itens, g.end, f, fps);
  if (!it || f >= b) return null;
  const a = quadro(fps, it.at);
  const k = entra(f, a, 5);
  const y = g.y ?? TOPO + 150;
  const tam = g.tamanho ?? 140;
  if (it.pilula) {
    const p = typeof it.pilula === 'object' ? it.pilula : {};
    const m = spring({frame: f - a, fps, config: {damping: 11, stiffness: 190, mass: 0.7}});
    return (
      <AbsoluteFill style={{pointerEvents: 'none'}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: y - 95, display: 'flex', justifyContent: 'center'}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 22, background: p.cor ?? ACCENT, borderRadius: 999, padding: '20px 56px 24px 36px', boxShadow: '0 18px 50px rgba(0,0,0,.35)', scale: String(0.4 + 0.6 * m), rotate: `${(1 - m) * -8}deg`, opacity: Math.min(1, m * 1.5)}}>
            {p.icone === undefined || p.icone === 'ia' ? (
              <svg width={120} height={120} viewBox="0 0 24 24"><Faisca cor="white" /></svg>
            ) : p.icone ? (
              <Icone nome={p.icone} px={190} />
            ) : null}
            <div style={{fontFamily: POPPINS, fontWeight: 700, fontSize: 118, color: 'white', letterSpacing: -2, lineHeight: 1}}>{it.t}</div>
          </div>
        </div>
      </AbsoluteFill>
    );
  }
  const palavras = (it.t ?? '').split(' ');
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: y - tam * 0.62, display: 'flex', justifyContent: 'center', gap: tam * 0.26, fontFamily: POPPINS, fontWeight: 900, fontSize: tam, letterSpacing: -3, lineHeight: 1.15, color: it.cor ?? g.cor ?? '#111', ...(it.contorno ? {WebkitTextStroke: `${tam * 0.07}px ${it.contorno}`, paintOrder: 'stroke fill', textShadow: '0 10px 28px rgba(0,0,0,.35)'} : {}), filter: `blur(${((1 - k) * 16).toFixed(1)}px)`, scale: String(1.2 - 0.2 * k), opacity: k}}>
        {palavras.map((w, i) => (
          <span key={i} style={{position: 'relative'}}>
            {w}
            {it.selecao && it.selecao.palavra === w ? <Selecao f={f - quadro(fps, it.selecao.at)} /> : null}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// ---- accent buttons, one at a time, with the cursor clicking each
const Botoes: React.FC<{g: De<'botoes'>}> = ({g}) => {
  const {f, fps, b} = useJanela(g);
  const it = daVez(g.itens, g.end, f, fps);
  if (!it || f >= b) return null;
  const a = quadro(fps, it.at);
  const m = spring({frame: f - a, fps, config: {damping: 12, stiffness: 220, mass: 0.6}});
  const clique = f >= a + 8 && f < a + 11;
  const onda = interpolate(f, [a + 8, a + 18], [0, 1], CL);
  const cx = interpolate(f, [a + 1, a + 8], [300, 0], {...CL, easing: Easing.out(Easing.cubic)});
  const cy = interpolate(f, [a + 1, a + 8], [220, 0], {...CL, easing: Easing.out(Easing.cubic)});
  const y = g.y ?? TOPO + 130;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: y - 66, display: 'flex', justifyContent: 'center', opacity: sai(f, b, 5)}}>
        <div style={{position: 'relative', scale: String((0.55 + 0.45 * m) * (clique ? 0.94 : 1)), translate: `0px ${(1 - m) * 40}px`}}>
          <div style={{position: 'absolute', inset: 0, borderRadius: 999, border: `6px solid ${ACCENT}`, scale: String(1 + onda * 0.35), opacity: (1 - onda) * (onda > 0 ? 0.9 : 0)}} />
          <div style={{display: 'flex', alignItems: 'center', gap: 24, background: ACCENT, borderRadius: 999, padding: '20px 58px 20px 20px', boxShadow: `0 0 0 6px ${comAlfa(ACCENT, 0.22)}, 0 0 70px ${comAlfa(ACCENT, 0.7)}, 0 16px 40px rgba(0,0,0,.35)`}}>
            <div style={{width: 92, height: 92, borderRadius: 999, background: TINTA, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: POPPINS}}>
              <Icone nome={it.icone} px={92} />
            </div>
            <div style={{fontFamily: POPPINS, fontWeight: 800, fontSize: 62, color: TINTA, letterSpacing: -1, whiteSpace: 'nowrap', lineHeight: 1}}>{it.t}</div>
          </div>
          <Cursor x={`calc(100% - 130px + ${cx.toFixed(1)}px)`} y={70 + cy} apertado={clique} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- a screen (an image from public/) inside a drawn phone, sliding in from the right
const Celular: React.FC<{g: De<'celular'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const m = spring({frame: f - a, fps, config: {damping: 14, stiffness: 160, mass: 0.8}});
  const w = g.w ?? 300;
  const h = w / 0.462;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: g.x ?? 550, top: g.y ?? TOPO + 40, width: w + 28, height: h + 28, borderRadius: 64, background: '#0b0b0d', padding: 14, boxSizing: 'border-box', boxShadow: '0 30px 70px rgba(0,0,0,.5), inset 0 0 0 3px #2b2b30', translate: `${(1 - m) * 520}px 0px`, rotate: `${(g.rot ?? 7) + (1 - m) * 10}deg`, opacity: sai(f, b, 5)}}>
        <Img src={staticFile(g.src)} style={{width: '100%', height: '100%', objectFit: 'cover', borderRadius: 52}} />
      </div>
    </AbsoluteFill>
  );
};

// ---- an objection: the picture loses its colour and the sentence becomes a viewer's comment
const Objecao: React.FC<{g: De<'objecao'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const c = a + 4;
  const m = spring({frame: f - c, fps, config: {damping: 12, stiffness: 200, mass: 0.7}});
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {g.cinza !== false ? (
        <>
          <AbsoluteFill style={{backdropFilter: 'grayscale(1) contrast(1.12) brightness(0.9)'}} />
          <AbsoluteFill style={{background: 'radial-gradient(ellipse at 45% 45%, rgba(0,0,0,0) 45%, rgba(0,0,0,.55) 100%)'}} />
        </>
      ) : null}
      {f >= c ? (
        <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 30, width: 860, display: 'flex', gap: 26, alignItems: 'flex-start', background: 'white', borderRadius: 40, padding: '30px 36px', boxSizing: 'border-box', boxShadow: '0 24px 60px rgba(0,0,0,.45)', fontFamily: POPPINS, transformOrigin: 'left top', scale: String(0.6 + 0.4 * m), rotate: `${-2 + (1 - m) * -6}deg`, opacity: Math.min(1, m * 1.4)}}>
          <div style={{flex: '0 0 auto', width: 92, height: 92, borderRadius: 999, background: 'linear-gradient(135deg,#bdbdc4,#7c7c86)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 800, fontSize: 48}}>?</div>
          <div style={{flex: 1}}>
            <div style={{fontWeight: 700, fontSize: 34, color: '#111'}}>
              {g.usuario} <span style={{fontWeight: 400, color: '#8a8a8a'}}>{g.quando ?? 'agora'}</span>
            </div>
            <div style={{fontWeight: 600, fontSize: 48, color: '#111', lineHeight: 1.18, marginTop: 6}}>{g.texto}</div>
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

// ---- a big word that lands (falls from a bigger size and shakes); `riscoAt` strikes it in red
const Grande: React.FC<{g: De<'grande'>}> = ({g}) => {
  const {f, fps, a: a0, b} = useJanela(g);
  const a = g.at !== undefined ? quadro(fps, g.at) : a0;
  if (f < a || f >= b) return null;
  const k = entra(f, a, 5);
  const esc = 2.3 - 1.3 * k;
  const r = g.riscoAt !== undefined ? quadro(fps, g.riscoAt) : null;
  const pr = r === null ? 0 : interpolate(f, [r, r + 5], [0, 1], {...CL, easing: Easing.out(Easing.cubic)});
  const tam = g.tamanho ?? 170;
  const sx = tremor(f, a + 5) + (r === null ? 0 : tremor(f, r + 4, 7));
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: (g.y ?? TOPO + 160) - tam * 0.6, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: interpolate(f, [a, a + 2], [0, 1], CL) * sai(f, b, 4), translate: `${sx}px 0px`}}>
        {g.sub ? <div style={{fontFamily: POPPINS, fontWeight: 800, fontSize: 64, color: 'white', WebkitTextStroke: '9px #111', paintOrder: 'stroke fill', marginBottom: -10, letterSpacing: -1}}>{g.sub}</div> : null}
        <div style={{position: 'relative', scale: String(esc)}}>
          <div style={{fontFamily: POPPINS, fontWeight: 900, fontSize: tam, color: g.cor ?? 'white', WebkitTextStroke: `${tam * 0.075}px ${g.contorno ?? '#111'}`, paintOrder: 'stroke fill', letterSpacing: -4, wordSpacing: tam * 0.18, lineHeight: 1.05, whiteSpace: 'nowrap', textShadow: '0 12px 30px rgba(0,0,0,.35)', opacity: 1 - 0.25 * pr}}>{g.t}</div>
          {r !== null && f >= r ? (
            <div style={{position: 'absolute', left: '-5%', top: '47%', height: tam * 0.12, width: `${110 * pr}%`, background: VERMELHO, borderRadius: 999, rotate: '-5deg', transformOrigin: 'left center', boxShadow: '0 4px 14px rgba(0,0,0,.35)'}} />
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- a dark card: each item comes in with a red X
const Lista: React.FC<{g: De<'lista'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const m = spring({frame: f - a, fps, config: {damping: 14, stiffness: 180, mass: 0.7}});
  const fim = interpolate(f, [b - 6, b], [0, 1], CL);
  const vistos = g.itens.filter((i) => f >= quadro(fps, i.at));
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 60, top: g.y ?? TOPO + 30, width: 860, background: 'rgba(14,14,16,.93)', borderRadius: 40, padding: '30px 42px 22px', boxSizing: 'border-box', border: '2px solid rgba(255,255,255,.08)', boxShadow: '0 24px 60px rgba(0,0,0,.45)', fontFamily: POPPINS, scale: String(0.8 + 0.2 * m), opacity: Math.min(1, m * 1.4) * (1 - fim), translate: `0px ${(1 - m) * -30 - fim * 40}px`}}>
        <div style={{fontWeight: 800, fontSize: 34, letterSpacing: 4, color: ACCENT, marginBottom: 14}}>{g.titulo}</div>
        {vistos.map((i, n) => {
          const k = entra(f, quadro(fps, i.at), 6);
          return (
            <div key={n} style={{display: 'flex', alignItems: 'center', gap: 24, padding: '10px 0', opacity: k, translate: `${(1 - k) * -50}px 0px`}}>
              <div style={{flex: '0 0 auto', width: 62, height: 62, borderRadius: 999, background: VERMELHO, display: 'flex', alignItems: 'center', justifyContent: 'center', scale: String(0.5 + 0.5 * k)}}>
                <svg width={34} height={34} viewBox="0 0 24 24"><path d="M5 5 L19 19 M19 5 L5 19" stroke="white" strokeWidth={4} strokeLinecap="round" /></svg>
              </div>
              <div style={{fontWeight: 700, fontSize: 52, color: 'white', letterSpacing: -1}}>{i.t}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---- a logo (an image from public/) on a dark seal
const Selo: React.FC<{g: De<'selo'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const m = spring({frame: f - a, fps, config: {damping: 12, stiffness: 200, mass: 0.7}});
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: (g.y ?? TOPO + 140) - 85, display: 'flex', justifyContent: 'center'}}>
        <div style={{background: g.fundo ?? '#101010', borderRadius: 999, padding: '30px 60px', boxShadow: `0 0 0 5px ${comAlfa(ACCENT, 0.5)}, 0 18px 50px rgba(0,0,0,.45)`, scale: String(0.5 + 0.5 * m), opacity: Math.min(1, m * 1.5) * sai(f, b, 3)}}>
          <Img src={staticFile(g.src)} style={{height: 110, maxWidth: 760, objectFit: 'contain', display: 'block'}} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- trimming by hand: the edge of a clip pulled by the cursor on a timeline
const Ajuste: React.FC<{g: De<'ajuste'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const k = entra(f, a, 7);
  const l = f - a;
  const arrasto = interpolate(l, [14, 30], [0, -110], {...CL, easing: Easing.inOut(Easing.cubic)});
  const pega = l >= 12 && l < 32;
  const cx = interpolate(l, [3, 12], [560, 452], {...CL, easing: Easing.out(Easing.cubic)}) + arrasto;
  const cy = interpolate(l, [3, 12], [260, 118], {...CL, easing: Easing.out(Easing.cubic)});
  const chips = [180, 300 + arrasto, 210];
  let x = 0;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 90, top: g.y ?? TOPO + 40, width: 840, height: 300, background: 'rgba(14,14,16,.94)', borderRadius: 36, border: '2px solid rgba(255,255,255,.08)', boxShadow: '0 24px 60px rgba(0,0,0,.45)', fontFamily: POPPINS, opacity: k * sai(f, b, 5), scale: String(0.9 + 0.1 * k)}}>
        <div style={{position: 'absolute', left: 40, top: 30, display: 'flex', alignItems: 'center', gap: 14, fontWeight: 700, fontSize: 32, color: 'white'}}>
          <div style={{width: 16, height: 16, borderRadius: 99, background: ACCENT}} />
          {g.titulo ?? 'linha do tempo'}
        </div>
        <div style={{position: 'absolute', left: 40, top: 100, width: 760, height: 110}}>
          {chips.map((w, i) => {
            const left = x;
            x += w + 10;
            const ativo = i === 1;
            const fundo = g.src
              ? {backgroundImage: `url(${staticFile(g.src)})`, backgroundSize: 'auto 100%', backgroundRepeat: 'repeat-x'}
              : {background: `linear-gradient(135deg, ${comAlfa(ACCENT, 0.55)}, ${comAlfa(ACCENT, 0.18)})`};
            return (
              <div key={i} style={{position: 'absolute', left, width: w, height: 110, borderRadius: 14, ...fundo, opacity: ativo ? 1 : 0.55, border: ativo ? `4px solid ${pega ? 'white' : ACCENT}` : '2px solid #3a3a40', boxSizing: 'border-box', overflow: 'visible'}}>
                {ativo ? <div style={{position: 'absolute', right: -4, top: -4, bottom: -4, width: 22, borderRadius: '0 12px 12px 0', background: pega ? 'white' : ACCENT}} /> : null}
              </div>
            );
          })}
        </div>
        <div style={{position: 'absolute', left: 40, top: 232, width: 760, height: 30, display: 'flex', gap: 3, alignItems: 'center'}}>
          {Array.from({length: 56}).map((_, i) => (
            <div key={i} style={{flex: 1, height: 6 + 22 * Math.abs(Math.sin(i * 1.7)) * Math.abs(Math.cos(i * 0.6)), background: '#5c5c66', borderRadius: 3}} />
          ))}
        </div>
        <Cursor x={cx} y={cy} apertado={pega} />
      </div>
    </AbsoluteFill>
  );
};

// ---- a bar that fills and closes with a green word at `fimAt`
const Progresso: React.FC<{g: De<'progresso'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const z = quadro(fps, g.fimAt);
  const k = entra(f, a, 7);
  const p = interpolate(f, [a + 6, z], [0, 1], {...CL, easing: Easing.inOut(Easing.quad)});
  const ok = spring({frame: f - z, fps, config: {damping: 11, stiffness: 220, mass: 0.6}});
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 40, width: 860, background: 'rgba(14,14,16,.94)', borderRadius: 40, padding: '34px 44px 36px', boxSizing: 'border-box', border: '2px solid rgba(255,255,255,.08)', boxShadow: '0 24px 60px rgba(0,0,0,.45)', fontFamily: POPPINS, opacity: k * sai(f, b, 5), translate: `0px ${(1 - k) * -30}px`}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 18, fontWeight: 700, fontSize: 44, color: 'white', letterSpacing: -1}}>
          <svg width={52} height={52} viewBox="0 0 24 24"><Faisca cor={ACCENT} /></svg>
          {g.titulo}
        </div>
        <div style={{marginTop: 26, height: 34, borderRadius: 99, background: '#2a2a2f', overflow: 'hidden'}}>
          <div style={{height: '100%', width: `${p * 100}%`, borderRadius: 99, background: `linear-gradient(90deg, ${ACCENT}, ${comAlfa(ACCENT, 0.55)})`}} />
        </div>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 18, height: 64}}>
          <div style={{fontWeight: 600, fontSize: 36, color: '#a6a6a6'}}>{Math.round(p * 100)}%</div>
          {f >= z ? <div style={{fontWeight: 800, fontSize: 52, color: VERDE, scale: String(0.5 + 0.5 * ok), opacity: Math.min(1, ok * 1.5)}}>{g.fim}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- "comment X": the comment box typing, an arrow down to the comments and the direct pill
const Comenta: React.FC<{g: De<'comenta'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const k = spring({frame: f - a, fps, config: {damping: 13, stiffness: 190, mass: 0.7}});
  const n = Math.round(interpolate(f, [quadro(fps, g.digitaAt), quadro(fps, g.digitaFimAt)], [0, g.texto.length], CL));
  const pronto = n >= g.texto.length;
  const pisca = Math.floor(f / 8) % 2 === 0;
  const y = g.y ?? TOPO + 40;
  const dmA = g.dmAt !== undefined ? quadro(fps, g.dmAt) : null;
  const dm = dmA === null ? 0 : spring({frame: f - dmA, fps, config: {damping: 12, stiffness: 200, mass: 0.6}});
  const quica = Math.abs(Math.sin((f - a) * 0.3)) * 26;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 60, top: y, width: 870, height: 130, borderRadius: 999, background: 'white', display: 'flex', alignItems: 'center', gap: 22, padding: '0 40px 0 22px', boxSizing: 'border-box', boxShadow: '0 22px 55px rgba(0,0,0,.45)', fontFamily: POPPINS, scale: String(0.7 + 0.3 * k), opacity: Math.min(1, k * 1.5)}}>
        <div style={{flex: '0 0 auto', width: 86, height: 86, borderRadius: 999, background: `linear-gradient(135deg, ${ACCENT}, ${comAlfa(ACCENT, 0.55)})`}} />
        <div style={{flex: 1, overflow: 'hidden', fontSize: 52, fontWeight: n ? 800 : 500, color: n ? '#111' : '#9a9a9a', letterSpacing: n ? 1 : 0, whiteSpace: 'nowrap'}}>
          {n ? g.texto.slice(0, n) : g.placeholder ?? 'Adicione um comentário...'}
          {n && !pronto && pisca ? <span style={{color: ACCENT}}>|</span> : null}
        </div>
        <div style={{fontSize: 38, fontWeight: 700, color: pronto ? '#0095F6' : '#b9dcf8'}}>{g.publicar ?? 'Publicar'}</div>
      </div>
      {g.seta ? (
        // points DOWN (to the comments): the tip sits on (seta.x, seta.y) and it bounces vertically
        <svg width={180} height={300} viewBox="0 0 60 100" style={{position: 'absolute', left: g.seta.x - 90, top: g.seta.y - 290 + quica, opacity: Math.min(1, k * 1.5), filter: 'drop-shadow(0 8px 14px rgba(0,0,0,.45))'}}>
          <path d="M30 6 C 22 34, 38 60, 30 90" fill="none" stroke={ACCENT} strokeWidth={8} strokeLinecap="round" />
          <path d="M15 76 L30 94 L45 76" fill="none" stroke={ACCENT} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : null}
      {dmA !== null && f >= dmA ? (
        <div style={{position: 'absolute', left: 0, right: 150, top: y + 170, display: 'flex', justifyContent: 'center'}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 20, background: '#101010', borderRadius: 999, padding: '22px 46px 22px 30px', boxShadow: '0 18px 45px rgba(0,0,0,.45)', fontFamily: POPPINS, scale: String(0.5 + 0.5 * dm), opacity: Math.min(1, dm * 1.5), translate: `${(1 - dm) * 120}px 0px`}}>
            <svg width={64} height={64} viewBox="0 0 24 24"><path d="M21.5 3 L2.8 10.2 L9.6 12.9 L12.2 20 Z M21.5 3 L9.6 12.9" fill="none" stroke="white" strokeWidth={2} strokeLinejoin="round" /></svg>
            <div style={{fontWeight: 800, fontSize: 54, color: 'white', letterSpacing: -1}}>{g.dm ?? 'direct'}</div>
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

// the types helpers/graficos.py validates (TIPOS there; tests/test_graficos.py keeps both equal)
export const TIPOS: Record<Grafico['tipo'], React.FC<{g: any}>> = {
  palavras: Palavras,
  botoes: Botoes,
  celular: Celular,
  objecao: Objecao,
  grande: Grande,
  lista: Lista,
  selo: Selo,
  ajuste: Ajuste,
  progresso: Progresso,
  comenta: Comenta,
};

const W = 1080;
const H = 1920;

export const Graficos: React.FC = () => {
  const {width} = useVideoConfig();
  const lista = ((editData as unknown as {graficos?: Grafico[]}).graficos ?? []).filter((g) => g && !g.desligada && TIPOS[g.tipo]);
  if (!lista.length) return null;
  return (
    <AbsoluteFill style={width === W ? {pointerEvents: 'none'} : {pointerEvents: 'none', width: W, height: H, transform: `scale(${width / W})`, transformOrigin: '0 0'}}>
      {lista.map((g, i) => {
        const Comp = TIPOS[g.tipo];
        return <Comp key={i} g={g} />;
      })}
    </AbsoluteFill>
  );
};
