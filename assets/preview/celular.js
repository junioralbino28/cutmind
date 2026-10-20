/* CENNO Edit — editor de celular (protótipo do passo 1).
 *
 * MESMO backend do editor de PC — nenhum servidor novo:
 *   GET  /api/state            state.json + edl.json + mtimes
 *   GET  /media/<arquivo>      vídeo, legendas, edit-data
 *   GET  /gen/thumbs/*.jpg     miniaturas (1 a cada 2 s)
 *   GET  /gen/waveform.json    forma de onda
 *   POST /api/save             timeline-edits → preview_edits.json
 *                              style-setup    → preview_style.json
 * O agente (Claude ou Codex) lê exatamente os arquivos que o editor de PC grava,
 * com os mesmos campos — por isso os payloads abaixo são cópia dos do app.js.
 *
 * Diferenças de propósito em relação ao app.js:
 *  - A agulha fica PARADA no centro e a linha do tempo anda por baixo dela
 *    (padrão CapCut/Edits). O gesto é próprio, não a rolagem nativa: um dedo
 *    arrasta (com inércia), dois dedos fazem pinça, toque seleciona. Rolagem
 *    nativa e pinça brigam pelo mesmo toque — por isso touch-action:none.
 *  - O Estilo abre num painel que sobe; a prévia fica em cima e mostra a escolha
 *    AO VIVO sobre o vídeo. Ela usa o CORTE LIMPO (cut.mp4), não o render final,
 *    senão a amostra apareceria por cima da legenda já queimada no vídeo.
 *  - Catálogo e amostras estão COPIADOS do app.js neste protótipo. No passo 2
 *    eles saem para um arquivo único usado pelos dois editores — duas cópias
 *    divergem, e uma amostra que mente sobre o estilo é pior que nenhuma.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, parent) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
};

const app = $('app');
const video = $('video');
const player = $('player');
const timeline = $('timeline');
const tracksEl = $('tracks');
const rulerCv = $('ruler');

// ---------- ícones ----------
const sv = (body, w = 1.7) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.2v11.6c0 .9 1 1.5 1.8 1L15 9.2c.8-.5.8-1.7 0-2.2L5.8 1.2C5 .7 4 1.3 4 2.2z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><rect x="3" y="2" width="3.6" height="12" rx="1"/><rect x="9.4" y="2" width="3.6" height="12" rx="1"/></svg>',
  vol: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11 5.2a3.4 3.4 0 0 1 0 5.6V9.4a2 2 0 0 0 0-2.8V5.2z"/></svg>',
  mute: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11.2 6.2l3.6 3.6m0-3.6l-3.6 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>',
  corte: sv('<circle cx="6" cy="6.5" r="2.6"/><circle cx="6" cy="17.5" r="2.6"/><path d="M8.2 8.1 20 18M8.2 15.9 20 6"/>'),
  final: sv('<rect x="3" y="4.5" width="18" height="15" rx="3"/><path d="M10 9.2v5.6l4.8-2.8z" fill="currentColor" stroke="none"/>'),
  estilo: sv('<path d="M12 3.5l1.9 4.6 4.6 1.9-4.6 1.9L12 16.5l-1.9-4.6L5.5 10l4.6-1.9z"/><path d="M18.5 15.5l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z"/>'),
  legenda: sv('<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10.4 10.3a2.1 2.1 0 1 0 0 3.4M16.6 10.3a2.1 2.1 0 1 0 0 3.4"/>'),
  marcar: sv('<path d="M5.5 20.5V4M5.5 4.5h10.2a.6.6 0 0 1 .48.96L14 8.6l2.18 3.14a.6.6 0 0 1-.48.96H5.5"/>'),
  enviar: sv('<path d="M12 15.5V4.5M7.5 9 12 4.5 16.5 9"/><path d="M4.5 14.5v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/>'),
  baixar: sv('<path d="M12 4.5v11M7.5 11l4.5 4.5 4.5-4.5"/><path d="M4.5 14.5v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/>'),
  voltar: sv('<path d="M14.5 6 8.5 12l6 6"/>'),
  ouvir: sv('<path d="M4.5 15v-2.5a7.5 7.5 0 0 1 15 0V15"/><rect x="3.5" y="14" width="4" height="6" rx="1.6"/><rect x="16.5" y="14" width="4" height="6" rx="1.6"/>'),
  remover: sv('<path d="M5 7h14M10 7V5.2c0-.4.3-.7.7-.7h2.6c.4 0 .7.3.7.7V7M7 7l.8 11.2c.1 1 .9 1.8 1.9 1.8h4.6c1 0 1.8-.8 1.9-1.8L17 7"/>'),
  restaurar: sv('<path d="M8.5 7 4.5 11l4 4"/><path d="M5 11h9a5 5 0 0 1 0 10h-3"/>'),
  original: sv('<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5v3.2h3.2"/>'),
  check: sv('<path d="M5 12.5l4.5 4.5L19 7.5"/>', 3),
  imagem: sv('<rect x="3" y="5" width="18" height="14" rx="2.6"/><circle cx="8.5" cy="10" r="1.6"/><path d="M4 17.5l5-4.6 3.4 3 2.4-2 5.2 4"/>'),
};

/* ---------- catálogo de estilos (cópia do app.js) ----------
 * Os ids e nomes são o contrato com a skill (preview_style.json). As miniaturas
 * desenhadas (mock) do editor de PC não vêm junto: aqui cada opção é mostrada
 * sobre um quadro do próprio vídeo. */
