/* CutMind — editor de celular.
 *
 * MESMO backend do editor de PC — nenhum servidor novo:
 *   GET  /api/state            state.json + edl.json + mtimes
 *   GET  /media/<arquivo>      vídeo, legendas, edit-data, transcrição do corte
 *   GET  /gen/thumbs/*.jpg     miniaturas (1 a cada 2 s)
 *   GET  /gen/waveform.json    forma de onda
 *   GET  /gen/frame?src=&t=    quadro do vídeo de ORIGEM (a alça ao aparar)
 *   POST /api/save             timeline-edits → preview_edits.json
 *                              style-setup    → preview_style.json
 *   POST /api/upload?name=     o vídeo escolhido → pasta dos vídeos no computador;
 *                              imagem e áudio → <edit>/midia/ (viram camadas)
 *   GET  /media/camadas.json   as camadas do projeto (o Salvar leva `camadas`)
 *   GET  /media/efeitos.json   filtros e transições do projeto (o Salvar leva `efeitos`)
 *   GET  /api/pacotes?tipo=    a biblioteca do kit: trilha, filtro, transicao
 *   GET  /gen/pacote/<id>/<a>  um arquivo de filtro/transição (o computador baixa na 1ª vez)
 *   GET  /efeitos/motor.js     o motor de efeitos, o mesmo do vídeo final
 * Pela rede (servidor com --host), os dados só saem para quem abriu pelo link
 * ou QR do computador; sem isso /api/state dá 403 e a tela diz o que falta.
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
 *  - Catálogo e amostras vêm de estilos.js, o mesmo arquivo do editor de PC.
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
/* Editor único: na tela larga com mouse, o mesmo editor se arruma no jeito do CapCut desktop
 * (biblioteca à esquerda, prévia no meio, propriedades à direita, linha do tempo embaixo).
 * A classe `desk` no <html> liga esse leiaute; `?leiaute=computador` força, para testar. */
const DESK_MQ = matchMedia('(min-width: 1024px) and (hover: hover) and (pointer: fine)');
const isDesk = () => document.documentElement.classList.contains('desk');
function aplicarDesk() {
  const forca = new URLSearchParams(location.search).get('leiaute');
  const on = forca ? forca === 'computador' : DESK_MQ.matches;
  document.documentElement.classList.toggle('desk', on);
}
aplicarDesk();
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
  avancar: sv('<path d="M9.5 6l6 6-6 6"/>'),
  ouvir: sv('<path d="M4.5 15v-2.5a7.5 7.5 0 0 1 15 0V15"/><rect x="3.5" y="14" width="4" height="6" rx="1.6"/><rect x="16.5" y="14" width="4" height="6" rx="1.6"/>'),
  remover: sv('<path d="M5 7h14M10 7V5.2c0-.4.3-.7.7-.7h2.6c.4 0 .7.3.7.7V7M7 7l.8 11.2c.1 1 .9 1.8 1.9 1.8h4.6c1 0 1.8-.8 1.9-1.8L17 7"/>'),
  restaurar: sv('<path d="M8.5 7 4.5 11l4 4"/><path d="M5 11h9a5 5 0 0 1 0 10h-3"/>'),
  original: sv('<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5v3.2h3.2"/>'),
  dividir: sv('<path d="M12 3.5v17"/><path d="M8.5 8 5 12l3.5 4M15.5 8 19 12l-3.5 4"/>'),
  duplicar: sv('<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>'),
  cheia: sv('<path d="M4.5 9V5.5a1 1 0 0 1 1-1H9M15 4.5h3.5a1 1 0 0 1 1 1V9M19.5 15v3.5a1 1 0 0 1-1 1H15M9 19.5H5.5a1 1 0 0 1-1-1V15"/>'),
  fechar: sv('<path d="M6 9.5l6 6 6-6"/>', 2),
  mais: sv('<path d="M12 5v14M5 12h14"/>', 2.2),
  seta: sv('<path d="M6 9.5l6 6 6-6"/>', 2.6),
  desfazer: sv('<path d="M3.5 7.5v6h6"/><path d="M20.5 17a8.5 8.5 0 0 0-8.5-8.5 8.6 8.6 0 0 0-5.9 2.4L3.5 13.5"/>', 1.9),
  refazer: sv('<path d="M20.5 7.5v6h-6"/><path d="M3.5 17a8.5 8.5 0 0 1 8.5-8.5 8.6 8.6 0 0 1 5.9 2.4l2.6 2.6"/>', 1.9),
  check: sv('<path d="M5 12.5l4.5 4.5L19 7.5"/>', 3),
  mover: sv('<path d="M12 3.5v17M3.5 12h17"/><path d="M9.5 6 12 3.5 14.5 6M9.5 18l2.5 2.5 2.5-2.5M6 9.5 3.5 12 6 14.5M18 9.5l2.5 2.5-2.5 2.5"/>'),
  todas: sv('<rect x="4" y="5" width="16" height="4" rx="1.4"/><rect x="4" y="11" width="16" height="4" rx="1.4"/><path d="M7 19.5h10"/>'),
  imagem: sv('<rect x="3" y="5" width="18" height="14" rx="2.6"/><circle cx="8.5" cy="10" r="1.6"/><path d="M4 17.5l5-4.6 3.4 3 2.4-2 5.2 4"/>'),
  audio: sv('<path d="M9 17.5V6.2l10-2v11"/><circle cx="6.6" cy="17.5" r="2.4"/><circle cx="16.6" cy="15.2" r="2.4"/>'),
  som: sv('<path d="M4.5 9.5v5h3.2l4.8 4V5.5l-4.8 4z"/><path d="M15.8 9a4 4 0 0 1 0 6M18.4 6.6a7.4 7.4 0 0 1 0 10.8"/>'),
  semSom: sv('<path d="M4.5 9.5v5h3.2l4.8 4V5.5l-4.8 4z"/><path d="M16 9.6l4.8 4.8m0-4.8L16 14.4"/>'),
  olho: sv('<path d="M2.8 12s3.4-6 9.2-6 9.2 6 9.2 6-3.4 6-9.2 6-9.2-6-9.2-6z"/><circle cx="12" cy="12" r="2.6"/>'),
  olhoFechado: sv('<path d="M2.8 12s3.4-6 9.2-6 9.2 6 9.2 6-3.4 6-9.2 6-9.2-6-9.2-6z"/><path d="M4 20 20 4"/>'),
  cadeado: sv('<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>'),
  cadeadoAberto: sv('<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 6.6-1.6"/>'),
  melhorar: sv('<path d="M3.5 12h2.2M7.7 8.5v7M11.9 5.5v13M16.1 8.5v7M20.3 12h-2.2"/>'),
  volume: sv('<path d="M4.5 9.5v5h3.2l4.8 4V5.5l-4.8 4z"/><path d="M15.8 9a4 4 0 0 1 0 6"/>'),
  estrela: sv('<path d="M12 3.8l2.5 5.1 5.6.8-4 3.9.9 5.6L12 16.6l-5 2.6.9-5.6-4-3.9 5.6-.8z"/>'),
  estrelaCheia: sv('<path d="M12 3.8l2.5 5.1 5.6.8-4 3.9.9 5.6L12 16.6l-5 2.6.9-5.6-4-3.9 5.6-.8z" fill="currentColor"/>'),
  efeitos: sv('<circle cx="9" cy="9.6" r="5"/><circle cx="15" cy="9.6" r="5"/><circle cx="12" cy="14.8" r="5"/>'),
  filtro: sv('<circle cx="12" cy="12" r="7.5"/><path d="M12 4.5a7.5 7.5 0 0 1 0 15z" fill="currentColor" stroke="none"/>'),
  transicao: sv('<rect x="2.5" y="6.5" width="7" height="11" rx="1.6"/><rect x="14.5" y="6.5" width="7" height="11" rx="1.6"/><path d="M12 9.4l2.6 2.6-2.6 2.6-2.6-2.6z" fill="currentColor" stroke="none"/>'),
  velocidade: sv('<path d="M4.5 16.5a8 8 0 1 1 15 0"/><path d="M12 13.2l3.6-4" stroke-width="2"/><circle cx="12" cy="13.6" r="1.4" fill="currentColor"/>'),
  ajustar: sv('<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="2.2" fill="currentColor"/><circle cx="15.5" cy="12" r="2.2" fill="currentColor"/><circle cx="7.5" cy="17" r="2.2" fill="currentColor"/>'),
  celular: sv('<rect x="6.5" y="2.5" width="11" height="19" rx="2.4"/><path d="M10.5 18.5h3"/>'),
  intensidade: sv('<path d="M4 12h16"/><circle cx="14.5" cy="12" r="2.6" fill="currentColor"/>'),
};

/* ---------- catálogo de estilos e amostras: estilos.js ----------
 * O mesmo arquivo do editor de PC, carregado antes deste. Os ids e nomes são o
 * contrato com a skill (preview_style.json). As miniaturas desenhadas (mock) do
 * editor de PC ficam de fora: aqui cada opção aparece sobre um quadro do vídeo. */
const {
  STYLE_CATALOG, ACCENT_USERS, ACCENT_DEFAULT, CAP_TEXT, HEADLINE_TEXT, HL_STYLES, STATIC_VARIANTS, ORPHAN_PT,
  CAP_BUILDERS, buildHeadlineDemo, buildStaticDemo, capPhrases,
} = CutMindEstilos;

// o "Nenhum" mais claro que o do PC: aqui ele fica sobre o vídeo, não sobre fundo liso
const NONE_MARK = '<svg viewBox="0 0 64 34" style="width:56%;height:auto">'
  + '<rect x="1" y="1" width="62" height="32" rx="5" fill="none" '
  + 'stroke="rgba(255,255,255,.4)" stroke-width="1.5" stroke-dasharray="4 3"/>'
  + '<path d="M14 24L50 10" stroke="rgba(255,255,255,.45)" stroke-width="1.5" '
  + 'stroke-linecap="round"/></svg>';

/* ---------- onde cada coisa fica no quadro: números do render ----------
 * Fonte (mudou lá, muda aqui), tudo em px do quadro 1080x1920:
 *  - CustomGraphics.tsx: tela dividida, faixa de 750 e LAYOUT top/bottom (zoom, focusY)
 *  - references/shortform.md: legenda na emenda, paddingBottom 1074 / 790
 *  - Main.tsx: HL_STYLES.top da headline; captionPlace.ts: na tela dividida TODO estilo
 *    de legenda assenta na linha do karaokê (captions.windows), e a frase que a pessoa
 *    arrastou (captions.positions) fica onde foi posta
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
const GEOM_VARS = ['--win-top', '--win-h', '--m-left', '--m-top', '--m-w', '--m-h', '--band-top', '--band-h', '--hl-top', '--cap-c', '--cap-pb', '--fx', '--fy'];
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
  // tela dividida: todo estilo de legenda na linha do karaokê, sobre a emenda
  node.classList.toggle('cap-seam', !!g);
  node.classList.remove('cap-free');
  if (g) node.style.setProperty('--cap-pb', pct(g.capPB / FRAME_H));
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
  const words = S.capText || undefined; // sem transcrição do corte: a frase padrão
  if (c && !c.none) {
    if (c.demo) anims.push(CAP_BUILDERS[c.demo](cap, words));
    else { const st = buildStaticDemo(cap, c.stat, words); if (st) anims.push(st); }
  }
}

/* A amostra de legenda com as palavras ditas no trecho que está na tela. Vêm da
 * transcrição do corte (transcripts/cut.json, a mesma que vira captions.json na
 * Fase 2). No primeiro portão de estilo ela pode ainda não existir: aí fica a
 * frase padrão, como no editor de PC. */
async function loadCutWords() {
  if (S.cutWords !== undefined) return S.cutWords;
  S.cutWords = null;
  try {
    const r = await fetch(`/media/transcripts/cut.json?v=${S.mtimes.video || 0}`);
    if (r.ok) {
      const d = await r.json();
      S.cutWords = (d.words || [])
        .filter((w) => w.type !== 'spacing' && String(w.text || '').trim())
        .map((w) => ({ t: String(w.text).trim(), s: +w.start, e: +w.end, k: w.type }));
    }
  } catch (e) { /* sem transcrição do corte */ }
  return S.cutWords;
}
function wordsAt(words, t) {
  if (!words || !words.length) return null;
  const i = words.findIndex((w) => w.e >= t);
  if (i < 0) return null;
  const out = [];
  for (let k = i; k < words.length && out.length < 7; k++) {
    const w = words[k].t;
    const clean = w.replace(/[.,!?…;:]+$/, '');
    if (clean) out.push(clean);
    if (out.length >= 4 && /[.!?…]$/.test(w)) break; // termina com a frase, se ela acabar logo
  }
  while (out.length > 3 && ORPHAN_PT.test(out[out.length - 1])) out.pop(); // não acaba em "e", "de", "que"
  return out.length >= 3 ? out.join(' ') : null;
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
  insSel: -1,         // o bloco da Fase 2 escolhido na vista Final (índice em insertsDraft)
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
  capFilter: 'uma',   // filtro da aba Legenda: 'uma' ou 'varias' (linhas)
  swipeTaught: false, // a dica "Deslize para trocar" já apareceu nesta visita
  posMode: false,     // "Posição das frases": toca na frase sobre o vídeo e arrasta
  frases: [],         // as frases da legenda escolhida, no relógio do cut.mp4
  frasesFor: '',      // estilo e corte para os quais S.frases foi montado
  fraseShown: null,   // a frase desenhada na prévia agora (a que está debaixo da agulha)
  todas: false,       // botão "Todas": mexer em uma mexe em todas
  posTaught: false,   // a dica "Toque na frase e arraste" já apareceu
  frameUrl: null,
  bandUrl: null,      // um quadro da imagem de apoio do projeto (cartões)
  bandFor: '',
  cardAnims: [],
  liveAnims: [],
  seq: 0,             // numeração das tomadas novas (divisão, cópia)
  base: [],           // as tomadas como estavam no último corte recebido ou no último Salvar
  camadas: { versao: 1, video: { mudo: false }, faixas: [] }, // imagens e áudios postos pela pessoa (camadas.json)
  camadasBase: '',    // as camadas como estavam ao abrir ou no último Salvar
  layerSel: null,     // id do item de camada escolhido
  mudoUsuario: false, // o alto-falante da linha do play (só a prévia; não vai para o vídeo)
  midiaDur: {},       // duração de cada áudio de midia/, lida do arquivo
  audioMenu: false,   // Áudio tocado: a barra mostra Trilhas / Do celular
  importMenu: false,  // Importar (ou o + da faixa) tocado: a barra mostra Vídeo / Imagem / Áudio
  trilhas: null,      // a biblioteca do kit (lista do servidor), carregada ao abrir
  trilhaNomes: {},    // id da trilha → nome, para o bloco na linha do tempo
  efeitos: { versao: 1, itens: [] }, // filtros e transições postos pela pessoa (efeitos.json)
  efeitosBase: '',    // os efeitos como estavam ao abrir ou no último Salvar
  fxSel: null,        // id do efeito escolhido na linha do tempo
  fxMenu: false,      // Efeitos tocado: a barra mostra Filtros / Transições
  fxLista: {},        // tipo → pacotes da biblioteca (filtro, transicao)
  fxNomes: {},        // id do pacote → nome, para o bloco na linha do tempo
  fxTeste: null,      // o efeito tocado no painel, mostrado na prévia antes do "Usar"
};

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const d = Math.floor(t * 10 + 1e-6); // décimos: o bastante para achar o ponto, sem piscar
  const m = Math.floor(d / 600);
  const s = (d - m * 600) / 10;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
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
// a velocidade com que a tomada i do edl.json já está no cut.mp4
const velR = (i) => (S.rendered[i] ? S.rendered[i].vel : 1);
/* Curva de velocidade (etapa 4d): `r.curva` = {nome, pontos [[x, y]]} ou null; com curva, `vel`
 * fica 1. Toda conta de tempo de uma tomada com curva passa pelos pedaços do tempo.js, os
 * mesmos do render; sem curva nenhum lado mudou, é a conta da 4c. */
const pedsD = (r) => Tempo.pedacos(r.start, r.end, r.vel, r.curva || null);
const pedsR = (i) => { const R = S.rendered[i]; return R ? Tempo.pedacos(R.start, R.end, R.vel, R.curva || null) : [[0, 1, 1]]; };
const curvaKey = (r) => (r && r.curva ? `${r.curva.nome}:${JSON.stringify(r.curva.pontos)}` : '');
const copiaCurva = (c) => (c ? { nome: c.nome, pontos: c.pontos.map((p) => [p[0], p[1]]) } : null);
const comCurva = (d) => !!(d.curva || (S.rendered[d.from] && S.rendered[d.from].curva));
/* Cada tomada do rascunho sabe de onde veio: `uid` (o<i> = tomada i do edl.json; n<k> =
 * nova, de uma divisão ou cópia) e `from` (a tomada do edl.json de onde sai o conteúdo).
 * Dividir, copiar e mover só mudam esta lista; o cut.mp4 continua o mesmo até o agente
 * refazer, e a prévia mostra cada pedaço achando o trecho dele dentro do cut.mp4. */
