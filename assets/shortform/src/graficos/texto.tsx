/**
 * The moving-type graphics of `graficos[]` (references/graficos.md): text that bounces with the voice,
 * letters that dance, a glitch, a counter, a highlighter, a chat, a typewriter. Same rules as
 * index.tsx: each item carries its window and its beats, the default places sit inside the Reels safe
 * zone and the colours follow the accent the user picked. Sound goes in the final mix.
 */
import React from 'react';
import {AbsoluteFill, Easing, interpolate, random, spring} from 'remotion';
import {ZONA_SEGURA} from '../zonaSegura';
import {ACCENT, Base, CL, Faisca, POPPINS, TINTA, comAlfa, entra, quadro, sai, tremor, useJanela} from './comum';

const TOPO = ZONA_SEGURA.topo;
const PILHA_MONO = '"Courier New", Courier, monospace';
const PILHA_EMOJI = '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif';

export type GraficoTexto = Base &
  (
    | {tipo: 'pula'; tamanho?: number; itens: {t: string; at: number}[]}
    | {tipo: 'partes'; tamanho?: number; itens: {t: string; at: number; cor?: string}[]}
    | {tipo: 'danca'; t: string; sub?: string; at?: number; tamanho?: number}
    | {tipo: 'glitch'; t: string; at?: number; tamanho?: number}
    | {tipo: 'marca'; texto: string; frase?: string; marcaAt: number; marcaFimAt: number; cor?: string}
    | {tipo: 'contador'; valor: number; inicio?: number; casas?: number; prefixo?: string; sufixo?: string; rotulo?: string; fimAt: number; tamanho?: number; local?: string}
    | {tipo: 'nome'; nome: string; cargo?: string}
    | {tipo: 'chat'; itens: {t: string; at: number; lado?: 'eu' | 'outro'}[]}
    | {tipo: 'maquina'; texto: string; digitaAt: number; digitaFimAt: number}
    | {tipo: 'prompt'; texto: string; titulo?: string; digitaAt: number; digitaFimAt: number}
    | {tipo: 'emoji'; tamanho?: number; itens: {t: string; at: number; ate?: number; x?: number; y?: number}[]}
  );
type De<T extends GraficoTexto['tipo']> = Extract<GraficoTexto, {tipo: T}>;

const contornado = (tam: number, cor = '#111'): React.CSSProperties => ({
  WebkitTextStroke: `${tam * 0.07}px ${cor}`,
  paintOrder: 'stroke fill',
  textShadow: '0 10px 28px rgba(0,0,0,.35)',
});