const STYLE_CATALOG = {
  edits: [
    { id: 'limpa', name: 'Limpa' },
    { id: 'split', name: 'Tela dividida' },
    { id: 'split2', name: 'Tela dividida 2' },
  ],
  headlines: [
    { id: 'outline', name: 'Contorno', hl: 'outline' },
    { id: 'card', name: 'Cartão', hl: 'card' },
    { id: 'realce', name: 'Realce', hl: 'realce' },
    { id: 'misto', name: 'Misto', hl: 'misto' },
    { id: 'none', name: 'Nenhum', none: true },
  ],
  captions: [
    { id: 'karaoke', name: 'Karaokê', demo: 'karaoke' },
    { id: 'stacked', name: 'Empilhado', demo: 'stacked' },
    { id: 'scatter', name: 'Disperso', demo: 'scatter' },
    { id: 'simples', name: 'Simples', stat: 'simples' },
    { id: 'serifada', name: 'Serifada', stat: 'serifada' },
    { id: 'classica', name: 'Clássica', stat: 'classica' },
    { id: 'none', name: 'Nenhum', none: true },
  ],
  elements: [
    { id: 'tracking', name: 'Movimento de tracking', def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 5.6V3.4A1.4 1.4 0 013.4 2h2.2M10.4 2h2.2A1.4 1.4 0 0114 3.4v2.2M14 10.4v2.2a1.4 1.4 0 01-1.4 1.4h-2.2M5.6 14H3.4A1.4 1.4 0 012 12.6v-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="8" r="2.1"/></svg>' },
    { id: 'zoomAuto', name: 'Automação de zoom in', def: true,
      icon: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10.6 10.6L14 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none"/><path d="M7 5.1v3.8M5.1 7h3.8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg>' },
    { id: 'zoomCuts', name: 'Zoom in e out nos cortes', def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.4" width="6" height="9.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="9.6" y="1.9" width="5.2" height="12.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.4 8h.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>' },
    { id: 'flashCut', name: 'Flash na transição', def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M3 13.2L13 3.2" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" fill="none"/><path d="M6.6 14L9.4 11.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/><path d="M6.6 4.8L3.8 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/></svg>' },
    { id: 'musicAI', name: 'Trilha sonora com IA', def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M12.6 1.6L6.9 3a.7.7 0 00-.55.68v5.6a2 2 0 101.35 1.9V5.9l4.4-1.05v2.9a2 2 0 101.35 1.9V2.3a.7.7 0 00-.85-.7z"/><path d="M2.4 2.2l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z"/></svg>' },
  ],
};
const ACCENT_USERS = { headlines: ['realce', 'misto'], captions: ['stacked'] };
const ACCENT_DEFAULT = '#ff5200';

/* ---------- amostras de legenda e headline (cópia fiel do app.js) ---------- */
const NONE_MARK = '<svg viewBox="0 0 64 34" style="width:56%;height:auto">'
  + '<rect x="1" y="1" width="62" height="32" rx="5" fill="none" '
  + 'stroke="rgba(255,255,255,.4)" stroke-width="1.5" stroke-dasharray="4 3"/>'
  + '<path d="M14 24L50 10" stroke="rgba(255,255,255,.45)" stroke-width="1.5" '
  + 'stroke-linecap="round"/></svg>';
const CAP_TEXT = 'É assim que sua legenda irá aparecer';
const FPS_REF = 30;

function bez(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const fx = (t) => ((ax * t + bx) * t + cx) * t;
  const dfx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    let t = x;
    for (let i = 0; i < 6; i++) {
      const e = fx(t) - x;
      if (Math.abs(e) < 1e-4) break;
      const d = dfx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    return ((ay * t + by) * t + cy) * t;
  };
}
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
const easeStack = bez(0.16, 1, 0.3, 1);
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

function buildKaraokeDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const lines = [];
  for (let i = 0; i < words.length; i += 3) lines.push(words.slice(i, i + 3));
  const STEP = 0.26, ENTER = 7 / FPS_REF, HOLD = 0.6;
  const rise = 34 * s;
  const built = [];
  let t = 0;
  for (const ln of lines) {
    const box = el('div', 'kar-line', wrap);
    box.style.fontSize = `${61 * s}px`;
    const spans = ln.map((w) => {
      const sp = el('span', '', box);
      sp.textContent = w;
      sp.style.marginRight = `${18 * s}px`;
      return sp;
    });
    const start = t;
    t = start + (ln.length - 1) * STEP + ENTER + HOLD;
    built.push({ box, spans, start, end: t });
  }
  const cycle = t + 0.3;
  return (now) => {
    const p = now % cycle;
    for (const L of built) {
      const on = p >= L.start && p < L.end;
      L.box.style.display = on ? '' : 'none';
      if (!on) continue;
      L.spans.forEach((sp, j) => {
        const e = easeOutCubic(clamp01((p - (L.start + j * STEP)) / ENTER));
        sp.style.opacity = e;
        sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      });
    }
  };
}

const STK_LINES = [
  { words: ['É', 'assim'], style: 0 },
  { words: ['que', 'sua', 'legenda'], style: 1 },
  { words: ['irá', 'aparecer'], style: 2 },
];
function buildStackedDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'stk-cue', wrap);
  const STEP = 0.2, ENTER = 8 / FPS_REF, HOLD = 0.8, EXIT = 7 / FPS_REF;
  const rise = 46 * s, blurIn = 5 * s, upY = 55 * s, cueBlur = 14 * s;
  const shadow = `drop-shadow(0 ${(5 * s).toFixed(2)}px ${(9 * s).toFixed(2)}px rgba(0,0,0,0.5))`;
  const all = [];
  let idx = 0;
  for (const L of STK_LINES) {
    const row = el('div', 'stk-line', cue);
    let size = 69;
    if (L.style === 1) size = Math.round(size * 0.72);
    if (L.style === 2) size = Math.round(size * 0.95);
    row.style.fontSize = `${size * s}px`;
    L.words.forEach((w, i) => {
      const sp = el('span', `s${L.style}`, row);
      sp.textContent = w + (i < L.words.length - 1 ? ' ' : '');
      all.push({ sp, start: idx * STEP });
      idx++;
    });
  }
  const exitStart = (idx - 1) * STEP + ENTER + HOLD;
  const cycle = exitStart + EXIT + 0.15;
  return (now) => {
    const p = now % cycle;
    const ex = clamp01((p - exitStart) / EXIT);
    cue.style.opacity = 1 - ex;
    cue.style.translate = `0px ${(-upY * ex).toFixed(2)}px`;
    cue.style.filter = ex > 0.02 ? `blur(${(cueBlur * ex).toFixed(2)}px)` : '';
    for (const w of all) {
      const e = easeStack(clamp01((p - w.start) / ENTER));
      const eb = (1 - e) * blurIn;
      w.sp.style.opacity = e;
      w.sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      w.sp.style.filter = `${eb > 0.06 ? `blur(${eb.toFixed(2)}px) ` : ''}${shadow}`;
    }
  };
}

const HEADLINE_TEXT = 'É assim que vai ficar a sua headline';
const HL_MIN = 28;
const HL_STYLES = {
  outline: { weights: [800, 800], cap: 51, safeW: 900, lh: 1.02 },
  card: { weights: [900, 900], cap: 46, safeW: 820, lh: 1.06 },
  realce: { weights: [900, 900], cap: 48, safeW: 830, lh: 1.04 },
  misto: { weights: [400, 900], cap: 55, safeW: 900, lh: 0.98 },
};
let hlMeter = null;
function measureType(text, size, weight, family, tracking) {
  if (!text) return 0;
  if (!hlMeter) {
    hlMeter = document.createElement('span');
    hlMeter.style.cssText = 'position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;';
    document.body.appendChild(hlMeter);
  }
  hlMeter.style.fontFamily = family || "'Poppins',sans-serif";
  hlMeter.style.letterSpacing = `${tracking == null ? -1 : tracking}px`;
  hlMeter.style.fontSize = `${size}px`;
  hlMeter.style.fontWeight = String(weight);
  hlMeter.textContent = text;
  return hlMeter.offsetWidth;
}
const hlWidth = (text, size, weight) => measureType(text, size, weight);
function hlTwoLines(text, weights) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] || '', ''];
  let best = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
    if (d < bestDiff) { bestDiff = d; best = [a, b]; }
  }
  return best;
}
function hlFit(lines, S_) {
  const widest = (size) => Math.max(hlWidth(lines[0], size, S_.weights[0]), hlWidth(lines[1], size, S_.weights[1]));
  let size = Math.floor((S_.safeW / Math.max(1, widest(100))) * 100);
  size = Math.floor((S_.safeW / Math.max(1, widest(size))) * size);
  return Math.max(HL_MIN, Math.min(size, S_.cap));
}
function buildHeadlineDemo(host, styleId, text = HEADLINE_TEXT) {
  const s = host.clientWidth / 1080;
  const HS = HL_STYLES[styleId];
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const raw = styleId === 'card' ? text.toUpperCase() : text;
  const lines = hlTwoLines(raw, HS.weights);
  const size = hlFit(lines, HS) * s;
  const box = el('div', `hl-demo hl-${styleId}`, wrap);
  box.style.lineHeight = String(HS.lh);
  box.style.letterSpacing = `${-1 * s}px`;
  if (styleId === 'realce') {
    for (const l of lines) {
      if (!l) continue;
      const b = el('div', 'hl-block', box);
      b.style.fontSize = `${size}px`;
      b.style.borderRadius = `${12 * s}px`;
      b.textContent = l;
    }
    return;
  }
  if (styleId === 'card') {
    box.style.borderRadius = `${24 * s}px`;
    box.style.padding = `${28 * s}px ${46 * s}px`;
  }
  if (styleId === 'outline') box.style.webkitTextStroke = `${7 * s}px #000`;
  lines.forEach((l, i) => {
    if (!l) return;
    const d = el('div', '', box);
    d.style.fontSize = `${size}px`;
    d.style.fontWeight = String(HS.weights[i]);
    if (styleId === 'misto') d.style.color = i === 1 ? 'var(--hl-accent)' : '#fff';
    d.textContent = l;
  });
}

const SCAT = { base: 58, hiScale: 1.62, gap: 12, spread: 0.45, safeW: 820 };
const scatHash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
function buildScatterDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'scat-cue', wrap);
  const words = CAP_TEXT.toLowerCase().split(' ');
  let hiIdx = -1, hiLen = 6;
  words.forEach((w, i) => { if (w.length > hiLen) { hiLen = w.length; hiIdx = i; } });
  const lines = [];
  let line = [];
  words.forEach((w, i) => {
    if (i === hiIdx) {
      if (line.length) lines.push(line);
      lines.push([{ w, i, hi: true }]);
      line = [];
      return;
    }
    line.push({ w, i, hi: false });
    if (line.length >= (scatHash(31 + i) > 0.5 ? 4 : 3)) { lines.push(line); line = []; }
  });
  if (line.length) lines.push(line);
  const STEP = 0.22, ENTER = 7 / FPS_REF, HI_ENTER = 10 / FPS_REF, HOLD = 0.9, EXIT = 8 / FPS_REF;
  const all = [];
  lines.forEach((ln, li) => {
    const row = el('div', 'scat-line', cue);
    row.style.gap = `${SCAT.gap * s}px`;
    let w = 0;
    for (const it of ln) {
      const sp = el('span', it.hi ? 'hi' : '', row);
      sp.textContent = it.w;
      sp.style.fontSize = `${(it.hi ? SCAT.base * SCAT.hiScale : SCAT.base) * s}px`;
      all.push({ sp, start: it.i * STEP, hi: it.hi });
      w += sp.offsetWidth + SCAT.gap * s;
    }
    const room = Math.max(0, (SCAT.safeW * s - w) / 2) * SCAT.spread;
    row.style.translate = `${((scatHash(17 + li * 5 + 3) * 2 - 1) * room).toFixed(1)}px 0px`;
  });
  const exitStart = (words.length - 1) * STEP + ENTER + HOLD;
  const cycle = exitStart + EXIT + 0.35;
  const blurIn = 26 * s, blurOut = 30 * s;
  return (now) => {
    const p = now % cycle;
    const out = clamp01((p - exitStart) / EXIT);
    for (const w of all) {
      const t = easeOutCubic(clamp01((p - w.start) / (w.hi ? HI_ENTER : ENTER)));
      w.sp.style.opacity = t * (1 - out);
      if (w.hi) {
        const b = (1 - t) * blurIn + out * blurOut;
        w.sp.style.filter = b > 0.1 ? `blur(${b.toFixed(2)}px)` : '';
      }
    }
  };
}