function draftLayout() {
  let t = 0;
  let at = 0;
  return S.draft.map((r) => {
    // a sobra do J-cut é de uma tomada inteira do edl.json; pedaço novo não tem
    const g = r.orig ? jcutGeom(r.from) : { lead: 0, tail: 0 };
    // a sobra e a cauda do J-cut estão em tempo do cut.mp4: na gravação, × a velocidade dele;
    // no rascunho, ÷ a velocidade nova da tomada (a régua de Velocidade). Com curva, pelos pedaços.
    const R = r.orig ? S.rendered[r.from] : null;
    let leadSrc, tailSrc;
    if (R && R.curva) {
      const pR = pedsR(r.from);
      leadSrc = Tempo.gravacaoEm(pR, g.lead) - R.start;
      tailSrc = R.end - Tempo.gravacaoEm(pR, Tempo.corteAte(pR, R.end) - g.tail);
    } else {
      const rv = r.orig ? velR(r.from) : 1;
      leadSrc = g.lead * rv;
      tailSrc = g.tail * rv;
    }
    let adur, lead;
    if (r.curva) {
      const pD = pedsD(r);
      adur = Math.max(0, Tempo.durTrecho(pD, r.start, r.end - tailSrc));
      lead = Tempo.durTrecho(pD, r.start, r.start + leadSrc);
    } else {
      adur = Math.max(0, (r.end - r.start - tailSrc) / r.vel);
      lead = leadSrc / r.vel;
    }
    const dur = Math.max(0, adur - lead);
    const item = { ...r, out: t, dur, aout: Math.max(0, at - lead), adur, lead, leadSrc, tailSrc };
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
  return S.rendered.map((r, i) => {
    const dur = r.curva ? Tempo.corteAte(pedsR(i), r.end) : (r.end - r.start) / r.vel;
    const item = { ...r, out: t, dur };
    t += dur;
    return item;
  });
}
const draftTotal = () => draftLayout().reduce((a, r) => a + r.dur, 0);
const totalT = () => draftTotal() || S.videoDuration || 0;
// onde, no cut.mp4, está o quadro que a tomada `d` do rascunho mostra no instante `t`
function itemRendered(d, t, rl = renderedLayout()) {
  const R = S.rendered[d.from], L = rl[d.from];
  if (!R || !L) return Math.min(t, S.videoDuration);
  let rt;
  if (comCurva(d)) { // o instante da gravação pela curva do rascunho; no cut.mp4, pela dele
    const s = Tempo.gravacaoEm(pedsD(d), (d.lead || 0) + (t - d.out));
    rt = L.out + Tempo.corteAte(pedsR(d.from), s) - jcutGeom(d.from).lead;
  } else {
    const s = d.start + (d.leadSrc || 0) + (t - d.out) * d.vel; // instante do arquivo de origem
    rt = L.out + (s - (R.start + jcutGeom(d.from).lead * R.vel)) / R.vel;
  }
  // além do que o cut.mp4 tem (alça puxada para fora): o quadro mais perto
  return Math.max(L.out, Math.min(rt, L.out + L.dur - 0.02));
}
function itemAt(dl, t) {
  for (let k = dl.length - 1; k >= 0; k--) if (t >= dl[k].out) return k;
  return dl.length ? 0 : -1;
}
function draftToRendered(t) {
  const dl = draftLayout();
  const k = itemAt(dl, t);
  if (k < 0) return Math.min(t, S.videoDuration);
  const d = dl[k];
  return itemRendered(d, Math.min(t, d.out + Math.max(0, d.dur - 1e-3)));
}
// o contrário, só para o que ainda está no lugar de origem (vídeo final e faixas dele)
function renderedToDraft(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = rl.length - 1; i >= 0; i--) {
    const r = rl[i];
    if (t < r.out) continue;
    const d = dl.find((x) => x.uid === `o${i}`);
    if (!d) return dl.length ? Math.min(t, dl[dl.length - 1].out) : t; // tomada excluída
    if (comCurva(d)) {
      const s = Tempo.gravacaoEm(pedsR(i), jcutGeom(i).lead + (t - r.out));
      return d.out + Math.max(0, Math.min(Tempo.corteAte(pedsD(d), s) - (d.lead || 0), d.dur));
    }
    return d.out + Math.min((t - r.out) * velR(i) / d.vel, d.dur); // velocidade nova: o trecho estica ou encolhe
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
  // o texto do gancho vem em `lines` (modelo antigo) ou em `text`, com quebra de linha
  const gancho = (h) => (h.lines || (h.text ? String(h.text).split('\n') : [])).join(' / ') || 'Gancho';
  if (d.hook && d.hook.enabled) list.push({ kind: 'hook', label: gancho(d.hook), start: 0, end: d.hook.endSec || 4 });
  (d.inserts || []).forEach((it, i) => list.push({ kind: 'insert', label: (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i }));
  (d.splitInserts || []).forEach((it, i) => list.push({ kind: 'split', label: it.label || (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i }));
  (d.splitVideos || []).forEach((it, i) => list.push({ kind: 'splitvideo', label: it.label || (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i }));
  (d.behind || []).forEach((b, i) => list.push({ kind: 'behind', label: b.kind === 'words' ? (b.words || []).map((w) => w.t).join(' ') : (b.src || '').split('/').pop(), start: +b.start, end: +b.start + +b.dur, ref: i }));
  (d.wordAccents || []).forEach((w, i) => list.push({ kind: 'word', label: w.text, start: +w.start, end: +w.end, ref: i }));
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
  S.insSel = -1;
}
const isText = (c) => c.kind === 'hook' || c.kind === 'word';
// o bloco andou ou foi aparado desde o último vídeo do agente (ou o último Salvar)
const insMudou = (c) => c.start !== c.orig.start || c.end !== c.orig.end;
const insertsDirty = () => S.insertsDraft.some(insMudou);

// ---------- o que mudou e ainda não foi salvo ----------
// comparado com o último corte recebido (ou o último Salvar): aparada, nova, excluída, ordem, volume
const baseOf = (draft) => draft.map((r) => ({ uid: r.uid, start: r.start, end: r.end, vol: r.vol, vel: r.vel, ck: curvaKey(r) }));
function diffBase() {
  const base = new Map(S.base.map((b) => [b.uid, b]));
  const now = new Set(S.draft.map((r) => r.uid));
  let mudou = 0;
  for (const r of S.draft) {
    const b = base.get(r.uid);
    if (!b || b.start !== r.start || b.end !== r.end || b.vol !== r.vol || b.vel !== r.vel || b.ck !== curvaKey(r)) mudou++;
  }
  mudou += S.base.filter((b) => !now.has(b.uid)).length;
  const antes = S.base.map((b) => b.uid).filter((u) => now.has(u));
  const depois = S.draft.map((r) => r.uid).filter((u) => base.has(u));
  if (antes.join() !== depois.join()) mudou++;
  return mudou;
}
const edlDirty = () => diffBase() > 0;
function dirtyCount() {
  return diffBase() + S.notes.length + S.insertsDraft.filter(insMudou).length + (camadasDirty() ? 1 : 0) + (efeitosDirty() ? 1 : 0);
}
const isChanged = (r) => {
  const b = S.base.find((x) => x.uid === r.uid);
  return !b || b.start !== r.start || b.end !== r.end || b.vol !== r.vol || b.vel !== r.vel || b.ck !== curvaKey(r);
};
function refreshHeader() {
  const n = dirtyCount();
  const hasVideo = S.videoDuration > 0;
  // um botão principal no canto: Salvar quando há ajuste; sem ajuste, Baixar
  $('btnSave').classList.toggle('hidden', n === 0);
  $('btnDownload').classList.toggle('hidden', n > 0 || !hasVideo);
  $('dirtyCount').textContent = n;
  $('sentPill').classList.toggle('hidden', !(S.savedPending && n === 0));
  $('modeLabel').textContent = S.view === 'final' ? 'Final' : 'Corte';
  $('projectSub').textContent = hasVideo ? fmtShort(totalT()) : '';
  $('btnMode').disabled = !hasFinal(); // sem vídeo final, a prévia só tem o corte
}

// ---------- desfazer / refazer ----------
// Antes de cada ação que muda o corte ou as marcações (aparar, tirar, restaurar,
// original, marcar, nota, posição de frase), guarda uma foto do estado. Depois de
// Salvar, ou quando chega um corte novo do agente, o histórico zera: o que foi
// enviado não volta daqui.
const HIST = { past: [], future: [], max: 100 };
function snap() {
  return {
    draft: S.draft.map((r) => ({ ...r, orig: r.orig ? { ...r.orig } : null, curva: copiaCurva(r.curva) })),
    notes: S.notes.map((n) => ({ ...n })),
    pendingIn: S.pendingIn,
    selected: S.selected,
    pos: S.style ? JSON.parse(JSON.stringify(capPos())) : null,
    cam: JSON.parse(JSON.stringify(S.camadas)),
    layerSel: S.layerSel,
    fx: JSON.parse(JSON.stringify(S.efeitos)),
    fxSel: S.fxSel,
    ins: S.insertsDraft.map((c) => ({ start: c.start, end: c.end })),
    insSel: S.insSel,
  };
}
function remember(before) {
  HIST.past.push(before || snap());
  if (HIST.past.length > HIST.max) HIST.past.shift();
  HIST.future = [];
  renderHistory();
}
function forgetHistory() {
  HIST.past = [];
  HIST.future = [];
  renderHistory();
}
function restore(s) {
  if (S.editingNote) { S.editingNote = null; showSheet($('noteSheet'), false); }
  S.draft = s.draft;
  S.notes = s.notes;
  S.pendingIn = s.pendingIn;
  S.selected = s.selected < S.draft.length ? s.selected : -1;
  if (S.style && s.pos) S.style.captionPositions = JSON.parse(JSON.stringify(s.pos));
  if (s.cam) S.camadas = s.cam;
  S.layerSel = s.layerSel && camItem(s.layerSel) ? s.layerSel : null;
  if (s.fx) S.efeitos = s.fx;
  S.fxSel = s.fxSel && fxItem(s.fxSel) ? s.fxSel : null;
  // os blocos da Fase 2 são os mesmos objetos (o agente manda outros junto com um histórico zerado)
  if (s.ins && s.ins.length === S.insertsDraft.length) s.ins.forEach((v, k) => Object.assign(S.insertsDraft[k], v));
  S.insSel = s.insSel != null && s.insSel < S.insertsDraft.length ? s.insSel : -1;
  applyMute();
  S.t = clampT(S.t);
  renderTimeline(); renderToolbar(); refreshHeader(); renderHistory();
  drawFrase(true);
  fxPreparar();
  fxRedesenhar();
}
function undo() {
  if (!HIST.past.length || G.mode) return;
  HIST.future.push(snap());
  restore(HIST.past.pop());
}
function redo() {
  if (!HIST.future.length || G.mode) return;
  HIST.past.push(snap());
  restore(HIST.future.pop());
}
function renderHistory() {
  $('btnUndo').disabled = !HIST.past.length;
  $('btnRedo').disabled = !HIST.future.length;
}

// ---------- dados ----------
// Pela rede, o servidor só entrega os dados a quem abriu pelo link/QR do computador.
const EMPTY_TEXTS = { title: $('emptyTitle').textContent, text: $('emptyText').textContent };
function setLocked(on) {
  if (!!S.locked === on) return;
  S.locked = on;
  $('emptyTitle').textContent = on ? 'Falta o código deste computador' : EMPTY_TEXTS.title;
  $('emptyText').textContent = on
    ? 'Por segurança, pela rede o editor só abre com o link ou o QR code que aparece no computador. Abra por ele uma vez: este celular fica liberado.'
    : EMPTY_TEXTS.text;
  $('btnEmptyUpload').classList.toggle('hidden', on);
  $('emptyAlt').classList.toggle('hidden', on);
  if (on) {
    $('empty').classList.remove('hidden');
    $('projectSub').textContent = 'sem o código deste computador';
  }
}

async function poll() {
  try {
    const res = await fetch('/api/state');
    if (res.status === 403) { setLocked(true); setTimeout(poll, 4000); return; }
    setLocked(false);
    const data = await res.json();
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
  S.cutWords = undefined; // o corte pode ter mudado: a transcrição dele é lida de novo
  S.videoDuration = data.videoDuration || 0;
  S.fps = S.state.fps || 30;
  S.savedPending = !!data.hasPendingEdits;
  document.title = S.state.project ? `${S.state.project} · CutMind` : 'CutMind';
  // o que o agente está fazendo, como no editor de PC antigo (no celular fica escondido)
  $('projectName').textContent = S.state.project || '';
  $('agentMsg').textContent = S.state.message || '';
  $('agent').title = [S.state.project, S.state.message].filter(Boolean).join(' — ');

  const ranges = (data.edl && data.edl.ranges) || [];
  S.jcut = (data.edl && data.edl.jcut_timeline) || null;
  // `vol` e `vel` são o volume e a velocidade da tomada (1 = como está); o cut.mp4 já sai com os do edl.json
  S.rendered = ranges.map((r) => ({ source: r.source, start: +r.start, end: +r.end, beat: r.beat || '',
    vol: r.volume == null ? 1 : +r.volume, vel: r.velocidade == null ? 1 : +r.velocidade,
    curva: r.curva && Array.isArray(r.curva.pontos) ? { nome: r.curva.nome || 'personalizar', pontos: r.curva.pontos.map((p) => [+p[0], +p[1]]) } : null }));
  S.draft = S.rendered.map((r, i) => ({ ...r, uid: `o${i}`, from: i, orig: { start: r.start, end: r.end } }));
  S.base = baseOf(S.draft);
  S.selected = -1;
  forgetHistory(); // corte novo: as fotos antigas são de outras tomadas

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
  S.layerSel = null;
  S.fxSel = null;
  S.fxTeste = null;
  await loadCamadas();
  await loadEfeitos();
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
  // ~14 s na largura da tela: dá para ver as miniaturas e acertar a alça com o dedo; no
  // computador a linha do tempo é larga e o mouse é preciso: ~40 s
  S.pps = Math.min(S.maxPps, Math.max(S.minPps, w / (isDesk() ? 40 : 14)));
  S.fitted = true;
  syncZoom();
}

function trackPlan() {
  const fin = S.view === 'final';
  const hasTxt = S.insertsDraft.some(isText);
  const hasIns = S.insertsDraft.some((c) => !isText(c));
  // camadas: as de imagem ficam acima do vídeo, as de áudio abaixo do som dele
  const fx = S.posMode ? [] : S.camadas.faixas;
  const lh = fx.length > 2 ? 20 : 26;
  const layer = (f) => ({ id: `L-${f.id}`, h: lh, show: true, faixa: f });
  return [
    { id: 'frases', h: 22, show: S.posMode && S.frases.length > 0 },
    { id: 'notes', h: 14, show: S.notes.length > 0 || S.pendingIn != null },
    { id: 'caps', h: 18, show: fin && S.captions.length > 0 },
    { id: 'text', h: 18, show: fin && hasTxt },
    { id: 'ins', h: 18, show: fin && hasIns },
    ...fx.filter((f) => f.tipo === 'imagem').reverse().map(layer), // a mais nova fica no alto, como no editor do PC
    // filtros, transições e ajustes valem para o corte: no Final já estão no vídeo. O ajuste
    // tem faixa própria, como no CapCut: na mesma tomada de um filtro, os dois ficariam um em cima do outro
    { id: 'fx', h: 22, show: !fin && !S.posMode && S.efeitos.itens.some((it) => it.tipo !== 'ajuste') },
    { id: 'aj', h: 22, show: !fin && !S.posMode && S.efeitos.itens.some((it) => it.tipo === 'ajuste') },
    { id: 'video', h: VIDEO_TRACK_H, show: true },
    { id: 'audio', h: 30, show: true },
    ...fx.filter((f) => f.tipo === 'audio').map(layer),
  ].filter((t) => t.show);
}
// a linha do tempo cresce com as camadas até um teto; acima dele as faixas encolhem
const TL_MIN = 178, TL_MAX = 292;

const VIDEO_TRACK_H = 56;
const MOVE_TILE = 60; // largura de cada tomada enquanto se move uma
const tileWidth = () => {
  const ar = video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 9 / 16;
  return Math.max(24, Math.round((VIDEO_TRACK_H - 3) * ar));
};

let lanes = []; // elementos que andam juntos sob a agulha
function renderTimeline() {
  tracksEl.innerHTML = '';
  lanes = [];
  const width = `${Math.max(totalT(), 0.1) * S.pps}px`;
  const plan = trackPlan();
  // régua (30) + respiro (6) + faixas e os vãos entre elas
  const need = 36 + plan.reduce((a, t) => a + t.h, 0) + 6 * (plan.length - 1);
  // no computador a linha do tempo acompanha a janela: ~1/4 da altura, e a prévia fica com o resto
  const [tlMin, tlMax] = isDesk()
    ? [Math.min(260, Math.max(170, Math.round(innerHeight * 0.26))), Math.round(innerHeight * 0.45)]
    : [TL_MIN, TL_MAX];
  const tlH = Math.min(tlMax, Math.max(tlMin, need));
  timeline.style.height = `${tlH}px`;
  document.documentElement.style.setProperty('--tl-h', `${tlH}px`); // os painéis encaixados param acima dela
  for (const tr of plan) {
    const track = el('div', `track tr-${tr.faixa ? 'layer' : tr.id}`, tracksEl);
    track.style.height = `${tr.h}px`;
    if (tr.id === 'audio') {
      track.classList.toggle('mudo', S.view === 'corte' && S.camadas.video.mudo);
      el('canvas', 'wave', track).id = 'wave';
      continue;
    }
    const lane = el('div', 'lane', track);
    lane.style.width = width;
    lane.dataset.track = tr.id;
    lanes.push(lane);
    if (tr.faixa) { renderLayerTrack(track, lane, tr.faixa); continue; }
    if (tr.id === 'video') { renderTakes(lane); if (S.view === 'corte' && !S.posMode) trackHead(track, null); }
    else if (tr.id === 'frases') renderFrases(lane);
    else if (tr.id === 'fx') renderFxTrack(lane, false);
    else if (tr.id === 'aj') renderFxTrack(lane, true);
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
      S.insertsDraft.forEach((c, i) => {
        if (isText(c) !== want) return;
        const chip = el('div', `chip f2 ${want ? 'txt' : 'ins'}`, lane);
        chip.dataset.i = i;
        chip.style.left = `${c.start * S.pps}px`;
        chip.style.width = `${Math.max((c.end - c.start) * S.pps, 6)}px`;
        el('span', 'l-name', chip).textContent = c.label; // escolhido, o bloco mostra as alças por fora: o nome corta dentro
        if (insMudou(c)) chip.classList.add('dirty');
        if (i === S.insSel) {
          chip.classList.add('sel');
          if (c.kind !== 'hook') el('div', 'lh l', chip).dataset.side = 'l'; // o gancho começa no 0
          el('div', 'lh r', chip).dataset.side = 'r';
        }
      });
    }
  }
  sizeCanvases();
  positionTimeline();
  if (S.posMode) markFrases();
}

function renderTakes(lane) {
  const dl = draftLayout();
  const rl = renderedLayout();
  const editable = S.view === 'corte';
  // movendo: toda tomada vira um quadrado do mesmo tamanho, para levar uma longa
  // de uma ponta à outra sem arrastar por um minuto de linha do tempo
  const movendo = G.mode === 'move' && G.mv;
  if (movendo) lane.style.width = `${dl.length * MOVE_TILE}px`;
  dl.forEach((r, i) => {
    const c = el('div', 'take', lane);
    c.dataset.i = i;
    if (movendo && G.mv.i === i) c.classList.add('lifted'); // a que está sendo movida
    c.style.left = movendo ? `${i * MOVE_TILE + 2}px` : `${r.out * S.pps}px`;
    c.style.width = movendo ? `${MOVE_TILE - 4}px` : `${Math.max(r.dur * S.pps, 6)}px`;
    if (isChanged(r)) c.classList.add('dirty');
    if (i === S.selected) c.classList.add('sel');
    if (S.thumbCount > 0 && rl[r.from]) {
      /* Quadros no tamanho natural, como no CapCut: com zoom alto o mesmo quadro
       * se repete (só existe 1 miniatura a cada 2 s); esticar um quadro de 2 s
       * por 170px vira uma faixa borrada. Com zoom baixo, quadros são pulados.
       * Cada quadro é o do trecho DESTA tomada no cut.mp4 (dividida, copiada ou movida). */
      const strip = el('div', 'strip', c);
      const tile = tileWidth();
      const n = movendo ? 1 : Math.ceil((r.dur * S.pps) / tile);
      for (let k = 0; k < n; k++) {
        const tr = itemRendered(r, r.out + Math.min((k * tile) / S.pps, Math.max(0, r.dur - 0.01)), rl);
        const idx = Math.min(S.thumbCount, Math.floor(tr / THUMB_EVERY) + 1); // %04d do ffmpeg começa em 1
        const img = el('img', '', strip);
        img.src = `/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
        img.style.width = movendo ? '100%' : `${tile}px`;
        img.alt = '';
        img.draggable = false;
      }
    }
    el('div', 't-label', c).textContent = r.beat || r.source || `tomada ${i + 1}`;
    if ((r.vol !== 1 || r.vel !== 1 || r.curva) && !movendo) {
      const tags = el('div', 't-tags', c);
      if (r.vol !== 1) el('span', 't-vol', tags).innerHTML = `${ICON.vol}${Math.round(r.vol * 100)}%`;
      if (r.curva) el('span', 't-vel', tags).textContent = nomeCurva(r.curva.nome);
      else if (r.vel !== 1) el('span', 't-vel', tags).textContent = fmtVel(r.vel);
    }
    if (editable && i === S.selected) {
      const l = el('div', 'handle l', c);
      l.dataset.i = i; l.dataset.side = 'l';
      const rr = el('div', 'handle r', c);
      rr.dataset.i = i; rr.dataset.side = 'r';
    }
  });
  if (editable && !movendo) {
    // "+" no fim da faixa: a mesma escolha do Importar (o toque é tratado em tapAt)
    const add = el('button', 'add-tile', lane);
    add.type = 'button';
    add.innerHTML = ICON.mais;
    add.setAttribute('aria-label', 'Importar vídeo, imagem ou áudio');
    add.style.left = `${dl.reduce((a, d) => Math.max(a, d.out + d.dur), 0) * S.pps + 10}px`;
  }
  if (G.mode === 'move') el('div', 'move-caret', lane).id = 'moveCaret'; // onde ela vai cair
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
  // movendo uma tomada, a faixa de vídeo (em quadrados) anda pelo próprio deslocamento
  const mv = G.mode === 'move' && G.mv ? `translate3d(${G.mv.off.toFixed(2)}px,0,0)` : null;
  for (const l of lanes) l.style.transform = mv && l.dataset.track === 'video' ? mv : tf;
  drawRuler();
  drawWave();
  $('tNow').textContent = fmt(S.t);
  $('tTotal').textContent = fmt(totalT());
  drawFrase(); // no "Posição das frases": a frase debaixo da agulha (só refaz quando muda)
}

function drawRuler() {
  const ctx = rulerCv.getContext('2d');
  const w = rulerCv.clientWidth, h = rulerCv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  const hw = w / 2;
  const t0 = S.t - hw / S.pps, t1 = S.t + hw / S.pps;
  const steps = [0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const step = steps.find((s) => s * S.pps >= 52) || 300;
  ctx.font = '600 9.5px Montserrat, system-ui, sans-serif';
  ctx.fillStyle = 'rgba(166,166,166,0.9)';
  ctx.strokeStyle = 'rgba(255,255,255,0.16)';
  ctx.lineWidth = 1;
  const end = totalT();
  for (let t = Math.max(0, Math.floor(t0 / step) * step); t <= Math.min(t1, end); t += step) {
    const x = Math.round(hw + (t - S.t) * S.pps) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, h - 7); ctx.lineTo(x, h); ctx.stroke();
    // com zoom alto as marcas caem no meio do segundo: elas mostram a fração (.25, .5, .75),
    // senão a régua repetiria "0:00 0:00 0:00 0:01"
    const inteiro = Math.abs(t - Math.round(t)) < 1e-6;
    ctx.fillText(inteiro ? fmtShort(Math.round(t)) : `.${String(Math.round((t % 1) * 100)).replace(/0$/, '')}`, x + 3, h - 8);
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
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(xa, 1, Math.max(0, xb - xa), h - 2, 4) : ctx.rect(xa, 1, Math.max(0, xb - xa), h - 2);
  ctx.fill();
  if (!S.wave) return;
  const mid = h / 2;
  ctx.fillStyle = 'rgba(214,214,214,0.6)';
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
  syncZoom();
  renderTimeline();
}
// régua de zoom do computador: escala logarítmica entre o vídeo inteiro e o zoom máximo
const zoomDe = (v) => S.minPps * Math.pow(S.maxPps / S.minPps, v / 100);
const syncZoom = () => {
  const v = Math.round((100 * Math.log(S.pps / S.minPps)) / Math.log(S.maxPps / S.minPps));
  $('zoomRange').value = Number.isFinite(v) ? v : 0;
};
$('zoomRange').addEventListener('input', (e) => setZoom(zoomDe(+e.target.value)));
$('zoomFit').addEventListener('click', () => setZoom(S.minPps));

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

// ---------- quadro do vídeo de ORIGEM na alça, enquanto apara ----------
// O corte (cut.mp4) não tem o que foi cortado: esticando a tomada não haveria o
// que mostrar. O servidor tira o quadro do arquivo de origem (/gen/frame). Um
// pedido por vez; o último tempo pedido vence, o resto é descartado.
const PEEK = { busy: false, want: null, shown: '' };
function requestPeek(source, t) {
  PEEK.want = { source, t: Math.max(0, t) };
  pumpPeek();
}
function pumpPeek() {
  if (PEEK.busy || !PEEK.want) return;
  const { source, t } = PEEK.want;
  PEEK.want = null;
  const key = `${source}@${t.toFixed(2)}`;
  if (key === PEEK.shown) return;
  PEEK.busy = true;
  const h = Math.min(960, Math.round(player.clientHeight * (window.devicePixelRatio || 1)));
  const img = new Image();
  img.onload = () => {
    PEEK.busy = false;
    PEEK.shown = key;
    if (G.mode === 'trim') { $('peek').src = img.src; $('peek').classList.remove('hidden'); }
    pumpPeek();
  };
  img.onerror = () => { PEEK.busy = false; pumpPeek(); };
  img.src = `/gen/frame?src=${encodeURIComponent(source)}&t=${t.toFixed(3)}&h=${h}`;
}
function hidePeek() {
  PEEK.want = null;
  $('peek').classList.add('hidden');
}
// a alça da direita mostra o ÚLTIMO quadro que fica, não o primeiro que sai
const edgeT = (r, side) => (side === 'l' ? r.start : Math.max(r.start, r.end - 1 / (S.fps || 30)));

// ---------- gestos: 1 dedo arrasta, 2 dedos pinça, toque seleciona ----------
const G = { pts: new Map(), mode: null };
let momentum = null;
function stopMomentum() { if (momentum) { cancelAnimationFrame(momentum); momentum = null; } }

timeline.addEventListener('pointerdown', (e) => {
  // os botões do cabeçalho da faixa e a régua de zoom recebem o próprio clique: capturar o toque o roubaria
  if (e.target.closest('.th, .tl-zoom')) return;
  try { timeline.setPointerCapture(e.pointerId); } catch (err) { /* toque sintético */ }
  G.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  stopMomentum();
  clearTimeout(G.lp);
  if (G.pts.size === 2) {
    if (G.mode === 'move' || G.mode === 'layer' || G.mode === 'ins') return; // movendo uma tomada, camada ou bloco, o segundo dedo não vira pinça
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
    G.trim = { i, side: h.dataset.side, x0: e.clientX, r: { ...S.draft[i] }, before: snap() };
    video.pause();
    requestPeek(S.draft[i].source, edgeT(S.draft[i], h.dataset.side));
    return;
  }
  const lh = e.target.closest('.lh');
  if (lh && lh.closest('.chip.f2')) { if (startInsDrag(e.clientX, 'trim', lh.dataset.side)) return; }
  else if (lh && startLayerDrag(e.clientX, 'trim', lh.dataset.side)) return;
  G.mode = 'pan';
  G.x0 = e.clientX; G.t0 = S.t; G.moved = false;
  G.lastX = e.clientX; G.lastT = performance.now(); G.vel = 0;
  G.down = e.target;
  G.downAt = performance.now();
  G.wasPlaying = !video.paused;
  // segurar uma tomada sem arrastar: ela sai da faixa e vai para onde o dedo levar
  const tk = e.target.closest('.take');
  if (tk && S.view === 'corte' && !S.posMode) G.lp = setTimeout(() => startMove(+tk.dataset.i, e.clientX), 450);
  // segurar um item de camada: ele passa a andar com o dedo
  const lc = e.target.closest('.chip.layer');
  if (lc) G.lp = setTimeout(() => holdLayer(lc.dataset.id, e.clientX), 450);
  // segurar um bloco da Fase 2 (vista Final): ele anda com o dedo
  const f2 = e.target.closest('.chip.f2');
  if (f2 && S.view === 'final') G.lp = setTimeout(() => holdIns(+f2.dataset.i, e.clientX), 450);
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
    // dt é do corte; a borda, da gravação (com curva, pela velocidade da curva naquela ponta)
    const vb = r.curva ? Tempo.velEm(pedsD(T.r), T.side === 'l' ? T.r.start : T.r.end - 1e-6) : r.vel;
    if (T.side === 'l') {
      r.start = Math.min(Math.max(0, T.r.start + dt * vb), r.end - MIN_SEG);
    } else {
      r.end = Math.max(T.r.end + dt * vb, r.start + MIN_SEG);
      const srcDur = (S.state.sourceDurations || {})[r.source];
      if (srcDur) r.end = Math.min(r.end, srcDur);
    }
    requestPeek(r.source, edgeT(r, T.side));
    const ref = r.orig || T.r; // pedaço novo (divisão, cópia) não tem borda original: conta do início do gesto
    const d = T.side === 'l' ? r.start - ref.start : r.end - ref.end;
    const tip = $('trimTip');
    tip.textContent = `${T.side === 'l' ? 'início' : 'fim'} ${d >= 0 ? '+' : ''}${d.toFixed(2)} s`;
    tip.classList.remove('hidden');
    if (!G.trimQueued) {
      G.trimQueued = true;
      requestAnimationFrame(() => { G.trimQueued = false; renderTimeline(); refreshHeader(); });
    }
    return;
  }
  if (G.mode === 'move') { G.mv.x = e.clientX; updateMove(); return; }
  if (G.mode === 'layer') { dragLayer(e.clientX); return; }
  if (G.mode === 'ins') { dragIns(e.clientX); return; }
  if (G.mode === 'pan') {
    const dx = e.clientX - G.x0;
    if (!G.moved && Math.abs(dx) > 6) {
      G.moved = true;
      clearTimeout(G.lp); // arrastou antes do tempo: é rolagem, não mover
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
  clearTimeout(G.lp);
  if (G.mode === 'move') { if (G.pts.size === 0) endMove(e.type === 'pointerup'); return; }
  if (G.mode === 'layer') { if (G.pts.size === 0) endLayerDrag(); return; }
  if (G.mode === 'ins') { if (G.pts.size === 0) endInsDrag(); return; }
  if (G.mode === 'pinch') {
    if (G.pts.size === 1) { // sobrou um dedo: ele passa a arrastar, sem pulo
      const [p] = [...G.pts.values()];
      G.mode = 'pan'; G.x0 = p.x; G.t0 = S.t; G.moved = true; G.lastX = p.x; G.lastT = performance.now(); G.vel = 0;
    } else if (G.pts.size === 0) G.mode = null;
    return;
  }
  if (G.mode === 'trim') {
    $('trimTip').classList.add('hidden');
    hidePeek();
    G.mode = null;
    const T = G.trim, r = S.draft[T.i];
    if (r.start !== T.r.start || r.end !== T.r.end) remember(T.before); // tocar na alça sem arrastar não conta
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

// ---------- mover: segurar a tomada e arrastar para outro lugar ----------
function startMove(i, x) {
  if (G.mode !== 'pan' || G.moved || !S.draft[i]) return;
  G.mode = 'move';
  const box = timeline.getBoundingClientRect();
  // os quadrados começam com o da tomada segurada debaixo do dedo
  G.mv = { i, x, to: i, off: x - box.left - (i * MOVE_TILE + MOVE_TILE / 2) };
  if (navigator.vibrate) navigator.vibrate(12);
  video.pause();
  S.selected = i;
  timeline.classList.add('moving');
  renderTimeline();
  renderToolbar();
  const ghost = el('div', 'move-ghost', timeline);
  const thumb = timeline.querySelector(`.take[data-i="${i}"] .strip img`);
  if (thumb) el('img', '', ghost).src = thumb.src;
  el('span', '', ghost).textContent = S.draft[i].beat || `tomada ${i + 1}`;
  G.mv.ghost = ghost;
  updateMove();
  let last = performance.now();
  const pan = (now) => { // dedo perto da borda: os quadrados andam sozinhos
    if (G.mode !== 'move') return;
    const r = timeline.getBoundingClientRect();
    const dir = G.mv.x < r.left + 44 ? -1 : G.mv.x > r.right - 44 ? 1 : 0;
    if (dir) {
      const n = S.draft.length;
      G.mv.off = Math.min(half(), Math.max(half() - n * MOVE_TILE, G.mv.off - (dir * 240 * (now - last)) / 1000));
      positionTimeline();
      updateMove();
    }
    last = now;
    requestAnimationFrame(pan);
  };
  requestAnimationFrame(pan);
}
function updateMove() {
  const M = G.mv;
  const r = timeline.getBoundingClientRect();
  M.ghost.style.left = `${M.x - r.left}px`;
  // metade esquerda de um quadrado = cai antes dele; metade direita = depois
  M.to = Math.max(0, Math.min(S.draft.length, Math.floor((M.x - r.left - M.off) / MOVE_TILE + 0.5)));
  const caret = $('moveCaret');
  if (caret) caret.style.left = `${M.to * MOVE_TILE}px`;
}
function endMove(keep) {
  const M = G.mv;
  G.mode = null;
  M.ghost.remove();
  timeline.classList.remove('moving');
  let to = M.to;
  if (keep && to !== M.i && to !== M.i + 1) {
    remember();
    const [it] = S.draft.splice(M.i, 1);
    if (to > M.i) to -= 1;
    S.draft.splice(to, 0, it);
    S.selected = to;
  }
  renderTimeline(); renderToolbar(); refreshHeader();
}

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
  if (S.posMode) {
    // no "Posição das frases" o toque na faixa leva a agulha até a frase; tomada não é escolhida
    const fr = target && target.closest && target.closest('.chip.frase');
    const f = fr && S.frases[+fr.dataset.i];
    if (f) { S.t = clampT(renderedToDraft(f.start) + 0.02); positionTimeline(); preciseSeek(); }
    return;
  }
  if (target && target.closest && target.closest('.add-tile')) {
    S.selected = -1; S.layerSel = null; S.fxSel = null; S.audioMenu = false; S.fxMenu = false; S.importMenu = true;
    renderTimeline(); renderToolbar();
    return;
  }
  const note = target && target.closest && target.closest('.chip.note');
  if (note) { openNote(note.dataset.id, false); return; }
  const lc = target && target.closest && target.closest('.chip.layer');
  if (lc) { S.fxSel = null; tapLayer(lc.dataset.id); return; }
  const fc = target && target.closest && target.closest('.chip.fx');
  if (fc) { tapFx(fc.dataset.id); return; }
  const f2 = target && target.closest && target.closest('.chip.f2');
  if (f2 && S.view === 'final') { tapIns(+f2.dataset.i); return; }
  S.layerSel = null;
  S.fxSel = null;
  S.insSel = -1;
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
$('btnFull').innerHTML = ICON.cheia;
$('btnFull').addEventListener('click', () => {
  if (player.requestFullscreen) player.requestFullscreen().catch(() => {});
  else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen(); // iPhone: só o vídeo vai para a tela cheia
});
function togglePlay() {
  if (video.paused) {
    if (S.t >= totalT() - 0.05) { S.t = 0; preciseSeek(); }
    video.play().catch(() => {});
  } else video.pause();
}
$('btnPlay').addEventListener('click', togglePlay);
// logo depois de deslizar para trocar o estilo, ou de mexer numa frase, o clique que o
// navegador manda junto não dá play
const tapGuard = { until: 0 };
$('tapPlay').addEventListener('click', () => { if (performance.now() > tapGuard.until) togglePlay(); });
video.addEventListener('play', () => { $('btnPlay').innerHTML = ICON.pause; });
video.addEventListener('pause', () => { $('btnPlay').innerHTML = ICON.play; });
video.addEventListener('ended', () => { $('btnPlay').innerHTML = ICON.play; });
$('btnMute').addEventListener('click', () => {
  S.mudoUsuario = !S.mudoUsuario; // só a prévia: o silenciar que vai para o vídeo fica no cabeçalho da faixa
  applyMute();
  $('btnMute').innerHTML = S.mudoUsuario ? ICON.mute : ICON.vol;
});
$('btnUndo').innerHTML = ICON.desfazer;
$('btnRedo').innerHTML = ICON.refazer;
$('btnUndo').addEventListener('click', undo);
$('btnRedo').addEventListener('click', redo);
// no computador: Ctrl+Z desfaz; Ctrl+Shift+Z ou Ctrl+Y refaz (fora dos campos de texto)
document.addEventListener('keydown', (e) => {
  if (!(e.ctrlKey || e.metaKey) || S.styling || e.target.closest('input, textarea')) return;
  const k = e.key.toLowerCase();
  if (k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
  else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); redo(); }
});

/* ---------- teclado: os atalhos do CapCut desktop que cabem aqui ----------
 * Fora dos campos de texto. Com o Estilo aberto ou no modo Posição, só Espaço e Esc. */
const emCampo = (e) => !!(e.target.closest && e.target.closest('input, textarea, select, [contenteditable]'));
function passo(seg) {
  if (!S.videoDuration) return;
  video.pause();
  S.t = clampT(S.t + seg);
  positionTimeline();
  preciseSeek();
}
// Esc fecha o painel aberto como o botão dele: o Estilo sem aplicar, a nota sem guardar,
// os de régua no Pronto (a régua já mudou ao vivo)
const FECHA_PAINEL = { sheet: 'sheetClose', noteSheet: 'noteCancel', volSheet: 'volOk', velSheet: 'velOk', ajSheet: 'ajOk',
  fxIntSheet: 'fxIntOk', trilhaSheet: 'trilhaClose', fxSheet: 'fxClose' };
function fechaPainel() {
  const aberto = document.querySelector('.sheet.open');
  if (!aberto || !FECHA_PAINEL[aberto.id]) return false;
  $(FECHA_PAINEL[aberto.id]).click();
  return true;
}
function mostraAjuda(abre) { $('helpModal').classList.toggle('hidden', !abre); }
document.addEventListener('keydown', (e) => {
  if (e.defaultPrevented || e.altKey || emCampo(e)) return;
  const k = e.key, ctrl = e.ctrlKey || e.metaKey;
  if (!$('phoneModal').classList.contains('hidden')) { // o quadro do QR por cima de tudo
    if (k === 'Escape') fechaCelular();
    return;
  }
  const ajuda = !$('helpModal').classList.contains('hidden');
  if (k === '?' && !ctrl) { e.preventDefault(); mostraAjuda(!ajuda); return; }
  if (k === 'Escape') {
    if (ajuda) mostraAjuda(false);
    else if (S.posMode) exitPosMode();
    else if (fechaPainel()) { /* fechou o painel */ }
    else if (S.pendingIn != null) { S.pendingIn = null; renderTimeline(); renderToolbar(); toast('Marcação cancelada', 1600); }
    else soltaEscolha();
    return;
  }
  if (ajuda || !S.videoDuration) return;
  if ((k === ' ' || e.code === 'Space') && !ctrl) {
    e.preventDefault();
    // o botão com foco "clicaria" de novo ao soltar a tecla
    if (document.activeElement && document.activeElement.tagName === 'BUTTON') document.activeElement.blur();
    togglePlay();
    return;
  }
  if (S.styling || S.posMode) return;
  const kl = k.toLowerCase();
  if ((k === 'ArrowLeft' || k === 'ArrowRight') && !ctrl) {
    e.preventDefault();
    const seg = e.shiftKey ? 1 : 1 / (S.fps || 30);
    passo(k === 'ArrowRight' ? seg : -seg);
  } else if (kl === 'm' && !ctrl) {
    toggleMark();
  } else if (k === 'Delete' || k === 'Backspace') {
    e.preventDefault();
    if (S.layerSel) deleteLayerSel();
    else if (S.fxSel) deleteFxSel();
    else if (S.selected >= 0 && S.view === 'corte') deleteSelected();
  } else if (ctrl && kl === 'b') { // dividir: sem nada escolhido, a tomada debaixo da agulha (CapCut)
    e.preventDefault();
    if (S.layerSel || S.fxSel) return;
    if (S.selected < 0 || S.view !== 'corte') selectUnderNeedle();
    if (S.selected >= 0) splitSelected();
  } else if (ctrl && kl === 'd') { // no navegador seria "favoritar"
    e.preventDefault();
    if (S.selected >= 0 && S.view === 'corte') duplicateSelected();
  }
});
$('btnHelp').addEventListener('click', () => mostraAjuda(true));
$('helpClose').addEventListener('click', () => mostraAjuda(false));
$('helpModal').addEventListener('click', (e) => { if (e.target === $('helpModal')) mostraAjuda(false); });

function loop() {
  const now = performance.now() / 1000;
  for (const f of S.cardAnims) f(now);
  for (const f of S.liveAnims) f(now);
  if (!video.paused && !video.ended && !G.mode && !momentum) {
    if (S.view === 'corte') followDraft();
    else { if (video.playbackRate !== 1) video.playbackRate = 1; S.t = clampT(renderedToDraft(video.currentTime)); positionTimeline(); }
  }
  syncLayers();
  syncVolTomada();
  if (!video.requestVideoFrameCallback) fxDesenhar(video.currentTime, false); // sem o aviso de quadro: a cada volta
  requestAnimationFrame(loop);
}

/* No corte, tocar segue a ORDEM DO RASCUNHO: dentro de uma tomada o vídeo anda sozinho;
 * no fim dela, salta para onde a próxima está no cut.mp4. Assim o que foi dividido,
 * copiado ou movido já toca na ordem nova, antes de o agente refazer o corte. */
function followDraft() {
  if (video.seeking) return;
  const dl = draftLayout();
  const k = itemAt(dl, S.t);
  if (k < 0) return;
  const d = dl[k];
  // tomada com velocidade nova: o cut.mp4 toca mais rápido ou mais devagar (o tom fica).
  // Com curva, o ritmo muda dentro da tomada: a razão entre as duas curvas naquele ponto.
  let ritmo, t;
  if (comCurva(d)) {
    const L = renderedLayout()[d.from];
    const pR = pedsR(d.from), pD = pedsD(d);
    const s = Tempo.gravacaoEm(pR, jcutGeom(d.from).lead + (video.currentTime - L.out));
    ritmo = Math.min(16, Math.max(0.0625, Tempo.velEm(pD, s) / Tempo.velEm(pR, s)));
    t = d.out + Tempo.corteAte(pD, s) - (d.lead || 0);
  } else {
    ritmo = d.vel / velR(d.from);
    t = d.out + (video.currentTime - itemRendered(d, d.out)) / ritmo;
  }
  if (video.playbackRate !== ritmo) video.playbackRate = ritmo;
  if (t < d.out - 0.3 || t > d.out + d.dur + 0.3) { video.currentTime = itemRendered(d, Math.min(S.t, d.out + d.dur)); return; }
  if (t >= d.out + d.dur - 0.02) {
    const nx = dl[k + 1];
    if (!nx) { video.pause(); S.t = totalT(); positionTimeline(); return; }
    S.t = nx.out;
    const alvo = itemRendered(nx, nx.out);
    if (Math.abs(video.currentTime - alvo) > 0.08) video.currentTime = alvo; // emenda que já é contínua não salta
  } else {
    S.t = Math.max(d.out, t);
  }
  positionTimeline();
}

// ---------- barra de ferramentas ----------
/* dica ao passar o mouse: o nome da ferramenta (quando o rótulo é um valor, como "100%") e o atalho */
const ATALHO = { dividir: 'Ctrl+B', duplicar: 'Ctrl+D', excluir: 'Delete', marcar: 'M', voltar: 'Esc' };
const DICA = { volume: 'Volume', velocidade: 'Velocidade e curva', intensidade: 'Intensidade do filtro' };
function renderToolbar() {
  const tb = $('toolbar');
  const ctx = $('ctxbar');
  const lsel = S.layerSel ? camItem(S.layerSel) : null;
  const fsel = !lsel && S.fxSel && S.view === 'corte' ? fxItem(S.fxSel) : null;
  const sel = !lsel && !fsel && S.selected >= 0 && S.view === 'corte' ? S.draft[S.selected] : null;
  const isel = !lsel && !fsel && S.view === 'final' && S.insSel >= 0 ? S.insertsDraft[S.insSel] || null : null;
  if (sel || lsel || fsel || isel) { S.audioMenu = false; S.importMenu = false; S.fxMenu = false; }
  const amenu = S.audioMenu, imenu = S.importMenu, fmenu = S.fxMenu;
  tb.classList.toggle('hidden', !!(sel || lsel || fsel || isel || amenu || imenu || fmenu));
  ctx.classList.toggle('hidden', !(sel || lsel || fsel || isel || amenu || imenu || fmenu));
  const hasVideo = S.videoDuration > 0;
  const tool = (host, id, label, opts = {}) => {
    const b = el('button', `tool${opts.on ? ' on' : ''}${opts.armed ? ' armed' : ''}${opts.cls ? ` ${opts.cls}` : ''}`, host);
    b.type = 'button';
    b.dataset.tool = id;
    b.disabled = !!opts.disabled;
    b.innerHTML = `${opts.icon || ICON[id]}<span>${label}</span>`;
    b.title = (DICA[id] || label) + (ATALHO[id] ? ` (${ATALHO[id]})` : '');
    return b;
  };
  if (S.posMode) { // "Posição das frases": a barra é do modo
    tb.classList.add('hidden');
    ctx.classList.remove('hidden');
    ctx.innerHTML = '';
    tool(ctx, 'pronto', 'Pronto', { icon: ICON.check, cls: 'back' });
    tool(ctx, 'todas', 'Todas', { icon: ICON.todas, on: S.todas });
    tool(ctx, 'padrao', 'Padrão', { icon: ICON.original });
    return;
  }
  tb.innerHTML = '';
  // Corte/Final virou o seletor do topo. Importar traz qualquer arquivo do celular e
  // pergunta o tipo (o + no fim da faixa abre a mesma escolha)
  tool(tb, 'importar', 'Importar', { icon: ICON.mais });
  tool(tb, 'cortar', 'Cortar', { icon: ICON.corte, disabled: !hasVideo });
  tool(tb, 'audio', 'Áudio', { disabled: !hasVideo });
  tool(tb, 'efeitos', 'Efeitos', { disabled: !hasVideo });
  tool(tb, 'legenda', 'Legenda', { disabled: !hasVideo || !canStyle() });
  tool(tb, 'estilo', 'Estilo', { disabled: !hasVideo || !canStyle() });
  tool(tb, 'marcar', S.pendingIn != null ? 'Fim' : 'Marcar', { armed: S.pendingIn != null, disabled: !hasVideo });

  ctx.innerHTML = '';
  if (imenu) { // Importar: o tipo do arquivo. Vídeo vai para a pasta dos vídeos (o agente corta);
    // imagem e áudio entram como camadas novas, na agulha (o servidor guarda em midia/)
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'imp-video', 'Vídeo', { icon: ICON.final });
    tool(ctx, 'imp-imagem', 'Imagem', { icon: ICON.imagem, disabled: !hasVideo });
    tool(ctx, 'imp-audio', 'Áudio', { icon: ICON.audio, disabled: !hasVideo });
    return;
  }
  if (amenu) { // Áudio: uma trilha da biblioteca do kit ou um arquivo do celular
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'trilhas', 'Trilhas', { icon: ICON.audio });
    tool(ctx, 'do-celular', 'Do celular', { icon: ICON.enviar });
    return;
  }
  if (fmenu) { // Efeitos: filtro na tomada debaixo da agulha, transição no corte mais perto
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'filtros', 'Filtros', { icon: ICON.filtro });
    tool(ctx, 'transicoes', 'Transições', { icon: ICON.transicao });
    return;
  }
  if (fsel) { // um efeito escolhido na linha do tempo
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    if (fsel.tipo === 'filtro') tool(ctx, 'intensidade', `${Math.round(fxIntensidade(fsel) * 100)}%`);
    if (fsel.tipo === 'ajuste') tool(ctx, 'ajustar', 'Ajustar');
    tool(ctx, 'excluir', 'Excluir', { icon: ICON.remover });
    return;
  }
  if (isel) { // um bloco da Fase 2: segurar move, as alças aparam; "Original" volta ao tempo do agente
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'f2-original', 'Original', { icon: ICON.original, disabled: !insMudou(isel) });
    return;
  }
  if (lsel) { // um item de camada escolhido
    const aud = lsel.f.tipo === 'audio';
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    if (aud) {
      tool(ctx, 'volume', `${Math.round(lsel.it.volume * 100)}%`);
      // Melhorar é a cadeia de voz (tira ruído): numa música da biblioteca só estragaria
      if (!lsel.it.trilha) tool(ctx, 'melhorar', 'Melhorar', { on: lsel.it.melhorar });
    }
    tool(ctx, 'excluir', 'Excluir', { icon: ICON.remover });
    return;
  }
  if (sel) {
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'dividir', 'Dividir');
    tool(ctx, 'duplicar', 'Duplicar');
    tool(ctx, 'volume', `${Math.round(sel.vol * 100)}%`);
    tool(ctx, 'velocidade', sel.curva ? nomeCurva(sel.curva.nome) : fmtVel(sel.vel));
    tool(ctx, 'ajustar', 'Ajustar');
    tool(ctx, 'excluir', 'Excluir', { icon: ICON.remover, disabled: S.draft.length < 2 });
    tool(ctx, 'ouvir', 'Ouvir');
    // "Original" volta às bordas que o agente cortou; pedaço novo não tem
    tool(ctx, 'original', 'Original', { disabled: !sel.orig || (sel.start === sel.orig.start && sel.end === sel.orig.end) });
  }
}

document.addEventListener('click', (e) => {
  const b = e.target.closest('.tool');
  if (!b || b.disabled) return;
  const id = b.dataset.tool;
  const r = S.draft[S.selected];
  switch (id) {
    case 'cortar': selectUnderNeedle(); break;
    case 'estilo': openStyle('edit'); break;
    case 'legenda': openStyle('captions'); break;
    case 'marcar': toggleMark(); break;
    case 'importar': S.importMenu = true; S.audioMenu = false; S.fxMenu = false; renderToolbar(); break;
    case 'efeitos': S.fxMenu = true; S.audioMenu = false; S.importMenu = false; renderToolbar(); break;
    case 'filtros': S.fxMenu = false; renderToolbar(); openFx('filtro'); break;
    case 'transicoes': S.fxMenu = false; renderToolbar(); openFx('transicao'); break;
    case 'intensidade': openIntensidade(); break;
    case 'ajustar': openAjuste(); break;
    case 'imp-video': S.importMenu = false; renderToolbar(); $('fileInput').click(); break;
    case 'imp-imagem': S.importMenu = false; renderToolbar(); $('fileImagem').click(); break;
    case 'imp-audio': S.importMenu = false; renderToolbar(); $('fileAudio').click(); break;
    case 'audio': S.audioMenu = true; S.importMenu = false; S.fxMenu = false; renderToolbar(); break;
    case 'trilhas': S.audioMenu = false; renderToolbar(); openTrilhas(); break;
    case 'do-celular': S.audioMenu = false; renderToolbar(); $('fileAudio').click(); break;
    case 'voltar': soltaEscolha(); break;
    case 'dividir': splitSelected(); break;
    case 'duplicar': duplicateSelected(); break;
    case 'excluir':
      if (S.layerSel) deleteLayerSel();
      else if (S.fxSel) deleteFxSel();
      else deleteSelected();
      break;
    case 'volume': openVolume(); break;
    case 'velocidade': openVelocidade(); break;
    case 'melhorar': toggleMelhorar(); break;
    case 'ouvir': {
      const d = draftLayout()[S.selected];
      S.t = d.out; preciseSeek(); positionTimeline(); video.play().catch(() => {});
      break;
    }
    case 'original': remember(); r.start = r.orig.start; r.end = r.orig.end; renderTimeline(); renderToolbar(); refreshHeader(); break;
    case 'f2-original': {
      const c = S.insertsDraft[S.insSel];
      if (c) { remember(); c.start = c.orig.start; c.end = c.orig.end; renderTimeline(); renderToolbar(); refreshHeader(); }
      break;
    }
    case 'pronto': exitPosMode(); break;
    case 'todas':
      S.todas = !S.todas;
      renderToolbar();
      flashName(`<span>${S.todas ? 'Todas: mexer em uma mexe em todas' : 'Só a frase que está na tela'}</span>`, 1800);
      break;
    case 'padrao': resetSpot(); break;
    default: break;
  }
});

function soltaEscolha() {
  S.selected = -1; S.layerSel = null; S.fxSel = null; S.insSel = -1;
  S.audioMenu = false; S.importMenu = false; S.fxMenu = false;
  renderTimeline(); renderToolbar();
}

// "Cortar": escolhe a tomada que está debaixo da agulha (no corte) e abre as ferramentas dela
function selectUnderNeedle() {
  if (S.view !== 'corte') switchView('corte');
  const dl = draftLayout();
  let i = dl.findIndex((d) => S.t >= d.out && S.t < d.out + d.dur);
  if (i < 0) i = dl.length - 1; // agulha no fim: a última
  if (i < 0) return;
  S.selected = i;
  renderTimeline();
  renderToolbar();
}

// Dividir: a tomada escolhida vira duas no ponto da agulha
function splitSelected() {
  const i = S.selected;
  const d = draftLayout()[i];
  if (!d || S.t <= d.out + MIN_SEG || S.t >= d.out + d.dur - MIN_SEG) {
    toast('Ponha a agulha dentro da tomada para dividir', 2400);
    return;
  }
  const r = S.draft[i];
  const s = r.curva // instante do arquivo de origem
    ? +Tempo.gravacaoEm(pedsD(d), (d.lead || 0) + (S.t - d.out)).toFixed(3)
    : +(r.start + (d.leadSrc || 0) + (S.t - d.out) * d.vel).toFixed(3);
  remember();
  // com curva, cada metade leva o seu pedaço dela: a mesma velocidade nos mesmos pontos
  const [esq, dir] = r.curva ? Tempo.cortarCurva(r.curva.pontos, (s - r.start) / (r.end - r.start)) : [null, null];
  S.draft.splice(i + 1, 0, { uid: `n${++S.seq}`, from: r.from, kind: 'split', source: r.source, start: s, end: r.end, beat: r.beat, vol: r.vol, vel: r.vel,
    curva: r.curva ? { nome: r.curva.nome, pontos: dir } : null, orig: null });
  r.end = s;
  if (r.curva) r.curva = { nome: r.curva.nome, pontos: esq };
  renderTimeline(); renderToolbar(); refreshHeader();
}
// Duplicar: uma cópia logo depois, já escolhida
function duplicateSelected() {
  const i = S.selected;
  const r = S.draft[i];
  remember();
  S.draft.splice(i + 1, 0, { uid: `n${++S.seq}`, from: r.from, kind: 'dup', source: r.source, start: r.start, end: r.end, beat: r.beat, vol: r.vol, vel: r.vel, curva: copiaCurva(r.curva), orig: null });
  S.selected = i + 1;
  renderTimeline(); renderToolbar(); refreshHeader();
}
// Excluir: sai da faixa (o ↶ traz de volta); a última tomada fica
function deleteSelected() {
  if (S.draft.length < 2) return;
  remember();
  S.draft.splice(S.selected, 1);
  S.selected = -1;
  S.t = clampT(S.t);
  renderTimeline(); renderToolbar(); refreshHeader();
}

$('btnMode').addEventListener('click', () => {
  if (!hasFinal()) return;
  switchView(S.view === 'corte' ? 'final' : 'corte');
});
$('modeCar').innerHTML = ICON.seta;
$('sheetClose').innerHTML = ICON.fechar;

function switchView(v) {
  if (v === S.view) return;
  S.view = v;
  S.selected = -1;
  S.layerSel = null;
  S.insSel = -1;
  applyMute(); // o silenciar do som do vídeo vale no corte; o final já sai mixado
  setVideoSrc(v);
  renderTimeline();
  renderToolbar();
  refreshHeader();
}

function download() {
  const rel = hasFinal() ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const a = document.createElement('a');
  a.href = `/media/${rel}`;
  a.download = `${(S.state.project || 'cutmind').replace(/[\\/:*?"<>|]+/g, '-')}.mp4`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(hasFinal() ? 'Baixando o vídeo final' : 'Baixando o corte (o final ainda não existe)', 2600);
}

// ---------- enviar vídeo: vai em pedaços para a pasta dos vídeos no computador ----------
// XHR e não fetch: só ele dá o progresso do envio. O corpo é o próprio arquivo,
// sem formulário — o servidor grava direto no disco, sem passar pela memória.
let upXhr = null;
const mb = (b) => `${Math.round(b / 1e6)} MB`;
function sendVideo(file) {
  if (upXhr) { toast('Já tem um envio indo — espere terminar', 2400); return; }
  const card = $('upload');
  card.className = 'upload';
  $('upName').textContent = file.name;
  $('upBar').style.width = '0%';
  $('upPct').textContent = `0% · 0 de ${mb(file.size)}`;
  $('upCancel').textContent = 'Cancelar';
  const xhr = new XMLHttpRequest();
  upXhr = xhr;
  xhr.open('POST', `/api/upload?name=${encodeURIComponent(file.name)}`);
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const f = e.loaded / e.total;
    $('upBar').style.width = `${(f * 100).toFixed(1)}%`;
    $('upPct').textContent = `${Math.floor(f * 100)}% · ${mb(e.loaded)} de ${mb(e.total)}`;
  };
  const end = (cls, msg) => {
    upXhr = null;
    card.className = `upload ${cls}`;
    $('upPct').textContent = msg;
    $('upCancel').textContent = 'Fechar';
  };
  xhr.onload = () => {
    let res = {};
    try { res = JSON.parse(xhr.responseText); } catch (err) { /* resposta sem JSON */ }
    if (xhr.status === 200 && res.ok) {
      $('upBar').style.width = '100%';
      const camada = res.tipo === 'imagem' || res.tipo === 'audio';
      end('done', camada ? 'Chegou. Está na linha do tempo, na agulha.' : 'Chegou no computador. O agente já foi avisado.');
      setTimeout(() => { if (!upXhr) card.classList.add('hidden'); }, 7000);
      if (camada) { addLayer(res.tipo, res.arquivo); return; }
      if (!(S.videoDuration > 0)) {
        $('emptyTitle').textContent = 'Vídeo recebido';
        $('emptyText').textContent = 'O agente já foi avisado. O corte aparece aqui sozinho quando ficar pronto.';
        $('btnEmptyUpload').textContent = 'Enviar outro';
      }
    } else {
      end('bad', res.error || `Não consegui enviar (erro ${xhr.status}).`);
    }
  };
  xhr.onerror = () => end('bad', 'A conexão caiu no meio do envio. O celular e o computador ainda estão na mesma rede?');
  xhr.onabort = () => { upXhr = null; card.classList.add('hidden'); toast('Envio cancelado', 2000); };
  xhr.send(file);
}
$('upCancel').addEventListener('click', () => { if (upXhr) upXhr.abort(); else $('upload').classList.add('hidden'); });
window.addEventListener('beforeunload', (e) => { if (upXhr) { e.preventDefault(); e.returnValue = ''; } });

$('fileInput').addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (f) sendVideo(f);
});
$('btnEmptyUpload').addEventListener('click', () => $('fileInput').click());
$('emptyIco').innerHTML = ICON.enviar;
$('upIco').innerHTML = ICON.enviar;
$('downloadIco').innerHTML = ICON.baixar;
$('phoneIco').innerHTML = ICON.celular;
$('btnDownload').addEventListener('click', download);

/* ---------- abrir no celular (computador) ----------
 * O servidor só entrega os links a este computador: eles levam o código que libera o
 * celular. Com o editor aberto só aqui (127.0.0.1), explica como pedir ao agente. */
async function abrirNoCelular() {
  const body = $('phoneBody');
  body.innerHTML = '';
  el('p', 'phone-hint', body).textContent = 'Carregando…';
  $('phoneModal').classList.remove('hidden');
  let d = null, r = null;
  try { r = await fetch('/api/celular'); d = await r.json(); } catch (e) { /* servidor reiniciando */ }
  body.innerHTML = '';
  if (r && r.status === 403) { // outro aparelho na rede: o código do QR só sai no computador do editor
    el('p', 'phone-hint', body).textContent = 'O código para abrir no celular só aparece no computador onde o editor está rodando.';
    return;
  }
  if (!d || !d.enabled) {
    el('p', 'phone-hint', body).textContent = 'Agora o editor está aberto só para este computador.';
    el('p', 'phone-hint', body).innerHTML = 'Para editar pelo celular, peça no chat: <b>"abre o editor no celular"</b>. '
      + 'O agente libera o editor para a sua rede, com um código, e o QR aparece aqui.';
    return;
  }
  if (!d.urls.length) {
    el('p', 'phone-hint', body).textContent = 'Não achei a rede deste computador. Ele está conectado ao Wi-Fi ou ao cabo?';
    return;
  }
  const tabs = d.urls.length > 1 ? el('div', 'phone-tabs', body) : null;
  const qr = el('div', 'phone-qr', body);
  const url = el('div', 'phone-url', body);
  const hint = el('p', 'phone-hint', body);
  const mostra = (i) => {
    const u = d.urls[i];
    qr.innerHTML = u.qr || '';
    qr.classList.toggle('hidden', !u.qr);
    url.textContent = u.url;
    hint.innerHTML = /tailscale/i.test(u.label)
      ? 'Com o <b>Tailscale ligado no celular</b>, funciona de qualquer lugar. Aponte a câmera para o código.'
      : 'Com o celular <b>no mesmo Wi-Fi</b> deste computador, aponte a câmera para o código. '
        + 'Se não abrir, o Windows pode estar pedindo para liberar o Python na rede: aceite para redes privadas.';
    if (tabs) [...tabs.children].forEach((b, k) => b.classList.toggle('on', k === i));
  };
  if (tabs) d.urls.forEach((u, i) => {
    const b = el('button', 'tb-btn', tabs);
    b.type = 'button';
    b.textContent = u.label;
    b.addEventListener('click', () => mostra(i));
  });
  mostra(0);
}
const fechaCelular = () => $('phoneModal').classList.add('hidden');
$('btnPhone').addEventListener('click', abrirNoCelular);
$('phoneClose').addEventListener('click', fechaCelular);
$('phoneModal').addEventListener('click', (e) => { if (e.target === $('phoneModal')) fechaCelular(); });

// ---------- marcar um trecho (IN → OUT → o que mudar) ----------
function toggleMark() {
  if (S.pendingIn == null) {
    remember();
    S.pendingIn = S.t;
    renderTimeline(); renderToolbar();
    toast('Início marcado. Arraste até o fim do trecho e toque em Fim.', 3000);
    return;
  }
  const start = Math.min(S.pendingIn, S.t), end = Math.max(S.pendingIn, S.t);
  if (end - start < 0.05) { toast('Trecho curto demais — arraste a linha do tempo', 2200); return; }
  remember();
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
  S.editingNew = !!isNew;
  $('noteRange').textContent = `${fmt(n.start)} → ${fmt(n.end)}`;
  $('noteText').value = n.text || '';
  $('noteDelete').classList.toggle('hidden', !!isNew);
  showSheet($('noteSheet'), true);
  setTimeout(() => $('noteText').focus(), 280);
}
function closeNote(keep) {
  const n = S.notes.find((x) => x.id === S.editingNote);
  const text = $('noteText').value.trim();
  // nota nova: a foto já foi tirada no "Fim"; aqui só conta mudar o texto de uma que já existia
  if (n && keep && !S.editingNew && text !== n.text) remember();
  if (n && keep) n.text = text;
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
$('noteText').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.preventDefault(); closeNote(false); }
  else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $('noteOk').click(); }
});
$('noteDelete').addEventListener('click', () => {
  remember();
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
  syncCapFilter();
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
  S.capText = wordsAt(await loadCutWords(), draftToRendered(S.t));
  await loadBandPoster();
  if (!S.styling) return;
  renderStyle();
  if (!S.swipeTaught) { // uma vez por visita: mostra que dá para deslizar
    S.swipeTaught = true;
    flashName(`${ICON.voltar}<span>Deslize para trocar</span>${ICON.avancar}`, 1800);
  }
}

function closeStyle() {
  S.styling = false;
  S.cardAnims = [];
  S.liveAnims = [];
  app.classList.remove('styling');
  player.classList.remove('styling', 'is-split', 'band-top', 'sw-next', 'sw-prev', 'cap-seam', 'cap-free');
  $('swipeName').classList.remove('on');
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
  tabsMore();
  const body = $('sheetBody');
  body.innerHTML = '';
  body.scrollTop = 0;
  S.cardAnims = [];

  if (S.styleTab === 'captions') renderCapFilter(body);
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
    case 'captions': return S.capText
      ? 'Toque num estilo e veja em cima, no seu vídeo, com as palavras deste trecho.'
      : 'Toque num estilo e veja em cima, no seu vídeo e no tamanho real.';
    case 'headline':
      return hookText() !== HEADLINE_TEXT
        ? 'A frase que abre o vídeo, já com a headline deste projeto.'
        : 'A frase que abre o vídeo. O texto de verdade o agente escreve depois.';
    default: return '';
  }
}

/* Legenda: o filtro de cima separa as de uma linha das de várias (o "Nenhum" aparece
 * nos dois). Ao entrar na aba ele abre no grupo da legenda escolhida. */
const CAP_FILTERS = [['uma', 'Uma linha'], ['varias', 'Várias linhas']];
const capFilterOf = (o) => (o.multiline ? 'varias' : 'uma');
function syncCapFilter() {
  const o = STYLE_CATALOG.captions.find((x) => x.id === S.style.captions);
  S.capFilter = o && !o.none ? capFilterOf(o) : S.capFilter || 'uma';
}
function optionsOf(group) {
  const all = STYLE_CATALOG[group];
  return group === 'captions' ? all.filter((o) => o.none || capFilterOf(o) === S.capFilter) : all;
}
function renderCapFilter(body) {
  const row = el('div', 'subtabs', body);
  for (const [id, label] of CAP_FILTERS) {
    const b = el('button', `subtab${S.capFilter === id ? ' on' : ''}`, row);
    b.type = 'button';
    b.dataset.f = id;
    b.textContent = label;
  }
  // "Posição das frases": a borda laranja diz que já há frase fora do lugar do estilo
  const p = capPos();
  const pos = el('button', `pos-btn${p.all || p.phrases.length ? ' own' : ''}`, row);
  pos.type = 'button';
  pos.disabled = !S.style.captions || S.style.captions === 'none';
  pos.innerHTML = `${ICON.mover}<span>Posição</span>`;
  pos.setAttribute('aria-label', 'Posição das frases');
}

const CARD_ZOOM = 1.15; // nos cartões de legenda e headline o quadro aparece um pouco ampliado
function renderCards(body, group, key) {
  const tall = group === 'edits';
  const grid = el('div', `cards ${tall ? 'tall' : 'wide'}`, body);
  for (const o of optionsOf(group)) {
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
  // a frase debaixo da agulha no lugar escolhido no "Posição das frases", se houver
  const sp = S.frasesFor.startsWith(`${S.style.captions}|`) ? spotOf(fraseAt(draftToRendered(S.t))) : capPos().all;
  if (sp) placeCap(player, sp);
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
  syncCapFilter();
  renderStyle();
});
function tabsMore() {
  const t = $('sheetTabs');
  t.classList.toggle('more', t.scrollLeft + t.clientWidth < t.scrollWidth - 2);
}
$('sheetTabs').addEventListener('scroll', tabsMore, { passive: true });
window.addEventListener('resize', tabsMore);

function pickStyle(key, id) {
  S.style[key] = id;
  const card = $('sheetBody').querySelector(`.card[data-id="${id}"]`);
  if (!card) { syncCapFilter(); renderStyle(); return; } // está no outro filtro da legenda
  // sem reconstruir os cartões: a lista não pula para o topo a cada toque
  for (const c of card.parentNode.children) c.classList.toggle('on', c === card);
  const hint = $('sheetBody').querySelector('.sheet-hint');
  if (hint) hint.textContent = styleHint();
  const pos = $('sheetBody').querySelector('.pos-btn');
  if (pos) pos.disabled = S.style.captions === 'none';
  updateSummary();
  applyLive();
}

/* Deslizar na prévia troca o estilo da aba aberta, na ordem dos cartões (na legenda,
 * as de uma linha, depois as de várias, depois o "Nenhum"), e dá a volta no fim. */
const SWIPE_TABS = { edit: ['edits', 'edit'], captions: ['captions', 'captions'], headline: ['headlines', 'headline'] };
function swipeOrder(group) {
  const all = STYLE_CATALOG[group];
  if (group !== 'captions') return all;
  const real = all.filter((o) => !o.none);
  return [...real.filter((o) => !o.multiline), ...real.filter((o) => o.multiline), ...all.filter((o) => o.none)];
}
function stepStyle(dir) {
  const tab = SWIPE_TABS[S.styleTab];
  if (!S.styling || !tab) return;
  const [group, key] = tab;
  const list = swipeOrder(group);
  const k = (list.findIndex((o) => o.id === S.style[key]) + dir + list.length) % list.length;
  pickStyle(key, list[k].id);
  const card = $('sheetBody').querySelector(`.card[data-id="${list[k].id}"]`);
  if (card) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  player.classList.remove('sw-next', 'sw-prev');
  void player.offsetWidth; // recomeça a animação de entrada
  player.classList.add(dir > 0 ? 'sw-next' : 'sw-prev');
  flashName(`${ICON.voltar}<span>${list[k].name}</span><small>${k + 1}/${list.length}</small>${ICON.avancar}`);
}
let flashTimer = 0;
function flashName(html, ms = 900) {
  const pill = $('swipeName');
  pill.innerHTML = html;
  pill.classList.add('on');
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => pill.classList.remove('on'), ms);
}
const swipe = { id: null, x: 0, y: 0 };
player.addEventListener('pointerdown', (e) => {
  if (!S.styling || !SWIPE_TABS[S.styleTab]) return;
  swipe.id = e.pointerId; swipe.x = e.clientX; swipe.y = e.clientY;
});
// o fim do gesto na janela: com mouse o botão costuma ser solto já fora da prévia
window.addEventListener('pointerup', (e) => {
  if (e.pointerId !== swipe.id) return;
  swipe.id = null;
  const dx = e.clientX - swipe.x, dy = e.clientY - swipe.y;
  if (Math.abs(dx) < 36 || Math.abs(dx) < Math.abs(dy) * 1.4) return;
  tapGuard.until = performance.now() + 400; // o clique que vem junto não pode dar play
  stepStyle(dx < 0 ? 1 : -1);
});
window.addEventListener('pointercancel', (e) => { if (e.pointerId === swipe.id) swipe.id = null; });
document.addEventListener('keydown', (e) => {
  if (!S.styling || e.target.closest('input, textarea')) return;
  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); stepStyle(e.key === 'ArrowRight' ? 1 : -1); }
});

$('sheetBody').addEventListener('click', (e) => {
  if (e.target.closest('.pos-btn')) { enterPosMode(); return; }
  const sub = e.target.closest('.subtab');
  if (sub) {
    S.capFilter = sub.dataset.f;
    renderStyle();
    return;
  }
  const card = e.target.closest('.card');
  if (card) {
    pickStyle(card.dataset.key, card.dataset.id);
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
    // frases arrastadas no "Posição das frases", ancoradas na gravação (caption_positions.py)
    captionPositions: capPos(),
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

// ---------- posição das frases (legenda livre) ----------
/* Frase por frase, como no CapCut e no Edits: toca na frase sobre o vídeo e arrasta,
 * e só ela muda; com "Todas" ligado, mexer em uma mexe em todas. Cada frase fica
 * ancorada no MOMENTO DA GRAVAÇÃO da primeira palavra (source + at): um recorte feito
 * depois não a desloca, e se aquele momento for cortado a frase volta ao lugar do
 * estilo. O agente leva isso ao relógio do corte (helpers/caption_positions.py) e o
 * template põe cada frase onde ela foi deixada (captionPlace.ts). */
const noPos = () => ({ all: null, phrases: [] });
function capPos() {
  const p = S.style.captionPositions;
  if (!p || typeof p !== 'object') return (S.style.captionPositions = noPos());
  if (!(p.all && isFinite(p.all.x) && isFinite(p.all.y))) p.all = null;
  if (!Array.isArray(p.phrases)) p.phrases = [];
  return p;
}
// instante do cut.mp4 → momento da gravação, pela IMAGEM de cada tomada (como o render)
function cutToSource(rt) {
  const rl = renderedLayout();
  for (let i = rl.length - 1; i >= 0; i--) {
    if (rt + 1e-6 < rl[i].out) continue;
    const R = S.rendered[i];
    const tc = jcutGeom(i).lead + Math.min(rt - rl[i].out, rl[i].dur); // desde o começo da tomada, no corte
    return { source: R.source, at: +(R.curva ? Tempo.gravacaoEm(pedsR(i), tc) : R.start + tc * R.vel).toFixed(3) };
  }
  return null;
}
// o contrário: todo lugar do cut.mp4 onde aquele momento aparece (tomada duplicada: mais de um)
function sourceToCut(source, at) {
  const out = [];
  renderedLayout().forEach((L, i) => {
    const R = S.rendered[i];
    const lead = jcutGeom(i).lead;
    if (R.curva) {
      const pR = pedsR(i);
      const v0 = Tempo.gravacaoEm(pR, lead), v1 = Tempo.gravacaoEm(pR, lead + L.dur);
      if (R.source === source && at >= v0 - 1e-3 && at < v1) out.push(L.out + Tempo.corteAte(pR, at) - lead);
      return;
    }
    const v0 = R.start + lead * R.vel;
    if (R.source === source && at >= v0 - 1e-3 && at < v0 + L.dur * R.vel) out.push(L.out + (at - v0) / R.vel);
  });
  return out;
}
// as marcas que caem dentro da frase — a regra do template (captionPlace.ts): a mesma
// folga nas duas pontas, senão a marca da frase seguinte também cai nesta
const anchorsIn = (f) => capPos().phrases.filter((p) => sourceToCut(p.source, p.at).some((t) => t >= f.start - 0.05 && t < f.end - 0.05));
// onde a frase fica: a marca dela → a de todas → null (o lugar do estilo)
function spotOf(f) {
  const own = f && anchorsIn(f)[0];
  return own ? { x: own.x, y: own.y } : capPos().all;
}
const fraseAt = (rt) => S.frases.find((f) => rt >= f.start && rt < f.end) || null;

async function loadFrases() {
  const id = S.style.captions;
  const key = `${id}|${S.mtimes.video || 0}`;
  if (S.frasesFor === key) return S.frases;
  let frases = [];
  if (id === 'stacked') {
    // as do diretor do render, servidas pelo PC (caption_style.py)
    try { frases = (await (await fetch('/gen/frases?estilo=stacked')).json()).frases || []; } catch (e) { frases = []; }
  } else if (id && id !== 'none') {
    const words = await loadCutWords();
    if (words && words.length) {
      if (document.fonts && document.fonts.ready) await document.fonts.ready; // os estáticos agrupam pela largura NA FONTE
      const ws = words.filter((w) => !w.k || w.k === 'word').map((w) => ({ text: w.t, start: w.s, end: w.e }));
      frases = capPhrases(id, ws, { maxWords: capsCfg().maxWords });
    }
  }
  S.frases = frases;
  S.frasesFor = key;
  return frases;
}

// o bloco nunca sai do quadro: 40 px do quadro 1080x1920 de folga, como no template
function clampSpot(s, box) {
  const P = player.getBoundingClientRect(), b = box.getBoundingClientRect();
  const mx = 40 / FRAME_W + b.width / P.width / 2, my = 40 / FRAME_H + b.height / P.height / 2;
  return {
    x: mx >= 0.5 ? 0.5 : Math.min(Math.max(s.x, mx), 1 - mx),
    y: my >= 0.5 ? 0.5 : Math.min(Math.max(s.y, my), 1 - my),
  };
}
function placeCap(node, spot) {
  const cap = node.querySelector('.cap');
  const box = cap && cap.querySelector('.cap-demo');
  node.classList.add('cap-free');
  if (!box) return;
  const s = spot || { x: 0.5, y: capCenter(S.style, 'abertura') }; // sem marca: o lugar do estilo
  if (spot) node.classList.remove('cap-seam'); // o lugar escolhido vale mais que a emenda
  const c = clampSpot(s, box);
  node.style.setProperty('--fx', pct(c.x));
  node.style.setProperty('--fy', pct(c.y));
  cap.classList.toggle('own', !!spot);
}
// desenha a frase que está debaixo da agulha (só refaz quando ela muda)
function drawFrase(force) {
  if (!S.posMode) return;
  const f = fraseAt(draftToRendered(S.t));
  if (!force && f === S.fraseShown) return;
  S.fraseShown = f;
  const cap = $('ovCap');
  cap.innerHTML = '';
  cap.classList.remove('own');
  if (f) {
    const c = STYLE_CATALOG.captions.find((o) => o.id === S.style.captions) || {};
    if (c.demo === 'stacked') CAP_BUILDERS.stacked(cap, f.text, true, f.cue || null);
    else if (c.demo === 'scatter') CAP_BUILDERS.scatter(cap, f.text.toLowerCase(), true, f.gi ?? 1);
    else if (c.demo) CAP_BUILDERS[c.demo](cap, f.text, true);
    else if (c.stat) buildStaticDemo(cap, c.stat, f.text);
    placeCap(player, spotOf(f));
  }
  markFrases();
}
function markFrases() {
  for (const chip of tracksEl.querySelectorAll('.chip.frase')) {
    const f = S.frases[+chip.dataset.i];
    chip.classList.toggle('cur', f === S.fraseShown);
    chip.classList.toggle('own', !!f && anchorsIn(f).length > 0);
  }
}
function renderFrases(lane) {
  S.frases.forEach((f, i) => {
    const a = renderedToDraft(f.start), b = renderedToDraft(f.end);
    const chip = el('div', 'chip frase', lane);
    chip.dataset.i = i;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps - 2, 4)}px`;
    chip.textContent = f.text;
  });
}

// a frase vai para `spot`; com "Todas", todas vão (e as marcas próprias saem)
function setSpot(f, spot) {
  const p = capPos();
  const s = { x: +spot.x.toFixed(4), y: +spot.y.toFixed(4) };
  if (S.todas) {
    p.all = s;
    p.phrases = [];
  } else {
    const a = cutToSource(f.start);
    if (!a) return;
    const old = new Set(anchorsIn(f));
    p.phrases = p.phrases.filter((q) => !old.has(q));
    p.phrases.push({ ...a, ...s, text: f.text });
  }
  drawFrase(true);
}
function resetSpot() {
  const p = capPos();
  if (S.todas) {
    if (!p.all && !p.phrases.length) { toast('Todas já estão no lugar do estilo', 2200); return; }
    remember();
    S.style.captionPositions = noPos();
  } else {
    const f = S.fraseShown;
    const own = f ? anchorsIn(f) : [];
    if (!own.length) {
      toast(p.all ? 'Esta frase segue a posição de todas. Ligue "Todas" para mexer nelas.' : 'Esta frase já está no lugar do estilo', 2800);
      return;
    }
    remember();
    p.phrases = p.phrases.filter((q) => !own.includes(q));
  }
  drawFrase(true);
}

async function enterPosMode() {
  if (!S.style.captions || S.style.captions === 'none') return;
  if (edlDirty()) { toast('Salve os cortes antes: as frases saem do vídeo já cortado.', 3200); return; }
  const frases = await loadFrases();
  if (!frases.length) { toast('Ainda não há transcrição do corte para montar as frases.', 3200); return; }
  closeStyle();
  if (S.view !== 'corte') switchView('corte');
  S.posMode = true;
  S.selected = -1;
  S.fraseShown = undefined;
  app.classList.add('posicionando');
  player.classList.add('posicionando');
  applyGeom(player, S.style, 'abertura');
  renderTimeline();
  renderToolbar();
  drawFrase(true);
  if (!S.posTaught) { S.posTaught = true; flashName('<span>Toque na frase e arraste</span>', 2200); }
}
function exitPosMode() {
  S.posMode = false;
  S.fraseShown = undefined;
  app.classList.remove('posicionando');
  player.classList.remove('posicionando', 'cap-free', 'cap-seam');
  for (const k of GEOM_VARS) player.style.removeProperty(k);
  $('ovCap').innerHTML = '';
  renderTimeline();
  renderToolbar();
  openStyle('captions');
}

// arrastar a frase na prévia (no resto da prévia, tocar continua dando play)
const capDrag = { id: null };
player.addEventListener('pointerdown', (e) => {
  if (!S.posMode || !S.fraseShown) return;
  const box = $('ovCap').querySelector('.cap-demo');
  if (!box) return;
  const b = box.getBoundingClientRect();
  const pad = 14; // a moldura tracejada e um pouco mais: frase curta é alvo pequeno
  if (e.clientX < b.left - pad || e.clientX > b.right + pad || e.clientY < b.top - pad || e.clientY > b.bottom + pad) return;
  const P = player.getBoundingClientRect();
  const c = clampSpot(spotOf(S.fraseShown) || { x: 0.5, y: capCenter(S.style, 'abertura') }, box);
  Object.assign(capDrag, { id: e.pointerId, x0: e.clientX, y0: e.clientY, fx: c.x, fy: c.y, w: P.width, h: P.height, moved: false, spot: c, before: snap() });
  video.pause();
});
window.addEventListener('pointermove', (e) => {
  if (e.pointerId !== capDrag.id) return;
  const dx = e.clientX - capDrag.x0, dy = e.clientY - capDrag.y0;
  if (!capDrag.moved && Math.hypot(dx, dy) < 5) return;
  capDrag.moved = true;
  capDrag.spot = clampSpot({ x: capDrag.fx + dx / capDrag.w, y: capDrag.fy + dy / capDrag.h }, $('ovCap').querySelector('.cap-demo'));
  player.style.setProperty('--fx', pct(capDrag.spot.x));
  player.style.setProperty('--fy', pct(capDrag.spot.y));
});
window.addEventListener('pointerup', (e) => {
  if (e.pointerId !== capDrag.id) return;
  capDrag.id = null;
  tapGuard.until = performance.now() + 400; // tocar ou arrastar a frase não dá play
  if (!capDrag.moved || !S.fraseShown) return;
  remember(capDrag.before);
  setSpot(S.fraseShown, capDrag.spot);
});
window.addEventListener('pointercancel', (e) => {
  if (e.pointerId === capDrag.id) { capDrag.id = null; drawFrase(true); }
});

// ---------- salvar ajustes do corte (os campos do editor de PC + take e ops) ----------
/* `ranges` é a lista INTEIRA, na ordem nova: aparos, divisões, cópias e ordem já
 * aplicados — o agente monta o edl.json a partir dela. `take` é o índice da tomada de
 * origem no edl.json (para levar quote, reason e gain_db). `changes` e `removed` resumem
 * o que mudou contra o edl.json de agora; `ops` conta o que não cabe neles. */
function edlPayload() {
  const tem = new Set(S.draft.map((r) => r.uid));
  const novos = S.draft.filter((r) => !r.orig);
  const ordem = S.draft.filter((r) => r.orig).map((r) => r.from);
  return {
    // `volume` só quando não é 100%: sem ele, a tomada sai como está (o agente não herda o do edl.json)
    ranges: S.draft.map((r) => ({ source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat, take: r.from,
      ...(r.vol !== 1 ? { volume: r.vol } : {}),
      ...(r.curva ? { curva: copiaCurva(r.curva) } : r.vel !== 1 ? { velocidade: r.vel } : {}) })),
    removed: S.rendered.map((r, i) => ({ r, i })).filter(({ i }) => !tem.has(`o${i}`))
      .map(({ r, i }) => ({ source: r.source, beat: r.beat, start: r.start, end: r.end, take: i })),
    changes: S.draft.filter((r) => r.orig && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
      source: r.source, beat: r.beat, take: r.from,
      from: { start: r.orig.start, end: r.orig.end },
      to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
    })),
    ops: {
      divisoes: novos.filter((r) => r.kind === 'split').length,
      copias: novos.filter((r) => r.kind === 'dup').length,
      ordemMudou: ordem.some((v, k) => k > 0 && v < ordem[k - 1]),
      volume: S.draft.filter((r) => r.vol !== volCorte(r)).length, // tomadas com volume diferente do corte atual
      velocidade: S.draft.filter((r) => !r.curva && r.vel !== velR(r.from)).length,
      curva: S.draft.filter((r) => curvaKey(r) !== curvaKey(S.rendered[r.from])).length,
    },
  };
}
$('btnSave').addEventListener('click', async () => {
  const payload = { type: 'timeline-edits' };
  const soCamadas = !edlDirty() && !S.notes.length;
  if (edlDirty()) payload.edl = edlPayload();
  const comBlocos = insertsDirty();
  if (comBlocos) { // blocos da Fase 2: todos os de cada tipo, pelo `ref`, como a desktop antiga mandava
    const de = (k) => S.insertsDraft.filter((c) => c.kind === k);
    const t = (v) => +v.toFixed(3);
    payload.editData = {
      inserts: de('insert').map((c) => ({ ref: c.ref, start: t(c.start), end: t(c.end) })),
      splitInserts: de('split').map((c) => ({ ref: c.ref, label: c.label, start: t(c.start), end: t(c.end) })),
      splitVideos: de('splitvideo').map((c) => ({ ref: c.ref, label: c.label, start: t(c.start), end: t(c.end) })),
      hook: de('hook').map((c) => ({ endSec: t(c.end) }))[0] || null,
      behind: de('behind').map((c) => ({ ref: c.ref, start: t(c.start), dur: t(c.end - c.start) })),
      wordAccents: de('word').map((c) => ({ ref: c.ref, text: c.label, start: t(c.start), end: t(c.end) })),
    };
  }
  if (camadasDirty()) payload.camadas = S.camadas;
  const comEfeitos = efeitosDirty();
  if (comEfeitos) payload.efeitos = S.efeitos;
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
    const out = await res.json();
    if (!out.ok) {
      // camada recusada pelo servidor: o motivo vale mais que o aviso genérico
      if (out.error) { toast(`Não salvei: ${out.error}`, 4500); return; }
      throw new Error('falhou');
    }
    S.savedPending = true;
    S.notes = [];
    S.pendingIn = null;
    // o que foi enviado vira a referência; `orig` segue sendo o edl.json até o agente refazer
    S.base = baseOf(S.draft);
    const comCamadas = 'camadas' in payload;
    S.camadasBase = camSig();
    S.efeitosBase = fxSig();
    S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
    S.selected = -1;
    S.layerSel = null;
    S.fxSel = null;
    S.insSel = -1;
    forgetHistory(); // o que foi enviado ao agente não se desfaz daqui
    renderTimeline(); renderToolbar(); refreshHeader();
    const oque = comEfeitos ? (comCamadas ? 'Camadas e efeitos salvos' : 'Efeitos salvos') : 'Camadas salvas';
    const aviso = !soCamadas ? 'Ajustes enviados. O agente refaz o corte.'
      : comBlocos ? 'Blocos enviados. O agente refaz o vídeo final.'
        : `${oque}. O agente põe no vídeo final.`;
    toast(aviso, 3000);
  } catch (err) {
    toast('Não consegui salvar — o editor ainda está ligado no computador?', 4000);
  }
});

// ---------- camadas: imagens e áudios na linha do tempo ----------
/* Como em qualquer editor: cada envio de imagem ou áudio vira uma faixa própria, com
 * cabeçalho à esquerda (silenciar ou esconder, e travar). O vídeo principal ganha o
 * "silenciar" do som original. Tudo fica em camadas.json, no relógio do cut.mp4: o
 * Salvar leva as camadas, o servidor grava o arquivo e o agente põe no vídeo final
 * (imagens no edit-data, áudio no mixar_final.py). A prévia toca e mostra as camadas no
 * Corte; no Final, o vídeo já é o que o agente montou com elas. */
function camVazio() { return { versao: 1, video: { mudo: false }, faixas: [] }; }
function camSig() { return JSON.stringify(S.camadas); }
function camadasDirty() { return camSig() !== S.camadasBase; }
S.camadasBase = camSig();
function camItem(id) {
  for (const f of S.camadas.faixas) {
    const it = f.itens.find((x) => x.id === id);
    if (it) return { f, it };
  }
  return null;
}
async function loadCamadas() {
  let c = null;
  try {
    const r = await fetch(`/media/camadas.json?v=${Date.now()}`);
    if (r.ok) c = await r.json();
  } catch (e) { /* ainda não existe */ }
  S.camadas = c && Array.isArray(c.faixas) ? { versao: 1, video: { mudo: !!(c.video && c.video.mudo) }, faixas: c.faixas } : camVazio();
  S.camadasBase = camSig();
  applyMute();
  // trilha da biblioteca aparece pelo nome do catálogo, não pelo nome do arquivo
  if (!S.trilhas && S.camadas.faixas.some((f) => f.itens.some((it) => it.trilha))) loadTrilhas().then(renderTimeline);
}
const nomeMidia = (arq) => String(arq || '').replace(/^midia\//, '');
function newFaixaId(letra) {
  let n = 0;
  for (const f of S.camadas.faixas) {
    const m = new RegExp(`^${letra}(\\d+)$`).exec(f.id);
    if (m) n = Math.max(n, +m[1]);
  }
  return `${letra}${n + 1}`;
}
// a duração de um áudio de midia/, lida do próprio arquivo pelo navegador
function midiaDuration(arq) {
  if (S.midiaDur[arq]) return Promise.resolve(S.midiaDur[arq]);
  return new Promise((ok) => {
    const a = new Audio();
    const fim = (d) => { clearTimeout(t); ok(d); };
    const t = setTimeout(() => fim(0), 8000);
    a.preload = 'metadata';
    a.onloadedmetadata = () => { if (isFinite(a.duration)) S.midiaDur[arq] = a.duration; fim(a.duration || 0); };
    a.onerror = () => fim(0);
    a.src = `/media/${arq}`;
  });
}
async function addLayer(tipo, arquivo, extra = {}) {
  const total = S.videoDuration || totalT();
  const inicio = +Math.min(draftToRendered(S.t), Math.max(0, total - 0.5)).toFixed(3);
  const resto = Math.max(0.5, total - inicio);
  let dur = tipo === 'imagem' ? 3 : await midiaDuration(arquivo);
  dur = Math.min(dur || 3, resto);
  remember();
  const letra = tipo === 'audio' ? 'a' : 'i';
  const fid = newFaixaId(letra);
  const item = { id: `${fid}-1`, arquivo, inicio, duracao: +dur.toFixed(3) };
  if (tipo === 'audio') Object.assign(item, { corte: 0, volume: 1, melhorar: false }, extra);
  const faixa = { id: fid, tipo, travado: false, itens: [item] };
  faixa[tipo === 'audio' ? 'mudo' : 'oculto'] = false;
  S.camadas.faixas.push(faixa);
  S.layerSel = item.id;
  S.fxSel = null;
  S.selected = -1;
  renderTimeline(); renderToolbar(); refreshHeader();
}

// cabeçalho fixo à esquerda da faixa: os botões dela (faixa null = o vídeo principal)
function trackHead(track, f) {
  const th = el('div', 'th', track);
  const btn = (act, icon, label, on) => {
    const b = el('button', `th-b${on ? ' on' : ''}`, th);
    b.type = 'button';
    b.dataset.act = act;
    if (f) b.dataset.f = f.id;
    b.innerHTML = icon;
    b.setAttribute('aria-label', label);
    b.setAttribute('aria-pressed', String(!!on));
  };
  if (!f) { btn('video-mudo', S.camadas.video.mudo ? ICON.semSom : ICON.som, 'Silenciar o som do vídeo', S.camadas.video.mudo); return; }
  if (f.tipo === 'audio') btn('mudo', f.mudo ? ICON.semSom : ICON.som, 'Silenciar a camada', f.mudo);
  else btn('oculto', f.oculto ? ICON.olhoFechado : ICON.olho, 'Esconder a camada', f.oculto);
  btn('travar', f.travado ? ICON.cadeado : ICON.cadeadoAberto, 'Travar a camada', f.travado);
}
function renderLayerTrack(track, lane, f) {
  track.classList.toggle('mudo', f.tipo === 'audio' && f.mudo);
  track.classList.toggle('oculto', f.tipo === 'imagem' && f.oculto);
  track.classList.toggle('travado', f.travado);
  for (const it of f.itens) {
    const a = renderedToDraft(it.inicio), b = renderedToDraft(it.inicio + it.duracao);
    const chip = el('div', `chip layer ${f.tipo === 'audio' ? 'aud' : 'img'}${it.trilha ? ' mus' : ''}`, lane);
    chip.dataset.id = it.id;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps, 8)}px`;
    if (f.tipo === 'imagem') {
      const im = el('img', 'l-thumb', chip);
      im.src = `/media/${it.arquivo}`;
      im.alt = '';
      im.draggable = false;
    } else {
      el('span', 'l-ico', chip).innerHTML = ICON.audio;
    }
    el('span', 'l-name', chip).textContent = it.trilha ? (S.trilhaNomes[it.trilha] || it.trilha) : nomeMidia(it.arquivo);
    if (it.melhorar) el('span', 'l-tag', chip).innerHTML = ICON.melhorar;
    if (it.id === S.layerSel) {
      chip.classList.add('sel');
      const l = el('div', 'lh l', chip);
      l.dataset.side = 'l';
      const r = el('div', 'lh r', chip);
      r.dataset.side = 'r';
    }
  }
  trackHead(track, f);
}
function tapLayer(id) {
  const hit = camItem(id);
  if (!hit) return;
  if (hit.f.travado) { toast('Camada travada: toque no cadeado para soltar', 2200); return; }
  S.layerSel = S.layerSel === id ? null : id;
  S.selected = -1;
  S.insSel = -1;
  renderTimeline();
  renderToolbar();
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('.th-b');
  if (!b) return;
  remember();
  const act = b.dataset.act;
  if (act === 'video-mudo') {
    S.camadas.video.mudo = !S.camadas.video.mudo;
    toast(S.camadas.video.mudo ? 'Som do vídeo desligado' : 'Som do vídeo ligado', 1600);
  } else {
    const f = S.camadas.faixas.find((x) => x.id === b.dataset.f);
    if (!f) return;
    if (act === 'mudo') f.mudo = !f.mudo;
    else if (act === 'oculto') f.oculto = !f.oculto;
    else if (act === 'travar') {
      f.travado = !f.travado;
      if (f.travado && f.itens.some((it) => it.id === S.layerSel)) S.layerSel = null;
    }
  }
  applyMute();
  renderTimeline(); renderToolbar(); refreshHeader();
});

// as alças do item escolhido aparam; segurar o item (como a tomada) o leva com o dedo
function startLayerDrag(x, kind, side) {
  const hit = camItem(S.layerSel);
  if (!hit || hit.f.travado) return false;
  G.mode = 'layer';
  G.ly = { id: hit.it.id, kind, side, x0: x, it0: { ...hit.it }, before: snap() };
  video.pause();
  return true;
}
function holdLayer(id, x) {
  if (G.mode !== 'pan' || G.moved) return;
  const hit = camItem(id);
  if (!hit) return;
  if (hit.f.travado) { toast('Camada travada: toque no cadeado para soltar', 2200); return; }
  const before = snap();
  S.layerSel = id;
  S.fxSel = null;
  S.selected = -1;
  if (navigator.vibrate) navigator.vibrate(12);
  startLayerDrag(x, 'move');
  G.ly.before = before; // desfazer volta também a escolha de antes
  renderTimeline(); renderToolbar();
}
function dragLayer(x) {
  const L = G.ly;
  const hit = camItem(L.id);
  if (!hit) return;
  const it = hit.it, o = L.it0, aud = hit.f.tipo === 'audio';
  const dt = (x - L.x0) / S.pps;
  const fim = S.videoDuration || totalT();
  if (L.kind === 'move') {
    it.inicio = +Math.max(0, Math.min(o.inicio + dt, fim - 0.2)).toFixed(3);
  } else if (L.side === 'r') {
    let d = Math.max(0.2, o.duracao + dt);
    const tot = aud && S.midiaDur[it.arquivo];
    if (tot) d = Math.min(d, tot - it.corte);
    it.duracao = +d.toFixed(3);
  } else { // a ponta esquerda anda; a direita fica onde está
    let k = Math.min(dt, o.duracao - 0.2);
    k = Math.max(k, -o.inicio);
    if (aud) k = Math.max(k, -o.corte); // não volta antes do começo do arquivo
    it.inicio = +(o.inicio + k).toFixed(3);
    it.duracao = +(o.duracao - k).toFixed(3);
    if (aud) it.corte = +(o.corte + k).toFixed(3);
  }
  const tip = $('trimTip');
  tip.textContent = L.kind === 'move' ? `começa em ${fmt(it.inicio)}` : `dura ${it.duracao.toFixed(2)} s`;
  tip.classList.remove('hidden');
  if (!G.layerQueued) {
    G.layerQueued = true;
    requestAnimationFrame(() => { G.layerQueued = false; renderTimeline(); refreshHeader(); });
  }
}
function endLayerDrag() {
  const L = G.ly;
  G.mode = null;
  $('trimTip').classList.add('hidden');
  const hit = camItem(L.id);
  if (hit && JSON.stringify(hit.it) !== JSON.stringify(L.it0)) remember(L.before); // tocar sem arrastar não conta
  renderTimeline(); renderToolbar(); refreshHeader();
}

// ---------- blocos da Fase 2 (inserts, gancho, palavras) na vista Final ----------
/* Como os itens de camada: tocar escolhe, as alças aparam, segurar leva com o dedo (ou o
 * mouse). O tempo é o do vídeo final. O Salvar manda tudo em `editData`, no formato da
 * desktop antiga, e o agente acerta o edit-data.json pelo `ref` de cada bloco. */
const MIN_INS = 0.15;
function tapIns(i) {
  if (!S.insertsDraft[i]) return;
  S.insSel = S.insSel === i ? -1 : i;
  S.selected = -1; S.layerSel = null; S.fxSel = null;
  renderTimeline();
  renderToolbar();
}
function startInsDrag(x, kind, side) {
  const c = S.insertsDraft[S.insSel];
  if (!c || S.view !== 'final' || (kind === 'move' && c.kind === 'hook')) return false;
  G.mode = 'ins';
  G.ins = { i: S.insSel, kind, side, x0: x, c0: { start: c.start, end: c.end }, before: snap() };
  video.pause();
  return true;
}
function holdIns(i, x) {
  if (G.mode !== 'pan' || G.moved) return;
  const c = S.insertsDraft[i];
  if (!c) return;
  // o gancho abre o vídeo: ele não anda, só a ponta da direita apara
  if (c.kind === 'hook') { toast('O gancho começa no início do vídeo: puxe a ponta da direita', 2400); return; }
  const before = snap();
  S.insSel = i; S.selected = -1; S.layerSel = null; S.fxSel = null;
  if (navigator.vibrate) navigator.vibrate(12);
  startInsDrag(x, 'move');
  G.ins.before = before; // desfazer volta também a escolha de antes
  renderTimeline(); renderToolbar();
}
function dragIns(x) {
  const D = G.ins, c = S.insertsDraft[D.i], o = D.c0;
  if (!c) return;
  const dt = (x - D.x0) / S.pps;
  const fim = S.videoDuration || totalT();
  if (D.kind === 'move') {
    const dur = o.end - o.start;
    c.start = +Math.max(0, Math.min(o.start + dt, fim - dur)).toFixed(3);
    c.end = +(c.start + dur).toFixed(3);
  } else if (D.side === 'l') {
    c.start = +Math.min(Math.max(0, o.start + dt), o.end - MIN_INS).toFixed(3);
  } else {
    c.end = +Math.min(fim, Math.max(o.end + dt, o.start + MIN_INS)).toFixed(3);
  }
  const tip = $('trimTip');
  tip.textContent = `${fmt(c.start)} → ${fmt(c.end)}`;
  tip.classList.remove('hidden');
  if (!G.insQueued) {
    G.insQueued = true;
    requestAnimationFrame(() => { G.insQueued = false; renderTimeline(); refreshHeader(); });
  }
}
function endInsDrag() {
  const D = G.ins, c = S.insertsDraft[D.i];
  G.mode = null;
  $('trimTip').classList.add('hidden');
  if (c && (c.start !== D.c0.start || c.end !== D.c0.end)) remember(D.before); // tocar sem arrastar não conta
  renderTimeline(); renderToolbar(); refreshHeader();
}

function deleteLayerSel() {
  const hit = camItem(S.layerSel);
  if (!hit) return;
  remember();
  hit.f.itens = hit.f.itens.filter((x) => x.id !== hit.it.id);
  if (!hit.f.itens.length) S.camadas.faixas = S.camadas.faixas.filter((f) => f !== hit.f);
  S.layerSel = null;
  renderTimeline(); renderToolbar(); refreshHeader();
}
function toggleMelhorar() {
  const hit = camItem(S.layerSel);
  if (!hit) return;
  remember();
  hit.it.melhorar = !hit.it.melhorar;
  toast(hit.it.melhorar ? 'O agente melhora este áudio: tira o ruído e acerta o volume' : 'Este áudio entra como está', 2600);
  renderTimeline(); renderToolbar(); refreshHeader();
}
/* volume: um painel pequeno com a régua; 100% é o arquivo como veio. Serve à camada de
 * áudio escolhida (até 200%) e à tomada escolhida (até 400%, como no CapCut). */
let volBefore = null;
function volAlvo() {
  const hit = S.layerSel ? camItem(S.layerSel) : null;
  if (hit) return { max: 200, nome: 'camada', get: () => hit.it.volume, set: (v) => { hit.it.volume = v; } };
  const r = S.selected >= 0 && S.view === 'corte' ? S.draft[S.selected] : null;
  if (r) return { max: 400, nome: 'tomada', get: () => r.vol, set: (v) => { r.vol = v; }, tomada: r };
  return null;
}
function volMostrar(a) {
  const v = a.get();
  $('volVal').textContent = `${Math.round(v * 100)}%`;
  // a prévia toca o vídeo e os áudios no máximo no volume do arquivo; o vídeo final leva o ganho
  $('volNota').classList.toggle('hidden', !(v > (a.tomada ? volCorte(a.tomada) : 1)));
}
function openVolume() {
  const a = volAlvo();
  if (!a) return;
  volBefore = snap();
  $('volRange').max = a.max;
  $('volRange').value = Math.round(a.get() * 100);
  $('volRange').setAttribute('aria-label', `Volume da ${a.nome}`);
  volMostrar(a);
  showSheet($('volSheet'), true);
}
$('volRange').addEventListener('input', () => {
  const a = volAlvo();
  if (!a) return;
  a.set(+($('volRange').value / 100).toFixed(2));
  volMostrar(a);
});
$('volOk').addEventListener('click', () => {
  showSheet($('volSheet'), false);
  if (volBefore && (JSON.stringify(volBefore.cam) !== camSig()
      || volBefore.draft.some((r, k) => S.draft[k] && r.vol !== S.draft[k].vol))) remember(volBefore);
  volBefore = null;
  renderTimeline(); renderToolbar(); refreshHeader();
});
/* Volume da tomada na prévia: o cut.mp4 já sai com o volume que o edl.json tinha
 * (`volCorte`), então a prévia toca a razão entre o pedido e o que já está no arquivo.
 * Acima do que o arquivo tem, fica no máximo (a prévia não aumenta, o final sim). */
const volCorte = (r) => (S.rendered[r.from] ? S.rendered[r.from].vol : 1);
function volPrevia(r) {
  const base = volCorte(r);
  if (!(base > 0)) return r.vol > 0 ? 1 : 0; // trecho mudo no cut.mp4: não há o que tocar mais alto
  return Math.max(0, Math.min(1, r.vol / base));
}
/* Velocidade da tomada: régua de 0,25× a 4× em escala de potências de 2 (1× no meio),
 * com marcas em 0,5×, 1×, 1,5× e 2× que puxam o dedo. A tomada encolhe ou estica na linha
 * do tempo na hora, e a prévia toca o mesmo cut.mp4 mais rápido ou mais devagar
 * (playbackRate, o tom da voz fica). Efeitos e camadas estão no relógio do cut.mp4: ficam
 * onde estão até o agente refazer o corte, como num corte refeito. */
const VEL_MARCAS = [0.5, 1, 1.5, 2];
const fmtVel = (v) => `${String(+v.toFixed(2)).replace('.', ',')}×`;
const fmtSeg = (t) => `${t.toFixed(1).replace('.', ',')} s`;
let velBefore = null;
function velTomada() { return S.selected >= 0 && S.view === 'corte' ? S.draft[S.selected] : null; }
function velMostrar(r) {
  $('velVal').textContent = r.curva ? nomeCurva(r.curva.nome) : fmtVel(r.vel);
  const d = draftLayout()[S.selected];
  const orig = d ? r.end - r.start - (d.leadSrc || 0) - (d.tailSrc || 0) : 0; // o trecho da gravação que aparece, a 1×
  const igual = r.vel === 1 && !r.curva;
  $('velDur').textContent = igual ? `Duração: ${fmtSeg(orig)}` : `Duração: ${fmtSeg(orig)} → ${fmtSeg(d ? d.dur : 0)}`;
}
function openVelocidade() {
  const r = velTomada();
  if (!r) return;
  video.pause();
  velBefore = snap();
  const d = draftLayout()[S.selected];
  S.t = d.out; // a agulha no começo da tomada: ele não anda quando a tomada estica
  positionTimeline();
  preciseSeek();
  $('velRange').value = Math.log2(r.vel).toFixed(2);
  S.velPonto = null;
  velModo(r.curva ? 'curva' : 'normal');
  velMostrar(r);
  showSheet($('velSheet'), true);
}
$('velRange').addEventListener('input', () => {
  const r = velTomada();
  if (!r) return;
  const p = +$('velRange').value;
  const marca = VEL_MARCAS.find((m) => Math.abs(Math.log2(m) - p) < 0.06); // perto de uma marca: encosta nela
  r.vel = marca || +Math.pow(2, p).toFixed(2);
  r.curva = null; // velocidade normal e curva não convivem
  velMostrar(r);
  velDesenhar();
  if (!G.velQueued) {
    G.velQueued = true;
    requestAnimationFrame(() => { G.velQueued = false; renderTimeline(); positionTimeline(); });
  }
});
$('velOk').addEventListener('click', () => {
  showSheet($('velSheet'), false);
  if (velBefore && velBefore.draft.some((r, k) => S.draft[k] && (r.vel !== S.draft[k].vel || curvaKey(r) !== curvaKey(S.draft[k])))) remember(velBefore);
  velBefore = null;
  renderTimeline(); renderToolbar(); refreshHeader();
});
// as marcas embaixo da régua, no lugar delas na escala de potências de 2
for (const m of VEL_MARCAS) {
  const b = el('button', 'vel-marca', $('velMarcas'));
  b.type = 'button';
  b.textContent = fmtVel(m);
  b.style.left = `${((Math.log2(m) + 2) / 4) * 100}%`;
  b.addEventListener('click', () => { $('velRange').value = Math.log2(m); $('velRange').dispatchEvent(new Event('input')); });
}

/* Curva (etapa 4d): as curvas do CapCut com os mesmos pontos (catálogo de recursos dele,
 * tipo 37). A grade aplica; o gráfico edita: arrastar um ponto (as pontas só sobem e
 * descem), + Ponto na agulha, − Ponto no escolhido, Redefinir volta ao desenho da curva.
 * Escala de 0,1× a 10× em log, com a linha do 1× no meio, como no CapCut. */
const CURVAS = [
  ['personalizar', 'Personalizar', [[0, 1], [0.25, 1], [0.5, 1], [0.75, 1], [1, 1]]],
  ['montagem', 'Montagem', [[0, 0.9], [0.1, 0.9], [0.5, 6.8], [0.65, 0.3], [0.8, 1], [1, 1]]],
  ['heroi', 'Herói', [[0, 1], [0.05, 1], [0.35, 5.5], [0.45, 0.5], [0.55, 0.5], [0.65, 5.5], [0.95, 1], [1, 1]]],
  ['bala', 'Bala', [[0, 5.2], [0.4, 5.2], [0.46, 0.5], [0.54, 0.5], [0.6, 5.2], [1, 5.2]]],
  ['salto', 'Salto', [[0, 0.6], [0.43, 0.6], [0.5, 6], [0.57, 0.6], [1, 0.6]]],
  ['entrada', 'Entrada rápida', [[0, 5.2], [0.4, 5.2], [0.6, 1], [1, 1]]],
  ['saida', 'Saída rápida', [[0, 1], [0.4, 1], [0.6, 5.2], [1, 5.2]]],
];
const CURVA_MAX_PONTOS = 20;
const nomeCurva = (id) => (CURVAS.find((c) => c[0] === id) || [id, 'Curva'])[1];
// posição vertical de uma velocidade no gráfico: log10 de −1 (0,1×) a 1 (10×)
const curvaY = (v, h) => h / 2 - Math.log10(Math.max(0.1, Math.min(10, v))) * (h / 2 - 8);
const curvaV = (y, h) => Math.pow(10, (h / 2 - y) / (h / 2 - 8));
function curvaPath(pontos, w, h, pad = 0) {
  const ps = [];
  for (let k = 0; k <= 60; k++) { // a reta entre pontos, desenhada na escala log
    const x = k / 60;
    let v = pontos[pontos.length - 1][1];
    for (let j = 0; j + 1 < pontos.length; j++) {
      const [xa, ya] = pontos[j], [xb, yb] = pontos[j + 1];
      if (x <= xb && xb > xa) { v = ya + (yb - ya) * Math.max(0, x - xa) / (xb - xa); break; }
    }
    ps.push(`${(pad + x * (w - 2 * pad)).toFixed(1)},${curvaY(v, h).toFixed(1)}`);
  }
  return `M${ps.join('L')}`;
}
function velModo(m) {
  for (const b of $('velModos').children) b.classList.toggle('on', b.dataset.modo === m);
  $('velNormal').hidden = m !== 'normal';
  $('velCurva').hidden = m !== 'curva';
  if (m === 'curva') { renderCurvas(); velDesenhar(); }
}
for (const b of $('velModos').children) b.addEventListener('click', () => velModo(b.dataset.modo));
function renderCurvas() {
  const r = velTomada();
  const box = $('velCurvas');
  box.textContent = '';
  for (const [id, nome, pts] of [[null, 'Nenhuma', [[0, 1], [1, 1]]], ...CURVAS]) {
    const b = el('button', 'vel-curva', box);
    b.type = 'button';
    b.dataset.curva = id || '';
    b.classList.toggle('on', r ? (r.curva ? r.curva.nome === id : id === null) : false);
    b.innerHTML = `<svg viewBox="0 0 54 30"><path d="${curvaPath(pts, 54, 30, 2)}" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>`;
    el('span', '', b).textContent = nome;
    b.addEventListener('click', () => aplicarCurva(id));
  }
}
function velMudou(r) {
  velMostrar(r);
  velDesenhar();
  if (!G.velQueued) {
    G.velQueued = true;
    requestAnimationFrame(() => { G.velQueued = false; renderTimeline(); positionTimeline(); });
  }
}
function aplicarCurva(id) {
  const r = velTomada();
  if (!r) return;
  const c = CURVAS.find((x) => x[0] === id);
  r.curva = c ? { nome: id, pontos: c[2].map((p) => [p[0], p[1]]) } : null;
  r.vel = 1;
  S.velPonto = null;
  renderCurvas();
  velMudou(r);
}
// a agulha dentro da tomada, em fração da gravação (onde o + Ponto entra)
function velAgulhaX(r) {
  const d = draftLayout()[S.selected];
  if (!d || !r) return null;
  const s = Tempo.gravacaoEm(pedsD(r), (d.lead || 0) + (S.t - d.out));
  const x = (s - r.start) / (r.end - r.start);
  return x > 0 && x < 1 ? x : null;
}
function velDesenhar() {
  const box = $('velGrafico');
  const r = velTomada();
  if (!r || $('velCurva').hidden) return;
  const w = Math.max(200, box.clientWidth || 300), h = 150;
  const pts = r.curva ? r.curva.pontos : [[0, r.vel], [1, r.vel]];
  const X = (x) => 12 + x * (w - 24);
  let svg = `<svg viewBox="0 0 ${w} ${h}">`;
  for (const [v, rot] of [[10, '10×'], [1, '1×'], [0.1, '0,1×']]) {
    const y = curvaY(v, h);
    svg += `<line class="guia${v === 1 ? ' um' : ''}" x1="0" x2="${w}" y1="${y}" y2="${y}"/><text class="rotulo" x="2" y="${y - 3}">${rot}</text>`;
  }
  const xa = velAgulhaX(r);
  if (xa != null) svg += `<line class="agulha" x1="${X(xa)}" x2="${X(xa)}" y1="0" y2="${h}"/>`;
  svg += `<path class="linha" d="${curvaPath(pts, w, h, 12)}"/>`;
  if (r.curva) {
    pts.forEach(([x, v], k) => {
      svg += `<circle class="ponto${k === S.velPonto ? ' on' : ''}" cx="${X(x)}" cy="${curvaY(v, h)}" r="6"/>`;
      svg += `<circle class="alvo" data-k="${k}" cx="${X(x)}" cy="${curvaY(v, h)}" r="18"/>`;
    });
  }
  box.innerHTML = `${svg}</svg>`;
  $('velMais').disabled = !r.curva || xa == null || pts.length >= CURVA_MAX_PONTOS;
  $('velMenos').disabled = !r.curva || S.velPonto == null || S.velPonto === 0 || S.velPonto === pts.length - 1;
  $('velRedefinir').disabled = !r.curva;
}
// arrastar um ponto: para cima e para baixo a velocidade; para os lados, entre os vizinhos
$('velGrafico').addEventListener('pointerdown', (e) => {
  const alvo = e.target.closest('.alvo');
  const r = velTomada();
  if (!alvo || !r || !r.curva) return;
  e.preventDefault();
  S.velPonto = +alvo.dataset.k;
  const box = $('velGrafico');
  box.setPointerCapture(e.pointerId);
  const mover = (ev) => {
    const rect = box.getBoundingClientRect();
    const w = rect.width, h = 150;
    const pts = r.curva.pontos.map((p) => [p[0], p[1]]);
    const k = S.velPonto;
    const v = +Math.max(0.1, Math.min(10, curvaV(ev.clientY - rect.top, h))).toFixed(2);
    let x = pts[k][0];
    if (k > 0 && k < pts.length - 1) { // as pontas ficam no começo e no fim da tomada
      x = (ev.clientX - rect.left - 12) / (w - 24);
      x = +Math.max(pts[k - 1][0] + 0.01, Math.min(pts[k + 1][0] - 0.01, x)).toFixed(4);
    }
    pts[k] = [x, v];
    r.curva = { nome: r.curva.nome, pontos: pts };
    velMudou(r);
  };
  const soltar = () => { box.removeEventListener('pointermove', mover); box.removeEventListener('pointerup', soltar); box.removeEventListener('pointercancel', soltar); velDesenhar(); };
  box.addEventListener('pointermove', mover);
  box.addEventListener('pointerup', soltar);
  box.addEventListener('pointercancel', soltar);
  velDesenhar();
});
$('velMais').addEventListener('click', () => {
  const r = velTomada();
  const x = velAgulhaX(r);
  if (!r || !r.curva || x == null || r.curva.pontos.length >= CURVA_MAX_PONTOS) return;
  const pts = r.curva.pontos.map((p) => [p[0], p[1]]);
  const j = pts.findIndex((p) => p[0] > x);
  const [xa, ya] = pts[j - 1], [xb, yb] = pts[j];
  if (x - xa < 0.01 || xb - x < 0.01) { toast('Já tem um ponto aí', 1800); return; }
  pts.splice(j, 0, [+x.toFixed(4), +(ya + (yb - ya) * (x - xa) / (xb - xa)).toFixed(2)]);
  r.curva = { nome: r.curva.nome, pontos: pts };
  S.velPonto = j;
  velMudou(r);
});
$('velMenos').addEventListener('click', () => {
  const r = velTomada();
  const k = S.velPonto;
  if (!r || !r.curva || k == null || k === 0 || k === r.curva.pontos.length - 1) return;
  r.curva = { nome: r.curva.nome, pontos: r.curva.pontos.filter((_, j) => j !== k).map((p) => [p[0], p[1]]) };
  S.velPonto = null;
  velMudou(r);
});
$('velRedefinir').addEventListener('click', () => { const r = velTomada(); if (r && r.curva) aplicarCurva(r.curva.nome); });

// no Final o vídeo já é o que o agente montou, com o volume de cada tomada dentro
function syncVolTomada() {
  let v = 1;
  if (S.view === 'corte' && S.draft.length) {
    const dl = draftLayout();
    const k = itemAt(dl, S.t);
    if (k >= 0) v = volPrevia(dl[k]);
  }
  if (video.volume !== v) video.volume = v;
}

// prévia: o som do vídeo, o som de cada camada e a imagem por cima
function applyMute() {
  video.muted = S.mudoUsuario || (S.view === 'corte' && S.camadas.video.mudo);
}
const AUD = new Map(); // id do item → <audio>
function audioEl(it) {
  let a = AUD.get(it.id);
  if (!a || a.dataset.arq !== it.arquivo) {
    if (a) a.pause();
    a = new Audio(`/media/${it.arquivo}`);
    a.preload = 'auto';
    a.dataset.arq = it.arquivo;
    AUD.set(it.id, a);
  }
  return a;
}
let ovShown = '';
function syncLayers() {
  const corte = S.view === 'corte';
  const playing = !video.paused && !video.ended && !G.mode;
  const rt = corte ? draftToRendered(S.t) : 0;
  const vivos = new Set();
  let img = '';
  if (corte && S.camadas) {
    for (const f of S.camadas.faixas) {
      for (const it of f.itens) {
        const dentro = rt >= it.inicio && rt < it.inicio + it.duracao;
        if (!dentro) continue;
        // a camada mais nova fica por cima, como no vídeo final (os inserts dela entram por último)
        if (f.tipo === 'imagem') { if (!f.oculto) img = it.arquivo; continue; }
        if (f.mudo || !playing) continue;
        vivos.add(it.id);
        const a = audioEl(it);
        const alvo = it.corte + (rt - it.inicio);
        a.volume = Math.min(1, it.volume); // acima de 100% a prévia toca a 100%; o vídeo final leva o ganho
        a.muted = S.mudoUsuario;
        if (Math.abs(a.currentTime - alvo) > 0.25) a.currentTime = alvo;
        if (a.paused) a.play().catch(() => {});
      }
    }
  }
  for (const [id, a] of AUD) if (!vivos.has(id) && !a.paused) a.pause();
  if (img !== ovShown) {
    ovShown = img;
    const ov = $('ovImg');
    if (img) ov.src = `/media/${img}`;
    ov.classList.toggle('hidden', !img);
  }
}
['fileAudio', 'fileImagem'].forEach((id) => {
  $(id).addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = '';
    if (f) sendVideo(f); // o servidor separa: vídeo para a pasta dos vídeos, o resto para midia/
  });
});

/* ---------- trilhas: a biblioteca do kit (helpers/pacotes.py) ----------
 * A lista vem do catálogo do kit, sem internet. A prévia e a trilha só descem
 * quando a pessoa toca: o servidor baixa para o cache do computador e copia a
 * trilha para midia/. Ela entra na agulha como camada de áudio, com volume de
 * fundo, e a partir daí é uma camada como as outras (mover, aparar, volume). */
const TRILHA_VOLUME = 0.15; // o mesmo do pacotes.py: embaixo da voz
/* O kit não hospeda música: com a biblioteca vazia, o painel mostra onde baixar de
 * graça. A mesma lista está em references/trilhas-gratis.md (o teste confere). */
const TRILHAS_GRATIS = [
  ['Sem precisar dar crédito', [
    ['Pixabay Música', 'https://pixabay.com/music/'],
    ['Mixkit', 'https://mixkit.co/free-stock-music/'],
    ['StreamBeats', 'https://www.streambeats.com/'],
    ['Holizna', 'https://holiznacc0.bandcamp.com/', 'lo-fi e hip hop em domínio público'],
  ]],
  ['Grátis, com crédito na descrição do post', [
    ['Biblioteca de áudio do YouTube', 'https://studio.youtube.com/', 'no YouTube Studio; só algumas pedem crédito'],
    ['Uppbeat', 'https://uppbeat.io/'],
    ['Incompetech', 'https://incompetech.com/music/royalty-free/music.html', 'do Kevin MacLeod'],
    ['Free To Use', 'https://freetouse.com/music'],
  ]],
];
const PREV = new Audio();
let trFiltro = 'todas', trSel = null, trBaixando = null;
const trAberto = () => $('trilhaSheet').classList.contains('open');
const fmtDur = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
async function loadTrilhas() {
  try {
    const r = await fetch('/api/pacotes?tipo=trilha');
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `erro ${r.status}`);
    S.trilhas = d.pacotes;
  } catch (e) {
    S.trilhas = S.trilhas || [];
  }
  for (const p of S.trilhas) S.trilhaNomes[p.id] = p.nome;
}
async function openTrilhas() {
  video.pause();
  if (!S.trilhas) $('trilhaLista').innerHTML = '<p class="sheet-hint">Carregando…</p>';
  showSheet($('trilhaSheet'), true);
  await loadTrilhas();
  renderTrilhas();
}
function closeTrilhas() {
  PREV.pause();
  trSel = null;
  showSheet($('trilhaSheet'), false);
}
function renderGuiaTrilhas(box) {
  const guia = el('div', 'tr-guia', box);
  el('p', 'tr-guia-lead', guia).textContent = 'Vai postar no Instagram, no TikTok ou no Shorts? '
    + 'Deixe sem trilha e escolha a música na hora de postar, no próprio app.';
  el('p', 'sheet-hint', guia).textContent = 'Conta comercial no Instagram vê só a Sound Collection da Meta. '
    + 'No TikTok, conta empresa vê só a Biblioteca de Música Comercial, que vale só dentro do TikTok.';
  el('p', 'tr-guia-lead', guia).textContent = 'Para a música ficar no vídeo, baixe de graça num destes sites e traga pelo botão.';
  for (const [grupo, sites] of TRILHAS_GRATIS) {
    el('b', 'tr-guia-grupo', guia).textContent = grupo;
    for (const [nome, url, nota] of sites) {
      const a = el('a', 'tr-site', guia);
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      el('b', null, a).textContent = nome;
      el('span', null, a).textContent = nota || new URL(url).hostname.replace(/^www\./, '');
    }
  }
  const btn = el('button', 'tb-btn primary tr-guia-btn', guia);
  btn.type = 'button';
  btn.dataset.act = 'do-celular';
  btn.textContent = 'Escolher música do celular';
  el('p', 'sheet-hint', guia).textContent = 'Se o YouTube reivindicar uma música grátis, '
    + 'conteste com o link da página onde você baixou.';
}
function renderTrilhas() {
  const lista = S.trilhas || [];
  const climas = [...new Set(lista.map((p) => p.clima).filter(Boolean))];
  const filtros = $('trilhaFiltros');
  filtros.innerHTML = '';
  if (!lista.length) { // biblioteca vazia: sem filtros, só o guia
    $('trilhaLista').innerHTML = '';
    renderGuiaTrilhas($('trilhaLista'));
    return;
  }
  for (const [id, nome] of [['todas', 'Todas'], ['favoritas', 'Favoritas'],
    ...climas.map((c) => [c, c[0].toUpperCase() + c.slice(1)])]) {
    const b = el('button', `subtab${trFiltro === id ? ' on' : ''}`, filtros);
    b.type = 'button';
    b.dataset.filtro = id;
    b.textContent = nome;
  }
  const box = $('trilhaLista');
  box.innerHTML = '';
  const vis = lista.filter((p) => trFiltro === 'todas' || (trFiltro === 'favoritas' ? p.favorito : p.clima === trFiltro));
  if (!vis.length) {
    el('p', 'sheet-hint', box).textContent = trFiltro === 'favoritas'
        ? 'Toque na estrela de uma trilha para guardá-la aqui. A favorita fica neste computador.'
        : 'Nenhuma trilha aqui.';
    return;
  }
  const tocando = !PREV.paused && PREV.dataset.id;
  for (const p of vis) {
    const row = el('div', `tr-row${trSel === p.id ? ' on' : ''}`, box);
    row.dataset.id = p.id;
    const play = el('button', 'tr-play', row);
    play.type = 'button';
    play.dataset.act = 'ouvir';
    play.disabled = !p.previa;
    play.innerHTML = tocando === p.id ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', `${tocando === p.id ? 'Parar' : 'Ouvir'} ${p.nome}`);
    const txt = el('div', 'tr-txt', row);
    el('b', null, txt).textContent = p.nome;
    const info = [p.clima, fmtDur(p.duracao)];
    if (p.baixado) info.push('no computador');
    el('span', null, txt).textContent = info.filter(Boolean).join(' · ');
    const fav = el('button', `tr-fav${p.favorito ? ' on' : ''}`, row);
    fav.type = 'button';
    fav.dataset.act = 'favorito';
    fav.innerHTML = p.favorito ? ICON.estrelaCheia : ICON.estrela;
    fav.setAttribute('aria-label', p.favorito ? 'Tirar dos favoritos' : 'Favoritar');
    fav.setAttribute('aria-pressed', String(!!p.favorito));
    if (trSel === p.id) { // a escolhida mostra Usar, como no app de celular
      const usar = el('button', 'tb-btn primary tr-usar', row);
      usar.type = 'button';
      usar.dataset.act = 'usar';
      usar.textContent = trBaixando === p.id ? 'Baixando…' : 'Usar';
      usar.disabled = !!trBaixando;
    }
  }
}
function ouvirTrilha(id) {
  const p = (S.trilhas || []).find((x) => x.id === id);
  if (!p) return;
  if (trSel === id && !PREV.paused) { PREV.pause(); return; }
  trSel = id;
  if (p.previa) {
    if (PREV.dataset.id !== id) {
      PREV.src = `/gen/pacote-previa?id=${encodeURIComponent(id)}`;
      PREV.dataset.id = id;
    }
    PREV.muted = S.mudoUsuario;
    PREV.play().catch(() => {});
  }
  renderTrilhas();
}
async function favTrilha(id) {
  const p = (S.trilhas || []).find((x) => x.id === id);
  if (!p) return;
  p.favorito = !p.favorito;
  renderTrilhas();
  try {
    const r = await fetch('/api/pacotes/favorito', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, on: p.favorito }) });
    if (!r.ok) throw new Error(String(r.status));
  } catch (e) {
    p.favorito = !p.favorito;
    if (trAberto()) renderTrilhas();
    toast('Não deu para favoritar agora', 2200);
  }
}
async function usarTrilha(id) {
  if (trBaixando) return;
  trBaixando = id;
  renderTrilhas();
  try {
    const r = await fetch('/api/pacotes/usar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `erro ${r.status}`);
    const p = S.trilhas.find((x) => x.id === id);
    if (p) p.baixado = true;
    S.trilhaNomes[id] = d.nome;
    trBaixando = null;
    closeTrilhas();
    await addLayer('audio', d.arquivo, { volume: TRILHA_VOLUME, trilha: id });
    toast(`"${d.nome}" entrou na agulha, com volume de fundo (${Math.round(TRILHA_VOLUME * 100)}%)`, 2600);
  } catch (e) {
    trBaixando = null;
    if (trAberto()) renderTrilhas();
    toast(`A trilha não baixou: ${e.message}`, 3600);
  }
}
$('trilhaClose').innerHTML = ICON.fechar;
$('trilhaClose').addEventListener('click', closeTrilhas);
$('trilhaFiltros').addEventListener('click', (e) => {
  const b = e.target.closest('[data-filtro]');
  if (!b) return;
  trFiltro = b.dataset.filtro;
  renderTrilhas();
});
$('trilhaLista').addEventListener('click', (e) => {
  if (e.target.closest('[data-act="do-celular"]')) { // o mesmo de Áudio → Do celular
    closeTrilhas();
    S.audioMenu = false;
    renderToolbar();
    $('fileAudio').click();
    return;
  }
  const row = e.target.closest('.tr-row');
  if (!row) return;
  const btn = e.target.closest('[data-act]');
  const act = btn ? btn.dataset.act : 'ouvir'; // tocar na linha ouve, como no app
  if (act === 'favorito') favTrilha(row.dataset.id);
  else if (act === 'usar') usarTrilha(row.dataset.id);
  else ouvirTrilha(row.dataset.id);
});
['play', 'pause'].forEach((ev) => PREV.addEventListener(ev, () => { if (trAberto()) renderTrilhas(); }));
PREV.addEventListener('error', () => {
  if (PREV.dataset.id && trAberto()) toast('A prévia não carregou. Confira a internet do computador.', 3000);
});

/* ---------- efeitos: filtros e transições da biblioteca (helpers/efeitos.py) ----------
 * O filtro entra na tomada debaixo da agulha; a transição, no corte mais perto dela,
 * centrada nele. Tudo fica em efeitos.json, no relógio do cut.mp4: o Salvar leva
 * `efeitos` e o agente aplica antes do render final (efeitos_render.py), com o MESMO
 * motor desta prévia (assets/efeitos/motor.js), na mesma resolução e pelo número do
 * quadro. A prévia desenha num canvas por cima do vídeo, só no Corte.
 * Transição: antes do corte, o lado A anda e o B fica parado no 1º quadro depois dele;
 * depois do corte, o A fica parado no último quadro antes dele e o B anda. Um quadro
 * com transição e filtro recebe a transição primeiro e o filtro por cima. */
const FX = { mod: null, motores: new Map(), congelados: new Map(), fila: Promise.resolve(), pararEm: null, naTela: null, aj: null };
const fxVazio = () => ({ versao: 1, itens: [] });
const fxSig = () => JSON.stringify(S.efeitos);
const efeitosDirty = () => fxSig() !== S.efeitosBase;
S.efeitosBase = fxSig();
const fxItem = (id) => S.efeitos.itens.find((x) => x.id === id) || null;
const fxTam = () => ({ largura: video.videoWidth || FRAME_W, altura: video.videoHeight || FRAME_H });
// o trecho do cut.mp4 que o efeito toca: a mesma conta do efeitos.py
function fxJanela(it) {
  if (it.tipo === 'transicao') return [it.corte - it.duracao / 2, it.corte + it.duracao / 2];
  return [it.inicio, it.inicio + it.duracao];
}
// 1 ms de folga: os tempos vão com 3 casas (até 0,5 ms além do corte), e sem ela o filtro
// de uma tomada pegava o 1º quadro da seguinte. A mesma conta do efeitos_render.py.
const fxDentro = (it, t) => { const [a, b] = fxJanela(it); return a - 1e-3 <= t && t < b - 1e-3; };
const fxCruzam = (x, y) => { const [a, b] = fxJanela(x), [c, d] = fxJanela(y); return a < d - 1e-6 && c < b - 1e-6; };

async function loadEfeitos() {
  let e = null;
  try {
    const r = await fetch(`/media/efeitos.json?v=${Date.now()}`);
    if (r.ok) e = await r.json();
  } catch (err) { /* ainda não existe */ }
  S.efeitos = e && Array.isArray(e.itens) ? { versao: 1, itens: e.itens } : fxVazio();
  S.efeitosBase = fxSig();
  FX.congelados.clear();
  fxPreparar(); // com o vídeo novo ainda carregando, quem prepara é o "loadeddata"
  // o bloco na linha do tempo mostra o nome do catálogo
  if (S.efeitos.itens.length) loadFxListas().then(renderTimeline);
}
async function loadFxLista(tipo) {
  try {
    const r = await fetch(`/api/pacotes?tipo=${tipo}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `erro ${r.status}`);
    S.fxLista[tipo] = d.pacotes;
  } catch (e) {
    S.fxLista[tipo] = S.fxLista[tipo] || [];
  }
  for (const p of S.fxLista[tipo]) S.fxNomes[p.id] = p.nome;
}
const loadFxListas = () => Promise.all([loadFxLista('filtro'), loadFxLista('transicao')]);

// um motor por pacote, na resolução do vídeo; o celular tem poucos contextos WebGL, ficam os 4 últimos
function fxMotor(pacote) {
  const { largura, altura } = fxTam();
  const chave = `${pacote}@${largura}x${altura}`;
  let m = FX.motores.get(chave);
  if (m) {
    FX.motores.delete(chave); // o mais usado vai para o fim da fila
  } else {
    FX.mod = FX.mod || import('/efeitos/motor.js');
    m = { ef: null };
    m.p = FX.mod.then((mod) => mod.carregarEfeito(`/gen/pacote/${encodeURIComponent(pacote)}/`, { largura, altura }));
    // falhou: fica marcado por 10 s, senão cada quadro pediria o pacote de novo
    m.p.then((ef) => { m.ef = ef; fxRedesenhar(); },
      () => setTimeout(() => { if (FX.motores.get(chave) === m) FX.motores.delete(chave); }, 10000));
  }
  FX.motores.set(chave, m);
  while (FX.motores.size > 4) {
    const [velha, v] = FX.motores.entries().next().value;
    FX.motores.delete(velha);
    v.p.then((ef) => ef.destruir()).catch(() => {});
  }
  return m;
}

// o ajuste não tem pacote: um motor só, o shader do próprio motor.js, refeito se o tamanho do vídeo mudar
function fxAjuste() {
  const { largura, altura } = fxTam();
  const chave = `${largura}x${altura}`;
  if (!FX.aj || FX.aj.chave !== chave) {
    const velho = FX.aj;
    const m = { chave, ef: null };
    FX.aj = m;
    FX.mod = FX.mod || import('/efeitos/motor.js');
    FX.mod.then((mod) => { if (FX.aj === m) { m.ef = mod.criarAjuste({ largura, altura }); fxRedesenhar(); } });
    if (velho && velho.ef) velho.ef.destruir();
  }
  return FX.aj.ef;
}

// os quadros parados da transição saem de um segundo vídeo, para não mexer no que está na tela
const fxVid = document.createElement('video');
fxVid.muted = true;
fxVid.playsInline = true;
fxVid.preload = 'auto';
function quadroDoCorte(n) {
  const fps = S.fps || 30;
  FX.fila = FX.fila.catch(() => {}).then(() => new Promise((ok, falha) => {
    const src = video.dataset.src;
    const tirar = () => {
      const { largura, altura } = fxTam();
      const c = document.createElement('canvas');
      c.width = largura;
      c.height = altura;
      c.getContext('2d').drawImage(fxVid, 0, 0, largura, altura);
      ok(c);
    };
    const ir = () => {
      fxVid.addEventListener('seeked', tirar, { once: true });
      fxVid.currentTime = (Math.max(0, n) + 0.5) / fps; // o meio do quadro: cai nele, não no vizinho
    };
    setTimeout(() => falha(new Error('o quadro parado não carregou')), 15000);
    if (fxVid.dataset.src !== src) {
      fxVid.dataset.src = src;
      fxVid.src = src;
      fxVid.addEventListener('loadeddata', ir, { once: true });
    } else ir();
  }));
  return FX.fila;
}
function fxCongelados(tr, fps) {
  const k = Math.floor(tr.corte * fps + 0.5); // o 1º quadro depois do corte
  const chave = `${video.dataset.src}#${k}`;
  let c = FX.congelados.get(chave);
  if (!c) {
    c = { pronto: null };
    FX.congelados.set(chave, c);
    while (FX.congelados.size > 6) FX.congelados.delete(FX.congelados.keys().next().value);
    Promise.all([quadroDoCorte(k - 1), quadroDoCorte(k)])
      .then(([a, b]) => { c.pronto = { a, b, k }; fxRedesenhar(); })
      .catch(() => FX.congelados.delete(chave));
  }
  return c.pronto;
}

/* O número do quadro na tela. Com o carimbo do próprio quadro (aviso de quadro do vídeo),
 * arredonda: o cut.mp4 pode vir com carimbos um pouco antes de n/fps (medido: 0,65 ms a
 * partir de um corte), e o "piso" cairia no quadro anterior bem no corte. Sem o aviso, o
 * tempo do vídeo pode estar no meio do quadro: piso, com 1 ms de folga para esse desvio. */
function fxNumero(tempo, exato, fps) {
  return exato ? Math.round(tempo * fps) : Math.floor(tempo * fps + 0.03);
}
function fxDesenhar(tempo, exato) {
  const cv = $('fxCanvas');
  const esconder = () => { if (!cv.classList.contains('hidden')) cv.classList.add('hidden'); };
  if (S.view !== 'corte' || S.posMode || S.styling || !video.videoWidth || G.mode === 'move') { esconder(); return; }
  const fps = S.fps || 30;
  const n = fxNumero(tempo, exato, fps); // o quadro do cut.mp4 que está na tela
  const t = n / fps;
  if (FX.pararEm != null && !video.paused && t >= FX.pararEm) { video.pause(); FX.pararEm = null; }
  let tr = null, fi = null, aj = null;
  for (const it of S.fxTeste ? [...S.efeitos.itens, S.fxTeste] : S.efeitos.itens) { // o de teste vale por último
    if (!fxDentro(it, t)) continue;
    if (it.tipo === 'transicao') tr = it; else if (it.tipo === 'ajuste') aj = it; else fi = it;
  }
  FX.completo = !tr && !fi && !aj; // o desenho tem tudo o que o quadro pede (os testes esperam por isto)
  if (!tr && !fi && !aj) { esconder(); return; }
  let fonte = video, saida = null, feitos = 0;
  if (tr) {
    const m = fxMotor(tr.pacote).ef;
    const cong = fxCongelados(tr, fps);
    if (m && cong) {
      const antes = n < cong.k;
      m.desenhar({ a: antes ? video : cong.a, b: antes ? cong.b : video,
        tempo_ms: (t - (tr.corte - tr.duracao / 2)) * 1000 });
      fonte = saida = m.canvas;
      feitos++;
    }
  }
  if (fi) {
    const m = fxMotor(fi.pacote).ef;
    if (m) {
      m.desenhar({ quadro: fonte, intensidade: fi.intensidade });
      fonte = saida = m.canvas;
      feitos++;
    }
  }
  if (aj) { // o ajuste por último, por cima do filtro: a mesma ordem do vídeo final
    const m = fxAjuste();
    if (m) {
      m.desenhar({ quadro: fonte, ajustes: aj.ajustes });
      saida = m.canvas;
      feitos++;
    }
  }
  FX.completo = feitos === (tr ? 1 : 0) + (fi ? 1 : 0) + (aj ? 1 : 0);
  if (!saida) { esconder(); return; } // o pacote ainda está descendo: mostra o vídeo como está
  const { largura, altura } = fxTam();
  if (cv.width !== largura || cv.height !== altura) { cv.width = largura; cv.height = altura; }
  cv.getContext('2d').drawImage(saida, 0, 0, largura, altura);
  cv.classList.remove('hidden');
}
// tocando, cada quadro novo do vídeo avisa (é o quadro que está na tela, não o relógio)
function fxQuadro(agora, meta) {
  FX.naTela = meta.mediaTime;
  fxDesenhar(meta.mediaTime, true);
  video.requestVideoFrameCallback(fxQuadro);
}
if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(fxQuadro);
// parado: o carimbo do último quadro mostrado, se o vídeo não saiu dele
function fxRedesenhar() {
  if (!(video.paused || video.ended)) return;
  const fps = S.fps || 30;
  if (FX.naTela != null && Math.abs(video.currentTime - FX.naTela) < 1 / fps) fxDesenhar(FX.naTela, true);
  else fxDesenhar(video.currentTime, false);
}
video.addEventListener('seeked', fxRedesenhar);
// motores e quadros parados prontos ANTES de a agulha chegar: tocando, a transição já
// aparece no 1º quadro da janela (preparar na entrada perdia os primeiros quadros)
function fxPreparar() {
  if (S.view !== 'corte' || !video.videoWidth || !video.dataset.src) return; // no Final o vídeo já tem os efeitos
  const fps = S.fps || 30;
  const pacotes = [...new Set(S.efeitos.itens.filter((it) => it.pacote).map((it) => it.pacote))].slice(0, 4); // o limite de motores
  for (const p of pacotes) fxMotor(p);
  if (S.efeitos.itens.some((it) => it.tipo === 'ajuste')) fxAjuste();
  for (const it of S.efeitos.itens) if (it.tipo === 'transicao') fxCongelados(it, fps);
}
video.addEventListener('loadeddata', fxPreparar);

function renderFxTrack(lane, ajustes) {
  for (const it of S.efeitos.itens) {
    if ((it.tipo === 'ajuste') !== ajustes) continue;
    const [a0, b0] = fxJanela(it);
    const a = renderedToDraft(Math.max(0, a0)), b = renderedToDraft(b0);
    const cls = { filtro: 'fi', transicao: 'tr', ajuste: 'aj' }[it.tipo];
    const chip = el('div', `chip fx ${cls}${it.id === S.fxSel ? ' sel' : ''}`, lane);
    chip.dataset.id = it.id;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps, 12)}px`;
    el('span', 'l-ico', chip).innerHTML = { filtro: ICON.filtro, transicao: ICON.transicao, ajuste: ICON.ajustar }[it.tipo];
    el('span', 'l-name', chip).textContent = it.tipo === 'ajuste' ? 'Ajuste' : S.fxNomes[it.pacote] || it.pacote;
  }
}
function tapFx(id) {
  if (!fxItem(id)) return;
  S.fxSel = S.fxSel === id ? null : id;
  S.layerSel = null;
  S.selected = -1;
  S.insSel = -1;
  renderTimeline();
  renderToolbar();
}
function deleteFxSel() {
  if (!fxItem(S.fxSel)) return;
  remember();
  S.efeitos.itens = S.efeitos.itens.filter((x) => x.id !== S.fxSel);
  S.fxSel = null;
  renderTimeline(); renderToolbar(); refreshHeader();
  fxRedesenhar();
}
// sem intensidade gravada, vale a do pacote (o motor já sabe qual é)
function fxIntensidade(it) {
  if (typeof it.intensidade === 'number') return it.intensidade;
  const m = fxMotor(it.pacote).ef;
  return (m && m.manifesto.intensidade && m.manifesto.intensidade.padrao) || 1;
}
let intBefore = null;
function openIntensidade() {
  const it = fxItem(S.fxSel);
  if (!it) return;
  intBefore = snap();
  const v = Math.round(fxIntensidade(it) * 100);
  $('fxIntRange').value = v;
  $('fxIntVal').textContent = `${v}%`;
  showSheet($('fxIntSheet'), true);
}
$('fxIntRange').addEventListener('input', () => {
  const it = fxItem(S.fxSel);
  if (!it) return;
  it.intensidade = +($('fxIntRange').value / 100).toFixed(2);
  $('fxIntVal').textContent = `${$('fxIntRange').value}%`;
  fxRedesenhar();
});
$('fxIntOk').addEventListener('click', () => {
  showSheet($('fxIntSheet'), false);
  if (intBefore && JSON.stringify(intBefore.fx) !== fxSig()) remember(intBefore);
  intBefore = null;
  renderToolbar(); refreshHeader();
});

/* Ajustar: a cor da tomada (brilho, contraste…), no shader do próprio motor.js, sem pacote.
 * Fica em efeitos.json como `ajuste` na janela da tomada (relógio do cut.mp4, como o filtro),
 * um por tomada; a prévia desenha ao vivo enquanto a régua anda, por cima do filtro. Valor
 * perto de zero encosta no zero (no dedo, acertar o 0 exato é difícil); tudo em zero tira o
 * ajuste no Pronto. As chaves são as do helpers/efeitos.py. */
const AJ_NOMES = { brilho: 'Brilho', contraste: 'Contraste', saturacao: 'Saturação', exposicao: 'Exposição',
  temperatura: 'Temperatura', matiz: 'Matiz', realces: 'Realces', sombras: 'Sombras', vinheta: 'Vinheta' };
const AJ = { id: null, k: 'brilho', antes: null };
const ajTexto = (v) => (v > 0 ? `+${v}` : `${v}`);
function openAjuste() {
  const antes = snap();
  let it = fxItem(S.fxSel);
  if (!it || it.tipo !== 'ajuste') {
    const r = S.draft[S.selected];
    const L = r && renderedLayout()[r.from]; // a tomada no cut.mp4, como o filtro
    if (!L) return;
    const jan = { tipo: 'ajuste', inicio: +L.out.toFixed(3), duracao: +L.dur.toFixed(3) };
    it = S.efeitos.itens.find((x) => x.tipo === 'ajuste' && fxCruzam(x, jan));
    if (!it) {
      it = { id: novoFxId('a'), ...jan, ajustes: {} };
      S.efeitos.itens.push(it);
    }
  }
  AJ.id = it.id;
  AJ.antes = antes;
  AJ.k = Object.keys(AJ_NOMES).find((k) => it.ajustes[k]) || 'brilho'; // abre no que já foi mexido
  // a agulha vai para dentro da tomada: a prévia mostra o que a régua faz
  video.pause();
  const [a, b] = fxJanela(it);
  const rt = draftToRendered(S.t);
  if (!(rt >= a && rt < b - 1e-3)) {
    S.t = clampT(renderedToDraft(a + Math.min(0.5, (b - a) / 2)));
    positionTimeline();
    preciseSeek();
  }
  renderAjuste();
  showSheet($('ajSheet'), true);
  fxPreparar();
  fxRedesenhar();
}
function renderAjuste() {
  const it = fxItem(AJ.id);
  if (!it) return;
  const v = it.ajustes[AJ.k] || 0;
  $('ajNome').textContent = AJ_NOMES[AJ.k];
  $('ajVal').textContent = ajTexto(v);
  $('ajRange').value = v;
  $('ajRange').setAttribute('aria-label', AJ_NOMES[AJ.k]);
  const box = $('ajParams');
  box.innerHTML = '';
  for (const k of Object.keys(AJ_NOMES)) {
    const b = el('button', `subtab aj-p${k === AJ.k ? ' on' : ''}${it.ajustes[k] ? ' mexido' : ''}`, box);
    b.type = 'button';
    b.dataset.k = k;
    b.textContent = AJ_NOMES[k];
  }
}
$('ajParams').addEventListener('click', (e) => {
  const b = e.target.closest('.aj-p');
  if (!b) return;
  AJ.k = b.dataset.k;
  renderAjuste();
});
$('ajRange').addEventListener('input', () => {
  const it = fxItem(AJ.id);
  if (!it) return;
  const v0 = Math.round(+$('ajRange').value);
  const v = Math.abs(v0) <= 3 ? 0 : v0;
  if (v) it.ajustes[AJ.k] = v; else delete it.ajustes[AJ.k];
  $('ajVal').textContent = ajTexto(v);
  const b = $('ajParams').querySelector(`[data-k="${AJ.k}"]`);
  if (b) b.classList.toggle('mexido', !!v);
  fxRedesenhar();
});
$('ajReset').addEventListener('click', () => {
  const it = fxItem(AJ.id);
  if (!it) return;
  it.ajustes = {};
  renderAjuste();
  fxRedesenhar();
});
$('ajOk').addEventListener('click', () => {
  const it = fxItem(AJ.id);
  if (it && !Object.keys(it.ajustes).length) S.efeitos.itens = S.efeitos.itens.filter((x) => x !== it); // tudo neutro: sai
  if (S.fxSel && !fxItem(S.fxSel)) S.fxSel = null;
  showSheet($('ajSheet'), false);
  if (AJ.antes && JSON.stringify(AJ.antes.fx) !== fxSig()) remember(AJ.antes);
  AJ.id = null;
  AJ.antes = null;
  renderTimeline(); renderToolbar(); refreshHeader();
  fxRedesenhar();
});

/* Miniatura de cada filtro: o quadro debaixo da agulha já com o filtro, como no app de
 * celular. Um motor pequeno por vez (criar, desenhar, copiar, destruir), porque o celular
 * tem poucos contextos WebGL e a prévia já usa até 4. Só desenha a linha que aparece no
 * painel, e só baixa sozinho pacote pequeno; o maior fica com o ícone até a pessoa tocar. */
const MINI = { w: 88, h: 112, limite: 1.5e6, fila: Promise.resolve(), quadro: null, chave: '',
  feitas: new Map(), falhas: new Set(), obs: null };
function miniQuadro() {
  if (!video.videoWidth || video.readyState < 2) return null;
  const chave = `${video.dataset.src}#${Math.round(video.currentTime * (S.fps || 30))}`;
  if (MINI.chave !== chave) { // o meio do quadro, na proporção da miniatura
    const c = document.createElement('canvas');
    c.width = MINI.w;
    c.height = MINI.h;
    const k = Math.min(video.videoWidth / MINI.w, video.videoHeight / MINI.h);
    const sw = MINI.w * k, sh = MINI.h * k;
    c.getContext('2d').drawImage(video, (video.videoWidth - sw) / 2, (video.videoHeight - sh) / 2, sw, sh, 0, 0, MINI.w, MINI.h);
    MINI.quadro = c;
    MINI.chave = chave;
  }
  return MINI.quadro;
}
function miniPintar(ico, img) {
  const c = document.createElement('canvas');
  c.width = MINI.w;
  c.height = MINI.h;
  c.getContext('2d').drawImage(img, 0, 0);
  ico.classList.add('com-mini');
  ico.replaceChildren(c);
}
function miniPedir(p) {
  const q = miniQuadro();
  if (!q || MINI.falhas.has(p.id)) return;
  const chave = `${p.id}|${MINI.chave}`;
  MINI.fila = MINI.fila.catch(() => {}).then(async () => {
    if (!MINI.feitas.has(chave) && fxAberto() && fxTipo === 'filtro') {
      FX.mod = FX.mod || import('/efeitos/motor.js');
      const ef = await (await FX.mod).carregarEfeito(`/gen/pacote/${encodeURIComponent(p.id)}/`, { largura: MINI.w, altura: MINI.h })
        .catch(() => { MINI.falhas.add(p.id); return null; }); // o pacote que falta fica com o ícone, sem aviso
      if (!ef) return;
      try {
        ef.desenhar({ quadro: q }); // a intensidade do pacote
        const img = document.createElement('canvas');
        img.width = MINI.w;
        img.height = MINI.h;
        img.getContext('2d').drawImage(ef.canvas, 0, 0);
        MINI.feitas.set(chave, img);
        while (MINI.feitas.size > 60) MINI.feitas.delete(MINI.feitas.keys().next().value);
        p.baixado = true;
      } finally {
        ef.destruir();
      }
    }
    const img = MINI.feitas.get(chave);
    const ico = document.querySelector(`#fxLista .tr-row[data-id="${CSS.escape(p.id)}"] .fx-ico`);
    if (img && ico && !ico.classList.contains('com-mini')) miniPintar(ico, img); // a lista pode ter sido redesenhada
  });
}
function miniObservar(lista) {
  if (MINI.obs) MINI.obs.disconnect();
  if (fxTipo !== 'filtro' || !window.IntersectionObserver) return;
  const porId = new Map(lista.map((p) => [p.id, p]));
  MINI.obs = new IntersectionObserver((vistos) => {
    for (const v of vistos) {
      if (!v.isIntersecting) continue;
      MINI.obs.unobserve(v.target);
      const p = porId.get(v.target.closest('.tr-row').dataset.id);
      if (p && !(p.tamanho > MINI.limite)) miniPedir(p);
    }
  }, { root: $('fxLista'), rootMargin: '120px' });
  for (const ico of $('fxLista').querySelectorAll('.tr-row .fx-ico:not(.com-mini)')) MINI.obs.observe(ico);
}

// o painel: tocar mostra o efeito no vídeo; "Usar" aplica
let fxTipo = 'filtro', fxEscolha = null, fxBaixando = null;
const fxAberto = () => $('fxSheet').classList.contains('open');
async function openFx(tipo) {
  fxTipo = tipo;
  fxEscolha = null;
  S.fxTeste = null;
  video.pause();
  $('fxTitle').textContent = tipo === 'filtro' ? 'Filtros' : 'Transições';
  if (!S.fxLista[tipo]) $('fxLista').innerHTML = '<p class="sheet-hint">Carregando…</p>';
  app.classList.add('efeitando');
  showSheet($('fxSheet'), true);
  await loadFxLista(tipo);
  renderFxLista();
}
function closeFx() {
  if (MINI.obs) MINI.obs.disconnect(); // fechado o painel, nenhuma miniatura nova entra na fila
  S.fxTeste = null;
  FX.pararEm = null;
  fxEscolha = null;
  app.classList.remove('efeitando');
  showSheet($('fxSheet'), false);
  sizeCanvases(); positionTimeline(); // a linha do tempo volta a aparecer
  fxRedesenhar();
}
function renderFxLista() {
  const box = $('fxLista');
  box.innerHTML = '';
  const lista = S.fxLista[fxTipo] || [];
  const filtro = fxTipo === 'filtro';
  if (!lista.length) {
    el('p', 'sheet-hint', box).textContent = filtro
      ? 'A biblioteca deste kit ainda não tem filtros.' : 'A biblioteca deste kit ainda não tem transições.';
    return;
  }
  el('p', 'sheet-hint', box).textContent = filtro
    ? 'Toque para ver no vídeo. "Usar" põe o filtro na tomada debaixo da agulha.'
    : 'Toque para ver no corte mais perto da agulha. "Usar" põe a transição nele.';
  for (const p of lista) {
    const row = el('div', `tr-row${fxEscolha === p.id ? ' on' : ''}`, box);
    row.dataset.id = p.id;
    const ico = el('span', 'tr-play fx-ico', row);
    ico.innerHTML = filtro ? ICON.filtro : ICON.transicao;
    const pronta = filtro && miniQuadro() && MINI.feitas.get(`${p.id}|${MINI.chave}`);
    if (pronta) miniPintar(ico, pronta); // redesenhar a lista não pisca: a miniatura já existe
    const txt = el('div', 'tr-txt', row);
    el('b', null, txt).textContent = p.nome;
    const info = [];
    if (!filtro && p.duracao) info.push(`${p.duracao.toFixed(1).replace('.', ',')} s`);
    if (fxBaixando === p.id) info.push('baixando…');
    else if (p.baixado) info.push('no computador');
    el('span', null, txt).textContent = info.join(' · ');
    if (fxEscolha === p.id) {
      const usar = el('button', 'tb-btn primary tr-usar', row);
      usar.type = 'button';
      usar.dataset.act = 'usar';
      usar.textContent = 'Usar';
      usar.disabled = fxBaixando === p.id;
    }
  }
  miniObservar(lista);
}
// a tomada debaixo da agulha e o corte mais perto dela, no relógio do cut.mp4
function tomadaEm(rt) {
  const rl = renderedLayout();
  return rl.find((r) => rt >= r.out && rt < r.out + r.dur) || rl[rl.length - 1] || null;
}
function corteMaisPerto(rt) {
  const cortes = renderedLayout().slice(1).map((r) => r.out);
  if (!cortes.length) return null;
  return cortes.reduce((a, c) => (Math.abs(c - rt) < Math.abs(a - rt) ? c : a));
}
function testarFx(id) {
  const p = (S.fxLista[fxTipo] || []).find((x) => x.id === id);
  if (!p) return;
  const rt = draftToRendered(S.t);
  if (fxTipo === 'filtro') {
    const tk = tomadaEm(rt);
    if (!tk) return;
    S.fxTeste = { id: '_teste', tipo: 'filtro', pacote: id, inicio: +tk.out.toFixed(3), duracao: +tk.dur.toFixed(3) };
  } else {
    const corte = corteMaisPerto(rt);
    if (corte == null) { toast('A transição vai num corte: este vídeo ainda é uma tomada só', 2800); return; }
    const dur = Math.min(5, Math.max(0.1, p.duracao || 1));
    S.fxTeste = { id: '_teste', tipo: 'transicao', pacote: id, corte: +corte.toFixed(3), duracao: dur };
    // mostra a transição tocando: começa um pouco antes da janela e para um pouco depois
    S.t = clampT(renderedToDraft(Math.max(0, corte - dur / 2 - 0.4)));
    positionTimeline();
    preciseSeek();
    FX.pararEm = corte + dur / 2 + 0.4;
    video.play().catch(() => {});
  }
  fxEscolha = id;
  const m = fxMotor(id);
  if (!m.ef) {
    fxBaixando = id;
    m.p.then(() => { if (fxBaixando === id) fxBaixando = null; p.baixado = true; if (fxAberto()) renderFxLista(); },
      (e) => { fxBaixando = null; if (fxAberto()) renderFxLista(); toast(`O efeito não baixou: ${e.message}`, 3600); });
  }
  renderFxLista();
  fxRedesenhar();
}
function novoFxId(letra) {
  let n = 0;
  for (const it of S.efeitos.itens) {
    const m = new RegExp(`^${letra}(\\d+)$`).exec(it.id);
    if (m) n = Math.max(n, +m[1]);
  }
  return `${letra}${n + 1}`;
}
function usarFx(id) {
  const t = S.fxTeste;
  if (!t || t.pacote !== id) return;
  remember();
  const novo = { ...t, id: novoFxId(t.tipo === 'filtro' ? 'f' : 't') };
  // como no app de celular: um filtro por tomada, uma transição por corte; o novo troca o que estava ali
  S.efeitos.itens = S.efeitos.itens.filter((x) => x.tipo !== novo.tipo || !fxCruzam(x, novo));
  S.efeitos.itens.push(novo);
  fxPreparar();
  S.fxSel = novo.id;
  S.layerSel = null;
  S.selected = -1;
  const nome = S.fxNomes[id] || id;
  closeFx();
  renderTimeline(); renderToolbar(); refreshHeader();
  toast(t.tipo === 'filtro' ? `"${nome}" entrou na tomada` : `"${nome}" entrou no corte`, 2400);
}
$('fxClose').innerHTML = ICON.fechar;
$('fxClose').addEventListener('click', closeFx);
$('fxLista').addEventListener('click', (e) => {
  const row = e.target.closest('.tr-row');
  if (!row) return;
  const btn = e.target.closest('[data-act]');
  if (btn && btn.dataset.act === 'usar') usarFx(row.dataset.id);
  else testarFx(row.dataset.id);
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
DESK_MQ.addEventListener('change', () => { // a janela cruzou a largura do computador
  aplicarDesk();
  S.fitted = false;
  if (S.videoDuration) { fitZoom(); renderTimeline(); }
});
let deskResize = 0;
window.addEventListener('resize', () => {
  sizeCanvases();
  positionTimeline();
  if (S.styling) requestAnimationFrame(renderStyle); // os cartões recortam pela largura
  // no computador a altura da linha do tempo segue a da janela: refaz quando ela para de mudar
  clearTimeout(deskResize);
  if (isDesk() && S.videoDuration) deskResize = setTimeout(renderTimeline, 120);
});
poll();
loop();
if (document.fonts && document.fonts.ready) {
  // as amostras medem o texto: erradas até a Poppins carregar
  document.fonts.ready.then(() => { if (S.styling) renderStyle(); });
}