// ---- the phrase said word by word: each word jumps in when spoken, the one being said in the accent
export const Pula: React.FC<{g: De<'pula'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const tam = g.tamanho ?? 92;
  const atual = g.itens.reduce((u, it, i) => (f >= quadro(fps, it.at) ? i : u), -1);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 60, width: 860, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', columnGap: tam * 0.26, rowGap: tam * 0.04, fontFamily: POPPINS, fontWeight: 900, fontSize: tam, letterSpacing: -2, lineHeight: 1.14, opacity: sai(f, b, 4), ...contornado(tam)}}>
        {g.itens.map((it, i) => {
          const w = quadro(fps, it.at);
          const m = spring({frame: f - w, fps, config: {damping: 9, stiffness: 260, mass: 0.55}});
          return (
            <span key={i} style={{display: 'inline-block', visibility: f >= w ? 'visible' : 'hidden', color: i === atual ? ACCENT : 'white', scale: String(0.5 + 0.5 * m), translate: `0px ${(1 - m) * 54}px`}}>
              {it.t}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---- a text that comes in by parts, each one on its word, and leaves all together at the end
export const Partes: React.FC<{g: De<'partes'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const tam = g.tamanho ?? 130;
  const fim = interpolate(f, [b - 5, b], [0, 1], CL);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: g.y ?? TOPO + 60, display: 'flex', flexDirection: 'column', alignItems: 'center', fontFamily: POPPINS, fontWeight: 900, fontSize: tam, letterSpacing: -3, lineHeight: 1.12, opacity: 1 - fim, translate: `0px ${fim * -36}px`, ...contornado(tam)}}>
        {g.itens.map((it, i) => {
          const w = quadro(fps, it.at);
          const k = entra(f, w, 5);
          return (
            <div key={i} style={{whiteSpace: 'nowrap', visibility: f >= w ? 'visible' : 'hidden', color: it.cor ?? (i % 2 ? ACCENT : 'white'), scale: String(1.5 - 0.5 * k), opacity: k, translate: `${tremor(f, w + 5, 9)}px 0px`}}>
              {it.t}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---- letters that come in one by one and keep dancing
export const Danca: React.FC<{g: De<'danca'>}> = ({g}) => {
  const {f, fps, a: a0, b} = useJanela(g);
  const a = g.at !== undefined ? quadro(fps, g.at) : a0;
  if (f < a || f >= b) return null;
  const tam = g.tamanho ?? 150;
  const l = f - a;
  const k = entra(f, a + 8, 8);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: g.y ?? TOPO + 60, display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: sai(f, b, 5)}}>
        <div style={{display: 'flex', fontFamily: POPPINS, fontWeight: 900, fontSize: tam, letterSpacing: -2, lineHeight: 1.1, whiteSpace: 'pre', ...contornado(tam)}}>
          {[...g.t].map((c, i) => {
            const e = spring({frame: l - i * 1.5, fps, config: {damping: 10, stiffness: 200, mass: 0.6}});
            const onda = Math.sin(l * 0.2 + i * 0.75) * tam * 0.07;
            const giro = Math.sin(l * 0.14 + i * 1.2) * 4.5 + (1 - e) * (i % 2 ? 16 : -16);
            return (
              <span key={i} style={{display: 'inline-block', color: i % 3 === 1 ? ACCENT : 'white', translate: `0px ${(1 - e) * tam * 0.9 + onda}px`, rotate: `${giro}deg`, scale: String(0.6 + 0.4 * e), opacity: Math.min(1, e * 1.6)}}>
                {c}
              </span>
            );
          })}
        </div>
        {g.sub ? <div style={{fontFamily: POPPINS, fontStyle: 'italic', fontWeight: 700, fontSize: tam * 0.42, color: ACCENT, opacity: k, marginTop: tam * 0.02, ...contornado(tam * 0.5)}}>{g.sub}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

// ---- a title that breaks into shifted slices in colour, hard on the way in and then in short bursts
const FATIAS = 6;
export const Glitch: React.FC<{g: De<'glitch'>}> = ({g}) => {
  const {f, fps, a: a0, b} = useJanela(g);
  const a = g.at !== undefined ? quadro(fps, g.at) : a0;
  if (f < a || f >= b) return null;
  const tam = g.tamanho ?? 170;
  const l = f - a;
  const surto = l < 10 || l % 22 < 4;
  const desvio = (k: string, m: number) => (surto ? (random(`${k}-${f}`) - 0.5) * m : 0);
  const letra: React.CSSProperties = {fontFamily: POPPINS, fontWeight: 900, fontSize: tam, letterSpacing: -4, lineHeight: 1.05, whiteSpace: 'nowrap'};
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: g.y ?? TOPO + 70, display: 'flex', justifyContent: 'center', opacity: interpolate(f, [a, a + 2], [0, 1], CL) * sai(f, b, 3)}}>
        <div style={{position: 'relative'}}>
          <div style={{...letra, visibility: 'hidden'}}>{g.t}</div>
          {Array.from({length: FATIAS}).map((_, i) => {
            const corte = `inset(${(i / FATIAS) * 100}% -20% ${100 - ((i + 1) / FATIAS) * 100}% -20%)`;
            const x = desvio(`x${i}`, tam * 0.5);
            return (
              <React.Fragment key={i}>
                <div style={{...letra, position: 'absolute', left: 0, top: 0, color: '#00f0ff', clipPath: corte, translate: `${x + desvio(`c${i}`, tam * 0.1) - (surto ? tam * 0.04 : tam * 0.012)}px 0px`}}>{g.t}</div>
                <div style={{...letra, position: 'absolute', left: 0, top: 0, color: '#ff0050', clipPath: corte, translate: `${x + desvio(`m${i}`, tam * 0.1) + (surto ? tam * 0.04 : tam * 0.012)}px 0px`}}>{g.t}</div>
                <div style={{...letra, position: 'absolute', left: 0, top: 0, color: 'white', clipPath: corte, translate: `${x}px 0px`}}>{g.t}</div>
              </React.Fragment>
            );
          })}
          {surto
            ? [0, 1, 2].map((i) => (
                <div key={i} style={{position: 'absolute', left: `${random(`bx${i}-${f}`) * 60 - 10}%`, top: `${random(`by${i}-${f}`) * 100}%`, width: `${30 + random(`bw${i}-${f}`) * 60}%`, height: tam * 0.035, background: i === 1 ? ACCENT : 'white', opacity: 0.85}} />
              ))
            : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- a white card with the sentence; the highlighter runs over the phrase that matters
export const Marca: React.FC<{g: De<'marca'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const m = spring({frame: f - a, fps, config: {damping: 14, stiffness: 190, mass: 0.7}});
  const p = interpolate(f, [quadro(fps, g.marcaAt), quadro(fps, g.marcaFimAt)], [0, 100], {...CL, easing: Easing.inOut(Easing.quad)});
  const i = g.frase ? g.texto.toLowerCase().indexOf(g.frase.toLowerCase()) : -1;
  const antes = i >= 0 ? g.texto.slice(0, i) : '';
  const meio = i >= 0 ? g.texto.slice(i, i + (g.frase ?? '').length) : g.texto;
  const depois = i >= 0 ? g.texto.slice(i + (g.frase ?? '').length) : '';
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 40, width: 860, background: 'white', borderRadius: 30, padding: '34px 42px', boxSizing: 'border-box', boxShadow: '0 24px 60px rgba(0,0,0,.45)', fontFamily: POPPINS, fontWeight: 700, fontSize: 58, lineHeight: 1.24, letterSpacing: -1, color: '#111', transformOrigin: 'left top', scale: String(0.8 + 0.2 * m), opacity: Math.min(1, m * 1.4) * sai(f, b, 5)}}>
        {antes}
        <span style={{backgroundImage: `linear-gradient(${g.cor ?? comAlfa(ACCENT, 0.5)}, ${g.cor ?? comAlfa(ACCENT, 0.5)})`, backgroundRepeat: 'no-repeat', backgroundSize: `${p}% 100%`, borderRadius: 8}}>{meio}</span>
        {depois}
      </div>
    </AbsoluteFill>
  );
};

// ---- a number climbing to its value at `fimAt`, with a label under it
export const Contador: React.FC<{g: De<'contador'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const z = quadro(fps, g.fimAt);
  const n = interpolate(f, [a + 3, z], [g.inicio ?? 0, g.valor], {...CL, easing: Easing.out(Easing.cubic)});
  const casas = g.casas ?? 0;
  const texto = new Intl.NumberFormat(g.local ?? 'pt-BR', {minimumFractionDigits: casas, maximumFractionDigits: casas}).format(n);
  const tam = g.tamanho ?? 190;
  const m = spring({frame: f - a, fps, config: {damping: 13, stiffness: 190, mass: 0.7}});
  const fim = f >= z ? spring({frame: f - z, fps, config: {damping: 8, stiffness: 280, mass: 0.5}}) : 0;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: g.y ?? TOPO + 60, display: 'flex', flexDirection: 'column', alignItems: 'center', fontFamily: POPPINS, opacity: Math.min(1, m * 1.5) * sai(f, b, 5), scale: String(0.75 + 0.25 * m)}}>
        <div style={{fontWeight: 900, fontSize: tam, lineHeight: 1.05, letterSpacing: -4, color: 'white', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', scale: String(1 + 0.1 * Math.sin(fim * Math.PI)), ...contornado(tam)}}>
          {g.prefixo ?? ''}
          {texto}
          {g.sufixo ?? ''}
        </div>
        {g.rotulo ? <div style={{fontWeight: 800, fontSize: 52, letterSpacing: 6, color: ACCENT, whiteSpace: 'nowrap', marginTop: 4, ...contornado(52)}}>{g.rotulo}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

// ---- name and role coming in at the corner, with the bar in the accent
export const Nome: React.FC<{g: De<'nome'>}> = ({g}) => {
  const {f, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const m = entra(f, a, 10);
  const s = interpolate(f, [b - 7, b], [0, 1], {...CL, easing: Easing.in(Easing.cubic)});
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 900, maxWidth: 840, display: 'flex', alignItems: 'stretch', fontFamily: POPPINS, clipPath: `inset(-10px ${Math.max((1 - m) * 100, s * 100)}% -10px 0)`, translate: `${(1 - m) * -60}px 0px`}}>
        <div style={{flex: '0 0 auto', width: 14, borderRadius: 7, background: ACCENT, marginRight: 22}} />
        <div style={{background: 'rgba(14,14,16,.92)', borderRadius: 22, padding: '20px 40px 22px', boxShadow: '0 18px 44px rgba(0,0,0,.4)'}}>
          <div style={{fontWeight: 800, fontSize: 62, lineHeight: 1.12, letterSpacing: -1, color: 'white', whiteSpace: 'nowrap'}}>{g.nome}</div>
          {g.cargo ? <div style={{fontWeight: 500, fontSize: 36, lineHeight: 1.2, color: '#bdbdc4', whiteSpace: 'nowrap', marginTop: 2}}>{g.cargo}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- a conversation, message by message; the other side shows the typing dots first
export const Chat: React.FC<{g: De<'chat'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const bolhas = g.itens.map((it, i) => ({...it, eu: it.lado ? it.lado === 'eu' : i % 2 === 1, w: quadro(fps, it.at)}));
  const vistos = bolhas.filter((x) => f >= x.w).slice(-4);
  const proxima = bolhas.find((x) => f < x.w);
  const anterior = proxima ? bolhas.filter((x) => x.w <= f).pop()?.w ?? a : a;
  const digitando = proxima && !proxima.eu && f >= proxima.w - 14 && proxima.w - 14 >= anterior + 6;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 30, width: 860, display: 'flex', flexDirection: 'column', gap: 18, fontFamily: POPPINS, opacity: sai(f, b, 5)}}>
        {vistos.map((x) => {
          const m = spring({frame: f - x.w, fps, config: {damping: 13, stiffness: 240, mass: 0.6}});
          return (
            <div key={x.w} style={{alignSelf: x.eu ? 'flex-end' : 'flex-start', maxWidth: 680, background: x.eu ? ACCENT : 'rgba(38,38,44,.96)', color: x.eu ? TINTA : 'white', borderRadius: 40, ...(x.eu ? {borderBottomRightRadius: 10} : {borderBottomLeftRadius: 10}), padding: '22px 36px 24px', fontWeight: 600, fontSize: 48, lineHeight: 1.2, boxShadow: '0 14px 36px rgba(0,0,0,.4)', transformOrigin: x.eu ? 'right bottom' : 'left bottom', scale: String(0.7 + 0.3 * m), translate: `0px ${(1 - m) * 30}px`, opacity: Math.min(1, m * 1.6)}}>
              {x.t}
            </div>
          );
        })}
        {digitando ? (
          <div style={{alignSelf: 'flex-start', display: 'flex', gap: 10, background: 'rgba(38,38,44,.96)', borderRadius: 40, borderBottomLeftRadius: 10, padding: '30px 34px', boxShadow: '0 14px 36px rgba(0,0,0,.4)'}}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{width: 18, height: 18, borderRadius: 99, background: '#bdbdc4', translate: `0px ${Math.sin(f * 0.55 - i * 0.9) * -7}px`}} />
            ))}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// the typed text keeps its place from the first letter: the card does not jump when a word wraps
const Digitado: React.FC<{texto: string; n: number; pisca: boolean; cor: string}> = ({texto, n, pisca, cor}) => (
  <>
    {texto.slice(0, n)}
    <span style={{display: 'inline-block', width: '0.56em', height: '1em', verticalAlign: '-0.16em', background: cor, opacity: pisca ? 1 : 0, marginLeft: '0.04em', marginRight: '-0.6em'}} />
    <span style={{visibility: 'hidden'}}>{texto.slice(n)}</span>
  </>
);

// ---- a typewriter: mono letters on a white sheet, one at a time, with a block caret
export const Maquina: React.FC<{g: De<'maquina'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const n = Math.round(interpolate(f, [quadro(fps, g.digitaAt), quadro(fps, g.digitaFimAt)], [0, g.texto.length], CL));
  const m = entra(f, a, 5);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 50, width: 860, display: 'flex', justifyContent: 'center', opacity: m * sai(f, b, 4), translate: `0px ${(1 - m) * 24}px`}}>
        <div style={{background: 'white', borderRadius: 6, padding: '26px 60px 26px 38px', boxShadow: '0 22px 55px rgba(0,0,0,.45)', fontFamily: PILHA_MONO, fontWeight: 700, fontSize: 66, lineHeight: 1.2, color: '#111', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
          <Digitado texto={g.texto} n={n} pisca={n < g.texto.length || Math.floor(f / 8) % 2 === 0} cor={ACCENT} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- a prompt box of an AI assistant typing the request; the send button lights up at the end
export const Prompt: React.FC<{g: De<'prompt'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const z = quadro(fps, g.digitaFimAt);
  const n = Math.round(interpolate(f, [quadro(fps, g.digitaAt), z], [0, g.texto.length], CL));
  const m = spring({frame: f - a, fps, config: {damping: 14, stiffness: 190, mass: 0.7}});
  const pronto = entra(f, z, 5);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', left: 70, top: g.y ?? TOPO + 40, width: 860, background: 'rgba(18,20,30,.95)', borderRadius: 36, padding: '26px 36px 24px', boxSizing: 'border-box', border: `2px solid ${comAlfa(ACCENT, 0.35)}`, boxShadow: `0 24px 60px rgba(0,0,0,.5), 0 0 60px ${comAlfa(ACCENT, 0.18)}`, fontFamily: POPPINS, scale: String(0.85 + 0.15 * m), opacity: Math.min(1, m * 1.4) * sai(f, b, 5), translate: `0px ${(1 - m) * -24}px`}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 12, fontWeight: 700, fontSize: 34, color: 'white'}}>
          <svg width={40} height={40} viewBox="0 0 24 24"><Faisca cor={ACCENT} /></svg>
          {g.titulo ?? 'Claude'}
        </div>
        <div style={{marginTop: 12, fontWeight: 500, fontSize: 46, lineHeight: 1.28, color: 'white', whiteSpace: 'pre-wrap'}}>
          <Digitado texto={g.texto} n={n} pisca={n < g.texto.length || Math.floor(f / 8) % 2 === 0} cor={ACCENT} />
        </div>
        <div style={{display: 'flex', justifyContent: 'flex-end', marginTop: 10}}>
          <div style={{width: 68, height: 68, borderRadius: 99, background: pronto > 0 ? ACCENT : 'rgba(255,255,255,.14)', display: 'flex', alignItems: 'center', justifyContent: 'center', scale: String(1 + 0.18 * Math.sin(pronto * Math.PI))}}>
            <svg width={36} height={36} viewBox="0 0 24 24"><path d="M12 20 V5 M5.5 11.5 L12 5 L18.5 11.5" fill="none" stroke={pronto > 0 ? TINTA : '#8a8a94'} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- emoji that pop in on their word, away from the middle of the face
const LUGARES: [number, number][] = [[150, 30], [730, 60], [440, -60], [90, 300], [760, 330], [270, -60]];
export const Emoji: React.FC<{g: De<'emoji'>}> = ({g}) => {
  const {f, fps, a, b} = useJanela(g);
  if (f < a || f >= b) return null;
  const tam = g.tamanho ?? 190;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {g.itens.map((it, i) => {
        const w = quadro(fps, it.at);
        const z = it.ate !== undefined ? quadro(fps, it.ate) : b;
        if (f < w || f >= z) return null;
        const m = spring({frame: f - w, fps, config: {damping: 7, stiffness: 240, mass: 0.6}});
        const l = f - w;
        const [lx, ly] = LUGARES[i % LUGARES.length];
        return (
          <div key={i} style={{position: 'absolute', left: it.x ?? lx, top: it.y ?? (g.y ?? TOPO + 150) + ly, fontFamily: PILHA_EMOJI, fontSize: tam, lineHeight: 1, filter: 'drop-shadow(0 12px 20px rgba(0,0,0,.4))', scale: String((0.2 + 0.8 * m) * sai(f, z, 4)), rotate: `${(1 - m) * -28 + Math.sin(l * 0.16 + i) * 5}deg`, translate: `0px ${Math.sin(l * 0.11 + i * 2) * 8}px`}}>
            {it.t}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