const STATIC_VARIANTS = {
  simples: { family: "'Poppins',sans-serif", weight: 600, size: 66, maxWords: 3, lines: 1, sx: 0.9, sy: 0.9, tracking: -3, maxW: 860 },
  serifada: { family: "'Libre Baskerville',serif", weight: 700, size: 67, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 860 },
  classica: { family: "'Inter',sans-serif", weight: 500, size: 42, maxWords: 14, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 840 },
};
const ORPHAN_PT = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;
function buildStaticDemo(host, id) {
  const V = STATIC_VARIANTS[id];
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const wOf = (ws) => measureType(ws.join(' '), V.size, V.weight, V.family, V.tracking) * V.sx;
  const cues = [];
  let cur = [];
  for (const w of words) {
    const trial = [...cur, w];
    if (cur.length && (trial.length > V.maxWords || wOf(trial) > V.maxW * V.lines)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
  }
  if (cur.length) cues.push(cur);
  const boxes = cues.map((cue) => {
    let lines = [cue];
    if (V.lines === 2 && cue.length > 1) {
      let best = 1, bestScore = Infinity;
      for (let i = 1; i < cue.length; i++) {
        const score = Math.abs(wOf(cue.slice(0, i)) - wOf(cue.slice(i))) + (ORPHAN_PT.test(cue[i - 1]) ? 200 : 0);
        if (score < bestScore) { bestScore = score; best = i; }
      }
      lines = [cue.slice(0, best), cue.slice(best)];
    }
    const box = el('div', 'stat-demo', wrap);
    box.style.fontFamily = V.family;
    box.style.fontWeight = String(V.weight);
    box.style.fontSize = `${V.size * s}px`;
    box.style.letterSpacing = `${V.tracking * s}px`;
    box.style.transform = V.sx === 1 && V.sy === 1 ? '' : `scale(${V.sx}, ${V.sy})`;
    for (const ln of lines) el('div', '', box).textContent = ln.join(' ');
    return box;
  });
  if (boxes.length < 2) return null;
  const HOLD = 0.95;
  const cycle = boxes.length * HOLD;
  return (now) => {
    const i = Math.floor((now % cycle) / HOLD);
    boxes.forEach((b, k) => { b.style.display = k === i ? '' : 'none'; });
  };
}
const CAP_BUILDERS = { karaoke: buildKaraokeDemo, stacked: buildStackedDemo, scatter: buildScatterDemo };

/* ---------- onde cada coisa fica no quadro: números do render ----------
 * Fonte (mudou lá, muda aqui), tudo em px do quadro 1080x1920:
 *  - CustomGraphics.tsx: tela dividida, faixa de 750 e LAYOUT top/bottom (zoom, focusY)
 *  - references/shortform.md: legenda na emenda, paddingBottom 1074 / 790
 *  - Main.tsx: HL_STYLES.top da headline; CaptionShell do karaokê (o ÚNICO estilo de
 *    legenda que obedece captions.windows e vai para a emenda na tela dividida)
 *  - StackedCaptions / ScatterCaptions / SimpleCaptions: posição de cada legenda
 * O edit-data.json do projeto sobrepõe os padrões (paddingBottom, stackedOffsetY…).
 * Dois momentos do vídeo, que no render NUNCA aparecem juntos:
 *  - 'abertura': quadro inteiro, headline e legenda (os primeiros segundos)
 *  - 'meio': a tela dividida com a imagem de apoio e a legenda, sem headline */
const FRAME_W = 1080;
const FRAME_H = 1920;
const SPLIT_GEOM = {
  split: { band: 'top', bandH: 750, zoom: 1.25, focusY: 400, capPB: 1074 },
  split2: { band: 'bottom', bandH: 750, zoom: 1.0, focusY: 225, capPB: 790 },
};
const HL_TOP = { outline: 330, card: 120, realce: 300, misto: 300 };
const STATIC_BOTTOM = 430;
const KARAOKE_LINE = 61; // a amostra do karaokê usa 61px de letra, line-height 1

const capsCfg = () => (S.editData && S.editData.captions) || {};
// fração da altura do quadro onde fica o CENTRO da legenda
function capCenter(look, moment) {
  const C = capsCfg();
  switch (look.captions) {
    case 'stacked': return 0.5 + (C.stackedOffsetY ?? 0.156);
    case 'scatter': return C.scatterOffsetY ?? 0.72;
    case 'karaoke': {
      const g = moment === 'meio' ? SPLIT_GEOM[look.edit] : null;
      return 1 - ((g ? g.capPB : (C.paddingBottom ?? 420)) + KARAOKE_LINE / 2) / FRAME_H;
    }
    default: {
      const V = STATIC_VARIANTS[look.captions];
      return V ? 1 - (STATIC_BOTTOM + (V.size * 1.18 * V.lines * V.sy) / 2) / FRAME_H : 0.76;
    }
  }
}
// centro do bloco de duas linhas da headline (para enquadrar o cartão)
function hlCenter(look) {
  const HS = HL_STYLES[look.headline];
  if (!HS) return 0.18;
  const pad = look.headline === 'card' ? 56 : look.headline === 'realce' ? 0.48 * HS.cap : 0;
  return (HL_TOP[look.headline] + (2 * HS.cap * HS.lh + pad) / 2) / FRAME_H;
}
function hookText() {
  const h = (S.editData && S.editData.hook) || {};
  const t = (h.text || (h.lines || []).join(' ') || '').replace(/\s+/g, ' ').trim();
  return t || HEADLINE_TEXT;
}

const pct = (f) => `${(f * 100).toFixed(3)}%`;
const GEOM_VARS = ['--win-top', '--win-h', '--m-left', '--m-top', '--m-w', '--m-h', '--band-top', '--band-h', '--hl-top', '--cap-c'];
function applyGeom(node, look, moment) {
  const g = moment === 'meio' ? SPLIT_GEOM[look.edit] : null;
  for (const k of GEOM_VARS) node.style.removeProperty(k);
  if (g) {
    // CustomGraphics.tsx: o vídeo é redesenhado na janela com zoom e focusY
    const winH = (FRAME_H - g.bandH) / FRAME_H;
    node.style.setProperty('--win-top', pct(g.band === 'top' ? g.bandH / FRAME_H : 0));
    node.style.setProperty('--win-h', pct(winH));
    node.style.setProperty('--m-w', pct(g.zoom));
    node.style.setProperty('--m-left', pct(-(g.zoom - 1) / 2));
    node.style.setProperty('--m-h', pct(g.zoom / winH));
    node.style.setProperty('--m-top', pct(-(g.focusY * g.zoom) / FRAME_H / winH));
    node.style.setProperty('--band-top', pct(g.band === 'top' ? 0 : winH));
    node.style.setProperty('--band-h', pct(g.bandH / FRAME_H));
  }
  node.style.setProperty('--hl-top', pct((HL_TOP[look.headline] ?? 300) / FRAME_H));
  node.style.setProperty('--cap-c', pct(capCenter(look, moment)));
  node.classList.toggle('is-split', !!g);
  node.classList.toggle('band-top', !!g && g.band === 'top');
}
function fillText(node, look, moment, anims, only) {
  const hl = node.querySelector('.hl');
  const cap = node.querySelector('.cap');
  hl.innerHTML = '';
  cap.innerHTML = '';
  if (moment === 'abertura' && only !== 'captions') {
    const h = STYLE_CATALOG.headlines.find((o) => o.id === look.headline);
    if (h && !h.none) buildHeadlineDemo(hl, h.hl, hookText());
  }
  if (only === 'headline') return;
  const c = STYLE_CATALOG.captions.find((o) => o.id === look.captions);
  if (c && !c.none) {
    if (c.demo) anims.push(CAP_BUILDERS[c.demo](cap));
    else { const st = buildStaticDemo(cap, c.stat); if (st) anims.push(st); }
  }
}

// a imagem de apoio de verdade do projeto (a 1ª da tela dividida), quando já existe
function bandSource() {
  const it = ((S.editData && S.editData.splitInserts) || [])[0];
  if (!it || !it.src) return null;
  const base = (S.state.editData || '').replace(/[^/]*$/, '');
  return { url: `/media/${base}${it.src}`, video: /\.(mp4|mov|webm)$/i.test(it.src) };
}
function setBand(band, on, live) {
  const src = on ? bandSource() : null;
  const want = on ? (src ? src.url : 'ph') : '';
  if (band.dataset.src === want) return;
  band.dataset.src = want;
  band.innerHTML = '';
  band.style.backgroundImage = '';
  if (!on) return;
  if (src && live && src.video) {
    const v = el('video', '', band);
    v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true;
    v.src = src.url;
    v.play().catch(() => {});
  } else if (src && !src.video) {
    band.style.backgroundImage = `url("${src.url}")`;
  } else if (src && S.bandUrl) {
    band.style.backgroundImage = `url("${S.bandUrl}")`;
  } else {
    el('div', 'band-ph', band).innerHTML = `${ICON.imagem}<span>sua imagem de apoio</span>`;
  }
}
// um quadro da imagem de apoio em vídeo, para os cartões (um vídeo tocando por cartão pesa no celular)
async function loadBandPoster() {
  const src = bandSource();
  if (!src || !src.video) { S.bandUrl = null; S.bandFor = ''; return; }
  if (S.bandFor === src.url) return;
  S.bandFor = src.url;
  S.bandUrl = null;
  const v = document.createElement('video');
  v.muted = true; v.playsInline = true; v.preload = 'auto'; v.src = src.url;
  try {
    await new Promise((ok, no) => {
      v.addEventListener('loadeddata', ok, { once: true });
      v.addEventListener('error', no, { once: true });
      setTimeout(no, 5000);
    });
    // no meio do clipe a arte já entrou; no celular o "seeked" chega antes do quadro
    // estar decodificado, então espera também um quadro pintado (senão sai preto)
    v.currentTime = Math.min(2.5, (v.duration || 2) / 2);
    await new Promise((ok) => { v.addEventListener('seeked', ok, { once: true }); setTimeout(ok, 4000); });
    if (typeof v.requestVideoFrameCallback === 'function') {
      await new Promise((ok) => { v.requestVideoFrameCallback(() => ok()); v.play().catch(ok); setTimeout(ok, 1500); });
      v.pause();
    }
    const W = 432, H = 300; // 1080x750
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const sc = Math.max(W / v.videoWidth, H / v.videoHeight);
    const sw = W / sc, sh = H / sc;
    cv.getContext('2d').drawImage(v, (v.videoWidth - sw) / 2, (v.videoHeight - sh) / 2, sw, sh, 0, 0, W, H);
    S.bandUrl = cv.toDataURL('image/jpeg', 0.82);
  } catch (e) {
    S.bandUrl = null;
  }
  v.removeAttribute('src');
  v.load();
}

// ---------- estado ----------
const THUMB_EVERY = 2.0;
const MIN_SEG = 0.2;
const S = {
  state: {},
  mtimes: {},
  rendered: [],
  draft: [],
  jcut: null,
  fps: 30,
  videoDuration: 0,
  thumbCount: 0,
  wave: null,
  captions: [],
  editData: null,
  insertsDraft: [],
  notes: [],
  pendingIn: null,
  editingNote: null,
  style: null,
  view: 'corte',      // 'corte' = cut.mp4 | 'final' = render da Fase 2
  t: 0,               // segundos (linha do tempo do rascunho) debaixo da agulha
  pps: 28,
  minPps: 2,
  maxPps: 220,
  selected: -1,
  lastSig: '',
  savedPending: false,
  styling: false,
  styleTab: 'edit',
  frameUrl: null,
  bandUrl: null,      // um quadro da imagem de apoio do projeto (cartões)
  bandFor: '',
  cardAnims: [],
  liveAnims: [],
};

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};
const fmtShort = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  return `${m}:${String(Math.floor(t - m * 60)).padStart(2, '0')}`;
};

function defaultStyle() {
  const elements = {};
  for (const e of STYLE_CATALOG.elements) elements[e.id] = !!e.def;
  return { edit: 'limpa', headline: 'outline', captions: 'karaoke', accent: ACCENT_DEFAULT, elements, note: '' };
}

// ---------- geometria do corte (cópia do app.js: J-cut, rascunho, render) ----------
function jcutGeom(i) {
  const j = S.jcut && S.jcut[i];
  if (!j) return { lead: 0, tail: 0 };
  return {
    lead: Math.max(0, (j.video_start_in_output || 0) - (j.audio_start_in_output || 0)),
    tail: (j.tail_trim_frames || 0) / (S.fps || 30),
  };
}
function draftLayout() {
  let t = 0;
  let at = 0;
  return S.draft.map((r, i) => {
    if (r.removed) return { ...r, out: t, dur: 0, aout: at, adur: 0 };
    const g = jcutGeom(i);
    const span = r.end - r.start;
    const adur = Math.max(0, span - g.tail);
    const dur = Math.max(0, adur - g.lead);
    const item = { ...r, out: t, dur, aout: Math.max(0, at - g.lead), adur, lead: g.lead };
    t += dur;
    at = item.aout + adur;
    return item;
  });
}
function renderedLayout() {
  if (S.jcut && S.jcut.length === S.rendered.length) {
    return S.rendered.map((r, i) => ({ ...r, out: S.jcut[i].video_start_in_output, dur: S.jcut[i].video_duration }));
  }
  let t = 0;
  return S.rendered.map((r) => {
    const dur = r.end - r.start;
    const item = { ...r, out: t, dur };
    t += dur;
    return item;
  });
}
const draftTotal = () => draftLayout().reduce((a, r) => a + r.dur, 0);
const totalT = () => draftTotal() || S.videoDuration || 0;
function draftToRendered(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = dl.length - 1; i >= 0; i--) {
    const d = dl[i];
    if (d.removed || t < d.out) continue;
    const off = Math.min(t - d.out, (rl[i]?.dur ?? d.dur) - 0.02);
    return (rl[i]?.out ?? d.out) + Math.max(0, off);
  }
  return Math.min(t, S.videoDuration);
}
function renderedToDraft(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = rl.length - 1; i >= 0; i--) {
    const r = rl[i];
    if (t < r.out) continue;
    if (dl[i]?.removed) return dl[i].out;
    const off = Math.min(t - r.out, dl[i]?.dur ?? r.dur);
    return (dl[i]?.out ?? r.out) + off;
  }
  return t;
}
function groupCaptions(caps) {
  const lines = [];
  let cur = [];
  for (const w of caps) {
    cur.push(w);
    if (cur.length >= 3 || /[.,!?…]$/.test(w.text)) { lines.push(cur); cur = []; }
  }
  if (cur.length) lines.push(cur);
  return lines.map((line) => ({
    text: line.map((w) => w.text.replace(/[.,!?…]+$/, '')).join(' '),
    start: line[0].startMs / 1000,
    end: line[line.length - 1].endMs / 1000,
  }));
}
function buildInsertsDraft() {
  const d = S.editData || {};
  const list = [];
  if (d.hook && d.hook.enabled) list.push({ kind: 'hook', label: (d.hook.lines || []).join(' / '), start: 0, end: d.hook.endSec || 4 });
  (d.inserts || []).forEach((it, i) => list.push({ kind: 'insert', label: (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i }));
  (d.splitInserts || []).forEach((it, i) => list.push({ kind: 'split', label: it.label || (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i }));
  (d.splitVideos || []).forEach((it, i) => list.push({ kind: 'splitvideo', label: it.label || (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i }));
  (d.behind || []).forEach((b, i) => list.push({ kind: 'behind', label: b.kind === 'words' ? (b.words || []).map((w) => w.t).join(' ') : (b.src || '').split('/').pop(), start: +b.start, end: +b.start + +b.dur, ref: i }));
  (d.wordAccents || []).forEach((w, i) => list.push({ kind: 'word', label: w.text, start: +w.start, end: +w.end, ref: i }));
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
}
const isText = (c) => c.kind === 'hook' || c.kind === 'word';

// ---------- o que mudou e ainda não foi salvo ----------
const edlDirty = () => S.draft.some((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end);
function dirtyCount() {
  return S.draft.filter((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end).length + S.notes.length;
}
function refreshHeader() {
  const n = dirtyCount();
  $('btnSave').classList.toggle('hidden', n === 0);
  $('dirtyCount').textContent = n;
  $('sentPill').classList.toggle('hidden', !(S.savedPending && n === 0));
  const label = S.view === 'final' ? 'Final' : 'Corte';
  $('projectSub').textContent = S.videoDuration ? `${label} · ${fmtShort(totalT())}` : 'sem vídeo ainda';
}

// ---------- dados ----------
async function poll() {
  try {
    const data = await (await fetch('/api/state')).json();
    const sig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration]);
    if (sig !== S.lastSig) {
      if (dirtyCount() === 0 && !S.styling) {
        S.lastSig = sig;
        await applyState(data);
      } else if (!S.newStateWarned) {
        S.newStateWarned = true;
        toast('Chegou uma versão nova — salve seus ajustes para ver', 4000);
      }
    }
  } catch (e) { /* servidor reiniciando: continua tentando */ }
  setTimeout(poll, 2000);
}

async function applyState(data) {
  S.newStateWarned = false;
  S.state = data.state || {};
  S.mtimes = data.mtimes || {};
  S.videoDuration = data.videoDuration || 0;
  S.fps = S.state.fps || 30;
  S.savedPending = !!data.hasPendingEdits;
  $('projectName').textContent = S.state.project || 'CENNO Edit';

  const ranges = (data.edl && data.edl.ranges) || [];
  S.jcut = (data.edl && data.edl.jcut_timeline) || null;
  S.rendered = ranges.map((r) => ({ source: r.source, start: +r.start, end: +r.end, beat: r.beat || '' }));
  S.draft = S.rendered.map((r) => ({ ...r, removed: false, orig: { start: r.start, end: r.end } }));
  S.selected = -1;

  S.style = { ...defaultStyle(), ...(S.state.style || {}) };
  S.style.elements = { ...defaultStyle().elements, ...((S.state.style || {}).elements || {}) };
  if (!/^#[0-9a-f]{6}$/i.test(S.style.accent || '')) S.style.accent = normHex(S.style.accentName) || ACCENT_DEFAULT;

  const hasVideo = S.videoDuration > 0;
  $('empty').classList.toggle('hidden', hasVideo);
  if (!hasFinal() && S.view === 'final') S.view = 'corte';

  S.captions = [];
  S.editData = null;
  S.insertsDraft = [];
  if ((S.state.phase || 1) >= 2) {
    if (S.state.captions) {
      try { S.captions = groupCaptions(await (await fetch(`/media/${S.state.captions}?v=${Date.now()}`)).json()); } catch (e) { /* ainda não existe */ }
    }
    if (S.state.editData) {
      try { S.editData = await (await fetch(`/media/${S.state.editData}?v=${Date.now()}`)).json(); buildInsertsDraft(); } catch (e) { /* ainda não existe */ }
    }
  }
  if (hasVideo) {
    setVideoSrc(S.view);
    loadWave();
    loadThumbsMeta();
  }
  if (!S.fitted && hasVideo) fitZoom();
  if (S.state.awaitingStyle && !S.styling) openStyle('edit'); // a skill abriu a escolha
  renderTimeline();
  renderToolbar();
  refreshHeader();
}
const hasFinal = () => (S.state.phase || 1) >= 2 && !!S.state.finalVideo;
const canStyle = () => !!(S.state.awaitingStyle || S.state.style);

function setVideoSrc(view) {
  const rel = view === 'final' && S.state.finalVideo ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const v = (view === 'final' ? S.mtimes.finalVideo : S.mtimes.video) || 0;
  const src = `/media/${rel}?v=${v}`;
  if (video.dataset.src === src) return Promise.resolve();
  const t = video.currentTime || 0;
  video.dataset.src = src;
  video.src = src;
  return new Promise((ok) => {
    video.addEventListener('loadeddata', () => { video.currentTime = t; ok(); }, { once: true });
  });
}
async function loadWave() {
  try { S.wave = await (await fetch('/gen/waveform.json')).json(); } catch (e) { S.wave = null; }
  drawWave();
}
async function loadThumbsMeta() {
  try {
    const meta = await (await fetch('/gen/thumbs/meta.json')).json();
    if (meta.count !== S.thumbCount) { S.thumbCount = meta.count || 0; renderTimeline(); }
  } catch (e) { S.thumbCount = 0; }
}
video.addEventListener('loadedmetadata', () => {
  if (!video.videoWidth || !video.videoHeight) return;
  player.style.setProperty('--ar', `${video.videoWidth} / ${video.videoHeight}`);
  if (S.draft.length) renderTimeline(); // a largura dos quadros da tira depende da proporção
});

// ---------- linha do tempo ----------
const half = () => timeline.clientWidth / 2;
const clampT = (t) => Math.max(0, Math.min(t, totalT()));
function fitZoom() {
  const w = timeline.clientWidth || 360;
  const total = Math.max(totalT(), 1);
  S.minPps = Math.max(1.5, (w * 0.9) / total);
  // ~14 s na largura da tela: dá para ver as miniaturas e acertar a alça com o dedo
  S.pps = Math.min(S.maxPps, Math.max(S.minPps, w / 14));
  S.fitted = true;
}

function trackPlan() {
  const fin = S.view === 'final';
  const hasTxt = S.insertsDraft.some(isText);
  const hasIns = S.insertsDraft.some((c) => !isText(c));
  return [
    { id: 'notes', h: 14, show: S.notes.length > 0 || S.pendingIn != null },
    { id: 'caps', h: 18, show: fin && S.captions.length > 0 },
    { id: 'text', h: 18, show: fin && hasTxt },
    { id: 'ins', h: 18, show: fin && hasIns },
    { id: 'video', h: VIDEO_TRACK_H, show: true },
    { id: 'audio', h: 30, show: true },
  ].filter((t) => t.show);
}

const VIDEO_TRACK_H = 56;
const tileWidth = () => {
  const ar = video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 9 / 16;
  return Math.max(24, Math.round((VIDEO_TRACK_H - 3) * ar));
};

let lanes = []; // elementos que andam juntos sob a agulha
function renderTimeline() {
  tracksEl.innerHTML = '';
  lanes = [];
  const width = `${Math.max(totalT(), 0.1) * S.pps}px`;
  for (const tr of trackPlan()) {
    const track = el('div', `track tr-${tr.id}`, tracksEl);
    track.style.height = `${tr.h}px`;
    if (tr.id === 'audio') {
      el('canvas', 'wave', track).id = 'wave';
      continue;
    }
    const lane = el('div', 'lane', track);
    lane.style.width = width;
    lanes.push(lane);
    if (tr.id === 'video') renderTakes(lane);
    else if (tr.id === 'notes') renderNotes(lane);
    else if (tr.id === 'caps') {
      for (const c of S.captions) {
        const a = renderedToDraft(c.start), b = renderedToDraft(c.end);
        const chip = el('div', 'chip cap', lane);
        chip.style.left = `${a * S.pps}px`;
        chip.style.width = `${Math.max((b - a) * S.pps, 4)}px`;
        chip.textContent = c.text;
      }
    } else {
      const want = tr.id === 'text';
      for (const c of S.insertsDraft) {
        if (isText(c) !== want) continue;
        const chip = el('div', `chip ${want ? 'txt' : 'ins'}`, lane);
        chip.style.left = `${c.start * S.pps}px`;
        chip.style.width = `${Math.max((c.end - c.start) * S.pps, 6)}px`;
        chip.textContent = c.label;
      }
    }
  }
  sizeCanvases();
  positionTimeline();
}

function renderTakes(lane) {
  const dl = draftLayout();
  const rl = renderedLayout();
  const editable = S.view === 'corte';
  dl.forEach((r, i) => {
    const c = el('div', 'take', lane);
    c.dataset.i = i;
    if (r.removed) {
      // tomada tirada: um marcador fino no lugar dela — toque e restaure
      c.classList.add('removed');
      if (i === S.selected) c.classList.add('sel');
      c.style.left = `${r.out * S.pps - 7}px`;
      c.style.width = '14px';
      return;
    }
    c.style.left = `${r.out * S.pps}px`;
    c.style.width = `${Math.max(r.dur * S.pps, 6)}px`;
    if (r.start !== r.orig.start || r.end !== r.orig.end) c.classList.add('dirty');
    if (i === S.selected) c.classList.add('sel');
    if (S.thumbCount > 0 && rl[i]) {
      /* Quadros no tamanho natural, como no CapCut: com zoom alto o mesmo quadro
       * se repete (só existe 1 miniatura a cada 2 s); esticar um quadro de 2 s
       * por 170px vira uma faixa borrada. Com zoom baixo, quadros são pulados. */
      const strip = el('div', 'strip', c);
      const tile = tileWidth();
      const n = Math.ceil((r.dur * S.pps) / tile);
      for (let k = 0; k < n; k++) {
        const tr = rl[i].out + Math.min((k * tile) / S.pps, Math.max(0, rl[i].dur - 0.01));
        const idx = Math.min(S.thumbCount, Math.floor(tr / THUMB_EVERY) + 1); // %04d do ffmpeg começa em 1
        const img = el('img', '', strip);
        img.src = `/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
        img.style.width = `${tile}px`;
        img.alt = '';
        img.draggable = false;
      }
    }
    el('div', 't-label', c).textContent = r.beat || r.source || `tomada ${i + 1}`;
    if (editable && i === S.selected) {
      const l = el('div', 'handle l', c);
      l.dataset.i = i; l.dataset.side = 'l';
      const rr = el('div', 'handle r', c);
      rr.dataset.i = i; rr.dataset.side = 'r';
    }
  });
}

function renderNotes(lane) {
  for (const n of S.notes) {
    const chip = el('div', 'chip note', lane);
    chip.style.left = `${n.start * S.pps}px`;
    chip.style.width = `${Math.max((n.end - n.start) * S.pps, 8)}px`;
    chip.textContent = n.text || '…';
    chip.dataset.id = n.id;
  }
  if (S.pendingIn != null) {
    const p = el('div', 'note-pending', lane);
    p.style.left = `${S.pendingIn * S.pps}px`;
  }
}

function sizeCanvases() {
  const dpr = window.devicePixelRatio || 1;
  for (const cv of [rulerCv, $('wave')]) {
    if (!cv) continue;
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

function positionTimeline() {
  const x0 = half() - S.t * S.pps;
  const tf = `translate3d(${x0.toFixed(2)}px,0,0)`;
  for (const l of lanes) l.style.transform = tf;
  drawRuler();
  drawWave();
  $('tNow').textContent = fmt(S.t);
  $('tTotal').textContent = fmt(totalT());
}

function drawRuler() {
  const ctx = rulerCv.getContext('2d');
  const w = rulerCv.clientWidth, h = rulerCv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  const hw = w / 2;
  const t0 = S.t - hw / S.pps, t1 = S.t + hw / S.pps;
  const steps = [0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const step = steps.find((s) => s * S.pps >= 52) || 300;
  ctx.font = '600 9.5px Poppins, sans-serif';
  ctx.fillStyle = 'rgba(139,148,163,0.9)';
  ctx.strokeStyle = 'rgba(255,255,255,0.16)';
  ctx.lineWidth = 1;
  const end = totalT();
  for (let t = Math.max(0, Math.floor(t0 / step) * step); t <= Math.min(t1, end); t += step) {
    const x = Math.round(hw + (t - S.t) * S.pps) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, h - 7); ctx.lineTo(x, h); ctx.stroke();
    ctx.fillText(fmtShort(t), x + 3, h - 8);
    for (let m = 1; m < 4; m++) {
      const tm = t + (m * step) / 4;
      if (tm > end) break;
      const xm = Math.round(hw + (tm - S.t) * S.pps) + 0.5;
      ctx.beginPath(); ctx.moveTo(xm, h - 3.5); ctx.lineTo(xm, h); ctx.stroke();
    }
  }
}

function drawWave() {
  const cv = $('wave');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const w = cv.clientWidth, h = cv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  // fundo da faixa só onde existe áudio — fora do vídeo a faixa fica vazia
  const end = totalT();
  const hw = w / 2;
  const xa = Math.max(0, hw - S.t * S.pps), xb = Math.min(w, hw + (end - S.t) * S.pps);
  ctx.fillStyle = 'rgba(115,139,3,0.10)';
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(xa, 1, Math.max(0, xb - xa), h - 2, 6) : ctx.rect(xa, 1, Math.max(0, xb - xa), h - 2);
  ctx.fill();
  if (!S.wave) return;
  const mid = h / 2;
  ctx.fillStyle = 'rgba(168,194,43,0.8)';
  const pps = S.wave.peaksPerSec;
  for (let px = Math.floor(xa); px < xb; px++) {
    const tDraft = S.t + (px - hw) / S.pps;
    const idx = Math.floor(draftToRendered(tDraft) * pps);
    if (idx < 0 || idx >= S.wave.max.length) continue;
    const hi = (S.wave.max[idx] / 100) * (mid - 2);
    const lo = (S.wave.min[idx] / 100) * (mid - 2);
    ctx.fillRect(px, mid - hi, 1, Math.max(1, hi - lo));
  }
}

function setZoom(pps) {
  S.pps = Math.min(S.maxPps, Math.max(S.minPps, pps));
  renderTimeline();
}

// ---------- busca no vídeo enquanto o dedo arrasta ----------
let seekQueued = false;
function scheduleSeek(fast) {
  if (seekQueued) return;
  seekQueued = true;
  requestAnimationFrame(() => {
    seekQueued = false;
    const tr = draftToRendered(S.t);
    if (Math.abs((video.currentTime || 0) - tr) < 0.02) return;
    if (fast && typeof video.fastSeek === 'function') video.fastSeek(tr);
    else video.currentTime = tr;
  });
}
function preciseSeek() {
  video.currentTime = draftToRendered(S.t);
}

// ---------- gestos: 1 dedo arrasta, 2 dedos pinça, toque seleciona ----------
const G = { pts: new Map(), mode: null };
let momentum = null;
function stopMomentum() { if (momentum) { cancelAnimationFrame(momentum); momentum = null; } }

timeline.addEventListener('pointerdown', (e) => {
  try { timeline.setPointerCapture(e.pointerId); } catch (err) { /* toque sintético */ }
  G.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  stopMomentum();
  if (G.pts.size === 2) {
    const [a, b] = [...G.pts.values()];
    G.mode = 'pinch';
    G.d0 = Math.hypot(a.x - b.x, a.y - b.y) || 1;
    G.pps0 = S.pps;
    return;
  }
  if (G.pts.size > 2) return;
  const h = e.target.closest('.handle');
  if (h && S.view === 'corte') {
    const i = +h.dataset.i;
    G.mode = 'trim';
    G.trim = { i, side: h.dataset.side, x0: e.clientX, r: { ...S.draft[i] } };
    video.pause();
    return;
  }
  G.mode = 'pan';
  G.x0 = e.clientX; G.t0 = S.t; G.moved = false;
  G.lastX = e.clientX; G.lastT = performance.now(); G.vel = 0;
  G.down = e.target;
  G.downAt = performance.now();
  G.wasPlaying = !video.paused;
});

timeline.addEventListener('pointermove', (e) => {
  if (!G.pts.has(e.pointerId)) return;
  G.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (G.mode === 'pinch' && G.pts.size >= 2) {
    const [a, b] = [...G.pts.values()];
    const d = Math.hypot(a.x - b.x, a.y - b.y);
    const want = G.pps0 * (d / G.d0);
    if (!G.zoomQueued) {
      G.zoomQueued = true;
      requestAnimationFrame(() => { G.zoomQueued = false; setZoom(want); });
    }
    return;
  }
  if (G.mode === 'trim') {
    const T = G.trim;
    const r = S.draft[T.i];
    const dt = (e.clientX - T.x0) / S.pps;
    if (T.side === 'l') {
      r.start = Math.min(Math.max(0, T.r.start + dt), r.end - MIN_SEG);
    } else {
      r.end = Math.max(T.r.end + dt, r.start + MIN_SEG);
      const srcDur = (S.state.sourceDurations || {})[r.source];
      if (srcDur) r.end = Math.min(r.end, srcDur);
    }
    const d = T.side === 'l' ? r.start - r.orig.start : r.end - r.orig.end;
    const tip = $('trimTip');
    tip.textContent = `${T.side === 'l' ? 'início' : 'fim'} ${d >= 0 ? '+' : ''}${d.toFixed(2)} s`;
    tip.classList.remove('hidden');
    if (!G.trimQueued) {
      G.trimQueued = true;
      requestAnimationFrame(() => { G.trimQueued = false; renderTimeline(); refreshHeader(); });
    }
    return;
  }
  if (G.mode === 'pan') {
    const dx = e.clientX - G.x0;
    if (!G.moved && Math.abs(dx) > 6) {
      G.moved = true;
      if (!video.paused) video.pause();
    }
    if (!G.moved) return;
    const now = performance.now();
    const dtMs = Math.max(1, now - G.lastT);
    G.vel = 0.8 * ((e.clientX - G.lastX) / dtMs) + 0.2 * G.vel; // px/ms, suavizada
    G.lastX = e.clientX; G.lastT = now;
    S.t = clampT(G.t0 - dx / S.pps);
    positionTimeline();
    scheduleSeek(true);
  }
});

function endPointer(e) {
  if (!G.pts.has(e.pointerId)) return;
  G.pts.delete(e.pointerId);
  if (G.mode === 'pinch') {
    if (G.pts.size === 1) { // sobrou um dedo: ele passa a arrastar, sem pulo
      const [p] = [...G.pts.values()];
      G.mode = 'pan'; G.x0 = p.x; G.t0 = S.t; G.moved = true; G.lastX = p.x; G.lastT = performance.now(); G.vel = 0;
    } else if (G.pts.size === 0) G.mode = null;
    return;
  }
  if (G.mode === 'trim') {
    $('trimTip').classList.add('hidden');
    G.mode = null;
    renderTimeline(); renderToolbar(); refreshHeader(); // o "Original" acende depois de aparar
    return;
  }
  if (G.mode === 'pan') {
    G.mode = null;
    if (!G.moved && e.type === 'pointerup') { tapAt(G.down); return; }
    if (performance.now() - G.lastT > 80) G.vel = 0; // o dedo parou antes de soltar
    startMomentum(G.vel);
  }
}
timeline.addEventListener('pointerup', endPointer);
timeline.addEventListener('pointercancel', endPointer);

function startMomentum(v) {
  if (Math.abs(v) < 0.05) { preciseSeek(); return; }
  let last = performance.now();
  const step = (now) => {
    const dt = now - last; last = now;
    S.t = clampT(S.t - (v * dt) / S.pps);
    v *= Math.pow(0.93, dt / 16);
    positionTimeline();
    scheduleSeek(true);
    if (Math.abs(v) < 0.02 || S.t <= 0 || S.t >= totalT()) { momentum = null; preciseSeek(); return; }
    momentum = requestAnimationFrame(step);
  };
  momentum = requestAnimationFrame(step);
}

function tapAt(target) {
  const note = target && target.closest && target.closest('.chip.note');
  if (note) { openNote(note.dataset.id, false); return; }
  const take = target && target.closest && target.closest('.take');
  if (take && S.view === 'corte') {
    const i = +take.dataset.i;
    S.selected = S.selected === i ? -1 : i;
  } else {
    S.selected = -1;
  }
  renderTimeline();
  renderToolbar();
}

// rodinha e trackpad, para quem abre no computador
timeline.addEventListener('wheel', (e) => {
  e.preventDefault();
  stopMomentum();
  if (e.ctrlKey) { setZoom(S.pps * Math.exp(-e.deltaY * 0.01)); return; }
  const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
  S.t = clampT(S.t + d / S.pps);
  positionTimeline();
  scheduleSeek(false);
}, { passive: false });

// ---------- reprodução ----------
$('btnPlay').innerHTML = ICON.play;
$('btnMute').innerHTML = ICON.vol;
function togglePlay() {
  if (video.paused) {
    if (S.t >= totalT() - 0.05) { S.t = 0; preciseSeek(); }
    video.play().catch(() => {});
  } else video.pause();
}
$('btnPlay').addEventListener('click', togglePlay);
$('tapPlay').addEventListener('click', togglePlay);
video.addEventListener('play', () => { $('btnPlay').innerHTML = ICON.pause; });
video.addEventListener('pause', () => { $('btnPlay').innerHTML = ICON.play; });
video.addEventListener('ended', () => { $('btnPlay').innerHTML = ICON.play; });
$('btnMute').addEventListener('click', () => {
  video.muted = !video.muted;
  $('btnMute').innerHTML = video.muted ? ICON.mute : ICON.vol;
});

function loop() {
  const now = performance.now() / 1000;
  for (const f of S.cardAnims) f(now);
  for (const f of S.liveAnims) f(now);
  if (!video.paused && !video.ended && !G.mode && !momentum) {
    S.t = clampT(renderedToDraft(video.currentTime));
    positionTimeline();
  }
  requestAnimationFrame(loop);
}

// ---------- barra de ferramentas ----------
function renderToolbar() {
  const tb = $('toolbar');
  const ctx = $('ctxbar');
  const sel = S.selected >= 0 && S.view === 'corte' ? S.draft[S.selected] : null;
  tb.classList.toggle('hidden', !!sel);
  ctx.classList.toggle('hidden', !sel);
  const hasVideo = S.videoDuration > 0;
  const tool = (host, id, label, opts = {}) => {
    const b = el('button', `tool${opts.on ? ' on' : ''}${opts.armed ? ' armed' : ''}${opts.cls ? ` ${opts.cls}` : ''}`, host);
    b.type = 'button';
    b.dataset.tool = id;
    b.disabled = !!opts.disabled;
    b.innerHTML = `${opts.icon || ICON[id]}<span>${label}</span>`;
    return b;
  };
  tb.innerHTML = '';
  tool(tb, 'corte', 'Corte', { on: S.view === 'corte', disabled: !hasVideo });
  tool(tb, 'final', 'Final', { on: S.view === 'final', disabled: !hasFinal() });
  tool(tb, 'estilo', 'Estilo', { disabled: !hasVideo || !canStyle() });
  tool(tb, 'legenda', 'Legenda', { disabled: !hasVideo || !canStyle() });
  tool(tb, 'marcar', S.pendingIn != null ? 'Fim' : 'Marcar', { armed: S.pendingIn != null, disabled: !hasVideo });
  tool(tb, 'enviar', 'Enviar');
  $('btnDownload').classList.toggle('hidden', !hasVideo);

  ctx.innerHTML = '';
  if (sel) {
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'ouvir', 'Ouvir', { disabled: sel.removed });
    if (sel.removed) tool(ctx, 'restaurar', 'Restaurar');
    else tool(ctx, 'remover', 'Tirar');
    tool(ctx, 'original', 'Original', { disabled: !sel.removed && sel.start === sel.orig.start && sel.end === sel.orig.end });
  }
}

document.addEventListener('click', (e) => {
  const b = e.target.closest('.tool');
  if (!b || b.disabled) return;
  const id = b.dataset.tool;
  const r = S.draft[S.selected];
  switch (id) {
    case 'corte': switchView('corte'); break;
    case 'final': switchView('final'); break;
    case 'estilo': openStyle('edit'); break;
    case 'legenda': openStyle('captions'); break;
    case 'marcar': toggleMark(); break;
    case 'enviar': $('fileInput').click(); break;
    case 'voltar': S.selected = -1; renderTimeline(); renderToolbar(); break;
    case 'ouvir': {
      const d = draftLayout()[S.selected];
      S.t = d.out; preciseSeek(); positionTimeline(); video.play().catch(() => {});
      break;
    }
    case 'remover': r.removed = true; renderTimeline(); renderToolbar(); refreshHeader(); break;
    case 'restaurar': r.removed = false; renderTimeline(); renderToolbar(); refreshHeader(); break;
    case 'original': r.start = r.orig.start; r.end = r.orig.end; r.removed = false; renderTimeline(); renderToolbar(); refreshHeader(); break;
    default: break;
  }
});

function switchView(v) {
  if (v === S.view) return;
  S.view = v;
  S.selected = -1;
  setVideoSrc(v);
  renderTimeline();
  renderToolbar();
  refreshHeader();
}

function download() {
  const rel = hasFinal() ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const a = document.createElement('a');
  a.href = `/media/${rel}`;
  a.download = `${(S.state.project || 'cenno-edit').replace(/[\\/:*?"<>|]+/g, '-')}.mp4`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(hasFinal() ? 'Baixando o vídeo final' : 'Baixando o corte (o final ainda não existe)', 2600);
}

$('fileInput').addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  toast(`"${f.name}" escolhido — o envio liga ao kit no próximo passo deste protótipo`, 4200);
});
$('btnEmptyUpload').addEventListener('click', () => $('fileInput').click());
$('emptyIco').innerHTML = ICON.enviar;
$('downloadIco').innerHTML = ICON.baixar;
$('btnDownload').addEventListener('click', download);

// ---------- marcar um trecho (IN → OUT → o que mudar) ----------
function toggleMark() {
  if (S.pendingIn == null) {
    S.pendingIn = S.t;
    renderTimeline(); renderToolbar();
    toast('Início marcado. Arraste até o fim do trecho e toque em Fim.', 3000);
    return;
  }
  const start = Math.min(S.pendingIn, S.t), end = Math.max(S.pendingIn, S.t);
  if (end - start < 0.05) { toast('Trecho curto demais — arraste a linha do tempo', 2200); return; }
  S.pendingIn = null;
  const note = { id: `n${Date.now()}`, start, end, text: '' };
  S.notes.push(note);
  S.notes.sort((a, b) => a.start - b.start);
  renderTimeline(); renderToolbar();
  openNote(note.id, true);
}
function openNote(id, isNew) {
  const n = S.notes.find((x) => x.id === id);
  if (!n) return;
  S.editingNote = id;
  $('noteRange').textContent = `${fmt(n.start)} → ${fmt(n.end)}`;
  $('noteText').value = n.text || '';
  $('noteDelete').classList.toggle('hidden', !!isNew);
  showSheet($('noteSheet'), true);
  setTimeout(() => $('noteText').focus(), 280);
}
function closeNote(keep) {
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (n && keep) n.text = $('noteText').value.trim();
  if (n && !n.text) S.notes = S.notes.filter((x) => x.id !== n.id);
  S.editingNote = null;
  showSheet($('noteSheet'), false);
  renderTimeline(); refreshHeader();
}
$('noteOk').addEventListener('click', () => {
  if (!$('noteText').value.trim()) { toast('Escreva o que mudar', 1800); return; }
  closeNote(true);
});
$('noteCancel').addEventListener('click', () => closeNote(false));
$('noteDelete').addEventListener('click', () => {
  S.notes = S.notes.filter((x) => x.id !== S.editingNote);
  closeNote(false);
});

function showSheet(sheet, open) {
  sheet.classList.toggle('open', open);
  sheet.setAttribute('aria-hidden', String(!open));
}

// ---------- Estilo: painel que sobe + prévia ao vivo ----------
const TABS = [['edit', 'Edição'], ['captions', 'Legenda'], ['headline', 'Headline'], ['accent', 'Cor'], ['extras', 'Extras']];
const normHex = (v) => {
  let s = String(v || '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join('');
  return /^[0-9a-f]{6}$/i.test(s) ? `#${s.toLowerCase()}` : null;
};
const styleName = (group, id) => (STYLE_CATALOG[group].find((o) => o.id === id) || {}).name || '—';
const accentUsed = () => ACCENT_USERS.headlines.includes(S.style.headline) || ACCENT_USERS.captions.includes(S.style.captions);

async function openStyle(tab) {
  if (!S.style) return;
  S.styleTab = tab;
  S.styling = true;
  S.selected = -1;
  video.pause();
  app.classList.add('styling');
  player.classList.add('styling');
  showSheet($('sheet'), true);
  // o corte limpo: no render final a legenda já vem queimada no vídeo
  await setVideoSrc('corte');
  await new Promise((ok) => {
    if (video.readyState >= 2 && !video.seeking) ok();
    else video.addEventListener('seeked', ok, { once: true });
    setTimeout(ok, 1200);
  });
  S.frameUrl = captureFrame();
  await loadBandPoster();
  if (S.styling) renderStyle();
}

function closeStyle() {
  S.styling = false;
  S.cardAnims = [];
  S.liveAnims = [];
  app.classList.remove('styling');
  player.classList.remove('styling', 'is-split', 'band-top');
  for (const k of GEOM_VARS) player.style.removeProperty(k);
  setBand($('ovBand'), false);
  $('ovHl').innerHTML = '';
  $('ovCap').innerHTML = '';
  showSheet($('sheet'), false);
  setVideoSrc(S.view);
  requestAnimationFrame(() => { sizeCanvases(); positionTimeline(); });
}

function captureFrame() {
  try {
    const vw = video.videoWidth, vh = video.videoHeight;
    if (!vw || !vh || video.readyState < 2) throw new Error('sem quadro');
    // 540x960: o cartão de legenda mostra o quadro ampliado; com 216px ficava borrado em tela 3x
    const W = 540, H = 960;
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const scale = Math.max(W / vw, H / vh);
    const sw = W / scale, sh = H / scale;
    cv.getContext('2d').drawImage(video, (vw - sw) / 2, (vh - sh) * 0.3, sw, sh, 0, 0, W, H);
    return cv.toDataURL('image/jpeg', 0.84);
  } catch (e) {
    const idx = Math.min(Math.max(1, Math.floor(draftToRendered(S.t) / THUMB_EVERY) + 1), Math.max(1, S.thumbCount));
    return `/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
  }
}

function renderStyle() {
  document.documentElement.style.setProperty('--hl-accent', S.style.accent || ACCENT_DEFAULT);
  const tabs = $('sheetTabs');
  tabs.innerHTML = '';
  for (const [id, label] of TABS) {
    const b = el('button', `stab${S.styleTab === id ? ' on' : ''}`, tabs);
    b.type = 'button';
    b.dataset.tab = id;
    b.textContent = label;
  }
  const body = $('sheetBody');
  body.innerHTML = '';
  body.scrollTop = 0;
  S.cardAnims = [];

  const hint = styleHint();
  if (hint) el('p', 'sheet-hint', body).textContent = hint;
  if (S.styleTab === 'edit') renderCards(body, 'edits', 'edit');
  else if (S.styleTab === 'captions') renderCards(body, 'captions', 'captions');
  else if (S.styleTab === 'headline') renderCards(body, 'headlines', 'headline');
  else if (S.styleTab === 'accent') renderAccent(body);
  else renderExtras(body);

  updateSummary();
  applyLive();
}

function styleHint() {
  switch (S.styleTab) {
    case 'edit':
      return S.style.edit === 'limpa'
        ? 'Sem imagem de apoio: tela inteira o vídeo todo.'
        : 'No resto do vídeo, você aparece na tela inteira.';
    case 'captions': return 'Toque num estilo e veja em cima, no seu vídeo e no tamanho real.';
    case 'headline':
      return hookText() !== HEADLINE_TEXT
        ? 'A frase que abre o vídeo, já com a headline deste projeto.'
        : 'A frase que abre o vídeo. O texto de verdade o agente escreve depois.';
    default: return '';
  }
}

const CARD_ZOOM = 1.15; // nos cartões de legenda e headline o quadro aparece um pouco ampliado
function renderCards(body, group, key) {
  const tall = group === 'edits';
  const grid = el('div', `cards ${tall ? 'tall' : 'wide'}`, body);
  for (const o of STYLE_CATALOG[group]) {
    const card = el('button', `card${S.style[key] === o.id ? ' on' : ''}`, grid);
    card.type = 'button';
    card.dataset.key = key;
    card.dataset.id = o.id;
    const face = el('div', 'face', card);
    const frame = el('div', 'comp frame', face);
    el('div', 'media', el('div', 'win', frame)).style.backgroundImage = `url("${S.frameUrl}")`;
    const band = el('div', 'band', frame);
    el('div', 'hl', frame);
    el('div', 'cap', frame);
    const look = { ...S.style, [key]: o.id };
    if (tall) {
      // tipo de edição: o quadro inteiro e só o layout (texto a 114px não se lê)
      applyGeom(frame, look, 'meio');
      setBand(band, frame.classList.contains('is-split'), false);
    } else {
      // legenda e headline: recorte do quadro em volta do texto, na proporção do render
      applyGeom(frame, look, 'abertura');
      const fw = face.clientWidth, fh = face.clientHeight;
      const W = fw * CARD_ZOOM, H = (W * FRAME_H) / FRAME_W;
      const c = key === 'headline' ? hlCenter(look) : capCenter(look, 'abertura');
      frame.style.width = `${W}px`;
      frame.style.height = `${H}px`;
      frame.style.left = `${-(W - fw) / 2}px`;
      frame.style.top = `${Math.min(0, Math.max(fh - H, fh / 2 - c * H))}px`;
      if (!o.none) fillText(frame, look, 'abertura', S.cardAnims, key === 'headline' ? 'headline' : 'captions');
    }
    if (o.none) el('div', 'none-mark', face).innerHTML = NONE_MARK;
    el('span', 'c-check', face).innerHTML = ICON.check;
    el('div', 'c-name', card).textContent = o.name;
  }
}

function renderAccent(body) {
  const row = el('div', 'accent-row', body);
  const cur = normHex(S.style.accent) || ACCENT_DEFAULT;
  const sw = el('label', 'swatch', row);
  sw.style.setProperty('--swatch-fill', cur);
  const inp = el('input', '', sw);
  inp.type = 'color';
  inp.value = cur;
  inp.setAttribute('aria-label', 'Escolher cor de destaque');
  const field = el('div', 'hex-field', row);
  el('span', '', field).textContent = '#';
  const hex = el('input', '', field);
  hex.type = 'text';
  hex.maxLength = 7;
  hex.spellcheck = false;
  hex.value = cur.slice(1).toUpperCase();
  hex.setAttribute('aria-label', 'Cor em hexadecimal');
  const where = [
    ACCENT_USERS.headlines.includes(S.style.headline) && 'na headline',
    ACCENT_USERS.captions.includes(S.style.captions) && 'na legenda',
  ].filter(Boolean);
  el('p', 'sheet-hint', body).textContent = where.length
    ? `Aparece ${where.join(' e ')}. Arraste a cor e veja ao vivo em cima.`
    : 'Os estilos escolhidos não usam cor de destaque. Troque a headline para Realce ou Misto, ou a legenda para Empilhado.';
  const commit = (v, fromHex) => {
    const n = normHex(v);
    if (!n) return;
    S.style.accent = n;
    sw.style.setProperty('--swatch-fill', n);
    inp.value = n;
    if (!fromHex) hex.value = n.slice(1).toUpperCase();
    document.documentElement.style.setProperty('--hl-accent', n);
    updateSummary();
  };
  inp.addEventListener('input', () => commit(inp.value));
  hex.addEventListener('input', () => {
    field.classList.toggle('bad', !normHex(hex.value) && hex.value.trim() !== '');
    commit(hex.value, true);
  });
  hex.addEventListener('blur', () => { field.classList.remove('bad'); hex.value = (normHex(S.style.accent) || ACCENT_DEFAULT).slice(1).toUpperCase(); });
}

function renderExtras(body) {
  const list = el('div', 'chk-list', body);
  for (const e of STYLE_CATALOG.elements) {
    const on = !!S.style.elements[e.id];
    const row = el('button', `chk${on ? ' on' : ''}`, list);
    row.type = 'button';
    row.dataset.el = e.id;
    el('span', 'chk-ico', row).innerHTML = e.icon;
    el('span', 'chk-name', row).textContent = e.name;
    el('span', 'switch', row);
  }
  const note = el('textarea', 'note-field', body);
  note.rows = 2;
  note.placeholder = 'Algo mais para o agente saber? (opcional)';
  note.value = S.style.note || '';
  note.addEventListener('input', () => { S.style.note = note.value; });
}

/* A prévia de cima: o vídeo de verdade com o estilo escolhido por cima. Na aba
 * Edição ela mostra um trecho do meio (tela dividida); nas outras, a abertura. */
function applyLive() {
  if (!S.styling) return;
  const moment = S.styleTab === 'edit' ? 'meio' : 'abertura';
  applyGeom(player, S.style, moment);
  setBand($('ovBand'), player.classList.contains('is-split'), true);
  S.liveAnims = [];
  fillText(player, S.style, moment, S.liveAnims);
}

function updateSummary() {
  const on = STYLE_CATALOG.elements.filter((e) => S.style.elements[e.id]);
  const accentBit = accentUsed() ? ` · cor ${String(S.style.accent).toUpperCase()}` : '';
  $('sheetSum').textContent = `${styleName('edits', S.style.edit)} · legenda ${styleName('captions', S.style.captions)}`
    + ` · headline ${styleName('headlines', S.style.headline)}${accentBit}`
    + (on.length ? ` · ${on.length} extra${on.length > 1 ? 's' : ''}` : '');
  $('sheetApply').textContent = S.state.awaitingStyle ? 'Começar' : 'Aplicar';
}

$('sheetTabs').addEventListener('click', (e) => {
  const b = e.target.closest('.stab');
  if (!b) return;
  S.styleTab = b.dataset.tab;
  renderStyle();
});
$('sheetBody').addEventListener('click', (e) => {
  const card = e.target.closest('.card');
  if (card) {
    // sem reconstruir os cartões: a lista não pula para o topo a cada toque
    S.style[card.dataset.key] = card.dataset.id;
    for (const c of card.parentNode.children) c.classList.toggle('on', c === card);
    const hint = $('sheetBody').querySelector('.sheet-hint');
    if (hint) hint.textContent = styleHint();
    updateSummary();
    applyLive();
    return;
  }
  const chk = e.target.closest('.chk');
  if (chk) {
    S.style.elements[chk.dataset.el] = !S.style.elements[chk.dataset.el];
    chk.classList.toggle('on', S.style.elements[chk.dataset.el]);
    updateSummary();
  }
});
$('sheetClose').addEventListener('click', closeStyle);

$('sheetApply').addEventListener('click', async () => {
  const payload = {
    type: 'style-setup',
    rerender: !S.state.awaitingStyle,
    edit: S.style.edit,
    editName: styleName('edits', S.style.edit),
    headline: S.style.headline,
    headlineName: styleName('headlines', S.style.headline),
    captions: S.style.captions,
    captionsName: styleName('captions', S.style.captions),
    accent: S.style.accent,
    accentName: String(S.style.accent || ACCENT_DEFAULT).toUpperCase(),
    accentUsed: accentUsed(),
    elements: { ...S.style.elements },
    elementNames: STYLE_CATALOG.elements.filter((e) => S.style.elements[e.id]).map((e) => e.name),
    note: (S.style.note || '').trim(),
  };
  try {
    const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!(await res.json()).ok) throw new Error('falhou');
    S.savedPending = true;
    closeStyle();
    refreshHeader();
    toast('Estilo enviado. O agente refaz o vídeo com ele.', 3200);
  } catch (err) {
    toast('Não consegui enviar — o editor ainda está ligado no computador?', 4000);
  }
});

// ---------- salvar ajustes do corte (mesmo payload do editor de PC) ----------
$('btnSave').addEventListener('click', async () => {
  const payload = { type: 'timeline-edits' };
  if (edlDirty()) {
    payload.edl = {
      ranges: S.draft.filter((r) => !r.removed).map((r) => ({ source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat })),
      removed: S.draft.filter((r) => r.removed).map((r) => ({ source: r.source, beat: r.beat, start: r.orig.start, end: r.orig.end })),
      changes: S.draft.filter((r) => !r.removed && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
        source: r.source, beat: r.beat,
        from: { start: r.orig.start, end: r.orig.end },
        to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
      })),
    };
  }
  if (S.notes.length) {
    payload.notes = S.notes.map((n) => ({
      start: +n.start.toFixed(3),
      end: +n.end.toFixed(3),
      renderedStart: +draftToRendered(n.start).toFixed(3),
      renderedEnd: +draftToRendered(n.end).toFixed(3),
      phase: S.view === 'final' ? 2 : 1,
      text: n.text,
    }));
  }
  try {
    const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!(await res.json()).ok) throw new Error('falhou');
    S.savedPending = true;
    S.notes = [];
    S.pendingIn = null;
    S.draft = S.draft.filter((r) => !r.removed);
    S.draft.forEach((r) => { r.orig = { start: r.start, end: r.end }; });
    S.selected = -1;
    renderTimeline(); renderToolbar(); refreshHeader();
    toast('Ajustes enviados. O agente refaz o corte.', 3000);
  } catch (err) {
    toast('Não consegui salvar — o editor ainda está ligado no computador?', 4000);
  }
});

// ---------- avisos ----------
let toastTimer = null;
function toast(msg, ms) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms || 3000);
}

// ---------- início ----------
window.addEventListener('resize', () => {
  sizeCanvases();
  positionTimeline();
  if (S.styling) requestAnimationFrame(renderStyle); // os cartões recortam pela largura
});
poll();
loop();
if (document.fonts && document.fonts.ready) {
  // as amostras medem o texto: erradas até a Poppins carregar
  document.fonts.ready.then(() => { if (S.styling) renderStyle(); });
}
