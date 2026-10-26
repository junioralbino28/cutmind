/* CutMind — o editor (o mesmo no computador e no celular).
 *
 * O backend é o preview_server.py:
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
 * É o editor único, no computador e no celular: o agente (Claude ou Codex) lê os
 * arquivos que ele grava, nos campos que a edição antiga do PC (app.js, que saiu em
 * 22/10) usava — por isso os payloads abaixo seguem aquele formato.
 *
 * Escolhas de propósito:
 *  - No celular a agulha fica PARADA no centro e a linha do tempo anda por baixo dela
 *    (padrão CapCut/Edits); no computador ela anda, como no CapCut desktop (ver
 *    agulhaAnda). O gesto do celular é próprio, não a rolagem nativa: um dedo
 *    arrasta (com inércia), dois dedos fazem pinça, toque seleciona. Rolagem
 *    nativa e pinça brigam pelo mesmo toque — por isso touch-action:none.
 *  - O Estilo abre num painel que sobe; a prévia fica em cima e mostra a escolha
 *    AO VIVO sobre o vídeo. Ela usa o CORTE LIMPO (cut.mp4), não o render final,
 *    senão a amostra apareceria por cima da legenda já queimada no vídeo.
 *  - Catálogo e amostras vêm de estilos.js.
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
 * A classe `desk` no <html> liga esse leiaute; `?leiaute=computador` força, para testar.
 * Com o vídeo em pé, a prévia vai para uma coluna ao lado da linha do tempo (classe `lado`):
 * com muitas faixas, empilhada ela encolhia no meio da tela. `?leiaute=empilhado` volta. */
const DESK_MQ = matchMedia('(min-width: 1024px) and (hover: hover) and (pointer: fine)');
const isDesk = () => document.documentElement.classList.contains('desk');
const ladoAtivo = () => isDesk() && ['lado', 'em-pe'].every((c) => document.documentElement.classList.contains(c));
function aplicarDesk() {
  const forca = new URLSearchParams(location.search).get('leiaute');
  const on = forca ? ['computador', 'empilhado'].includes(forca) : DESK_MQ.matches;
  document.documentElement.classList.toggle('desk', on);
  document.documentElement.classList.toggle('lado', on && forca !== 'empilhado');
}
// em pé até o vídeo dizer o contrário: é o caso comum, e assim a tela não pula ao abrir
document.documentElement.classList.add('em-pe');
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
  compartilhar: sv('<circle cx="17.5" cy="5.5" r="2.5"/><circle cx="6.5" cy="12" r="2.5"/><circle cx="17.5" cy="18.5" r="2.5"/><path d="M8.7 10.7l6.6-3.9M8.7 13.3l6.6 3.9"/>'),
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
  voz: sv('<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.8 11.5a6.2 6.2 0 0 0 12.4 0M12 17.7v2.8"/>'),
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
  lupa: sv('<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5M8 10.5h5M10.5 8v5"/>'),
  semZoom: sv('<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5M8 10.5h5"/>'),
  texto: sv('<path d="M5 7V5h14v2M12 5v14M9.5 19h5"/>'),
  // texto atrás da pessoa: a silhueta na frente da linha do texto
  pessoa: sv('<path d="M3 8.5h18" stroke-dasharray="2.2 2"/><circle cx="12" cy="9" r="3.1"/><path d="M5.8 20.5c.7-3.6 3.2-5.6 6.2-5.6s5.5 2 6.2 5.6"/>'),
  // o Fundo: a pessoa na frente de uma paisagem nova
  fundo: sv('<rect x="3" y="4" width="18" height="16" rx="2.6"/><path d="M3.5 14.2l4-3.6 2.8 2.4"/><circle cx="16.8" cy="8.2" r="1.4"/><circle cx="12.6" cy="12.2" r="2.3"/><path d="M8.3 19.8c.6-2.5 2.2-3.8 4.3-3.8s3.7 1.3 4.3 3.8"/>'),
  // texto que acompanha a pessoa: a mira
  alvo: sv('<circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/>'),
  // seleção em massa: a caixa tracejada; "tudo": as duas pontas do vídeo
  selecionar: sv('<rect x="3.5" y="5" width="17" height="14" rx="2.2" stroke-dasharray="3.2 2.6"/><path d="M8 12h8"/>'),
  // a tela Projetos: a casa
  montagem: sv('<rect x="3" y="4.5" width="18" height="15" rx="3"/><path d="M7.5 15.5v-3M10.5 15.5v-7M13.5 15.5v-5M16.5 15.5v-2"/>'),
  casa: sv('<path d="M4 10.8 12 4.5l8 6.3"/><path d="M6 9.5v9a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 18.5v-9"/><path d="M10 20v-5h4v5"/>'),
  tudo: sv('<path d="M3.5 12h17M7 8.5 3.5 12 7 15.5M17 8.5l3.5 3.5-3.5 3.5"/>'),
  // o ímã da linha do tempo: a agulha e as pontas grudam na batida da música
  ima: sv('<path d="M5 4v8a7 7 0 0 0 14 0V4h-4v8a3 3 0 0 1-6 0V4z"/><path d="M5 7.6h4M15 7.6h4"/>'),
  // um lugar da montagem: Trocar a mídia (as duas setas) e o Trecho do clipe (a janela na tira)
  trocar: sv('<path d="M4.5 8.5h14l-3.5-3.5M19.5 15.5h-14l3.5 3.5"/>'),
  formato: sv('<rect x="3" y="7" width="11" height="10" rx="1.6"/><rect x="15.5" y="4" width="5.5" height="16" rx="1.4"/>'),
  trecho: sv('<rect x="2.5" y="7" width="19" height="10" rx="1.6"/><rect x="8" y="4.5" width="7" height="15" rx="1.4" stroke-width="2.3"/>'),
};

/* ---------- catálogo de estilos e amostras: estilos.js ----------
 * Carregado antes deste. Os ids e nomes são o contrato com a skill
 * (preview_style.json). Cada opção aparece sobre um quadro do próprio vídeo. */
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
// o quadro do vídeo em px, com o lado menor 1080 (1080x1920 em pé, 1920x1080 deitado, 1080x1080
// quadrado): muda quando o vídeo carrega (loadedmetadata)
let FRAME_W = 1080;
let FRAME_H = 1920;
// os formatos de uma montagem (montagem.FORMATOS): em pé, deitado e quadrado
const FORMATOS = {
  '9:16': { nome: 'Em pé', uso: 'Reels, TikTok, Shorts', w: 9, h: 16, px: [1080, 1920] },
  '16:9': { nome: 'Deitado', uso: 'YouTube, TV', w: 16, h: 9, px: [1920, 1080] },
  '1:1': { nome: 'Quadrado', uso: 'Feed', w: 1, h: 1, px: [1080, 1080] },
};
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
 * frase padrão. */
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
// preferência de tela guardada no navegador (sem armazenamento, vale só nesta aba)
const lerPref = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const gravaPref = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } };

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
  cenasDraft: [],     // os efeitos do agente (cenas[] do edit-data.json), um bloco cada
  cenaSel: -1,
  zoomDraft: null,    // o zoom de cada tomada (camera.zooms, aberto um por tomada)
  zoomOrig: null,
  zoomSel: -1,
  destaques: { hook: null, numeros: [] }, // o gancho e os números, com o painel de Texto dos efeitos
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
  v0: 0,              // computador: o tempo na margem esquerda da linha do tempo (a vista rola sem mexer na agulha)
  tVisto: null,       // o tempo da última vez que a linha do tempo foi posta no lugar
  jcutOpen: lerPref('cutmind.jcutOpen') === '1', // faixas A1/A2 do J-cut abertas (lembrado)
  mudoUsuario: false, // o alto-falante da linha do play (só a prévia; não vai para o vídeo)
  midiaDur: {},       // duração de cada áudio de midia/, lida do arquivo
  audioMenu: false,   // Áudio tocado: a barra mostra Trilhas / Do celular / Melhorar voz
  melhorar: null,     // Melhorar voz no rascunho: {voz, fundo} ou {desligar: true}; null = não mexeu
  melhorarBase: 'null', // o que o vídeo tem (ou terá quando o agente aplicar o último Salvar)
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
  vel: { versao: 1, trechos: [] }, // a velocidade do vídeo final (velocidade.json): trechos no relógio do final.mp4
  velBase: '',        // os trechos como estavam ao abrir ou no último Salvar
  faixa: null,        // a seleção em massa na vista Final: {a, b} no relógio do final.mp4 (todas as faixas)
  montagem: null,     // a montagem na batida do edl.json (lugares, mídias), quando o projeto é uma montagem
  montMidias: null,   // o que o Trocar oferece (/api/montagem/midias): [{midia, nome, tipo, duracao}]
  batidas: {},        // arquivo de midia/ → a grade de batida dele ({estado, batidas, fortes, bpm, confianca})
  grade: [],          // as batidas das músicas no tempo da linha do tempo: [{t, forte, it}], em ordem
  ima: lerPref('cutmind.ima') !== '0', // ímã ligado: agulha e pontas grudam na batida (lembrado)
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

// ---------- geometria do corte (J-cut, rascunho, render) ----------
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
// o contrário, só para o que ainda está no lugar de origem (vídeo final e faixas dele). Quem
// converte muitos tempos de uma vez (as batidas) passa os dois layouts prontos
function renderedToDraft(t, dl = draftLayout(), rl = renderedLayout()) {
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
// os pedaços da faixa de legenda; `i0`/`n` são as palavras do captions.json (o que o arraste
// desloca) e `ms` o começo como está no arquivo
function groupCaptions(caps) {
  const lines = [];
  let cur = [];
  caps.forEach((w, i) => {
    cur.push(i);
    if (cur.length >= 3 || /[.,!?…]$/.test(w.text)) { lines.push(cur); cur = []; }
  });
  if (cur.length) lines.push(cur);
  return lines.map((ix) => ({
    text: ix.map((i) => caps[i].text.replace(/[.,!?…]+$/, '')).join(' '),
    start: caps[ix[0]].startMs / 1000,
    end: caps[ix[ix.length - 1]].endMs / 1000,
    i0: ix[0], n: ix.length, ms: caps[ix[0]].startMs,
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
  // o número que conta (numeros[]: at → end) anda e apara como as palavras
  (d.numeros || []).forEach((n, i) => list.push({ kind: 'numero', label: `${n.prefixo || ''}${n.valor}${n.sufixo || ''}`, start: +n.at, end: +(n.end ?? +n.at + 2.4), ref: i }));
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
  S.insSel = -1;
  buildCenasDraft(d);
  buildDestaques(d);
  buildLegenda(d);
}
const isText = (c) => c.kind === 'hook' || c.kind === 'word' || c.kind === 'numero';
// o bloco andou ou foi aparado desde o último vídeo do agente (ou o último Salvar)
const insMudou = (c) => c.start !== c.orig.start || c.end !== c.orig.end;
const insertsDirty = () => S.insertsDraft.some(insMudou);

// ---------- montagem na batida: cada tomada é um lugar ----------
/* O agente monta (montagem.py) e cada tomada é um lugar com a duração das batidas dele: aparar,
 * dividir, mover e excluir sairiam da batida, então o editor avisa em vez de agir. O que muda é a
 * mídia (Trocar) e, num clipe, que parte dele entra (Trecho): `r.troca = {midia, nome, de}`, por
 * salvar até o agente refazer o lugar (`montagem.py aplicar`). */
const emLugar = (r) => !!(S.montagem && r && r.vaga != null);
const lugarDe = (r) => (S.montagem && r ? S.montagem.lugares.find((lg) => lg.vaga === r.vaga) : null) || null;
const nomeArq = (p) => String(p || '').split(/[\\/]/).pop();
const trocaKey = (r) => (r.troca ? `${r.troca.midia || ''}|${r.troca.de ?? ''}|${'enq' in r.troca ? JSON.stringify(r.troca.enq) : ''}` : '');
const opcaoDe = (midia) => (S.montMidias || []).find((m) => m.midia === midia) || null;
// a mídia e o trecho que o lugar vai ter: o pedido por salvar, ou o que está no vídeo
function lugarAgora(r) {
  const lg = lugarDe(r) || {};
  const t = r.troca || {};
  const midia = t.midia || lg.midia || '';
  return { midia, nome: nomeArq(midia), de: t.de != null ? t.de : t.midia ? 0 : +(lg.de || 0), enq: enqDoLugar(r) };
}
// o enquadramento à mão do lugar ({escala, x, y}) ou null (o automático): o pedido por salvar vale; mídia
// nova ou formato novo voltam ao automático (a escala e o centro eram daquela mídia naquele quadro)
function enqDoLugar(r) {
  const t = r.troca || {};
  if ('enq' in t) return t.enq;
  if (t.midia || formatoPrevia()) return null;
  return (lugarDe(r) || {}).enquadre || null;
}
const mesmoEnq = (a, b) => JSON.stringify(a || null) === JSON.stringify(b || null);
// o que vai no Salvar para um lugar; o lugar que voltou a ser como está diz isso (por cima de um Salvar anterior)
function pedidoDoLugar(r) {
  const lg = lugarDe(r) || {};
  const a = lugarAgora(r);
  const p = { vaga: r.vaga };
  if (a.midia !== lg.midia) p.midia = a.midia;
  if (p.midia || Math.abs(a.de - +(lg.de || 0)) > 0.0005) p.de = +a.de.toFixed(3);
  if (r.troca && 'enq' in r.troca && !mesmoEnq(a.enq, lg.enquadre)) p.enquadre = a.enq;
  if (p.midia == null && p.de == null && !('enquadre' in p)) {
    p.midia = lg.midia;
    p.de = +(+(lg.de || 0)).toFixed(3);
    if (r.troca && 'enq' in r.troca) p.enquadre = lg.enquadre || null;
  }
  return p;
}
function avisaLugar() {
  toast('Numa montagem, a duração de cada lugar segue a batida da música. Troque a mídia ou o trecho.', 3200);
}
async function carregaMontMidias() {
  if (!ehMontagem()) { S.montMidias = null; return; } // a Nova montagem também: o painel mostra o que chegou
  try {
    const r = await fetch('/api/montagem/midias');
    if (r.ok) S.montMidias = (await r.json()).opcoes || [];
  } catch (e) { /* sem a lista: o Trocar diz que está carregando */ }
}
const quadroDaMidia = (midia, t, h) => `/gen/montagem-quadro?midia=${encodeURIComponent(midia)}&t=${(+t || 0).toFixed(2)}&h=${h}`;

// ---------- o que mudou e ainda não foi salvo ----------
// comparado com o último corte recebido (ou o último Salvar): aparada, nova, excluída, ordem, volume
// (`tk`, a troca de um lugar da montagem, conta à parte: não muda o corte)
const baseOf = (draft) => draft.map((r) => ({ uid: r.uid, start: r.start, end: r.end, vol: r.vol, vel: r.vel, ck: curvaKey(r), tk: trocaKey(r) }));
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
// os lugares da montagem trocados depois do último Salvar
const lugaresMudados = () => {
  if (!S.montagem) return [];
  const base = new Map(S.base.map((b) => [b.uid, b]));
  return S.draft.filter((r) => r.vaga != null && trocaKey(r) !== ((base.get(r.uid) || {}).tk || ''));
};
// o formato escolhido aqui e ainda não salvo (o salvo que o agente não refez não conta)
const formatoMudou = () => !!(S.montagem && S.formato && S.formato !== (S.formatoPendente || S.formatoAtual));
function dirtyCount() {
  return (formatoMudou() ? 1 : 0) + diffBase() + S.notes.length + S.insertsDraft.filter(insMudou).length + (camadasDirty() ? 1 : 0) + (efeitosDirty() ? 1 : 0)
    + S.cenasDraft.filter(cenaMudou).length + zoomMudados() + destaquesMudados().length + (legendaMudou() ? 1 : 0)
    + (velDirty() ? 1 : 0) + (melhorarDirty() ? 1 : 0) + lugaresMudados().length;
}
const isChanged = (r) => {
  const b = S.base.find((x) => x.uid === r.uid);
  return !b || b.start !== r.start || b.end !== r.end || b.vol !== r.vol || b.vel !== r.vel || b.ck !== curvaKey(r)
    || (b.tk || '') !== trocaKey(r);
};
function refreshHeader() {
  const n = dirtyCount();
  const hasVideo = S.videoDuration > 0;
  // um botão principal no canto: Salvar quando há ajuste; sem ajuste, Baixar
  $('btnSave').classList.toggle('hidden', n === 0);
  $('btnDiscard').classList.toggle('hidden', n === 0);
  $('btnDownload').classList.toggle('hidden', n > 0 || !hasVideo);
  $('dirtyCount').textContent = n;
  $('sentPill').classList.toggle('hidden', !(S.savedPending && n === 0));
  $('modeLabel').textContent = S.view === 'final' ? 'Final' : 'Corte';
  // com trechos acelerados, a duração da entrega ao lado da do final
  const entregue = S.view === 'final' && S.vel.trechos.length ? duracaoEntregue() : null;
  $('projectSub').textContent = !hasVideo ? '' : entregue != null ? `${fmtShort(totalT())} → ${fmtShort(entregue)}` : fmtShort(totalT());
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
    cenas: S.cenasDraft.filter((c) => !c.nova).map(cenaValor), // os do agente, pela posição
    cenasNovas: S.cenasDraft.filter((c) => c.nova).map(copiaNova), // os Fundos criados aqui, inteiros
    destaques: listaDestaques().map(cenaValor),
    cenaSel: S.cenaSel,
    zooms: S.zoomDraft ? [...S.zoomDraft] : null,
    zoomSel: S.zoomSel,
    legenda: S.legenda ? JSON.parse(JSON.stringify(S.legenda)) : null,
    legSel: S.legSel,
    vel: JSON.parse(JSON.stringify(S.vel)),
    faixa: S.faixa ? { ...S.faixa } : null,
    melhorar: S.melhorar ? { ...S.melhorar } : null,
    formato: S.formato,
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
  const doAgente = S.cenasDraft.filter((c) => !c.nova);
  if (s.cenas && s.cenas.length === doAgente.length) s.cenas.forEach((v, k) => Object.assign(doAgente[k], cenaValor(v)));
  if (s.cenasNovas) S.cenasDraft = [...doAgente, ...s.cenasNovas.map(copiaNova)]; // os novos vêm sempre depois
  const dl = listaDestaques();
  if (s.destaques && s.destaques.length === dl.length) { s.destaques.forEach((v, k) => Object.assign(dl[k], cenaValor(v))); rotulosDestaques(); }
  S.cenaSel = s.cenaSel != null && s.cenaSel < S.cenasDraft.length ? s.cenaSel : -1;
  if (s.zooms && S.zoomDraft && s.zooms.length === S.zoomDraft.length) S.zoomDraft = [...s.zooms];
  S.zoomSel = s.zoomSel != null && S.zoomDraft && s.zoomSel < S.zoomDraft.length ? s.zoomSel : -1;
  if (S.legenda && s.legenda) S.legenda = s.legenda;
  S.legSel = !!(S.legenda && s.legSel);
  if (s.vel) S.vel = s.vel;
  if ('melhorar' in s) S.melhorar = s.melhorar;
  if (s.formato && s.formato !== S.formato) { S.formato = s.formato; aplicaQuadro(); }
  S.faixa = s.faixa && S.view === 'final' ? s.faixa : null;
  drawCenaBox();
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
// no computador o vídeo vem do computador; no celular, da galeria (o texto do HTML)
if (isDesk()) $('emptyText').textContent = 'Escolha um vídeo do computador. O corte começa assim que ele chegar.';
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
    // outro projeto aberto (aqui na tela Projetos, ou no celular): sem ajuste pendente, recarrega
    const pid = data.projeto && data.projeto.id;
    if (pid && S.projetoId && pid !== S.projetoId) {
      if (dirtyCount() === 0) { location.reload(); return; }
      avisaTroca(pid);
      setTimeout(poll, 2000);
      return;
    }
    if (pid) S.projetoId = pid;
    S.lastData = data; // o Descartar volta a ela
    const sig = assinatura(data);
    if (sig !== S.lastSig) {
      // com Filtros/Transições aberto também espera: recarregar apagava a prévia tocando e a
      // escolha, e o "Usar" seguinte não fazia nada (o agente regravando o final a cada 2 s).
      // Com o Fundo aberto, a lista de efeitos nova trocaria o item que o Pronto vai mudar
      if (dirtyCount() === 0 && !S.styling && !fxAberto() && !vozAberto() && !FU.aberto) {
        S.lastSig = sig;
        await applyState(data);
      } else if (!S.newStateWarned) { // uma vez só, até a versão nova entrar
        S.newStateWarned = true;
        toast(S.styling ? 'Chegou uma versão nova: ela aparece quando você fechar o Estilo.'
          : fxAberto() || vozAberto() || FU.aberto ? 'Chegou uma versão nova: ela aparece quando você fechar este painel.'
          : isDesk() ? 'Chegou uma versão nova do agente. Salve ou descarte seus ajustes para ver.'
            : 'Chegou uma versão nova — salve seus ajustes para ver', 4500);
      }
    }
  } catch (e) { /* servidor reiniciando: continua tentando */ }
  setTimeout(poll, 2000);
}

// o que, mudando, traz o editor para a versão nova do agente (com o envio ainda pendente ou não)
const assinatura = (data) => JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration, !!data.hasPendingEdits]);
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
    curva: r.curva && Array.isArray(r.curva.pontos) ? { nome: r.curva.nome || 'personalizar', pontos: r.curva.pontos.map((p) => [+p[0], +p[1]]) } : null,
    ...(r.vaga != null ? { vaga: +r.vaga } : {}) })); // o número do lugar, numa montagem na batida
  // a montagem na batida (montagem.py): os lugares, de onde cada um saiu e as mídias que ela usou
  S.montagem = (data.edl && data.edl.montagem && Array.isArray(data.edl.montagem.lugares)) ? data.edl.montagem : null;
  S.formatoAtual = (S.montagem && FORMATOS[S.montagem.formato] && S.montagem.formato) || '9:16';
  S.formatoPendente = (S.montagem && FORMATOS[data.formatoPendente] && data.formatoPendente) || null;
  S.formato = S.formatoPendente || S.formatoAtual;
  aplicaQuadro();
  carregaMontMidias().then(() => { if (S.selected >= 0) renderToolbar(); }); // o Trecho precisa saber quem é clipe
  S.draft = S.rendered.map((r, i) => ({ ...r, uid: `o${i}`, from: i, orig: { start: r.start, end: r.end } }));
  // os lugares já salvos que o agente ainda não refez seguem marcados com a mídia nova (não contam
  // como por salvar); quando o edl.json passa a ter a mídia e o trecho pedidos, a marca sai sozinha
  for (const p of (S.montagem && data.montagemPendente) || []) {
    const r = S.draft.find((x) => x.vaga === p.vaga);
    const lg = r && lugarDe(r);
    if (!lg) continue;
    const t = {};
    if (p.midia && p.midia !== lg.midia) { t.midia = p.midia; t.nome = nomeArq(p.midia); }
    if (p.de != null && (t.midia || Math.abs(p.de - +(lg.de || 0)) > 0.0005)) t.de = +p.de;
    if ('enquadre' in p && !mesmoEnq(p.enquadre, lg.enquadre)) t.enq = p.enquadre;
    if (t.midia || t.de != null || 'enq' in t) r.troca = t;
  }
  S.base = baseOf(S.draft);
  S.melhorar = null;
  vozCarregaInfo().then(() => { renderTimeline(); refreshHeader(); });
  S.selected = -1;
  forgetHistory(); // corte novo: as fotos antigas são de outras tomadas

  S.style = { ...defaultStyle(), ...(S.state.style || {}) };
  S.style.elements = { ...defaultStyle().elements, ...((S.state.style || {}).elements || {}) };
  if (!/^#[0-9a-f]{6}$/i.test(S.style.accent || '')) S.style.accent = normHex(S.style.accentName) || ACCENT_DEFAULT;

  const hasVideo = S.videoDuration > 0;
  $('empty').classList.toggle('hidden', hasVideo);
  // ainda sem corte, mas o agente já trabalha em vídeos do computador: a tela mostra o
  // que ele está fazendo, não o convite para enviar um vídeo do celular
  const agente = !hasVideo && !S.locked && !!S.state.message && Object.keys(S.state.sourceDurations || {}).length > 0;
  if (agente !== !!S.emptyAgente) {
    S.emptyAgente = agente;
    $('btnEmptyUpload').classList.toggle('hidden', agente);
    $('emptyAlt').classList.toggle('hidden', agente);
    $('emptyIco').innerHTML = agente ? ICON.corte : ICON.enviar;
    if (!agente) { $('emptyTitle').textContent = EMPTY_TEXTS.title; $('emptyText').textContent = EMPTY_TEXTS.text; }
  }
  if (agente) { $('emptyTitle').textContent = 'O agente está editando'; $('emptyText').textContent = S.state.message; }
  S.montagemNova = data.montagemNova || null; // o Montar do painel, salvo e ainda não feito pelo agente
  vazioDaMontagem();
  if (!hasFinal() && S.view === 'final') S.view = 'corte';

  S.captions = [];
  S.editData = null;
  S.insertsDraft = [];
  S.cenasDraft = []; S.cenaSel = -1;
  S.destaques = { hook: null, numeros: [] };
  S.zoomDraft = null; S.zoomOrig = null; S.zoomSel = -1;
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
  S.insSel = -1;
  S.fxTeste = null;
  S.faixa = null;
  drawCenaBox();
  await loadCamadas();
  await loadRastreio();
  await loadEfeitos();
  await loadVelocidade();
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
  // a Nova montagem abre já no painel (uma vez por carga da página)
  if (S.state.montagem && !hasVideo && !S.montagemNova && !S.locked && !MT.autoAberto) {
    MT.autoAberto = true;
    abreMontagem();
  }
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
  aplicaQuadro();
  if (S.draft.length) renderTimeline(); // a largura dos quadros da tira depende da proporção
});
// o quadro do player: o do vídeo, ou, na prévia de outro formato da montagem, o do formato escolhido
function aplicaQuadro() {
  let w, h;
  if (formatoPrevia()) [w, h] = FORMATOS[S.formato].px;
  else if (video.videoWidth && video.videoHeight) {
    const menor = Math.min(video.videoWidth, video.videoHeight);
    w = Math.round((1080 * video.videoWidth) / menor);
    h = Math.round((1080 * video.videoHeight) / menor);
  } else return;
  FRAME_W = w;
  FRAME_H = h;
  player.style.setProperty('--ar', `${w} / ${h}`);
  player.style.setProperty('--arn', (w / h).toFixed(6));
  // a coluna da prévia ao lado da linha do tempo tem a largura do quadro na altura da tela
  const raiz = document.documentElement, emPe = w < h;
  raiz.style.setProperty('--arn-v', (w / h).toFixed(6));
  if (raiz.classList.contains('em-pe') !== emPe) {
    raiz.classList.toggle('em-pe', emPe);
    if (S.fitted) fitZoom(); // a linha do tempo mudou de largura
  }
  if (formatoPrevia()) preCarregaQuadros(); // o laço do player (syncLayers) desenha a cada quadro
}

// ---------- linha do tempo ----------
const half = () => timeline.clientWidth / 2;
const clampT = (t) => Math.max(0, Math.min(t, totalT()));
/* No computador a agulha ANDA, como no CapCut desktop: a vista tem rolagem própria (`S.v0`,
 * o tempo na margem esquerda) e a agulha é desenhada no tempo atual. No celular ela fica
 * parada no centro e a linha do tempo corre por baixo dela. */
const DESK_MARGEM = 120; // à esquerda, debaixo do tempo e dos cabeçalhos das faixas
const agulhaAnda = () => isDesk();
const visivel = () => Math.max(1, (timeline.clientWidth - DESK_MARGEM - 24) / S.pps); // segundos à vista
// o x do tempo 0 numa largura w (a da linha do tempo ou a de um canvas dela)
const origemEm = (w) => (agulhaAnda() ? DESK_MARGEM - S.v0 * S.pps : w / 2 - S.t * S.pps);
const xDaAgulha = () => DESK_MARGEM + (S.t - S.v0) * S.pps;
// dá para rolar até o fim do vídeo ficar no meio da vista (o "+" de importar aparece)
function prendeVista() { S.v0 = Math.max(0, Math.min(S.v0, Math.max(0, totalT() - visivel() * 0.5))); }
// a agulha saiu da vista: a vista vai até ela, com um respiro à esquerda
function seguirAgulha() {
  const x = xDaAgulha();
  if (x < DESK_MARGEM || x > timeline.clientWidth - 24) S.v0 = S.t - visivel() * 0.1;
}
function levaAgulha(x, rapido) {
  x = Math.max(DESK_MARGEM, Math.min(x, timeline.clientWidth - 1));
  S.t = clampT(imaPonto(S.v0 + (x - DESK_MARGEM) / S.pps)); // com o ímã, gruda na batida
  positionTimeline();
  scheduleSeek(rapido);
}
const xNaLinha = (e) => e.clientX - timeline.getBoundingClientRect().left;
function fitZoom() {
  const w = timeline.clientWidth || 360;
  const total = Math.max(totalT(), 1);
  S.minPps = Math.max(1.5, (agulhaAnda() ? w - DESK_MARGEM - 40 : w * 0.9) / total);
  // ~14 s na largura da tela: dá para ver as miniaturas e acertar a alça com o dedo; no
  // computador a linha do tempo é larga e o mouse é preciso: ~40 s
  S.pps = Math.min(S.maxPps, Math.max(S.minPps, w / (isDesk() ? 40 : 14)));
  S.v0 = 0;
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
    // a velocidade do vídeo final (seleção em massa): vale para todas as faixas embaixo dela
    { id: 'vel', h: 18, show: fin && !S.posMode && S.vel.trechos.length > 0 },
    { id: 'caps', h: 18, show: fin && S.captions.length > 0 },
    { id: 'text', h: 18, show: fin && hasTxt },
    { id: 'ins', h: 18, show: fin && hasIns },
    // os efeitos que o agente pôs (cenas[]): cada um liga, desliga, troca o texto e tem o bloco arrastado no vídeo
    { id: 'cenas', h: 20, show: fin && S.cenasDraft.length > 0 },
    // os textos ficam acima das imagens, como no vídeo final; a mais nova fica no alto, como no editor do PC
    ...fx.filter((f) => f.tipo === 'texto').reverse().map(layer),
    ...fx.filter((f) => f.tipo === 'imagem').reverse().map(layer),
    // filtros, transições e ajustes valem para o corte: no Final já estão no vídeo. O ajuste
    // tem faixa própria, como no CapCut: na mesma tomada de um filtro, os dois ficariam um em cima do outro
    { id: 'fx', h: 22, show: !fin && !S.posMode && S.efeitos.itens.some((it) => it.tipo !== 'ajuste') },
    { id: 'aj', h: 22, show: !fin && !S.posMode && S.efeitos.itens.some((it) => it.tipo === 'ajuste') },
    // o zoom de cada tomada no vídeo final, colado em cima dela
    { id: 'zoom', h: 16, show: fin && !!S.zoomDraft },
    { id: 'video', h: VIDEO_TRACK_H, show: true },
    { id: 'audio', h: 30, show: true },
    // J-cut: a voz de cada tomada em duas faixas alternadas, com a sobra que entra antes da imagem
    { id: 'a1', h: 18, show: jcutAberto() },
    { id: 'a2', h: 18, show: jcutAberto() },
    // a trilha da Fase 2 (`soundtrack` do edit-data.json): só leitura, o vídeo inteiro
    { id: 'trilha', h: 18, show: fin && !S.posMode && !!trilhaF2() },
    ...fx.filter((f) => f.tipo === 'audio').map(layer),
  ].filter((t) => t.show);
}
const temJcut = () => !!(S.jcut && S.jcut.length);
const jcutAberto = () => S.jcutOpen && temJcut() && !S.posMode;
const trilhaF2 = () => { const st = S.editData && S.editData.soundtrack; return st && st.enabled ? st : null; };
// a linha do tempo cresce com as camadas até um teto; acima dele as faixas encolhem
const TL_MIN = 178, TL_MAX = 292;

const VIDEO_TRACK_H = 56;
const MOVE_TILE = 60; // largura de cada tomada enquanto se move uma
const tileWidth = () => {
  const ar = video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 9 / 16;
  return Math.max(24, Math.round((VIDEO_TRACK_H * (S.kFaixa || 1) - 3) * ar));
};

let lanes = []; // elementos que andam juntos sob a agulha
function renderTimeline() {
  tracksEl.innerHTML = '';
  lanes = [];
  S.grade = batidasNaLinha(); // as marcas e o ímã andam com a música (ela pode ter sido arrastada)
  syncIma();
  const width = `${Math.max(totalT(), 0.1) * S.pps}px`;
  const plan = trackPlan();
  const vaos = 6 * (plan.length - 1);
  /* lado a lado: a linha do tempo fica com a altura que a prévia liberou, e as faixas crescem
     (até 1,6x) em vez de sobrar vão: menos apertadas e mais fáceis de pegar com o mouse */
  const soma = plan.reduce((a, t) => a + t.h, 0);
  S.kFaixa = ladoAtivo() ? Math.min(1.6, Math.max(1, (innerHeight * 0.47 - 36 - vaos) / soma)) : 1;
  for (const t of plan) t.h = Math.round(t.h * S.kFaixa);
  // régua (30) + respiro (6) + faixas e os vãos entre elas
  const need = 36 + plan.reduce((a, t) => a + t.h, 0) + vaos;
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
      if (temJcut() && !S.posMode) jcutHead(track);
      vozEtiqueta(track);
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
    else if (tr.id === 'a1' || tr.id === 'a2') renderJcutLane(track, lane, tr.id === 'a1' ? 0 : 1);
    else if (tr.id === 'trilha') renderTrilhaF2(lane);
    else if (tr.id === 'vel') renderVelTrack(lane);
    else if (tr.id === 'cenas') renderCenas(lane);
    else if (tr.id === 'zoom') renderZoom(lane);
    else if (tr.id === 'caps') {
      const estilo = legendaEstiloMudou();
      S.captions.forEach((c, k) => {
        // o pedaço arrastado anda; marcado (por salvar) quando anda desde o último Salvar, e todos
        // quando o estilo mudou
        const dl = deslocCap(c), dl0 = (S.legendaOrig && S.legendaOrig.tempos && S.legendaOrig.tempos[c.i0]) || 0;
        const a = renderedToDraft(c.start + dl), b = renderedToDraft(c.end + dl);
        const chip = el('div', `chip cap${S.legSel ? ' sel' : ''}${estilo || dl !== dl0 ? ' dirty' : ''}`, lane);
        chip.dataset.k = k;
        chip.style.left = `${a * S.pps}px`;
        chip.style.width = `${Math.max((b - a) * S.pps, 4)}px`;
        chip.textContent = c.text;
      });
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
  renderFaixa(); // a seleção em massa, por cima de todas as faixas
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
    // um lugar da montagem: o número dele e a mídia que ele tem (a trocada, por salvar, com a miniatura)
    const lugar = emLugar(r) ? lugarAgora(r) : null;
    if (lugar && r.troca && r.troca.midia && !movendo) {
      const im = el('img', 't-troca', c);
      im.src = quadroDaMidia(r.troca.midia, (r.troca.de || 0) + 0.1, 120); // o começo do trecho que entra
      im.alt = ''; im.draggable = false;
    }
    if (lugar) { c.classList.add('lugar'); el('span', 't-vaga', c).textContent = r.vaga; }
    el('div', 't-label', c).textContent = lugar ? lugar.nome : r.beat || r.source || `tomada ${i + 1}`;
    if (r.troca) c.classList.add('trocado');
    if ((r.vol !== 1 || r.vel !== 1 || r.curva) && !movendo) {
      const tags = el('div', 't-tags', c);
      if (r.vol !== 1) el('span', 't-vol', tags).innerHTML = `${ICON.vol}${Math.round(r.vol * 100)}%`;
      if (r.curva) el('span', 't-vel', tags).textContent = nomeCurva(r.curva.nome);
      else if (r.vel !== 1) el('span', 't-vel', tags).textContent = fmtVel(r.vel);
    }
    if (editable && i === S.selected && !lugar) { // o lugar não apara: a duração é a da batida
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

/* Faixas A1/A2 (como na edição do PC antiga): o som de cada tomada, alternando entre as
 * duas, onde ele toca no corte. O tracejado no começo é o J-cut, a voz que já entra
 * enquanto a tomada anterior ainda está na tela. Sai do rascunho: anda com as aparas. */
function jcutHead(track) {
  const th = el('div', 'th', track);
  const b = el('button', `th-b jcut${S.jcutOpen ? ' on' : ''}`, th);
  b.type = 'button';
  b.dataset.act = 'jcut';
  b.innerHTML = ICON.seta;
  const dica = S.jcutOpen ? 'Esconder as faixas A1 e A2 do J-cut' : 'Mostrar as faixas A1 e A2 do J-cut (a voz que entra antes da imagem)';
  b.setAttribute('aria-label', dica);
  b.setAttribute('aria-expanded', String(S.jcutOpen));
  b.title = dica;
}
function renderJcutLane(track, lane, par) {
  el('div', 'th th-tag', track).textContent = par ? 'A2' : 'A1';
  const fps = S.fps || 30;
  draftLayout().forEach((r, i) => {
    if (i % 2 !== par || r.adur <= 0) return;
    const b = el('div', 'ablock', lane);
    b.style.left = `${r.aout * S.pps}px`;
    b.style.width = `${Math.max(r.adur * S.pps, 6)}px`;
    if (r.lead > 1e-6) el('div', 'ablock-lead', b).style.width = `${r.lead * S.pps}px`;
    const nome = r.beat || r.source || `tomada ${i + 1}`;
    el('span', 'ablock-label', b).textContent = nome;
    const tf = (r.orig && S.jcut[r.from] && S.jcut[r.from].tail_trim_frames) || 0;
    let dica = `${nome}\náudio ${r.adur.toFixed(2)} s`;
    if (r.lead > 1e-6) dica += `\nJ-cut: a voz entra ${Math.round(r.lead * fps)} quadros (${Math.round(r.lead * 1000)} ms) antes da imagem`;
    if (tf) dica += `\ncauda aparada: ${tf} quadros`;
    b.title = dica;
  });
}
function renderTrilhaF2(lane) {
  const st = trilhaF2();
  const fim = Math.min(totalT(), renderedToDraft(S.editData.durationSec || S.videoDuration || totalT()));
  const chip = el('div', 'chip st', lane);
  chip.style.left = '0px';
  chip.style.width = `${Math.max(fim * S.pps, 10)}px`;
  el('span', 'l-ico', chip).innerHTML = ICON.audio;
  const nome = String(st.file || 'trilha.mp3').split('/').pop();
  el('span', 'l-name', chip).textContent = st.volume != null ? `${nome} · ${Math.round(st.volume * 100)}%` : nome;
  chip.title = 'Trilha da Fase 2. Para trocar, mudar o volume ou tirar, peça ao agente.';
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
  if (agulhaAnda()) {
    // a agulha andou (tocando, teclado, clique): se saiu da vista, a vista vai até ela.
    // Rolar a vista não mexe no tempo, então não a traz de volta.
    if (S.t !== S.tVisto && G.mode !== 'scrub') seguirAgulha();
    prendeVista();
  }
  S.tVisto = S.t;
  const x0 = origemEm(timeline.clientWidth);
  const ag = $('needle');
  if (agulhaAnda()) {
    const xa = x0 + S.t * S.pps;
    ag.style.left = `${xa}px`;
    ag.style.visibility = xa < DESK_MARGEM - 1 || xa > timeline.clientWidth ? 'hidden' : '';
  } else if (ag.style.left) { ag.style.left = ''; ag.style.visibility = ''; }
  const tf = `translate3d(${x0.toFixed(2)}px,0,0)`;
  // movendo uma tomada, a faixa de vídeo (em quadrados) anda pelo próprio deslocamento
  const mv = G.mode === 'move' && G.mv ? `translate3d(${G.mv.off.toFixed(2)}px,0,0)` : null;
  for (const l of lanes) l.style.transform = mv && l.dataset.track === 'video' ? mv : tf;
  drawRuler();
  drawWave();
  $('tNow').textContent = fmt(S.t);
  $('tTotal').textContent = fmt(totalT());
  drawFrase(); // no "Posição das frases": a frase debaixo da agulha (só refaz quando muda)
  if (S.cenaSel >= 0 || S.insSel >= 0) drawCenaBox(); // a moldura do escolhido só aparece dentro dele
}

function drawRuler() {
  const ctx = rulerCv.getContext('2d');
  const w = rulerCv.clientWidth, h = rulerCv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  const x0 = origemEm(w);
  const t0 = -x0 / S.pps, t1 = (w - x0) / S.pps;
  const steps = [0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const step = steps.find((s) => s * S.pps >= 52) || 300;
  ctx.font = '600 9.5px Montserrat, system-ui, sans-serif';
  ctx.fillStyle = 'rgba(166,166,166,0.9)';
  ctx.strokeStyle = 'rgba(255,255,255,0.16)';
  ctx.lineWidth = 1;
  const end = totalT();
  for (let t = Math.max(0, Math.floor(t0 / step) * step); t <= Math.min(t1, end); t += step) {
    const x = Math.round(x0 + t * S.pps) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, h - 7); ctx.lineTo(x, h); ctx.stroke();
    // com zoom alto as marcas caem no meio do segundo: elas mostram a fração (.25, .5, .75),
    // senão a régua repetiria "0:00 0:00 0:00 0:01"
    const inteiro = Math.abs(t - Math.round(t)) < 1e-6;
    ctx.fillText(inteiro ? fmtShort(Math.round(t)) : `.${String(Math.round((t % 1) * 100)).replace(/0$/, '')}`, x + 3, h - 8);
    for (let m = 1; m < 4; m++) {
      const tm = t + (m * step) / 4;
      if (tm > end) break;
      const xm = Math.round(x0 + tm * S.pps) + 0.5;
      ctx.beginPath(); ctx.moveTo(xm, h - 3.5); ctx.lineTo(xm, h); ctx.stroke();
    }
  }
  drawBatidasRegua(ctx, x0, t0, t1, h);
}
/* As batidas da música na régua: um ponto em cada uma, maior e laranja no tempo forte. Com o zoom
 * baixo, quando ficariam a menos de 5 px umas das outras, só os tempos fortes; e nem eles, se
 * também colarem. */
function drawBatidasRegua(ctx, x0, t0, t1, h) {
  const grade = S.grade;
  if (!grade.length) return;
  const passo = grade.length > 1 ? ((grade[grade.length - 1].t - grade[0].t) / (grade.length - 1)) * S.pps : Infinity;
  if (passo * 4 < 5) return;
  const soFortes = passo < 5;
  for (const g of grade) {
    if (g.t < t0 - 0.1) continue;
    if (g.t > t1 + 0.1) break;
    if (soFortes && !g.forte) continue;
    ctx.fillStyle = g.forte ? '#f87000' : 'rgba(255,255,255,0.55)';
    ctx.beginPath();
    ctx.arc(x0 + g.t * S.pps, h - 3, g.forte ? 2.4 : 1.5, 0, Math.PI * 2);
    ctx.fill();
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
  const x0 = origemEm(w);
  const xa = Math.max(0, x0), xb = Math.min(w, x0 + end * S.pps);
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(xa, 1, Math.max(0, xb - xa), h - 2, 4) : ctx.rect(xa, 1, Math.max(0, xb - xa), h - 2);
  ctx.fill();
  if (!S.wave) return;
  const mid = h / 2;
  ctx.fillStyle = 'rgba(214,214,214,0.6)';
  const pps = S.wave.peaksPerSec;
  for (let px = Math.floor(xa); px < xb; px++) {
    const tDraft = (px - x0) / S.pps;
    const idx = Math.floor(draftToRendered(tDraft) * pps);
    if (idx < 0 || idx >= S.wave.max.length) continue;
    const hi = (S.wave.max[idx] / 100) * (mid - 2);
    const lo = (S.wave.min[idx] / 100) * (mid - 2);
    ctx.fillRect(px, mid - hi, 1, Math.max(1, hi - lo));
  }
}

function setZoom(pps, ancora) {
  let tA = null, xA = 0;
  if (agulhaAnda()) {
    const xa = xDaAgulha();
    xA = ancora != null ? ancora : (xa >= DESK_MARGEM && xa <= timeline.clientWidth ? xa : DESK_MARGEM);
    tA = S.v0 + (xA - DESK_MARGEM) / S.pps;
  }
  S.pps = Math.min(S.maxPps, Math.max(S.minPps, pps));
  if (tA != null) { S.v0 = tA - (xA - DESK_MARGEM) / S.pps; prendeVista(); }
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
$('zoomFit').addEventListener('click', () => { S.v0 = 0; setZoom(S.minPps, DESK_MARGEM); });
$('btnIma').innerHTML = `${ICON.ima}<span>Ímã</span>`;
$('btnIma').addEventListener('click', alternaIma);
syncIma();

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
    if (G.mode === 'move' || ARRASTES.includes(G.mode)) return; // movendo uma tomada, camada, bloco ou ponta da seleção, o segundo dedo não vira pinça
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
  // as pontas laranja da seleção em massa: puxar ajusta o trecho
  const fh = e.target.closest('.fh');
  if (fh && S.faixa) {
    G.mode = 'faixa-borda';
    G.fb = { borda: fh.dataset.borda };
    video.pause();
    G.ultX = e.clientX;
    bordaRola();
    return;
  }
  const lh = e.target.closest('.lh');
  if (lh && lh.closest('.chip.f2')) { if (startInsDrag(e.clientX, 'trim', lh.dataset.side)) return; }
  else if (lh && startLayerDrag(e.clientX, 'trim', lh.dataset.side)) return;
  if (agulhaAnda() && G.pts.size === 1 && e.target === rulerCv) {
    G.mode = 'scrub'; // a régua: clicar leva a agulha, arrastar passa o vídeo
    video.pause();
    levaAgulha(xNaLinha(e), true);
    return;
  }
  G.mode = 'pan';
  G.x0 = e.clientX; G.t0 = S.t; G.moved = false; G.v00 = S.v0;
  // computador: a própria agulha, por cima das faixas, é agarrada só se ARRASTAR; o clique
  // parado continua escolhendo a tomada (ou o bloco) que está debaixo dela
  G.agulha = agulhaAnda() && G.pts.size === 1 && Math.abs(xNaLinha(e) - xDaAgulha()) <= 4;
  G.lastX = e.clientX; G.lastT = performance.now(); G.vel = 0;
  G.down = e.target;
  G.downAt = performance.now();
  G.wasPlaying = !video.paused;
  // segurar uma tomada sem arrastar: ela sai da faixa e vai para onde o dedo levar.
  // `G.pega` é o mesmo "pegar" do item: no computador ele vem já no arraste (ver o pointermove)
  G.pega = null;
  const tk = e.target.closest('.take');
  if (tk && S.view === 'corte' && !S.posMode) G.pega = () => startMove(+tk.dataset.i, e.clientX);
  // segurar um item de camada: ele passa a andar com o dedo
  const lc = e.target.closest('.chip.layer');
  if (lc) G.pega = () => holdLayer(lc.dataset.id, e.clientX);
  // segurar um bloco da Fase 2 (vista Final): ele anda com o dedo
  const f2 = e.target.closest('.chip.f2');
  if (f2 && S.view === 'final') G.pega = () => holdIns(+f2.dataset.i, e.clientX);
  // um pedaço da legenda (vista Final): ele anda no tempo
  const cp = e.target.closest('.chip.cap');
  if (cp && S.view === 'final' && S.legenda) G.pega = () => holdCap(+cp.dataset.k, e.clientX);
  if (G.pega) G.lp = setTimeout(G.pega, 450);
});
// o item pego segue o ponteiro (na vista que pode ter andado sozinha desde que o arraste começou)
function arrasteSegue(x) {
  G.ultX = x;
  const rolou = agulhaAnda() && G.v0arraste != null ? (S.v0 - G.v0arraste) * S.pps : 0;
  if (G.mode === 'move') { G.mv.x = x; updateMove(); } else if (G.mode === 'layer') dragLayer(x + rolou);
  else if (G.mode === 'ins') dragIns(x + rolou);
  else if (G.mode === 'cap') dragCap(x + rolou);
  else if (G.mode === 'faixa' || G.mode === 'faixa-borda') puxaFaixa(x); // o tempo debaixo do ponteiro já conta a vista
}
const ARRASTES = ['layer', 'ins', 'cap', 'faixa', 'faixa-borda'];
/* Computador: levando um item (ou a ponta dele) para perto da borda da linha do tempo, a vista
 * anda sozinha, como no CapCut desktop; sem isso não dava para levar um texto dos 9 s aos 60 s
 * sem antes afastar o zoom. O celular não precisa: lá a linha do tempo corre sob o dedo. */
function bordaRola() {
  if (!agulhaAnda()) return;
  G.v0arraste = S.v0;
  let last = performance.now();
  const passo = (now) => {
    if (!ARRASTES.includes(G.mode)) { G.v0arraste = null; return; }
    const r = timeline.getBoundingClientRect(), x = G.ultX;
    const zona = 48;
    const fundo = x == null ? 0 : x < r.left + DESK_MARGEM + zona ? -(r.left + DESK_MARGEM + zona - x) / zona
      : x > r.right - zona ? (x - (r.right - zona)) / zona : 0;
    if (fundo) {
      const v0 = S.v0;
      S.v0 += Math.max(-1, Math.min(1, fundo)) * visivel() * 0.9 * ((now - last) / 1000);
      prendeVista();
      if (S.v0 !== v0) { positionTimeline(); arrasteSegue(x); }
    }
    last = now;
    requestAnimationFrame(passo);
  };
  requestAnimationFrame(passo);
}

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
      // o ímã: o fim da tomada é o corte para a seguinte, e ele gruda na batida. A ponta esquerda
      // não anda na linha do tempo (aparar o começo encurta a tomada no mesmo lugar)
      const d = draftLayout()[T.i], fim = d.out + d.dur, alvo = imaPonto(fim);
      const e2 = r.end + (alvo - fim) * vb;
      if (alvo !== fim && e2 > r.start + MIN_SEG && (!srcDur || e2 <= srcDur)) r.end = e2;
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
  if (G.mode === 'scrub') { levaAgulha(xNaLinha(e), true); return; }
  if (G.mode === 'move' || ARRASTES.includes(G.mode)) { arrasteSegue(e.clientX); return; }
  if (G.mode === 'pan') {
    const dx = e.clientX - G.x0;
    if (G.agulha && Math.abs(dx) > 2) {
      G.mode = 'scrub'; G.agulha = false;
      clearTimeout(G.lp);
      video.pause();
      levaAgulha(xNaLinha(e), true);
      return;
    }
    if (!G.moved && Math.abs(dx) > 6) {
      clearTimeout(G.lp);
      // computador: o mouse não tem o "segurar" do dedo; arrastar um item já o leva, como no
      // CapCut desktop (antes o arraste virava rolagem e nada saía do lugar)
      if (agulhaAnda() && G.pega) {
        G.pega();
        if (G.mode !== 'pan') { arrasteSegue(e.clientX); return; }
      }
      // computador, vista Final: arrastar no vão escolhe um trecho de TODAS as faixas, como a
      // caixa de seleção do CapCut (a vista rola pela rodinha)
      if (agulhaAnda() && !G.pega && S.view === 'final' && hasFinal() && !S.posMode) {
        comecaMarquee();
        arrasteSegue(e.clientX);
        return;
      }
      G.moved = true; // celular: arrastou antes do tempo, é rolagem, não mover
      if (!video.paused) video.pause();
    }
    if (!G.moved) return;
    if (agulhaAnda()) { S.v0 = G.v00 - dx / S.pps; prendeVista(); positionTimeline(); return; } // computador: arrastar rola a vista
    const now = performance.now();
    const dtMs = Math.max(1, now - G.lastT);
    G.vel = 0.8 * ((e.clientX - G.lastX) / dtMs) + 0.2 * G.vel; // px/ms, suavizada
    G.lastX = e.clientX; G.lastT = now;
    S.t = clampT(imaPonto(G.t0 - dx / S.pps)); // com o ímã, a agulha gruda na batida enquanto o dedo arrasta
    positionTimeline();
    scheduleSeek(true);
  }
});

function endPointer(e) {
  if (!G.pts.has(e.pointerId)) return;
  G.pts.delete(e.pointerId);
  clearTimeout(G.lp);
  if (G.mode === 'scrub') { G.mode = null; preciseSeek(); return; }
  if (G.mode === 'move') { if (G.pts.size === 0) endMove(e.type === 'pointerup'); return; }
  if (G.mode === 'layer') { if (G.pts.size === 0) endLayerDrag(); return; }
  if (G.mode === 'ins') { if (G.pts.size === 0) endInsDrag(); return; }
  if (G.mode === 'cap') { if (G.pts.size === 0) endCap(); return; }
  if (G.mode === 'faixa' || G.mode === 'faixa-borda') {
    if (G.pts.size === 0) { G.mode = null; if (S.faixa) preciseSeek(); renderTimeline(); renderToolbar(); }
    return;
  }
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
    if (!G.moved && e.type === 'pointerup') {
      // computador: clicar num vão leva a agulha até ali (num item, só escolhe)
      if (agulhaAnda() && !(G.down && G.down.closest && G.down.closest('.take, .chip, .add-tile'))) {
        levaAgulha(G.x0 - timeline.getBoundingClientRect().left, false);
      }
      tapAt(G.down);
      return;
    }
    if (agulhaAnda()) return; // o mouse não tem embalo
    if (performance.now() - G.lastT > 80) G.vel = 0; // o dedo parou antes de soltar
    startMomentum(G.vel);
  }
}
timeline.addEventListener('pointerup', endPointer);
timeline.addEventListener('pointercancel', endPointer);

// ---------- mover: segurar a tomada e arrastar para outro lugar ----------
function startMove(i, x) {
  if (G.mode !== 'pan' || G.moved || !S.draft[i]) return;
  if (emLugar(S.draft[i])) { G.pega = null; avisaLugar(); return; } // a ordem dos lugares é a do modelo
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
  // um bloco da faixa de velocidade: a seleção em massa vira o trecho dele; qualquer outro
  // toque solta a seleção
  const vc = target && target.closest && target.closest('.chip.velc');
  const tv = vc && S.view === 'final' ? S.vel.trechos[+vc.dataset.v] : null;
  S.faixa = null;
  if (tv) {
    S.selected = -1; S.layerSel = null; S.fxSel = null; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1; S.legSel = false;
    S.faixa = { a: tv.inicio, b: tv.fim };
    drawCenaBox(); renderTimeline(); renderToolbar();
    return;
  }
  // a legenda é uma só: tocar em qualquer frase da faixa escolhe todas
  const cp = target && target.closest && target.closest('.chip.cap');
  if (cp && S.view === 'final' && S.legenda) { tapLegenda(); return; }
  S.legSel = false;
  const note = target && target.closest && target.closest('.chip.note');
  if (note) { openNote(note.dataset.id, false); return; }
  const lc = target && target.closest && target.closest('.chip.layer');
  if (lc) { S.fxSel = null; tapLayer(lc.dataset.id); return; }
  const fc = target && target.closest && target.closest('.chip.fx');
  if (fc) { tapFx(fc.dataset.id); return; }
  const f2 = target && target.closest && target.closest('.chip.f2');
  if (f2 && S.view === 'final') { tapIns(+f2.dataset.i); return; }
  const ce = target && target.closest && target.closest('.chip.cena');
  if (ce && S.view === 'final') { tapCena(+ce.dataset.c); return; }
  const zc = target && target.closest && target.closest('.chip.zoom');
  if (zc && S.view === 'final') { tapZoom(+zc.dataset.z); return; }
  S.layerSel = null;
  S.fxSel = null;
  S.insSel = -1;
  S.cenaSel = -1;
  S.zoomSel = -1;
  drawCenaBox();
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
  if (e.ctrlKey) { setZoom(S.pps * Math.exp(-e.deltaY * 0.01), agulhaAnda() ? xNaLinha(e) : undefined); return; }
  const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
  if (agulhaAnda()) { S.v0 += d / S.pps; prendeVista(); positionTimeline(); return; } // a vista rola, a agulha fica
  S.t = clampT(S.t + d / S.pps);
  positionTimeline();
  scheduleSeek(false);
}, { passive: false });

// ---------- reprodução ----------
$('btnPlay').innerHTML = ICON.play;
$('btnMute').innerHTML = ICON.vol;
$('btnFull').innerHTML = ICON.cheia;
$('btnFull').addEventListener('click', () => {
  // a tela cheia é do PALCO, não do player (ver .stage:fullscreen no CSS)
  const palco = $('stage');
  if (palco.requestFullscreen) palco.requestFullscreen().catch(() => {});
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
  fxIntSheet: 'fxIntOk', trilhaSheet: 'trilhaClose', fxSheet: 'fxClose', tomZoomSheet: 'tomZoomOk', cenaSheet: 'cenaCancel',
  modeloSheet: 'modeloClose', fundoSheet: 'fundoClose', lugarSheet: 'lugarClose', trechoSheet: 'trechoCancel', montSheet: 'montClose' };
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
  if (!$('trocaModal').classList.contains('hidden')) return; // a escolha é pelos dois botões
  if (!$('projModal').classList.contains('hidden')) {
    if (k === 'Escape') fechaProjetos();
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
  // texto escolhido na tela: as setas o empurram (2 px do quadro; Shift, 10)
  if (k.startsWith('Arrow') && !ctrl && textoSelNaTela()) {
    e.preventDefault();
    const d = e.shiftKey ? 10 : 2;
    textoEmpurra(k === 'ArrowLeft' ? -d : k === 'ArrowRight' ? d : 0, k === 'ArrowUp' ? -d : k === 'ArrowDown' ? d : 0);
    return;
  }
  // efeito escolhido com a moldura na tela: as setas empurram o bloco (2 px do quadro; Shift, 10)
  if (k.startsWith('Arrow') && !ctrl && cenaNaTela()) {
    e.preventDefault();
    const d = e.shiftKey ? 10 : 2;
    cenaEmpurra(k === 'ArrowLeft' ? -d : k === 'ArrowRight' ? d : 0, k === 'ArrowUp' ? -d : k === 'ArrowDown' ? d : 0);
    return;
  }
  if ((k === 'ArrowLeft' || k === 'ArrowRight') && !ctrl) {
    e.preventDefault();
    const seg = e.shiftKey ? 1 : 1 / (S.fps || 30);
    passo(k === 'ArrowRight' ? seg : -seg);
  } else if (kl === 'm' && !ctrl) {
    toggleMark();
  } else if (kl === 'n' && !ctrl) { // o "snapping" do CapCut desktop também é no N
    alternaIma();
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
    if (S.layerSel) duplicateLayerSel();
    else if (S.selected >= 0 && S.view === 'corte') duplicateSelected();
  } else if (ctrl && kl === 'a') { // tudo de uma vez (no navegador seria escolher o texto da página)
    e.preventDefault();
    selecionaTudo();
  }
});
$('btnHelp').addEventListener('click', () => mostraAjuda(true));
$('helpClose').addEventListener('click', () => mostraAjuda(false));
$('helpModal').addEventListener('click', (e) => { if (e.target === $('helpModal')) mostraAjuda(false); });

// ---------- Projetos (botão de casa) ----------
/* A tela lista o que o servidor conhece (~/.cutmind/projetos.json): capa, nome, duração,
 * fase e a última mudança. Abrir troca o projeto do servidor inteiro, então o celular
 * conectado acompanha. Com ajuste sem salvar, nada troca: salve ou descarte antes. */
function quandoFoi(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'agora';
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  const d = Math.round(s / 86400);
  return d === 1 ? 'ontem' : `há ${d} dias`;
}
function faseDoProjeto(p) {
  if (p.novo) return p.montagem ? 'Montagem nova' : 'Novo';
  if (p.aguardandoEstilo) return 'Estilo';
  if (p.fase >= 2) return 'Final';
  return p.fase === 1 ? 'Corte' : 'Começando';
}
function fechaProjetos() { $('projModal').classList.add('hidden'); }
async function abreProjetos() {
  $('projModal').classList.remove('hidden');
  $('projNovo').classList.add('hidden');
  $('projInfo').textContent = 'Carregando…';
  try {
    const d = await (await fetch('/api/projetos')).json();
    $('projInfo').textContent = d.projetos.length > 1 ? '' : 'Por enquanto só este. Os próximos vídeos que você editar aparecem aqui.';
    desenhaProjetos(d.projetos);
  } catch (e) {
    $('projInfo').textContent = 'Não consegui ler a lista de projetos. O editor ainda está ligado no computador?';
  }
}
function desenhaProjetos(lista) {
  const g = $('projGrade');
  g.innerHTML = `<button class="pj novo" type="button" data-novo="corte"><div class="pj-capa">${ICON.mais}</div>
    <div class="pj-nome">Novo projeto</div><div class="pj-meta">envie os vídeos e o agente corta</div></button>
    <button class="pj novo" type="button" data-novo="montagem"><div class="pj-capa">${ICON.montagem}</div>
    <div class="pj-nome">Nova montagem</div><div class="pj-meta">fotos e clipes na batida de uma música</div></button>`;
  for (const p of lista) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'pj' + (p.aberto ? ' on' : '');
    b.dataset.id = p.id;
    const dur = p.duracao > 0 ? ` · ${fmtShort(p.duracao)}` : '';
    b.innerHTML = `<div class="pj-capa">${p.temCapa ? '' : ICON.final}</div>
      ${p.aberto ? '<span class="pj-selo">aberto</span>' : ''}
      <div class="pj-nome">${escSvg(p.nome)}</div><div class="pj-meta">${faseDoProjeto(p)}${dur} · ${quandoFoi(p.mudou)}</div>`;
    // a capa por URL (com o id), sem montar CSS com texto do projeto
    if (p.temCapa) b.querySelector('.pj-capa').style.backgroundImage = `url("/gen/projeto-capa?id=${encodeURIComponent(p.id)}&v=${Math.round(p.mudou)}")`;
    b.title = p.mensagem || p.nome;
    g.appendChild(b);
  }
}
async function abreProjeto(id) {
  if (id === S.projetoId) { fechaProjetos(); return; }
  const n = dirtyCount();
  if (n) { toast(`${n === 1 ? 'Há 1 ajuste' : `Há ${n} ajustes`} sem salvar aqui. Salve ou descarte antes de trocar de projeto.`, 4200); return; }
  try {
    const out = await (await fetch('/api/projetos/abrir', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }) })).json();
    if (!out.ok) throw new Error(out.error || 'falhou');
    location.reload();
  } catch (e) { toast(`Não abri o projeto: ${e.message}`, 4000); }
}
$('projIco').innerHTML = ICON.casa;
$('btnProjetos').addEventListener('click', abreProjetos);
$('projClose').addEventListener('click', fechaProjetos);
$('projModal').addEventListener('click', (e) => {
  if (e.target === $('projModal')) { fechaProjetos(); return; }
  const card = e.target.closest('.pj');
  if (!card) return;
  if (card.dataset.novo) novoProjeto(card.dataset.novo);
  else abreProjeto(card.dataset.id);
});
// o nome do projeto novo; a Nova montagem nasce marcada e abre no painel Modelos de montagem
function novoProjeto(tipo) {
  if (dirtyCount()) { toast('Salve ou descarte seus ajustes antes de começar outro projeto.', 4000); return; }
  $('projNovo').dataset.tipo = tipo;
  $('projGrade').querySelectorAll('.pj.novo').forEach((b) => b.classList.toggle('on', b.dataset.novo === tipo));
  $('projNome').placeholder = tipo === 'montagem' ? 'Nome da montagem (ex.: Viagem de julho)' : 'Nome do projeto (ex.: Reels da semana)';
  $('projNovo').classList.remove('hidden');
  $('projNome').focus();
}
$('projNovo').addEventListener('submit', async (e) => {
  e.preventDefault();
  const nome = $('projNome').value.trim();
  if (!nome) { $('projNome').focus(); return; }
  const tipo = $('projNovo').dataset.tipo === 'montagem' ? 'montagem' : undefined;
  try {
    const out = await (await fetch('/api/projetos/novo', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome, tipo }) })).json();
    if (!out.ok) throw new Error(out.error || 'falhou');
    location.reload(); // o projeto novo abre vazio, pedindo os vídeos (Enviar) ou, na montagem, no painel
  } catch (err) { toast(`Não criei o projeto: ${err.message}`, 4200); }
});
// outro aparelho trocou o projeto e este tinha ajustes: voltar (o servidor reabre este) ou descartar
function avisaTroca(novoId) {
  if (S.trocaAvisada === novoId) return;
  S.trocaAvisada = novoId;
  const n = dirtyCount();
  $('trocaTxt').textContent = `Outro aparelho abriu outro projeto neste editor, e aqui ${n === 1 ? 'há 1 ajuste' : `há ${n} ajustes`} `
    + `sem salvar em "${(S.state && S.state.project) || 'este projeto'}". Volte para ele para salvar, ou descarte e siga no outro.`;
  $('trocaModal').classList.remove('hidden');
}
$('trocaVoltar').addEventListener('click', async () => {
  try {
    const out = await (await fetch('/api/projetos/abrir', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: S.projetoId }) })).json();
    if (!out.ok) throw new Error(out.error || 'falhou');
    S.trocaAvisada = null;
    $('trocaModal').classList.add('hidden');
    toast('Voltou para este projeto. Agora dá para salvar.', 3200);
  } catch (e) { toast(`Não voltei: ${e.message}`, 4000); }
});
$('trocaDescartar').addEventListener('click', () => location.reload());

function loop() {
  const now = performance.now() / 1000;
  for (const f of S.cardAnims) f(now);
  for (const f of S.liveAnims) f(now);
  if (!video.paused && !video.ended && !G.mode && !momentum) {
    if (S.view === 'corte') followDraft();
    else {
      // no Final, o trecho com velocidade toca no fator dele (o tom da voz fica, como no atempo)
      const f = fatorEm(video.currentTime);
      if (video.playbackRate !== f) video.playbackRate = f;
      S.t = clampT(renderedToDraft(video.currentTime)); positionTimeline();
    }
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
const ATALHO = { dividir: 'Ctrl+B', duplicar: 'Ctrl+D', excluir: 'Delete', marcar: 'M', voltar: 'Esc', selecionar: 'Ctrl+A', tudo: 'Ctrl+A' };
const DICA = { volume: 'Volume', velocidade: 'Velocidade e curva', intensidade: 'Intensidade do filtro',
  texto: 'Texto solto ou modelo', 'texto-novo': 'Texto novo na agulha', modelos: 'Dois ou três textos de uma vez, em fontes misturadas',
  'texto-editar': 'Texto, fonte, cor, tamanho, contorno, curva e altura',
  atras: 'No vídeo final, a camada passa atrás da pessoa', 'texto-segue': 'No vídeo final, o texto anda junto com a pessoa',
  'leg-texto': 'Fonte, cor, tamanho e contorno de todas as frases', 'leg-segue': 'No vídeo final, a legenda anda junto com a pessoa',
  'leg-posicao': 'O lugar de cada frase da legenda', 'leg-original': 'A legenda como o agente fez',
  selecionar: 'Escolhe o vídeo todo (imagem, som, legenda e efeitos juntos); no computador, arrastar no vão escolhe um trecho',
  'vel-trecho': 'Velocidade de tudo no trecho: nada sai do lugar', 'vel-normal': 'O trecho volta à velocidade normal',
  tudo: 'O vídeo inteiro',
  'melhorar-voz': 'A voz do vídeo mais limpa ou com som de estúdio, e quanto do ambiente fica',
  fundo: 'Um fundo novo atrás de você, na tomada debaixo da agulha',
  'lugar-trocar': 'Outra foto ou vídeo neste lugar, com a mesma duração', 'lugar-trecho': 'Que parte do clipe entra neste lugar',
  'lugar-original': 'O lugar volta à mídia e ao trecho do vídeo',
  'modelos-montagem': 'Os modelos de montagem: o ritmo, a música e as fotos e clipes; ou guardar esta montagem como modelo',
  formato: 'O formato do vídeo: em pé, deitado ou quadrado',
  'lugar-caber': 'A foto ou o clipe inteiro na tela (arraste a mídia e a bolinha do canto para ajustar à mão)',
  'lugar-encher': 'A foto ou o clipe cobrindo a tela inteira', 'lugar-auto': 'O enquadramento automático do lugar',
  'lugar-repetir': 'O mesmo enquadramento nos outros lugares com esta mídia' };
function renderToolbar() {
  const tb = $('toolbar');
  const ctx = $('ctxbar');
  const lsel = S.layerSel ? camItem(S.layerSel) : null;
  const fsel = !lsel && S.fxSel && S.view === 'corte' ? fxItem(S.fxSel) : null;
  const sel = !lsel && !fsel && S.selected >= 0 && S.view === 'corte' ? S.draft[S.selected] : null;
  const isel = !lsel && !fsel && S.view === 'final' && S.insSel >= 0 ? S.insertsDraft[S.insSel] || null : null;
  const csel = !lsel && !fsel && !isel && S.view === 'final' && S.cenaSel >= 0 ? S.cenasDraft[S.cenaSel] || null : null;
  const zsel = !lsel && !fsel && !isel && !csel && S.view === 'final' && S.zoomDraft && S.zoomSel >= 0;
  const lgsel = !lsel && !fsel && !isel && !csel && !zsel && S.view === 'final' && S.legSel && !!S.legenda;
  const bsel = !lsel && !fsel && !isel && !csel && !zsel && !lgsel && S.view === 'final' && S.faixa ? S.faixa : null;
  const algum = !!(sel || lsel || fsel || isel || csel || zsel || lgsel || bsel);
  if (algum) { S.audioMenu = false; S.importMenu = false; S.fxMenu = false; S.textMenu = false; }
  const amenu = S.audioMenu, imenu = S.importMenu, fmenu = S.fxMenu, tmenu = S.textMenu;
  tb.classList.toggle('hidden', !!(algum || amenu || imenu || fmenu || tmenu));
  ctx.classList.toggle('hidden', !(algum || amenu || imenu || fmenu || tmenu));
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
  if (ehMontagem()) tool(tb, 'modelos-montagem', 'Montagem', { icon: ICON.montagem, on: MT.aberto });
  if (S.montagem) tool(tb, 'formato', 'Formato', { icon: ICON.formato, disabled: !hasVideo,
    on: S.formato !== S.formatoAtual });
  tool(tb, 'cortar', 'Cortar', { icon: ICON.corte, disabled: !hasVideo });
  // no Final: escolhe tudo (imagem, som, legenda, efeitos) para mexer junto, como o Ctrl+A
  if (S.view === 'final') tool(tb, 'selecionar', 'Selecionar', { disabled: !hasVideo });
  tool(tb, 'audio', 'Áudio', { disabled: !hasVideo });
  tool(tb, 'texto', 'Texto', { disabled: !hasVideo });
  tool(tb, 'efeitos', 'Efeitos', { disabled: !hasVideo });
  tool(tb, 'legenda', 'Legenda', { disabled: !hasVideo || !canStyle() });
  tool(tb, 'estilo', 'Estilo', { disabled: !hasVideo || !canStyle() });
  tool(tb, 'marcar', S.pendingIn != null ? 'Fim' : 'Marcar', { armed: S.pendingIn != null, disabled: !hasVideo });

  ctx.innerHTML = '';
  if (imenu) { // Importar: o tipo do arquivo. Vídeo vai para a pasta dos vídeos (o agente corta);
    // imagem e áudio entram como camadas novas, na agulha (o servidor guarda em midia/)
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'imp-video', 'Vídeo', { icon: ICON.final });
    tool(ctx, 'imp-imagem', 'Imagem', { icon: ICON.imagem, disabled: !hasVideo && !ehMontagem() });
    tool(ctx, 'imp-audio', 'Áudio', { icon: ICON.audio, disabled: !hasVideo && !ehMontagem() });
    return;
  }
  if (amenu) { // Áudio: uma trilha da biblioteca do kit ou um arquivo do celular
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'trilhas', 'Trilhas', { icon: ICON.audio });
    tool(ctx, 'do-celular', doAparelho(), { icon: ICON.enviar }); // no computador, "Do computador"
    tool(ctx, 'melhorar-voz', 'Melhorar voz', { icon: ICON.voz });
    return;
  }
  if (tmenu) { // Texto: um texto solto na agulha, ou um modelo de dois ou três textos em fontes misturadas
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'texto-novo', 'Texto', { icon: ICON.texto });
    tool(ctx, 'modelos', 'Modelos', { icon: ICON.estilo });
    return;
  }
  if (fmenu) { // Efeitos: filtro e fundo na tomada debaixo da agulha, transição no corte mais perto
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'filtros', 'Filtros', { icon: ICON.filtro });
    tool(ctx, 'transicoes', 'Transições', { icon: ICON.transicao });
    tool(ctx, 'fundo', 'Fundo', { icon: ICON.fundo, disabled: !fundoPode() });
    return;
  }
  if (bsel) { // a seleção em massa: o trecho de todas as faixas
    const f = fatorDaFaixa(bsel);
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'vel-trecho', f == null ? 'Velocidade' : fmtVel(f), { icon: ICON.velocidade });
    tool(ctx, 'vel-normal', 'Normal', { icon: ICON.original, disabled: f === 1 });
    tool(ctx, 'tudo', 'Tudo', { disabled: faixaETudo(bsel) });
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
    const dq = destaqueDoBloco(isel);
    if (dq) {
      tool(ctx, 'cena-texto', 'Texto', { icon: ICON.texto });
      tool(ctx, 'cena-lugar', 'Centralizar', { icon: ICON.mover, disabled: Math.round(blocoDaCena(dq).x) === FRAME_W / 2 });
    }
    tool(ctx, 'f2-original', 'Original', { icon: ICON.original, disabled: !insMudou(isel) && !(dq && cenaMudou(dq)) });
    return;
  }
  if (csel) { // um efeito: o tempo segue a tomada; o bloco se arrasta na prévia; o Fundo troca a imagem
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    if (csel.tipo === 'fundo') tool(ctx, 'fundo', 'Fundo', { icon: ICON.fundo });
    tool(ctx, 'cena-liga', csel.desligada ? 'Ligar' : 'Desligar', { icon: csel.desligada ? ICON.olhoFechado : ICON.olho });
    if (Object.keys(csel.textos).length) tool(ctx, 'cena-texto', 'Texto', { icon: ICON.texto, disabled: csel.desligada });
    if (CENA_BLOCO[csel.tipo]) tool(ctx, 'cena-lugar', 'Centralizar', { icon: ICON.mover, disabled: csel.desligada || Math.round(blocoDaCena(csel).x) === FRAME_W / 2 });
    // o Fundo criado aqui não tem um original para onde voltar: sai da tomada
    if (csel.nova) tool(ctx, 'excluir', 'Excluir', { icon: ICON.remover });
    else tool(ctx, 'cena-original', 'Original', { icon: ICON.original, disabled: !cenaMudou(csel) });
    return;
  }
  if (lgsel) { // a legenda do vídeo final: o texto dela, acompanhar a pessoa e o lugar das frases
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'leg-texto', 'Texto', { icon: ICON.texto });
    tool(ctx, 'leg-segue', 'Acompanhar', { icon: ICON.alvo, on: S.legenda.acompanhar });
    tool(ctx, 'leg-posicao', 'Posição', { icon: ICON.mover, disabled: !S.style || !S.style.captions || S.style.captions === 'none' });
    tool(ctx, 'leg-original', 'Original', { icon: ICON.original, disabled: !legendaMudou() });
    return;
  }
  if (zsel) { // o zoom de uma tomada no vídeo final
    const z = S.zoomDraft[S.zoomSel];
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'zoom-valor', `${Math.round(z * 100)}%`, { icon: ICON.lupa });
    tool(ctx, 'zoom-sem', 'Sem zoom', { icon: ICON.semZoom, disabled: Math.abs(z - 1) < 0.005 });
    tool(ctx, 'zoom-original', 'Original', { icon: ICON.original, disabled: z === S.zoomOrig[S.zoomSel] });
    return;
  }
  if (lsel) { // um item de camada escolhido
    const aud = lsel.f.tipo === 'audio';
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    if (lsel.f.tipo === 'texto') {
      tool(ctx, 'texto-editar', 'Editar', { icon: ICON.texto });
      tool(ctx, 'atras', 'Atrás da pessoa', { icon: ICON.pessoa, on: lsel.it.atras });
      tool(ctx, 'texto-segue', 'Acompanhar', { icon: ICON.alvo, on: lsel.it.acompanhar });
    }
    if (lsel.f.tipo === 'imagem') tool(ctx, 'atras', 'Atrás da pessoa', { icon: ICON.pessoa, on: !!lsel.it.atras });
    if (aud) {
      tool(ctx, 'volume', `${Math.round(lsel.it.volume * 100)}%`);
      // Melhorar é a cadeia de voz (tira ruído): numa música da biblioteca só estragaria
      if (!lsel.it.trilha) tool(ctx, 'melhorar', 'Melhorar', { on: lsel.it.melhorar });
    }
    tool(ctx, 'duplicar', 'Duplicar');
    tool(ctx, 'excluir', 'Excluir', { icon: ICON.remover });
    return;
  }
  if (sel && emLugar(sel)) { // um lugar da montagem: a mídia e o trecho mudam, a duração não
    const op = opcaoDe(lugarAgora(sel).midia);
    tool(ctx, 'voltar', 'Voltar', { cls: 'back' });
    tool(ctx, 'lugar-trocar', 'Trocar', { icon: ICON.trocar });
    tool(ctx, 'lugar-trecho', 'Trecho', { icon: ICON.trecho, disabled: !(op && op.tipo === 'video') });
    // o volume do clipe só vale com o som dos clipes ligado (o da faixa de vídeo)
    if (!S.camadas.video.mudo) tool(ctx, 'volume', `${Math.round(sel.vol * 100)}%`);
    tool(ctx, 'ouvir', 'Ouvir');
    tool(ctx, 'lugar-caber', 'Caber', { icon: ICON.formato });
    tool(ctx, 'lugar-encher', 'Encher', { icon: ICON.formato });
    tool(ctx, 'lugar-auto', 'Automático', { icon: ICON.formato, disabled: !enqDoLugar(sel) });
    const outras = outrasVezes(sel).length;
    tool(ctx, 'lugar-repetir', outras ? `Repetir (${outras})` : 'Repetir', { icon: ICON.formato, disabled: !outras });
    tool(ctx, 'lugar-original', 'Original', { icon: ICON.original, disabled: !sel.troca });
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
    case 'selecionar': case 'tudo': selecionaTudo(); break;
    case 'vel-trecho': openVelFaixa(); break;
    case 'vel-normal': if (S.faixa) { remember(); S.vel.trechos = comFator(S.vel.trechos, S.faixa.a, S.faixa.b, 1); renderTimeline(); renderToolbar(); refreshHeader(); } break;
    case 'estilo': openStyle('edit'); break;
    case 'legenda': openStyle('captions'); break;
    case 'marcar': toggleMark(); break;
    case 'importar': S.importMenu = true; S.audioMenu = false; S.fxMenu = false; S.textMenu = false; renderToolbar(); break;
    case 'efeitos': S.fxMenu = true; S.audioMenu = false; S.importMenu = false; S.textMenu = false; renderToolbar(); break;
    case 'filtros': S.fxMenu = false; renderToolbar(); openFx('filtro'); break;
    case 'transicoes': S.fxMenu = false; renderToolbar(); openFx('transicao'); break;
    case 'fundo': { // do menu Efeitos (a tomada da agulha) ou do Fundo escolhido na faixa
      const c = S.cenaSel >= 0 ? S.cenasDraft[S.cenaSel] : null;
      S.fxMenu = false; renderToolbar();
      openFundo(c && c.tipo === 'fundo' ? S.cenaSel : null);
      break;
    }
    case 'intensidade': openIntensidade(); break;
    case 'ajustar': openAjuste(); break;
    // numa montagem, o vídeo é um clipe para ela (midia/), não material novo para cortar; sem vídeo
    // ainda, a foto e a música também vão para o painel Modelos de montagem
    case 'imp-video': S.importMenu = false; renderToolbar(); $(ehMontagem() ? 'fileMontMidia' : 'fileInput').click(); break;
    case 'imp-imagem': S.importMenu = false; renderToolbar(); $(montagemSemVideo() ? 'fileMontMidia' : 'fileImagem').click(); break;
    case 'imp-audio': S.importMenu = false; renderToolbar(); $(montagemSemVideo() ? 'fileMontMusica' : 'fileAudio').click(); break;
    case 'modelos-montagem': if (MT.aberto) fechaMontagem(); else abreMontagem(); break;
    case 'formato': openFormato(); break;
    case 'lugar-caber': enqRapido('caber'); break;
    case 'lugar-encher': enqRapido('encher'); break;
    case 'lugar-auto': enqRapido('auto'); break;
    case 'lugar-repetir': enqNasOutras(); break;
    case 'audio': S.audioMenu = true; S.importMenu = false; S.fxMenu = false; S.textMenu = false; renderToolbar(); break;
    case 'trilhas': S.audioMenu = false; renderToolbar(); openTrilhas(); break;
    case 'do-celular': S.audioMenu = false; renderToolbar(); $('fileAudio').click(); break;
    case 'melhorar-voz': S.audioMenu = false; renderToolbar(); openVoz(); break;
    case 'voltar': soltaEscolha(); break;
    case 'dividir': splitSelected(); break;
    case 'duplicar': if (S.layerSel) duplicateLayerSel(); else duplicateSelected(); break;
    case 'texto': S.textMenu = true; S.audioMenu = false; S.importMenu = false; S.fxMenu = false; renderToolbar(); break;
    case 'texto-novo': S.textMenu = false; addTexto(); break;
    case 'modelos': S.textMenu = false; renderToolbar(); openModelos(); break;
    case 'texto-editar': openTextoCamada(false); break;
    case 'atras': textoLiga('atras'); break;
    case 'texto-segue': textoLiga('acompanhar'); break;
    case 'leg-texto': openLegendaTexto(); break;
    case 'leg-segue': legendaSegue(); break;
    case 'leg-posicao': soltaEscolha(); enterPosMode(); break;
    case 'leg-original': if (legendaMudou()) { remember(); S.legenda = JSON.parse(JSON.stringify(S.legendaOrig)); renderTimeline(); renderToolbar(); refreshHeader(); } break;
    case 'excluir':
      if (S.layerSel) deleteLayerSel();
      else if (S.fxSel) deleteFxSel();
      else if (S.cenaSel >= 0) cenaExclui();
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
    case 'lugar-trocar': openTroca(); break;
    case 'lugar-trecho': openTrecho(); break;
    case 'lugar-original': if (r && r.troca) { remember(); r.troca = null; renderTimeline(); renderToolbar(); refreshHeader(); } break;
    case 'f2-original': {
      const c = S.insertsDraft[S.insSel];
      if (c) {
        remember();
        c.start = c.orig.start; c.end = c.orig.end;
        const dq = destaqueDoBloco(c);
        if (dq) { Object.assign(dq, cenaValor(dq.orig)); rotulosDestaques(); }
        renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
      }
      break;
    }
    case 'cena-liga': cenaMuda((c) => { c.desligada = !c.desligada; }); break;
    case 'cena-texto': openCenaTexto(); break;
    case 'cena-lugar': cenaCentraliza(); break;
    case 'cena-original': cenaMuda((c) => Object.assign(c, cenaValor(c.orig))); break;
    case 'zoom-valor': openZoom(); break;
    case 'zoom-sem': zoomPara(1); break;
    case 'zoom-original': zoomPara(S.zoomOrig[S.zoomSel]); break;
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
  S.selected = -1; S.layerSel = null; S.fxSel = null; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1; S.legSel = false;
  S.faixa = null;
  S.audioMenu = false; S.importMenu = false; S.fxMenu = false; S.textMenu = false;
  renderTimeline(); renderToolbar(); drawCenaBox();
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
  if (emLugar(S.draft[i])) { avisaLugar(); return; }
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
  if (emLugar(r)) { avisaLugar(); return; }
  remember();
  S.draft.splice(i + 1, 0, { uid: `n${++S.seq}`, from: r.from, kind: 'dup', source: r.source, start: r.start, end: r.end, beat: r.beat, vol: r.vol, vel: r.vel, curva: copiaCurva(r.curva), orig: null });
  S.selected = i + 1;
  renderTimeline(); renderToolbar(); refreshHeader();
}
// Excluir: sai da faixa (o ↶ traz de volta); a última tomada fica
function deleteSelected() {
  if (S.draft.length < 2) return;
  if (emLugar(S.draft[S.selected])) { avisaLugar(); return; }
  remember();
  S.draft.splice(S.selected, 1);
  S.selected = -1;
  S.t = clampT(S.t);
  renderTimeline(); renderToolbar(); refreshHeader();
}

// ---------- Trocar: outra foto ou vídeo num lugar da montagem ----------
/* As mídias da montagem e as fotos e vídeos de midia/ (o que vem "Do aparelho" cai ali). A escolha
 * fica na tomada (`troca`) até o Salvar; o agente refaz só os lugares trocados. */
const LT = { aberto: false, uid: null };
const tomadaPorUid = (uid) => S.draft.find((x) => x.uid === uid) || null;
async function openTroca() {
  const r = S.draft[S.selected];
  if (!emLugar(r)) return;
  video.pause();
  LT.aberto = true;
  LT.uid = r.uid;
  $('lugarTitulo').textContent = `Trocar o lugar ${r.vaga}`;
  showSheet($('lugarSheet'), true);
  renderTroca();
  await carregaMontMidias(); // de novo: pode ter chegado mídia nova
  if (LT.aberto) renderTroca();
}
function closeTroca() {
  LT.aberto = false;
  showSheet($('lugarSheet'), false);
}
function renderTroca() {
  const box = $('lugarLista');
  box.innerHTML = '';
  const r = tomadaPorUid(LT.uid);
  if (!r) return;
  const agora = lugarAgora(r);
  el('p', 'sheet-hint', box).textContent = S.montMidias
    ? `Toque numa foto ou vídeo: entra no lugar ${r.vaga} com a mesma duração, na batida.` : 'Carregando as mídias…';
  const grade = el('div', 'mod-grade troca-grade', box);
  for (const m of S.montMidias || []) {
    const b = el('button', 'mod-card troca-card', grade);
    b.type = 'button';
    b.dataset.midia = m.midia;
    b.classList.toggle('on', m.midia === agora.midia);
    const im = el('img', 'troca-img', b);
    im.loading = 'lazy'; im.alt = ''; im.draggable = false;
    im.src = quadroDaMidia(m.midia, m.tipo === 'video' ? Math.min(1, m.duracao / 2) : 0, 240);
    if (m.tipo === 'video') el('span', 'troca-dur', b).textContent = fmtShort(m.duracao);
    el('span', 'mod-nome', b).textContent = m.nome.replace(/\.[^.]+$/, '');
  }
  const mais = el('button', 'mod-card troca-mais', grade);
  mais.type = 'button';
  mais.dataset.trocaMais = '1';
  mais.innerHTML = ICON.mais;
  el('span', 'mod-nome', mais).textContent = 'Do aparelho';
}
function escolheTroca(midia) {
  const r = tomadaPorUid(LT.uid);
  closeTroca();
  if (!r) return;
  const lg = lugarDe(r) || {};
  const antes = snap(), k = trocaKey(r);
  r.troca = midia === lg.midia ? null : { midia, nome: nomeArq(midia) }; // a de agora: o lugar fica como está
  if (trocaKey(r) === k) return;
  remember(antes);
  renderTimeline(); renderToolbar(); refreshHeader();
  if (r.troca) toast(`Lugar ${r.vaga}: ${r.troca.nome}. Salve: o agente refaz só este lugar.`, 3000);
}
$('lugarClose').innerHTML = ICON.fechar;
$('lugarClose').addEventListener('click', closeTroca);
$('lugarLista').addEventListener('click', (e) => {
  const b = e.target.closest('.mod-card');
  if (!b) return;
  if (b.dataset.trocaMais) { $('fileLugar').click(); return; }
  escolheTroca(b.dataset.midia);
});
$('fileLugar').addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  // vai para midia/ do projeto (não é material para o agente cortar) e entra no lugar
  if (f) sendVideo(f, async (res) => { await carregaMontMidias(); if (LT.uid) escolheTroca(res.arquivo); }, 'montagem');
});

// ---------- Modelos de montagem: o modelo, a música e as fotos e clipes ----------
/* Um modelo de montagem é um ritmo (montagens.py): quantos lugares, as batidas de cada um, onde cai
 * o drop e os textos. O painel escolhe o modelo, a música (as de midia/, as trilhas da biblioteca ou
 * uma enviada daqui) e as fotos e clipes na ordem do toque. O Montar vai pelo Salvar
 * (`montagem.usar`) e o agente monta (montagem.py montar). Numa montagem pronta, o painel também
 * guarda ela como modelo: o servidor lê a montagem salva, não o que o editor mostra. */
const MT = { aberto: false, passo: 'modelos', desenhado: null, modelos: null, sel: null, musica: null, midias: [],
  audios: null, ouvindo: null, trSel: null, baixando: null, guardando: false, enviando: false, fila: [], autoAberto: false,
  formato: null, // o formato escolhido no painel; sem ele, o da montagem aberta ou o do modelo
  // o mural da comunidade (mural.py): `mural` diz se ele está ligado neste kit; `com` é a lista de lá
  mural: false, aba: 'meus', com: null, pegando: null };
const MT_PREV = new Audio();
const ehMontagem = () => !!(S.montagem || (S.state && S.state.montagem));
const montagemSemVideo = () => ehMontagem() && !(S.videoDuration > 0);
const modeloEscolhido = () => (MT.modelos || []).find((m) => m.id === MT.sel) || null;
const doAparelho = () => (isDesk() ? 'Do computador' : 'Do celular');
const semExt = (nome) => String(nome || '').replace(/\.[^.]+$/, '');
const ehAudio = (f) => /\.(mp3|m4a|aac|wav|ogg|opus|flac|weba)$/i.test(f.name); // os de camadas.AUDIO_EXTS
async function carregaMontagens() {
  try {
    const r = await fetch('/api/montagens');
    if (r.ok) {
      const d = await r.json();
      MT.modelos = d.modelos || [];
      MT.mural = !!d.mural;
    }
  } catch (e) { /* sem a lista: o painel diz que está carregando */ }
}
// Da comunidade: uma página do mural de cada vez (o servidor local fala com ele)
async function carregaComunidade(mais) {
  const c = MT.com || (MT.com = { modelos: [], seguinte: null, carregando: false, erro: null });
  if (c.carregando) return;
  c.carregando = true;
  c.erro = null;
  if (MT.aberto) renderMontagem();
  try {
    const r = await fetch(`/api/mural${mais && c.seguinte ? `?antes=${encodeURIComponent(c.seguinte)}` : ''}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `erro ${r.status}`);
    c.modelos = mais ? [...c.modelos, ...d.modelos.filter((x) => !c.modelos.some((y) => y.id === x.id))] : d.modelos;
    c.seguinte = d.seguinte;
  } catch (e) { c.erro = e.message; }
  c.carregando = false;
  if (MT.aberto) renderMontagem();
}
// tocar num modelo da comunidade traz ele para os seus e já deixa escolhido
async function pegaDoMural(codigo) {
  if (MT.pegando) return;
  const m = ((MT.com && MT.com.modelos) || []).find((x) => x.id === codigo);
  MT.pegando = codigo;
  renderMontagem();
  try {
    const r = await fetch('/api/mural/pegar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codigo }) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || `erro ${r.status}`);
    await carregaMontagens();
    MT.sel = d.modelo.id;
    MT.aba = 'meus';
    toast(`"${d.modelo.nome}"${m && m.autor ? `, de @${m.autor},` : ''} está nos seus modelos. Toque em Próximo para escolher a música.`, 4500);
  } catch (e) { toast(`Não trouxe o modelo: ${e.message}`, 4500); }
  MT.pegando = null;
  if (MT.aberto) renderMontagem();
}
async function carregaMusicas() {
  try {
    const r = await fetch('/api/midia');
    if (r.ok) MT.audios = ((await r.json()).midia || []).filter((x) => x.tipo === 'audio');
  } catch (e) { MT.audios = MT.audios || []; }
}
async function abreMontagem() {
  video.pause();
  S.importMenu = false; S.audioMenu = false; S.fxMenu = false; S.textMenu = false;
  MT.aberto = true;
  MT.guardando = false;
  showSheet($('montSheet'), true);
  renderToolbar();
  renderMontagem();
  await Promise.all([carregaMontagens(), carregaMontMidias(), carregaMusicas(), S.trilhas ? null : loadTrilhas()]);
  if (MT.aberto) renderMontagem();
}
function fechaMontagem() {
  MT.aberto = false;
  MT_PREV.pause();
  showSheet($('montSheet'), false);
  renderToolbar();
}
function resumoMontagem(m) {
  const b = [`${m.lugares} ${m.lugares === 1 ? 'lugar' : 'lugares'}`, `${m.batidas} batidas`];
  if (m.textos.length) b.push(m.textos.length === 1 ? '1 texto' : `${m.textos.length} textos`);
  if (m.transicoes) b.push(m.transicoes === 1 ? '1 transição' : `${m.transicoes} transições`);
  if (m.doKit) b.push('do kit');
  return b.join(' · ');
}
// a capa é o ritmo: uma barra por lugar, na largura das batidas dele, mais alta do drop em diante;
// em cima, a janela de cada texto do modelo
function capaRitmo(face, m) {
  const total = Math.max(1, m.batidas);
  const barras = el('div', `mt-barras${m.drop_na_vaga ? '' : ' sem-drop'}`, face);
  m.ritmo.forEach((nb, i) => {
    el('span', `mt-barra${m.drop_na_vaga && i + 1 >= m.drop_na_vaga ? ' drop' : ''}`, barras).style.flexGrow = nb;
  });
  const faixa = el('div', 'mt-textos', face);
  for (const t of m.textos) {
    const ini = m.ritmo.slice(0, t.vaga - 1).reduce((a, b) => a + b, 0);
    if (ini >= total) continue;
    const x = el('span', 'mt-texto', faixa);
    x.style.left = `${(ini / total) * 100}%`;
    x.style.width = `${(Math.min(t.batidas || m.ritmo[t.vaga - 1] || 1, total - ini) / total) * 100}%`;
  }
}
function renderMontagem() {
  const body = $('montCorpo');
  const topo = MT.desenhado === MT.passo ? body.scrollTop : 0; // tocar uma música não pula a lista
  if (MT.passo !== 'modelos' && !modeloEscolhido()) MT.passo = 'modelos';
  body.innerHTML = '';
  const passo = MT.passo;
  $('montTitulo').textContent = passo === 'musica' ? 'A música' : passo === 'midias' ? 'As fotos e clipes' : 'Modelos de montagem';
  if (passo === 'musica') renderMontMusica(body);
  else if (passo === 'midias') renderMontMidias(body);
  else renderMontModelos(body);
  body.scrollTop = topo;
  MT.desenhado = passo;
  // o rodapé: Voltar, o que já foi escolhido e o passo seguinte
  const m = modeloEscolhido();
  $('montRodape').classList.remove('hidden');
  $('montVoltar').classList.toggle('invisivel', passo === 'modelos');
  const seguir = $('montSeguir');
  if (passo === 'modelos' && MT.mural && MT.aba === 'comunidade') {
    $('montConta').textContent = 'Toque num modelo';
    seguir.textContent = 'Próximo';
    seguir.disabled = true;
  } else if (passo === 'modelos') {
    $('montConta').textContent = m ? m.nome : 'Escolha um modelo';
    seguir.textContent = 'Próximo';
    seguir.disabled = !m;
  } else if (passo === 'musica') {
    $('montConta').textContent = MT.musica ? semExt(nomeArq(MT.musica)) : 'Escolha a música';
    seguir.textContent = 'Próximo';
    seguir.disabled = !MT.musica;
  } else {
    $('montConta').textContent = `${MT.midias.length} de ${m.lugares}`;
    seguir.textContent = MT.enviando ? 'Enviando…' : 'Montar';
    seguir.disabled = !MT.midias.length || MT.enviando;
  }
}
function renderMontModelos(body) {
  if (MT.mural) { // com o mural ligado: os seus e os do kit, ou os da comunidade
    const abas = el('div', 'subtabs mt-abas', body);
    for (const [k, nome] of [['meus', 'Seus e do kit'], ['comunidade', 'Da comunidade']]) {
      const b = el('button', `subtab${MT.aba === k ? ' on' : ''}`, abas);
      b.type = 'button';
      b.dataset.mtAba = k;
      b.textContent = nome;
    }
    if (MT.aba === 'comunidade') { renderComunidade(body); return; }
  }
  if (S.montagem) { // numa montagem pronta: guardar ela como modelo
    const linha = el('div', 'mt-guardar', body);
    if (MT.guardando) {
      const form = el('form', 'mod-salvar', linha);
      const inp = el('input', '', form);
      inp.type = 'text'; inp.maxLength = 60; inp.placeholder = 'Nome do modelo (ex.: Viagem rápida)';
      inp.setAttribute('aria-label', 'Nome do modelo de montagem');
      const ok = el('button', 'tb-btn primary', form);
      ok.type = 'submit'; ok.textContent = 'Guardar';
      form.addEventListener('submit', (e) => { e.preventDefault(); guardaMontagem(inp.value); });
      setTimeout(() => inp.focus(), 50);
    } else {
      const b = el('button', 'tb-btn ghost mt-guardar-btn', linha);
      b.type = 'button';
      b.dataset.mtGuardar = '1';
      b.textContent = 'Guardar esta montagem como modelo';
    }
  }
  if (!MT.modelos) { el('p', 'sheet-hint', body).textContent = 'Carregando os modelos…'; return; }
  el('p', 'sheet-hint', body).textContent = S.montagem
    ? 'Outro modelo refaz a montagem inteira. Escolha um, a música e as fotos e clipes.'
    : 'Cada modelo é um ritmo: uma barra por lugar, na largura das batidas, mais alta do drop em diante. Escolha um.';
  const grid = el('div', 'cards wide mt-grade', body);
  for (const m of MT.modelos) {
    const card = el('button', `card mt-card${MT.sel === m.id ? ' on' : ''}`, grid);
    card.type = 'button';
    card.dataset.mtModelo = m.id;
    const face = el('div', 'face mt-face', card);
    capaRitmo(face, m);
    if (m.previa) { // o da biblioteca tem um vídeo de exemplo (baixado só ao tocar)
      const ver = el('span', 'c-ver', face);
      ver.dataset.mtPrevia = m.previa;
      ver.dataset.nome = m.nome;
      ver.innerHTML = ICON.play;
      ver.title = 'Ver o exemplo';
    }
    if (!m.doKit) {
      const del = el('span', 'c-del', face);
      del.dataset.mtApagar = m.id;
      del.innerHTML = ICON.remover;
      del.title = 'Apagar o modelo';
      if (MT.mural) {
        const sh = el('span', 'c-share', face);
        sh.dataset.mtCompartilhar = m.id;
        sh.innerHTML = ICON.compartilhar;
        sh.title = 'Compartilhar no mural';
      }
    }
    el('div', 'c-name', card).textContent = m.nome;
    el('div', 'c-sub', card).textContent = resumoMontagem(m);
  }
}
// o exemplo de um modelo da biblioteca: clipes grátis no lugar das fotos de quem usa, numa batida do kit
function verExemplo(pid, nome) {
  MT_PREV.pause();
  let d = $('mtExemplo');
  if (!d) {
    d = el('dialog', 'mt-exemplo', document.body);
    d.id = 'mtExemplo';
    d.addEventListener('click', (e) => { if (e.target === d) d.close(); }); // tocar fora fecha
    d.addEventListener('close', () => {
      const v = d.querySelector('video');
      if (v) { v.pause(); v.removeAttribute('src'); v.load(); } // para de baixar
    });
  }
  d.innerHTML = '';
  const topo = el('div', 'mt-exemplo-topo', d);
  el('b', null, topo).textContent = nome;
  const x = el('button', 'sh-close', topo);
  x.type = 'button';
  x.innerHTML = ICON.fechar;
  x.setAttribute('aria-label', 'Fechar o exemplo');
  x.addEventListener('click', () => d.close());
  const v = el('video', 'mt-exemplo-video', d);
  v.controls = true; v.playsInline = true; v.autoplay = true; v.muted = !!S.mudoUsuario;
  const aviso = el('p', 'sheet-hint', d);
  aviso.textContent = 'No seu vídeo, as suas fotos e vídeos entram no lugar destas imagens. A batida é do kit.';
  v.addEventListener('error', () => { aviso.textContent = 'O exemplo não baixou agora. Confira a internet e tente de novo.'; });
  v.src = `/gen/pacote-previa?id=${encodeURIComponent(pid)}`;
  d.showModal();
}
function linkExterno(host, href, texto) {
  const a = el('a', null, host);
  a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
  a.textContent = texto;
}
function renderComunidade(body) {
  const c = MT.com;
  el('p', 'sheet-hint', body).textContent = 'Modelos que outras pessoas publicaram no mural. Toque num para trazer '
    + 'para os seus; depois é só escolher a música e as fotos e clipes.';
  if (!c || (c.carregando && !c.modelos.length)) { el('p', 'sheet-hint', body).textContent = 'Carregando o mural…'; return; }
  if (c.erro && !c.modelos.length) {
    el('p', 'sheet-hint', body).textContent = `O mural não abriu: ${c.erro}.`;
    const de = el('button', 'tb-btn ghost mt-mais', body);
    de.type = 'button'; de.dataset.mtComRecarregar = '1'; de.textContent = 'Tentar de novo';
    return;
  }
  if (!c.modelos.length) { el('p', 'sheet-hint', body).textContent = 'Ninguém publicou um modelo ainda.'; return; }
  const grid = el('div', 'cards wide mt-grade', body);
  for (const m of c.modelos) {
    const card = el('div', `card mt-card mt-com${MT.pegando === m.id ? ' pegando' : ''}`, grid);
    const b = el('button', 'mt-pegar', card);
    b.type = 'button';
    b.dataset.mtPegar = m.id;
    b.disabled = !!MT.pegando;
    const face = el('div', 'face mt-face', b);
    capaRitmo(face, m);
    el('span', 'mt-fmt', face).textContent = m.formato;
    el('div', 'c-name', b).textContent = MT.pegando === m.id ? 'Trazendo…' : m.nome;
    el('div', 'c-sub', b).textContent = resumoMontagem(m);
    if (m.autor || m.post) { // quem fez e o post em que ela usou: abrem no Instagram, TikTok ou YouTube
      const quem = el('div', 'c-sub mt-quem', card);
      if (m.autor) linkExterno(quem, m.perfil, `@${m.autor}`);
      if (m.autor && m.post) quem.append(' · ');
      if (m.post) linkExterno(quem, m.post, 'ver o post');
    }
  }
  if (c.seguinte) {
    const mais = el('button', 'tb-btn ghost mt-mais', body);
    mais.type = 'button'; mais.dataset.mtComMais = '1';
    mais.textContent = c.carregando ? 'Carregando…' : 'Ver mais';
    mais.disabled = c.carregando;
  }
}
function linhaMusica(host, o) {
  const row = el('div', `tr-row mt-musica${o.on ? ' on' : ''}`, host);
  row.dataset.mtMusica = o.id;
  if (o.trilha) row.dataset.mtTrilha = o.trilha;
  if (o.previa) row.dataset.previa = o.previa;
  const tocando = MT.ouvindo === o.id && !MT_PREV.paused;
  const play = el('button', 'tr-play', row);
  play.type = 'button';
  play.dataset.act = 'ouvir';
  play.disabled = !o.previa;
  play.innerHTML = tocando ? ICON.pause : ICON.play;
  play.setAttribute('aria-label', `${tocando ? 'Parar' : 'Ouvir'} ${o.nome}`);
  const txt = el('div', 'tr-txt', row);
  el('b', null, txt).textContent = o.nome;
  el('span', null, txt).textContent = o.info;
  if (o.trilha && o.on) { // a da biblioteca vem para o projeto antes de virar a música
    const usar = el('button', 'tb-btn primary tr-usar', row);
    usar.type = 'button';
    usar.dataset.act = 'usar';
    usar.textContent = MT.baixando === o.trilha ? 'Baixando…' : 'Usar';
    usar.disabled = !!MT.baixando;
  } else if (o.on) el('span', 'mt-check', row).innerHTML = ICON.check;
}
function renderMontMusica(body) {
  el('p', 'sheet-hint', body).textContent = 'A montagem segue a batida da música. Toque numa para ouvir e escolher.';
  const lista = el('div', 'tr-lista mt-musicas', body);
  if (!MT.audios) el('p', 'sheet-hint', lista).textContent = 'Carregando…';
  else if (!MT.audios.length) el('p', 'sheet-hint', lista).textContent = 'Nenhuma música no projeto ainda.';
  for (const a of MT.audios || []) {
    linhaMusica(lista, { id: a.arquivo, nome: semExt(a.nome), info: 'no projeto', on: MT.musica === a.arquivo,
      previa: `/media/${a.arquivo.split('/').map(encodeURIComponent).join('/')}` });
  }
  const enviar = el('button', 'tb-btn ghost mt-enviar', body);
  enviar.type = 'button';
  enviar.dataset.mtEnviar = 'musica';
  enviar.innerHTML = `${ICON.enviar}<span>${doAparelho()}</span>`;
  if (!(S.trilhas || []).length) return;
  el('b', 'mt-sec', body).textContent = 'Da biblioteca';
  const bib = el('div', 'tr-lista mt-musicas', body);
  for (const p of S.trilhas) {
    linhaMusica(bib, { id: `trilha:${p.id}`, trilha: p.id, nome: p.nome, on: MT.trSel === p.id,
      info: [p.clima, fmtDur(p.duracao), p.baixado ? 'no computador' : ''].filter(Boolean).join(' · '),
      previa: p.previa ? `/gen/pacote-previa?id=${encodeURIComponent(p.id)}` : '' });
  }
}
function renderMontMidias(body) {
  const m = modeloEscolhido();
  const ops = S.montMidias || [];
  if (S.montMidias) { // o que sumiu do projeto sai da ordem
    const tem = new Set(ops.map((o) => o.midia));
    MT.midias = MT.midias.filter((k) => tem.has(k));
  }
  el('b', 'mt-sec', body).textContent = 'Formato do vídeo';
  gradeDeFormatos(body, formatoDaMontagemNova(), (k) => { MT.formato = k; renderMontagem(); });
  el('p', 'sheet-hint', body).textContent = !S.montMidias ? 'Carregando as fotos e clipes…'
    : `Toque na ordem em que elas entram. O modelo tem ${m.lugares} ${m.lugares === 1 ? 'lugar' : 'lugares'}: `
      + 'com menos fotos e clipes, eles se repetem em ordem; com mais, os que sobram ficam de fora.';
  if (ops.length > 1) {
    const acoes = el('div', 'subtabs mt-acoes', body);
    const todas = el('button', 'subtab', acoes);
    todas.type = 'button';
    todas.dataset.mtTodas = '1';
    todas.textContent = MT.midias.length === ops.length ? 'Nenhuma' : 'Todas, na ordem';
  }
  const grade = el('div', 'mod-grade troca-grade mt-midias', body);
  for (const o of ops) {
    const k = MT.midias.indexOf(o.midia);
    const b = el('button', `mod-card troca-card${k >= 0 ? ' on' : ''}`, grade);
    b.type = 'button';
    b.dataset.mtMidia = o.midia;
    const im = el('img', 'troca-img', b);
    im.loading = 'lazy'; im.alt = ''; im.draggable = false;
    im.src = quadroDaMidia(o.midia, o.tipo === 'video' ? Math.min(1, o.duracao / 2) : 0, 240);
    if (o.tipo === 'video') el('span', 'troca-dur', b).textContent = fmtShort(o.duracao);
    if (k >= 0) el('span', 'mt-ordem', b).textContent = k + 1;
    el('span', 'mod-nome', b).textContent = semExt(o.nome);
  }
  const mais = el('button', 'mod-card troca-mais', grade);
  mais.type = 'button';
  mais.dataset.mtEnviar = 'midias';
  mais.innerHTML = ICON.mais;
  el('span', 'mod-nome', mais).textContent = doAparelho();
}
const formatoDaMontagemNova = () => {
  const m = modeloEscolhido();
  return MT.formato || (S.montagem && S.formatoAtual) || (m && FORMATOS[m.formato] && m.formato) || '9:16';
};
// tocar na linha escolhe e ouve; o play só liga e desliga a prévia
function escolheMusica(row, soOuvir) {
  const id = row.dataset.mtMusica;
  const tocando = MT.ouvindo === id && !MT_PREV.paused;
  if (!soOuvir) {
    if (row.dataset.mtTrilha) MT.trSel = row.dataset.mtTrilha;
    else { MT.musica = id; MT.trSel = null; }
  }
  if (tocando && soOuvir) MT_PREV.pause();
  else if (!tocando && row.dataset.previa) {
    if (MT_PREV.dataset.id !== id) { MT_PREV.src = row.dataset.previa; MT_PREV.dataset.id = id; }
    MT_PREV.muted = !!S.mudoUsuario;
    MT.ouvindo = id;
    MT_PREV.play().catch(() => {});
  }
  renderMontagem();
}
async function baixaTrilha(id) {
  if (MT.baixando) return;
  MT.baixando = id;
  renderMontagem();
  try {
    const r = await fetch('/api/pacotes/usar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `erro ${r.status}`);
    const p = (S.trilhas || []).find((x) => x.id === id);
    if (p) p.baixado = true;
    MT.musica = d.arquivo;
    MT.trSel = null;
    await carregaMusicas();
  } catch (e) { toast(`A trilha não baixou: ${e.message}`, 3600); }
  MT.baixando = null;
  if (MT.aberto) renderMontagem();
}
// um de cada vez (o envio é um só): a foto ou o clipe que chega entra no fim da ordem; a música, escolhida
function enviaParaMontagem(arquivos, tipo) {
  MT.fila.push(...arquivos.map((f) => ({ f, tipo })));
  proximoEnvioMontagem();
}
function proximoEnvioMontagem() {
  if (upXhr || !MT.fila.length) return;
  const { f, tipo } = MT.fila.shift();
  sendVideo(f, async (res) => {
    if (tipo === 'musica') { MT.musica = res.arquivo; MT.trSel = null; await carregaMusicas(); }
    else {
      await carregaMontMidias();
      if (!MT.midias.includes(res.arquivo)) MT.midias.push(res.arquivo);
    }
    if (MT.aberto) renderMontagem();
    proximoEnvioMontagem();
  }, tipo === 'musica' ? 'musica' : 'montagem-nova', () => { MT.fila = []; });
}
function guardarComo() {
  const n = dirtyCount();
  if (n) { toast(`Salve ou descarte ${n === 1 ? 'o ajuste' : `os ${n} ajustes`} antes: o modelo sai da montagem salva.`, 4200); return; }
  if (S.savedPending) { toast('Espere o agente aplicar o último Salvar: o modelo sai da montagem como ela está no vídeo.', 4500); return; }
  MT.guardando = true;
  renderMontagem();
}
async function guardaMontagem(nome) {
  nome = String(nome || '').trim();
  if (!nome) { toast('Dê um nome ao modelo', 2200); return; }
  try {
    const r = await fetch('/api/montagens', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome }) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || `erro ${r.status}`);
    MT.guardando = false;
    MT.sel = d.modelo.id;
    await carregaMontagens();
    renderMontagem();
    const avisos = (d.avisos || []).map((a) => a.charAt(0).toUpperCase() + a.slice(1)).join('. ');
    toast(`Modelo "${d.modelo.nome}" guardado (${resumoMontagem(d.modelo)}).${avisos ? ` ${avisos}.` : ''}`, avisos ? 6500 : 3600);
  } catch (e) { toast(`Não guardei o modelo: ${e.message}`, 4500); }
}
async function apagaMontagem(id) {
  const m = (MT.modelos || []).find((x) => x.id === id);
  if (!m || !confirm(`Apagar o modelo de montagem "${m.nome}"? As montagens já feitas com ele não mudam.`)) return;
  try {
    const d = await (await fetch('/api/montagens/apagar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }) })).json();
    if (!d.ok) throw new Error(d.error || 'falhou');
    if (MT.sel === id) MT.sel = null;
    await carregaMontagens();
    renderMontagem();
  } catch (e) { toast(`Não apaguei: ${e.message}`, 3600); }
}
// o Montar: vai pelo Salvar, sozinho (a montagem nova refaz o projeto inteiro)
async function pedeMontagem() {
  const m = modeloEscolhido();
  if (!m || !MT.musica || !MT.midias.length || MT.enviando) return;
  const n = dirtyCount();
  if (n) { toast(`Salve ou descarte ${n === 1 ? 'o ajuste' : `os ${n} ajustes`} antes: a montagem nova refaz o projeto inteiro.`, 4500); return; }
  if (S.montagem && !confirm(`Montar de novo com o modelo "${m.nome}"? A montagem de agora é refeita inteira, `
    + 'com os textos e as transições do modelo.')) return;
  MT.enviando = true;
  renderMontagem();
  const usar = { modelo: m.id, musica: MT.musica, midias: [...MT.midias], formato: formatoDaMontagemNova() };
  try {
    const r = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'timeline-edits', projeto: S.projetoId, montagem: { usar } }) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || `erro ${r.status}`);
    S.savedPending = true;
    S.montagemNova = usar;
    MT.enviando = false;
    MT.passo = 'modelos'; // reabre nos modelos (guardar esta, ou outra); a música e as fotos ficam escolhidas
    fechaMontagem();
    refreshHeader();
    vazioDaMontagem();
    toast('Montagem enviada. O agente monta na batida, e o vídeo aparece aqui sozinho.', 4200);
  } catch (e) {
    MT.enviando = false;
    if (MT.aberto) renderMontagem();
    toast(`Não enviei a montagem: ${e.message}`, 4500);
  }
}
/* Formato: em pé, deitado ou quadrado, como a proporção do CapCut. O agente refaz todos os lugares
 * no quadro novo (montagem.py aplicar) e leva os textos para o mesmo lugar relativo; a foto ou o clipe
 * de formato longe do novo entra inteiro, sobre ele mesmo desfocado. */
function gradeDeFormatos(host, atual, cada) {
  const grade = el('div', 'fmt-grade', host);
  for (const [k, f] of Object.entries(FORMATOS)) {
    const b = el('button', `fmt-op${k === atual ? ' on' : ''}`, grade);
    b.type = 'button';
    b.dataset.formato = k;
    const caixa = el('span', 'fmt-caixa', b);
    const forma = el('span', 'fmt-forma', caixa);
    forma.style.aspectRatio = `${f.w} / ${f.h}`;
    forma.style[f.w >= f.h ? 'width' : 'height'] = '100%';
    el('b', 'fmt-nome', b).textContent = f.nome;
    el('span', 'fmt-uso', b).textContent = `${k} · ${f.uso}`;
    b.addEventListener('click', () => cada(k));
  }
}
function openFormato() {
  if (!S.montagem) return;
  video.pause();
  const box = $('formatoCorpo');
  box.innerHTML = '';
  const pend = S.formatoPendente && S.formatoPendente !== S.formatoAtual ? FORMATOS[S.formatoPendente] : null;
  el('p', 'sheet-hint', box).textContent = pend && S.formato === S.formatoPendente
    ? `${pend.nome} já foi salvo: o agente está refazendo o vídeo nesse formato.`
    : 'Escolha e veja a prévia no player, sem esperar. Ao salvar, o agente faz o vídeo nesse formato. A foto ou '
      + 'o clipe de outro formato entra inteiro, sobre um fundo desfocado dele mesmo; os textos vão para o mesmo lugar da tela.';
  gradeDeFormatos(box, S.formato, (k) => {
    showSheet($('formatoSheet'), false);
    if (k === S.formato) return;
    remember();
    for (const r of S.draft) { // os ajustes à mão por salvar eram do quadro de antes
      if (!r.troca || !('enq' in r.troca)) continue;
      const t = { ...r.troca };
      delete t.enq;
      r.troca = Object.keys(t).length ? t : null;
    }
    S.formato = k;
    aplicaQuadro();
    renderToolbar(); refreshHeader();
    const f = FORMATOS[k];
    toast(k === (S.formatoPendente || S.formatoAtual) ? `${f.nome} (${k}): o vídeo fica como está.`
      : `Prévia: ${f.nome} (${k}). Toque o vídeo para ver; salve para o agente fazer nesse formato.`, 3600);
  });
  showSheet($('formatoSheet'), true);
}
$('formatoOk').addEventListener('click', () => showSheet($('formatoSheet'), false));

// a Nova montagem sem vídeo: o convite é o modelo; depois do Montar, o aviso de que o agente monta
// (com o agente já trabalhando nos clipes, vale o "O agente está editando" de sempre)
function vazioDaMontagem() {
  if (S.videoDuration > 0 || S.locked || S.emptyAgente || !ehMontagem()) return;
  const montando = !!S.montagemNova;
  $('emptyIco').innerHTML = ICON.montagem;
  $('emptyAlt').classList.add('hidden');
  $('btnEmptyUpload').classList.toggle('hidden', montando);
  $('btnEmptyUpload').textContent = 'Escolher o modelo';
  $('emptyTitle').textContent = montando ? 'O agente está montando' : 'Monte um vídeo na batida';
  $('emptyText').textContent = montando
    ? 'Ele põe as fotos e clipes na batida da música. O vídeo aparece aqui sozinho quando ficar pronto.'
    : 'Escolha um modelo de montagem, a música e as fotos e clipes. O agente monta na batida.';
}
$('montClose').innerHTML = ICON.fechar;
$('montClose').addEventListener('click', fechaMontagem);
$('montVoltar').addEventListener('click', () => {
  MT.passo = MT.passo === 'midias' ? 'musica' : 'modelos';
  renderMontagem();
});
$('montSeguir').addEventListener('click', () => {
  if (MT.passo === 'modelos') {
    if (modeloEscolhido()) { MT.passo = 'musica'; renderMontagem(); }
  } else if (MT.passo === 'musica') {
    if (MT.musica) { MT_PREV.pause(); MT.passo = 'midias'; renderMontagem(); }
  } else pedeMontagem();
});
$('montCorpo').addEventListener('click', (e) => {
  const t = e.target;
  const apagar = t.closest('[data-mt-apagar]');
  if (apagar) { apagaMontagem(apagar.dataset.mtApagar); return; }
  const ver = t.closest('[data-mt-previa]');
  if (ver) { verExemplo(ver.dataset.mtPrevia, ver.dataset.nome); return; }
  // o Compartilhar abre o mural em outra aba já no gesto (sem fetch antes: nada de bloqueio de janela)
  const share = t.closest('[data-mt-compartilhar]');
  if (share) { window.open(`/api/mural/compartilhar?id=${encodeURIComponent(share.dataset.mtCompartilhar)}`, '_blank', 'noopener'); return; }
  const aba = t.closest('[data-mt-aba]');
  if (aba) {
    MT.aba = aba.dataset.mtAba;
    if (MT.aba === 'comunidade' && (!MT.com || (MT.com.erro && !MT.com.modelos.length))) carregaComunidade();
    renderMontagem();
    return;
  }
  const pegar = t.closest('[data-mt-pegar]');
  if (pegar) { pegaDoMural(pegar.dataset.mtPegar); return; }
  if (t.closest('[data-mt-com-mais]')) { carregaComunidade(true); return; }
  if (t.closest('[data-mt-com-recarregar]')) { carregaComunidade(); return; }
  const card = t.closest('[data-mt-modelo]');
  if (card) { MT.sel = card.dataset.mtModelo; renderMontagem(); return; }
  if (t.closest('[data-mt-guardar]')) { guardarComo(); return; }
  const env = t.closest('[data-mt-enviar]');
  if (env) { $(env.dataset.mtEnviar === 'musica' ? 'fileMontMusica' : 'fileMontMidia').click(); return; }
  if (t.closest('[data-mt-todas]')) {
    const ops = (S.montMidias || []).map((o) => o.midia);
    MT.midias = MT.midias.length === ops.length ? [] : [...MT.midias, ...ops.filter((k) => !MT.midias.includes(k))];
    renderMontagem();
    return;
  }
  const md = t.closest('[data-mt-midia]');
  if (md) {
    const k = md.dataset.mtMidia;
    MT.midias = MT.midias.includes(k) ? MT.midias.filter((x) => x !== k) : [...MT.midias, k];
    renderMontagem();
    return;
  }
  const row = t.closest('[data-mt-musica]');
  if (row) {
    const btn = t.closest('[data-act]');
    const act = btn ? btn.dataset.act : '';
    if (act === 'usar') baixaTrilha(row.dataset.mtTrilha);
    else escolheMusica(row, act === 'ouvir');
  }
});
['play', 'pause', 'ended'].forEach((ev) => MT_PREV.addEventListener(ev, () => { if (MT.aberto && MT.passo === 'musica') renderMontagem(); }));
MT_PREV.addEventListener('error', () => { if (MT.aberto && MT_PREV.dataset.id) toast('A prévia da música não carregou.', 2600); });
$('fileMontMidia').addEventListener('change', (e) => {
  const fs = [...(e.target.files || [])];
  e.target.value = '';
  if (fs.length) enviaParaMontagem(fs, 'midias');
});
$('fileMontMusica').addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  if (!ehAudio(f)) { toast('A música da montagem: mp3, m4a, wav, ogg, aac, opus ou flac.', 3200); return; }
  enviaParaMontagem([f], 'musica');
});

// ---------- Trecho: que parte do clipe entra no lugar ----------
/* Como o Recortar de um modelo do CapCut: a janela (a duração do lugar) fica parada no meio e a
 * tira de quadros do clipe corre por baixo, numa escala em que a janela tem tamanho de dedo; a
 * barra fina de cima é o clipe inteiro, para saltar longe num clipe comprido. O vídeo de cima toca
 * a janela em volta. Os quadros saem do servidor um a um, só os que aparecem. */
const TC = { aberto: false, uid: null, midia: '', dur: 0, lugar: 0, de: 0, arr: null, pps: 0, jan: 0, tile: 32, feitos: new Set() };
const trechoCurto = () => TC.dur <= TC.lugar + 0.02; // nem cabe: entra inteiro, mais lento (como no vídeo)
const trechoMax = () => Math.max(0, TC.dur - TC.lugar);
const segs = (s) => `${s.toFixed(1).replace('.', ',')} s`;
function openTrecho() {
  const r = S.draft[S.selected];
  if (!emLugar(r)) return;
  const a = lugarAgora(r);
  const op = opcaoDe(a.midia);
  if (!op || op.tipo !== 'video') return;
  video.pause();
  const d = draftLayout()[S.selected];
  Object.assign(TC, { aberto: true, uid: r.uid, midia: a.midia, dur: op.duracao, lugar: d.dur, arr: null, feitos: new Set() });
  TC.de = Math.min(a.de, trechoMax());
  $('trechoTitulo').textContent = `Trecho do lugar ${r.vaga}`;
  $('trechoQuadros').innerHTML = '';
  $('trechoTira').classList.toggle('curto', trechoCurto());
  const v = $('trechoVideo');
  v.src = `/gen/montagem-video?midia=${encodeURIComponent(a.midia)}`;
  v.addEventListener('loadedmetadata', () => { if (TC.aberto) { v.currentTime = TC.de; v.play().catch(() => {}); } }, { once: true });
  showSheet($('trechoSheet'), true);
  requestAnimationFrame(() => { trechoMede(); trechoDesenha(); }); // as larguras só existem com o painel aberto
}
// a escala da tira: a janela com ~1/3 dela (entre 64 e 220 px); o clipe curto cabe inteiro
function trechoMede() {
  const w = $('trechoTira').clientWidth;
  TC.jan = Math.round(Math.min(Math.max(w * 0.36, 64), 220));
  TC.pps = trechoCurto() ? w / Math.max(TC.dur, 0.01) : TC.jan / TC.lugar;
}
function trechoDesenha() {
  const curto = trechoCurto();
  const w = $('trechoTira').clientWidth;
  const jan = $('trechoJanela');
  const q = $('trechoQuadros');
  const esq = curto ? 0 : (w - TC.jan) / 2;
  const x0 = esq - (curto ? 0 : TC.de) * TC.pps; // onde o começo do clipe está, na tira
  jan.style.left = `${esq}px`;
  jan.style.width = `${curto ? TC.dur * TC.pps : TC.jan}px`;
  q.style.width = `${TC.dur * TC.pps}px`;
  q.style.transform = `translateX(${x0.toFixed(1)}px)`;
  // os quadros que aparecem (com um de folga de cada lado), cada um pedido uma vez; arrastando na
  // barra do clipe inteiro, só quando o dedo solta (senão cada ponto do caminho pediria os seus)
  const passo = TC.tile / TC.pps;
  const ultimo = Math.max(0, Math.ceil(TC.dur / passo) - 1);
  const k0 = Math.max(0, Math.floor(-x0 / TC.tile) - 1);
  const k1 = TC.arr && TC.arr.tipo === 'geral' ? -1 : Math.min(ultimo, Math.ceil((w - x0) / TC.tile) + 1);
  for (let k = k0; k <= k1; k++) {
    if (TC.feitos.has(k)) continue;
    TC.feitos.add(k);
    const im = el('img', '', q);
    im.alt = ''; im.draggable = false;
    im.style.left = `${k * TC.tile}px`;
    im.src = quadroDaMidia(TC.midia, Math.min(Math.max(0, TC.dur - 0.05), (k + 0.5) * passo), 112);
  }
  const m = $('trechoMarca');
  m.style.left = `${curto ? 0 : (TC.de / TC.dur) * 100}%`;
  m.style.width = `${curto ? 100 : (TC.lugar / TC.dur) * 100}%`;
  $('trechoVal').textContent = curto ? 'o clipe inteiro' : `${segs(TC.de)} → ${segs(TC.de + TC.lugar)}`;
  $('trechoNota').textContent = curto
    ? 'O clipe é mais curto que o lugar: entra inteiro, mais lento, e para no último quadro.'
    : 'Arraste a tira: o que fica dentro da moldura entra neste lugar, com a duração da batida.';
}
function trechoVai(de, tocar) {
  TC.de = Math.min(trechoMax(), Math.max(0, de));
  trechoDesenha();
  const v = $('trechoVideo');
  if (tocar) { v.currentTime = TC.de; v.play().catch(() => {}); } else if (!v.seeking) v.currentTime = TC.de;
}
function closeTrecho() {
  TC.aberto = false;
  TC.arr = null;
  const v = $('trechoVideo');
  v.pause();
  v.removeAttribute('src');
  v.load(); // solta o arquivo
  showSheet($('trechoSheet'), false);
}
function trechoPronto() {
  const r = tomadaPorUid(TC.uid);
  const de = +TC.de.toFixed(2);
  closeTrecho();
  if (!r) return;
  const lg = lugarDe(r) || {};
  const antes = snap(), k = trocaKey(r);
  const nova = r.troca && r.troca.midia;
  if (!nova && Math.abs(de - +(lg.de || 0)) < 0.005) r.troca = null; // o trecho de agora: como está
  else r.troca = { ...(r.troca || {}), de };
  if (trocaKey(r) === k) return;
  remember(antes);
  renderTimeline(); renderToolbar(); refreshHeader();
  toast(`Lugar ${r.vaga}: entra aos ${segs(de)} do clipe. Salve: o agente refaz só este lugar.`, 3000);
}
// a tira: arrastar corre o clipe por baixo da janela (para a esquerda, mais adiante no clipe)
$('trechoTira').addEventListener('pointerdown', (e) => {
  if (!TC.aberto || trechoCurto()) return;
  TC.arr = { tipo: 'tira', x0: e.clientX, de0: TC.de };
  try { $('trechoTira').setPointerCapture(e.pointerId); } catch (err) { /* toque sintético */ }
  $('trechoVideo').pause();
});
// a barra do clipe inteiro: tocar ou arrastar põe a janela ali
$('trechoGeral').addEventListener('pointerdown', (e) => {
  if (!TC.aberto || trechoCurto()) return;
  TC.arr = { tipo: 'geral' };
  try { $('trechoGeral').setPointerCapture(e.pointerId); } catch (err) { /* toque sintético */ }
  $('trechoVideo').pause();
  trechoGeralEm(e.clientX);
});
function trechoGeralEm(x) {
  const g = $('trechoGeral').getBoundingClientRect();
  trechoVai(((x - g.left) / g.width) * TC.dur - TC.lugar / 2, false);
}
const trechoArrasta = (e) => {
  if (!TC.arr) return;
  if (TC.arr.tipo === 'geral') trechoGeralEm(e.clientX);
  else trechoVai(TC.arr.de0 - (e.clientX - TC.arr.x0) / TC.pps, false);
};
const trechoSolta = () => {
  if (!TC.arr) return;
  TC.arr = null;
  trechoVai(TC.de, true);
};
for (const id of ['trechoTira', 'trechoGeral']) {
  $(id).addEventListener('pointermove', trechoArrasta);
  $(id).addEventListener('pointerup', trechoSolta);
  $(id).addEventListener('pointercancel', trechoSolta);
}
// o vídeo de cima toca só a janela, em volta
$('trechoVideo').addEventListener('timeupdate', () => {
  const v = $('trechoVideo');
  if (TC.aberto && !TC.arr && !trechoCurto() && v.currentTime >= TC.de + TC.lugar) v.currentTime = TC.de;
});
window.addEventListener('resize', () => { if (TC.aberto) { trechoMede(); TC.feitos.clear(); $('trechoQuadros').innerHTML = ''; trechoDesenha(); } });
$('trechoCancel').addEventListener('click', closeTrecho);
$('trechoOk').addEventListener('click', trechoPronto);

// Descartar (computador, como a desktop antiga): tudo volta ao último vídeo do agente, e se
// chegou uma versão nova ela já entra. Não tem desfazer, por isso pergunta antes.
$('btnDiscard').addEventListener('click', async () => {
  const n = dirtyCount();
  if (!n || !S.lastData) return;
  if (!confirm(`Descartar ${n} ajuste${n > 1 ? 's' : ''}? O editor volta ao último vídeo do agente, e isso não se desfaz.`)) return;
  if (S.editingNote) { S.editingNote = null; showSheet($('noteSheet'), false); }
  S.notes = [];
  S.pendingIn = null;
  S.lastSig = assinatura(S.lastData);
  await applyState(S.lastData);
  toast('Ajustes descartados', 2000);
});

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
  S.faixa = null; // a seleção em massa é da vista Final
  S.layerSel = null;
  S.insSel = -1;
  S.cenaSel = -1;
  S.zoomSel = -1;
  drawCenaBox();
  applyMute(); // o silenciar do som do vídeo vale no corte; o final já sai mixado
  setVideoSrc(v);
  renderTimeline();
  renderToolbar();
  refreshHeader();
}

// a entrega com a velocidade só vale se o agente a fez depois dos trechos e do final de agora
function entregaPronta() {
  const m = S.mtimes;
  return !!(S.state.entregaVideo && S.vel.trechos.length && m.entregaVideo
    && m.entregaVideo >= (m.velocidade || 0) && m.entregaVideo >= (m.finalVideo || 0));
}
function download() {
  const entrega = hasFinal() && entregaPronta();
  const rel = entrega ? S.state.entregaVideo : hasFinal() ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const a = document.createElement('a');
  a.href = `/media/${rel}`;
  a.download = `${(S.state.project || 'cutmind').replace(/[\\/:*?"<>|]+/g, '-')}.mp4`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(entrega ? 'Baixando o vídeo final, com a velocidade'
    : hasFinal() && S.vel.trechos.length ? 'Baixando o final SEM a velocidade: a versão acelerada ainda não ficou pronta'
      : hasFinal() ? 'Baixando o vídeo final' : 'Baixando o corte (o final ainda não existe)', 3200);
}

// ---------- enviar vídeo: vai em pedaços para a pasta dos vídeos no computador ----------
// XHR e não fetch: só ele dá o progresso do envio. O corpo é o próprio arquivo,
// sem formulário — o servidor grava direto no disco, sem passar pela memória.
let upXhr = null;
const mb = (b) => `${Math.round(b / 1e6)} MB`;
// `aoChegar`: a imagem enviada vai para quem pediu (o painel Fundo) em vez de virar camada
// `para` 'montagem': a foto ou o vídeo de um lugar (fica em midia/ e entra no lugar, sem avisar o agente);
// 'montagem-nova', uma foto ou clipe para o painel Modelos de montagem (também em midia/); 'musica', a
// música dele (o áudio já vai para midia/ sem `para`, e não vira camada). `aoFalhar`: o envio não chegou
const PARA_SERVIDOR = { montagem: 'montagem', 'montagem-nova': 'montagem' };
const CHEGOU = { montagem: 'Chegou. Entra no lugar quando você salvar.', 'montagem-nova': 'Chegou. Está na lista da montagem.',
  musica: 'Chegou. Está entre as músicas da montagem.' };
function sendVideo(file, aoChegar, para, aoFalhar) {
  if (upXhr) { toast('Já tem um envio indo — espere terminar', 2400); return; }
  const card = $('upload');
  card.className = 'upload';
  $('upName').textContent = file.name;
  $('upBar').style.width = '0%';
  $('upPct').textContent = `0% · 0 de ${mb(file.size)}`;
  $('upCancel').textContent = 'Cancelar';
  const xhr = new XMLHttpRequest();
  upXhr = xhr;
  xhr.open('POST', `/api/upload?name=${encodeURIComponent(file.name)}${S.projetoId ? `&projeto=${S.projetoId}` : ''}${PARA_SERVIDOR[para] ? `&para=${PARA_SERVIDOR[para]}` : ''}`);
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
      if (CHEGOU[para]) {
        end('done', CHEGOU[para]);
        setTimeout(() => { if (!upXhr) card.classList.add('hidden'); }, 5000);
        if (aoChegar) aoChegar(res);
        return;
      }
      const camada = res.tipo === 'imagem' || res.tipo === 'audio';
      const fundo = aoChegar && res.tipo === 'imagem';
      end('done', fundo ? 'Chegou. Está entre os fundos.' : camada ? 'Chegou. Está na linha do tempo, na agulha.' : 'Chegou no computador. O agente já foi avisado.');
      setTimeout(() => { if (!upXhr) card.classList.add('hidden'); }, 7000);
      if (fundo) { aoChegar(res); return; }
      if (camada) { addLayer(res.tipo, res.arquivo); return; }
      if (!(S.videoDuration > 0)) {
        $('emptyTitle').textContent = 'Vídeo recebido';
        $('emptyText').textContent = 'O agente já foi avisado. O corte aparece aqui sozinho quando ficar pronto.';
        $('btnEmptyUpload').textContent = 'Enviar outro';
      }
    } else {
      end('bad', res.error || `Não consegui enviar (erro ${xhr.status}).`);
      if (aoFalhar) aoFalhar();
    }
  };
  xhr.onerror = () => { end('bad', 'A conexão caiu no meio do envio. O celular e o computador ainda estão na mesma rede?'); if (aoFalhar) aoFalhar(); };
  xhr.onabort = () => { upXhr = null; card.classList.add('hidden'); toast('Envio cancelado', 2000); if (aoFalhar) aoFalhar(); };
  xhr.send(file);
}
$('upCancel').addEventListener('click', () => { if (upXhr) upXhr.abort(); else $('upload').classList.add('hidden'); });
window.addEventListener('beforeunload', (e) => { if (upXhr) { e.preventDefault(); e.returnValue = ''; } });

$('fileInput').addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (f) sendVideo(f);
});
$('btnEmptyUpload').addEventListener('click', () => (ehMontagem() ? abreMontagem() : $('fileInput').click()));
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
const TABS = [['edit', 'Edição'], ['captions', 'Legenda'], ['headline', 'Headline'], ['accent', 'Cor'], ['extras', 'Extras'], ['modelos', 'Modelos']];
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
  else if (S.styleTab === 'modelos') renderModelos(body);
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

/* Modelos de estilo (~/.cutmind/modelos, modelos.py): o visual de um vídeo com nome, para
 * outro vídeo. O cartão desenha o modelo sobre o quadro deste vídeo (filtro e ajuste pelo
 * mesmo motor do vídeo final, legenda e headline no estilo e na cor dele). Tocar mostra o
 * modelo na prévia; Aplicar leva tudo: o Estilo, e pelo Salvar o filtro e o ajuste em todas
 * as tomadas, a transição em todos os cortes e a trilha do começo ao fim. */
async function carregaModelos() {
  try { S.modelos = (await (await fetch('/api/modelos')).json()).modelos || []; } catch (e) { S.modelos = S.modelos || []; }
}
const MOD_CAPA = new Map(); // id|quadro → dataURL com o filtro e o ajuste do modelo
async function capaModelo(m) {
  if (!m.filtro && !m.ajuste) return null;
  const chave = `${m.id}|${m.filtro ? m.filtro.pacote + m.filtro.intensidade : ''}|${JSON.stringify(m.ajuste)}|${S.frameUrl.length}`;
  if (MOD_CAPA.has(chave)) return MOD_CAPA.get(chave);
  const W = 270, H = 480;
  const img = new Image();
  img.src = S.frameUrl;
  await img.decode();
  const base = document.createElement('canvas');
  base.width = W; base.height = H;
  base.getContext('2d').drawImage(img, 0, 0, W, H);
  FX.mod = FX.mod || import('/efeitos/motor.js');
  const mod = await FX.mod;
  let fonte = base;
  const gastos = [];
  try {
    if (m.filtro) {
      const ef = await mod.carregarEfeito(`/gen/pacote/${encodeURIComponent(m.filtro.pacote)}/`, { largura: W, altura: H });
      gastos.push(ef);
      ef.desenhar({ quadro: fonte, intensidade: m.filtro.intensidade });
      fonte = ef.canvas;
    }
    if (m.ajuste) {
      const aj = mod.criarAjuste({ largura: W, altura: H });
      gastos.push(aj);
      aj.desenhar({ quadro: fonte, ajustes: m.ajuste });
      fonte = aj.canvas;
    }
    const out = document.createElement('canvas');
    out.width = W; out.height = H;
    out.getContext('2d').drawImage(fonte, 0, 0);
    const url = out.toDataURL('image/jpeg', 0.82);
    MOD_CAPA.set(chave, url);
    return url;
  } catch (e) {
    return null; // pacote que não baixou: o cartão fica com o quadro limpo
  } finally {
    gastos.forEach((g) => g.destruir && g.destruir());
  }
}
const lookDoModelo = (m) => ({ ...S.style, ...m.estilo, elements: { ...defaultStyle().elements, ...(m.estilo.elements || {}) } });
function resumoModelo(m) {
  const b = [`legenda ${styleName('captions', m.estilo.captions || S.style.captions)}`];
  if (m.legenda && m.legenda.estilo && m.legenda.estilo.fonte) b.push(m.legenda.estilo.fonte);
  if (m.filtro) b.push(`filtro ${m.filtro.nome || S.fxNomes[m.filtro.pacote] || m.filtro.pacote}`);
  if (m.transicao) b.push(`transição ${m.transicao.nome || S.fxNomes[m.transicao.pacote] || ''}`.trim());
  if (m.ajuste) b.push('cor ajustada');
  if (m.trilha) b.push(`trilha ${m.trilha.nome || ''}`.trim());
  return b.join(' · ');
}
function renderModelos(body) {
  if (!S.modelos) {
    el('p', 'sheet-hint', body).textContent = 'Carregando os modelos…';
    carregaModelos().then(() => { if (S.styling && S.styleTab === 'modelos') renderStyle(); });
    return;
  }
  el('p', 'sheet-hint', body).textContent = S.modelos.length
    ? 'Toque num modelo para ver no seu vídeo. Aplicar leva o visual inteiro (legenda, headline, cor, filtro, transição e trilha).'
    : 'Guarde o visual deste vídeo com um nome (a marca de um cliente, por exemplo) e use em qualquer outro vídeo.';
  const form = el('form', `mod-salvar${S.modSalvando ? '' : ' hidden'}`, body);
  const inp = el('input', '', form);
  inp.type = 'text'; inp.maxLength = 60; inp.placeholder = 'Nome do modelo (ex.: Canal de Receitas)';
  inp.setAttribute('aria-label', 'Nome do modelo');
  const ok = el('button', 'tb-btn primary', form);
  ok.type = 'submit'; ok.textContent = 'Salvar';
  form.addEventListener('submit', (e) => { e.preventDefault(); salvaModelo(inp.value); });
  if (S.modSalvando) setTimeout(() => inp.focus(), 50);
  const grid = el('div', 'cards mods', body);
  const novo = el('button', 'card mod-novo', grid);
  novo.type = 'button';
  novo.dataset.salvarModelo = '1';
  el('div', 'face', novo).innerHTML = ICON.mais;
  el('div', 'c-name', novo).textContent = 'Salvar o estilo deste vídeo';
  for (const m of S.modelos) {
    const card = el('button', `card mod${S.modeloSel === m.id ? ' on' : ''}`, grid);
    card.type = 'button';
    card.dataset.modelo = m.id;
    const face = el('div', 'face', card);
    const frame = el('div', 'comp frame', face);
    const media = el('div', 'media', el('div', 'win', frame));
    media.style.backgroundImage = `url("${S.frameUrl}")`;
    el('div', 'band', frame);
    el('div', 'hl', frame);
    el('div', 'cap', frame);
    const look = lookDoModelo(m);
    if (m.estilo.accent) frame.style.setProperty('--hl-accent', m.estilo.accent); // a cor do modelo, só no cartão dele
    applyGeom(frame, look, 'abertura');
    fillText(frame, look, 'abertura', S.cardAnims);
    capaModelo(m).then((url) => { if (url) media.style.backgroundImage = `url("${url}")`; });
    const del = el('span', 'c-del', face);
    del.dataset.apagar = m.id;
    del.innerHTML = ICON.remover;
    del.title = 'Apagar o modelo';
    el('div', 'c-name', card).textContent = m.nome;
    el('div', 'c-sub', card).textContent = resumoModelo(m);
  }
  // a montagem na batida tem os modelos dela, num projeto próprio (o painel Modelos de montagem)
  const atalho = el('p', 'sheet-hint mt-atalho', body);
  atalho.append('Fotos e clipes na batida de uma música? ');
  const ir = el('button', 'mt-link', atalho);
  ir.type = 'button';
  ir.dataset.novaMontagem = '1';
  ir.textContent = 'Comece uma Nova montagem';
}
// o visual deste vídeo agora: o Estilo, a legenda fina e o que o vídeo usa em todas as tomadas
function capturaModelo(nome) {
  const st = S.style;
  const m = { nome, estilo: { edit: st.edit, headline: st.headline, captions: st.captions,
    accent: normHex(st.accent) || ACCENT_DEFAULT, elements: { ...st.elements } } };
  if (S.legenda && S.legenda.estilo) m.legenda = { estilo: S.legenda.estilo, acompanhar: !!S.legenda.acompanhar };
  const itens = (S.efeitos && S.efeitos.itens) || [];
  const so = (tipo) => itens.filter((x) => x.tipo === tipo);
  const umSo = (lista, chave) => lista.length && new Set(lista.map(chave)).size === 1;
  const fs = so('filtro'), ts = so('transicao'), as = so('ajuste');
  // o nome da biblioteca vai junto: noutro projeto a lista de filtros pode nem ter carregado
  const rotulo = (nome) => (nome ? { nome } : {});
  if (umSo(fs, (x) => x.pacote)) m.filtro = { pacote: fs[0].pacote, ...rotulo(S.fxNomes[fs[0].pacote]), ...(fs[0].intensidade != null ? { intensidade: fs[0].intensidade } : {}) };
  if (umSo(ts, (x) => x.pacote)) m.transicao = { pacote: ts[0].pacote, ...rotulo(S.fxNomes[ts[0].pacote]), duracao: ts[0].duracao };
  if (umSo(as, (x) => JSON.stringify(x.ajustes))) m.ajuste = as[0].ajustes;
  const trs = S.camadas.faixas.flatMap((f) => (f.tipo === 'audio' ? f.itens.filter((it) => it.trilha) : []));
  if (umSo(trs, (x) => x.trilha)) m.trilha = { pacote: trs[0].trilha, ...rotulo((S.trilhaNomes || {})[trs[0].trilha]), volume: trs[0].volume == null ? 1 : trs[0].volume };
  return m;
}
async function salvaModelo(nome) {
  nome = String(nome || '').trim();
  if (!nome) { toast('Dê um nome ao modelo', 2200); return; }
  try {
    const r = await fetch('/api/modelos', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo: capturaModelo(nome) }) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'falhou');
    S.modSalvando = false;
    S.modeloSel = null;
    await carregaModelos();
    renderStyle();
    toast(`Modelo "${d.modelo.nome}" guardado. Ele aparece aqui em qualquer projeto.`, 3200);
  } catch (e) { toast(`Não guardei o modelo: ${e.message}`, 4200); }
}
async function apagaModelo(id) {
  const m = (S.modelos || []).find((x) => x.id === id);
  if (!m || !confirm(`Apagar o modelo "${m.nome}"? Os vídeos que já usaram ele não mudam.`)) return;
  try {
    const d = await (await fetch('/api/modelos/apagar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }) })).json();
    if (!d.ok) throw new Error(d.error || 'falhou');
    if (S.modeloSel === id) S.modeloSel = null;
    await carregaModelos();
    renderStyle();
  } catch (e) { toast(`Não apaguei: ${e.message}`, 3600); }
}
// tocar no cartão: o Estilo vira o do modelo, e a prévia de cima mostra
function escolheModelo(id) {
  const m = (S.modelos || []).find((x) => x.id === id);
  if (!m) return;
  if (!S.estiloAntesDoModelo) S.estiloAntesDoModelo = JSON.parse(JSON.stringify(S.style));
  S.modeloSel = id;
  const look = lookDoModelo(m);
  S.style = { ...S.style, ...look, note: S.style.note, captionPositions: S.style.captionPositions };
  document.documentElement.style.setProperty('--hl-accent', S.style.accent || ACCENT_DEFAULT);
  for (const c of $('sheetBody').querySelectorAll('.card.mod')) c.classList.toggle('on', c.dataset.modelo === id);
  updateSummary();
  applyLive();
}
// a transição de um modelo em cada corte, cabendo entre os cortes vizinhos (o começo e o fim
// do vídeo contam): numa tomada mais curta que ela, as duas transições dessa tomada encurtam
function transicoesNosCortes(rl, dur) {
  if (!rl.length) return [];
  const cortes = rl.slice(1).map((tk) => tk.out);
  const ult = rl[rl.length - 1];
  const lim = [0, ...cortes, ult.out + ult.dur];
  return cortes.map((c, i) => ({ corte: +c.toFixed(3), duracao: +Math.min(dur, c - lim[i], lim[i + 2] - c).toFixed(3) }))
    .filter((t) => t.duracao >= 0.1);
}
// Aplicar com um modelo escolhido: o que vai pelo Salvar (efeitos e trilha) antes do Estilo
async function aplicaModeloDeEstilo(m) {
  const rl = renderedLayout();
  // a trilha baixa primeiro: é o único passo que pode falhar, e aí nada do modelo fica pela metade
  let trilha = null;
  if (m.trilha) {
    const r = await fetch('/api/pacotes/usar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: m.trilha.pacote }) });
    const d = await r.json();
    if (!r.ok) throw new Error(`a trilha não baixou: ${d.error || r.status}`);
    trilha = { arquivo: d.arquivo, dur: await midiaDuration(d.arquivo) };
  }
  if (m.filtro || m.transicao || m.ajuste || m.trilha) remember();
  if (m.filtro || m.transicao || m.ajuste) {
    const tira = new Set([m.filtro && 'filtro', m.transicao && 'transicao', m.ajuste && 'ajuste'].filter(Boolean));
    S.efeitos.itens = S.efeitos.itens.filter((x) => !tira.has(x.tipo));
    const poe = (letra, item) => S.efeitos.itens.push({ id: novoFxId(letra), ...item });
    for (const tk of rl) {
      const jan = { inicio: +tk.out.toFixed(3), duracao: +tk.dur.toFixed(3) };
      if (m.filtro) poe('f', { tipo: 'filtro', pacote: m.filtro.pacote, ...jan, ...(m.filtro.intensidade != null ? { intensidade: m.filtro.intensidade } : {}) });
      if (m.ajuste) poe('a', { tipo: 'ajuste', ...jan, ajustes: { ...m.ajuste } });
    }
    if (m.transicao) for (const t of transicoesNosCortes(rl, m.transicao.duracao)) poe('t', { tipo: 'transicao', pacote: m.transicao.pacote, ...t });
    fxPreparar();
  }
  if (trilha) {
    // a trilha da biblioteca que havia sai; a do modelo entra do começo ao fim
    S.camadas.faixas = S.camadas.faixas
      .map((f) => (f.tipo === 'audio' ? { ...f, itens: f.itens.filter((it) => !it.trilha) } : f))
      .filter((f) => f.tipo !== 'audio' || f.itens.length);
    const total = S.videoDuration || totalT();
    const dur = Math.min(trilha.dur || total, total);
    const fid = newFaixaId('a');
    S.camadas.faixas.push({ id: fid, tipo: 'audio', travado: false, mudo: false, itens: [{ id: `${fid}-1`, arquivo: trilha.arquivo,
      inicio: 0, duracao: +dur.toFixed(3), corte: 0, volume: m.trilha.volume, melhorar: false, trilha: m.trilha.pacote }] });
  }
  renderTimeline(); renderToolbar(); refreshHeader();
  if (dirtyCount()) return salvar(`Modelo "${m.nome}" aplicado. O agente refaz o vídeo com ele.`);
  return true;
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
  // aba Modelos: apagar (a lixeira do cartão), guardar este estilo, ou ver um modelo no vídeo
  const apagar = e.target.closest('[data-apagar]');
  if (apagar) { apagaModelo(apagar.dataset.apagar); return; }
  if (e.target.closest('[data-salvar-modelo]')) { S.modSalvando = true; renderStyle(); return; }
  if (e.target.closest('[data-nova-montagem]')) { // fecha o Estilo sem aplicar e vai para os Projetos
    $('sheetClose').click();
    abreProjetos().then(() => novoProjeto('montagem'));
    return;
  }
  const mod = e.target.closest('[data-modelo]');
  if (mod) { escolheModelo(mod.dataset.modelo); return; }
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
$('sheetClose').addEventListener('click', () => {
  // fechar sem aplicar: o modelo só foi visto, o Estilo volta ao de antes dele
  if (S.modeloSel && S.estiloAntesDoModelo) S.style = S.estiloAntesDoModelo;
  S.modeloSel = null;
  S.estiloAntesDoModelo = null;
  S.modSalvando = false;
  closeStyle();
});

$('sheetApply').addEventListener('click', async () => {
  const modelo = S.modeloSel ? (S.modelos || []).find((x) => x.id === S.modeloSel) : null;
  if (modelo) {
    // efeitos e trilha vão pelo Salvar (são do corte); se não deu, nada do Estilo sai sozinho
    try {
      if (!(await aplicaModeloDeEstilo(modelo))) return;
    } catch (err) { toast(`Não apliquei o modelo: ${err.message}`, 4200); return; }
  }
  const payload = {
    type: 'style-setup',
    projeto: S.projetoId,
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
    // modelo aplicado: o nome para o agente saber, e a legenda fina dele (fonte, cor, contorno)
    ...(modelo ? { modelo: { id: modelo.id, nome: modelo.nome }, ...(modelo.legenda ? { legenda: modelo.legenda } : {}) } : {}),
  };
  try {
    const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const out = await res.json();
    if (!out.ok) {
      if (out.error) { toast(`Não enviei: ${out.error}`, 4500); return; }
      throw new Error('falhou');
    }
    S.savedPending = true;
    S.modeloSel = null;
    S.estiloAntesDoModelo = null;
    closeStyle();
    refreshHeader();
    toast(modelo ? `Modelo "${modelo.nome}" aplicado. O agente refaz o vídeo com ele.` : 'Estilo enviado. O agente refaz o vídeo com ele.', 3200);
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

// ---------- salvar ajustes do corte (os campos da edição antiga do PC + take e ops) ----------
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
      ...(r.vaga != null ? { vaga: r.vaga } : {}), // sem ele, o primeiro Salvar apagaria os lugares da montagem
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
$('btnSave').addEventListener('click', () => salvar());
/* Manda ao agente tudo o que está por salvar (e as marcações). `aviso` troca a mensagem do fim
 * (a caixa de pedido tem a sua). Devolve se o servidor aceitou. */
async function salvar(aviso) {
  // o id do projeto vai junto: se outro aparelho trocou o projeto, o servidor recusa (409)
  const payload = { type: 'timeline-edits', projeto: S.projetoId };
  const soCamadas = !edlDirty() && !S.notes.length;
  if (edlDirty()) payload.edl = edlPayload();
  const comBlocos = insertsDirty();
  const comCenas = S.cenasDraft.some(cenaMudou), comZoom = zoomMudados() > 0;
  const dqs = destaquesMudados();
  const comLegenda = legendaMudou();
  const comF2 = comBlocos || comCenas || comZoom || dqs.length > 0 || comLegenda;
  if (comF2) payload.editData = {};
  if (comBlocos) { // blocos da Fase 2: todos os de cada tipo, pelo `ref`, como a desktop antiga mandava
    const de = (k) => S.insertsDraft.filter((c) => c.kind === k);
    const t = (v) => +v.toFixed(3);
    Object.assign(payload.editData, {
      inserts: de('insert').map((c) => ({ ref: c.ref, start: t(c.start), end: t(c.end) })),
      splitInserts: de('split').map((c) => ({ ref: c.ref, label: c.label, start: t(c.start), end: t(c.end) })),
      splitVideos: de('splitvideo').map((c) => ({ ref: c.ref, label: c.label, start: t(c.start), end: t(c.end) })),
      hook: de('hook').map((c) => ({ endSec: t(c.end) }))[0] || null,
      behind: de('behind').map((c) => ({ ref: c.ref, start: t(c.start), dur: t(c.end - c.start) })),
      wordAccents: de('word').map((c) => ({ ref: c.ref, text: c.label, start: t(c.start), end: t(c.end) })),
      numeros: de('numero').map((c) => ({ ref: c.ref, at: t(c.start), end: t(c.end) })),
    });
  }
  // efeitos: só os que mudaram, pelo `ref` (o agente refaz só a janela de cada um); o Fundo
  // criado aqui vai como `nova`, com a janela da tomada (o agente acrescenta em cenas[])
  if (comCenas) payload.editData.cenas = S.cenasDraft.filter(cenaMudou).map((c) => (c.nova
    ? { nova: true, tipo: c.tipo, start: c.start, end: c.end, ...cenaValor(c) }
    : { ref: c.ref, tipo: c.tipo, start: c.start, end: c.end, ...cenaValor(c) }));
  // gancho e números com texto, estilo ou lugar mudados: `alvo` hook, ou numero + ref
  if (dqs.length) payload.editData.destaques = dqs.map((c) => ({ alvo: c.tipo, ...(c.tipo === 'numero' ? { ref: c.ref } : {}), ...cenaValor(c) }));
  // zoom: a lista inteira, uma por tomada (o template usa zooms[i] quando há uma para cada)
  if (comZoom) payload.editData.camera = { zooms: S.zoomDraft.map((z) => +z.toFixed(3)), mudou: S.zoomDraft.map((z, i) => i).filter((i) => S.zoomDraft[i] !== S.zoomOrig[i]) };
  // a legenda: o estilo do painel de Texto e o acompanhar, inteiros (vão para `captions` no
  // edit-data); `tempos`, os pedaços arrastados no tempo (legenda_tempos.py no captions.json)
  if (comLegenda) {
    const tempos = temposLegenda();
    payload.editData.legenda = { estilo: S.legenda.estilo || null, acompanhar: !!S.legenda.acompanhar, ...(tempos.length ? { tempos } : {}) };
  }
  if (camadasDirty()) payload.camadas = camadasParaSalvar();
  const comEfeitos = efeitosDirty();
  if (comEfeitos) payload.efeitos = S.efeitos;
  // a velocidade do vídeo final: a lista inteira, e a duração do final em que foi marcada
  // (corte refeito depois = outra duração: o velocidade_final.py para antes de aplicar)
  const comVel = velDirty();
  if (comVel) payload.velocidade = { versao: 1, duracao: +fimFinal().toFixed(3), trechos: S.vel.trechos };
  // Melhorar voz: a Voz e o Fundo escolhidos, ou {desligar}; o agente aplica no cut.mp4
  const comVoz = melhorarDirty();
  if (comVoz) payload.melhorar = S.melhorar;
  // os lugares da montagem trocados: o agente refaz só eles (montagem.py aplicar)
  // e o formato novo: o agente refaz todos os lugares no quadro dele
  const lugares = lugaresMudados();
  const comFormato = formatoMudou();
  if (lugares.length || comFormato) {
    payload.montagem = { lugares: lugares.map(pedidoDoLugar), ...(comFormato ? { formato: S.formato } : {}) };
  }
  if (S.notes.length) {
    payload.notes = S.notes.map((n) => ({
      start: +n.start.toFixed(3),
      end: +n.end.toFixed(3),
      renderedStart: +draftToRendered(n.start).toFixed(3),
      renderedEnd: +draftToRendered(n.end).toFixed(3),
      phase: S.view === 'final' ? 2 : 1,
      text: n.text,
      ...(n.geral ? { geral: true } : {}), // pedido da caixa: sem trecho, só a agulha de referência
    }));
  }
  try {
    const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const out = await res.json();
    if (!out.ok) {
      // camada recusada pelo servidor: o motivo vale mais que o aviso genérico
      if (out.error) { toast(`Não salvei: ${out.error}`, 4500); return false; }
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
    S.velBase = velSig();
    if (comFormato) S.formatoPendente = S.formato === S.formatoAtual ? null : S.formato; // o servidor guarda o mesmo
    if (comVoz) { S.melhorarBase = JSON.stringify(S.melhorar); vozCarregaInfo().then(() => renderTimeline()); }
    S.faixa = null;
    S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
    S.cenasDraft = S.cenasDraft.filter((c) => !(c.nova && !c.orig && c.desligada)); // o Fundo novo desligado não foi a lugar nenhum
    S.cenasDraft.forEach((c) => { c.orig = cenaValor(c); });
    listaDestaques().forEach((c) => { c.orig = cenaValor(c); });
    if (S.zoomDraft) S.zoomOrig = [...S.zoomDraft];
    // sem isto a legenda salva seguia "mudada": o Salvar 1 não saía e a versão nova do agente não entrava
    if (S.legenda) S.legendaOrig = JSON.parse(JSON.stringify(S.legenda));
    S.selected = -1;
    S.layerSel = null;
    S.fxSel = null;
    S.insSel = -1;
    S.cenaSel = -1;
    S.zoomSel = -1;
    drawCenaBox();
    forgetHistory(); // o que foi enviado ao agente não se desfaz daqui
    renderTimeline(); renderToolbar(); refreshHeader();
    const oque = comEfeitos ? (comCamadas ? 'Camadas e efeitos salvos' : 'Efeitos salvos') : 'Camadas salvas';
    const soVoz = comVoz && soCamadas && !comF2 && !comVel && !comCamadas && !comEfeitos;
    const soLugares = lugares.length > 0 && soCamadas && !comF2 && !comVel && !comCamadas && !comEfeitos && !comVoz;
    toast(aviso || (soVoz ? 'Melhorar voz enviado. O agente aplica a voz no vídeo.'
      : soLugares ? `${lugares.length > 1 ? `${lugares.length} lugares enviados` : 'Lugar enviado'}. O agente refaz só ${lugares.length > 1 ? 'eles' : 'ele'}, na batida.`
      : lugares.length && soCamadas && !comF2 && !comVel ? 'Lugares e camadas enviados. O agente refaz a montagem na batida.'
      : !soCamadas ? 'Ajustes enviados. O agente refaz o corte.'
      : comF2 ? 'Ajustes enviados. O agente refaz só os trechos do vídeo final que mudaram.'
        : comVel && !comCamadas && !comEfeitos ? 'Velocidade salva. O agente faz o vídeo de entrega com ela.'
          : `${oque}. O agente põe no vídeo final.`), 3000);
    return true;
  } catch (err) {
    toast('Não consegui salvar — o editor ainda está ligado no computador?', 4000);
    return false;
  }
}

// ---------- pedido ao agente: a caixa "O que você quer mudar?" (computador) ----------
/* Um pedido em texto livre, sem trecho marcado. Vai como uma marcação `geral` na posição da
 * agulha, junto com o que estiver por salvar: o mesmo caminho do Salvar, que o agente já lê. */
$('pedido').addEventListener('submit', async (e) => {
  e.preventDefault();
  const campo = $('pedidoTexto'), txt = campo.value.trim();
  if (!txt) { toast('Escreva o que mudar', 1800); campo.focus(); return; }
  const id = `p${Date.now()}`;
  S.notes.push({ id, start: S.t, end: S.t, text: txt, geral: true });
  if (await salvar('Pedido enviado. O agente responde na barra de cima.')) {
    campo.value = '';
    crescePedido();
    const h = new Date();
    $('pedidoInfo').textContent = `Enviado às ${h.getHours()}:${String(h.getMinutes()).padStart(2, '0')}. A resposta aparece na barra de cima.`;
  } else S.notes = S.notes.filter((n) => n.id !== id); // não foi: o texto fica na caixa para tentar de novo
});
$('pedidoTexto').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $('pedido').requestSubmit(); }
});
// uma linha parada; cresce com o texto até o teto do CSS (o resto rola dentro)
function crescePedido() {
  const c = $('pedidoTexto');
  c.style.height = '';
  if (c.value) c.style.height = `${Math.min(c.scrollHeight + 2, 120)}px`;
}
$('pedidoTexto').addEventListener('input', crescePedido);

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
  if (S.camadas.faixas.some((f) => f.tipo === 'texto')) CutMindFontes.carregarTodas(); // os textos aparecem com a fonte de verdade
  applyMute();
  // trilha da biblioteca aparece pelo nome do catálogo, não pelo nome do arquivo
  if (!S.trilhas && S.camadas.faixas.some((f) => f.itens.some((it) => it.trilha))) loadTrilhas().then(renderTimeline);
  carregaBatidas();
}

// ---------- batidas das músicas: as marcas e o ímã da linha do tempo ----------
/* O servidor tira a grade de cada música das camadas (batida.py, num processo à parte, uma vez
 * por música; na 1ª vez baixa o modelo). Enquanto calcula, o editor pergunta a cada 2 s. */
function carregaBatidas() {
  for (const f of S.camadas.faixas) {
    if (f.tipo !== 'audio') continue;
    for (const it of f.itens) if (!S.batidas[it.arquivo]) pedeBatida(it.arquivo, 0);
  }
}
async function pedeBatida(arq, vez) {
  S.batidas[arq] = S.batidas[arq] || { estado: 'calculando' };
  let j = null;
  try { j = await (await fetch(`/api/batida?arquivo=${encodeURIComponent(arq)}`)).json(); } catch (e) { /* tenta de novo */ }
  if (j && (j.estado === 'pronta' || j.estado === 'falhou')) {
    S.batidas[arq] = j;
    if (j.estado === 'pronta') renderTimeline();
    return;
  }
  if (vez < 150) setTimeout(() => pedeBatida(arq, vez + 1), 2000); // calculando ou na fila
  else S.batidas[arq] = { estado: 'falhou', erro: 'a análise da batida demorou demais' };
}
/* As batidas das músicas das camadas no tempo da linha do tempo, com o tempo forte marcado. Fica de
 * fora a faixa silenciada e a música de batida irregular (confiança baixa): ali o ímã mais
 * atrapalharia do que ajudaria. */
function batidasNaLinha() {
  const out = [], dl = draftLayout(), rl = renderedLayout();
  for (const f of S.camadas.faixas) {
    if (f.tipo !== 'audio' || f.mudo) continue;
    for (const it of f.itens) {
      const g = S.batidas[it.arquivo];
      if (!g || g.estado !== 'pronta' || g.confianca === 'baixa') continue;
      const fortes = new Set((g.fortes || []).map((x) => x.toFixed(3)));
      for (const b of g.batidas || []) {
        if (b < it.corte - 1e-6 || b > it.corte + it.duracao + 1e-6) continue;
        out.push({ t: renderedToDraft(it.inicio + (b - it.corte), dl, rl), forte: fortes.has(b.toFixed(3)), it: it.id });
      }
    }
  }
  return out.sort((a, b) => a.t - b.t);
}
const IMA_PX = () => (isDesk() ? 8 : 14); // o alcance do ímã na tela: o dedo é menos preciso que o mouse
/* O ímã: a batida mais perto de t (tempo da linha do tempo), se estiver a poucos pixels; senão o
 * próprio t. `exceto` deixa de fora as batidas do item que está sendo arrastado: grudar a música
 * nela mesma não faz sentido. */
function imaGruda(t, exceto) {
  if (!S.ima || !S.grade.length) return t;
  let melhor = t, d0 = IMA_PX() / S.pps;
  for (const g of S.grade) {
    if (exceto && g.it === exceto) continue;
    const d = Math.abs(g.t - t);
    if (d <= d0) { d0 = d; melhor = g.t; }
  }
  return melhor;
}
// o celular vibra de leve quando grudou numa batida nova (e não a cada quadro em que continua grudado)
function imaSinal(grudou) {
  if (grudou != null && grudou !== S.imaUltima && navigator.vibrate) navigator.vibrate(8);
  S.imaUltima = grudou;
}
// um ponto só (a agulha, uma ponta): o tempo grudado, ou o próprio
function imaPonto(t, exceto) {
  const a = imaGruda(t, exceto);
  imaSinal(a !== t ? a : null);
  return a;
}
// um item inteiro sendo levado: a ponta mais perto de uma batida gruda; devolve quanto ele anda (0 se nada)
function imaDesloca(pontas, exceto) {
  let melhor = 0, dist = Infinity;
  for (const p of pontas) {
    const a = imaGruda(p, exceto);
    if (a !== p && Math.abs(a - p) < dist) { dist = Math.abs(a - p); melhor = a - p; }
  }
  imaSinal(melhor ? pontas[0] + melhor : null);
  return melhor;
}
function alternaIma() {
  S.ima = !S.ima;
  gravaPref('cutmind.ima', S.ima ? '1' : '0');
  syncIma();
  toast(S.ima ? 'Ímã ligado: a agulha e as pontas grudam na batida da música' : 'Ímã desligado', 2200);
}
function syncIma() {
  const b = $('btnIma');
  if (!b) return;
  b.classList.toggle('on', S.ima);
  b.setAttribute('aria-pressed', String(S.ima));
  const n = S.grade.length;
  b.title = S.ima
    ? `Ímã ligado (N): a agulha e as pontas grudam na batida${n ? '' : '. Ainda não tem música com batida no projeto'}`
    : 'Ímã desligado (N): ligue para a agulha e as pontas grudarem na batida da música';
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
  if (tipo === 'audio') carregaBatidas(); // a música nova ganha as marcas de batida quando a grade sai
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
  track.classList.toggle('oculto', f.tipo !== 'audio' && f.oculto);
  track.classList.toggle('travado', f.travado);
  for (const it of f.itens) {
    const a = renderedToDraft(it.inicio), b = renderedToDraft(it.inicio + it.duracao);
    const chip = el('div', `chip layer ${f.tipo === 'audio' ? 'aud' : f.tipo === 'texto' ? 'txt' : 'img'}${it.trilha ? ' mus' : ''}`, lane);
    chip.dataset.id = it.id;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps, 8)}px`;
    if (f.tipo === 'texto') { // a 1ª linha do texto, e as marcas de atrás e acompanhar
      el('span', 'l-ico', chip).innerHTML = ICON.texto;
      const linha = String(it.texto).split('\n')[0].slice(0, 60) || 'Texto';
      el('span', 'l-name', chip).textContent = it.nome ? `${it.nome}: ${linha}` : linha; // o do modelo diz qual é
      if (it.atras) el('span', 'l-tag', chip).innerHTML = ICON.pessoa;
      if (it.acompanhar) el('span', 'l-tag', chip).innerHTML = ICON.alvo;
      if (it.id === S.layerSel) {
        chip.classList.add('sel');
        el('div', 'lh l', chip).dataset.side = 'l';
        el('div', 'lh r', chip).dataset.side = 'r';
      }
      continue;
    }
    if (f.tipo === 'imagem') {
      const im = el('img', 'l-thumb', chip);
      im.src = `/media/${it.arquivo}`;
      im.alt = '';
      im.draggable = false;
    } else {
      el('span', 'l-ico', chip).innerHTML = ICON.audio;
      const g = S.batidas[it.arquivo];
      if (g && g.estado === 'pronta' && g.confianca !== 'baixa') pontosDeBatida(chip, it, g, a);
    }
    el('span', 'l-name', chip).textContent = it.trilha ? (S.trilhaNomes[it.trilha] || it.trilha) : nomeMidia(it.arquivo);
    if (it.melhorar) el('span', 'l-tag', chip).innerHTML = ICON.melhorar;
    if (it.atras) el('span', 'l-tag', chip).innerHTML = ICON.pessoa;
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
// os pontos das batidas em cima do bloco da música, maiores no tempo forte (como no CapCut); com o
// zoom baixo, só os tempos fortes, e nenhum se eles também colarem
function pontosDeBatida(chip, it, g, a) {
  const bs = (g.batidas || []).filter((b) => b >= it.corte - 1e-6 && b <= it.corte + it.duracao + 1e-6);
  if (bs.length < 2) return;
  const passo = ((bs[bs.length - 1] - bs[0]) / (bs.length - 1)) * S.pps;
  if (passo * 4 < 5) return;
  const fortes = new Set((g.fortes || []).map((x) => x.toFixed(3)));
  const box = el('div', 'l-bat', chip), dl = draftLayout(), rl = renderedLayout();
  for (const b of bs) {
    const forte = fortes.has(b.toFixed(3));
    if (passo < 5 && !forte) continue;
    el('i', forte ? 'f' : '', box).style.left = `${(renderedToDraft(it.inicio + (b - it.corte), dl, rl) - a) * S.pps}px`;
  }
}
function tapLayer(id) {
  const hit = camItem(id);
  if (!hit) return;
  if (hit.f.travado) { toast('Camada travada: toque no cadeado para soltar', 2200); return; }
  S.layerSel = S.layerSel === id ? null : id;
  S.selected = -1;
  S.insSel = -1;
  S.cenaSel = -1; S.zoomSel = -1; drawCenaBox();
  // um texto escolhido com a agulha fora dele: ela vai para dentro, e o texto aparece pronto para arrastar
  if (S.layerSel && hit.f.tipo === 'texto') {
    const rt = draftToRendered(S.t), it = hit.it;
    if (!(rt >= it.inicio && rt < it.inicio + it.duracao)) {
      video.pause(); S.t = clampT(renderedToDraft(it.inicio + Math.min(0.5, it.duracao / 2))); positionTimeline(); preciseSeek();
    }
  }
  renderTimeline();
  renderToolbar();
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('.th-b');
  if (!b) return;
  const act = b.dataset.act;
  if (act === 'jcut') { // só mostra ou esconde: não é edição, não entra no desfazer
    S.jcutOpen = !S.jcutOpen;
    gravaPref('cutmind.jcutOpen', S.jcutOpen ? '1' : '0');
    renderTimeline();
    return;
  }
  remember();
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
  G.ultX = x;
  bordaRola();
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
  let dt = (x - L.x0) / S.pps;
  const fim = S.videoDuration || totalT();
  // o ímã: a ponta que anda (ou a mais perto, levando o item inteiro) gruda na batida da música. Só
  // mexe quando grudou: a ida e volta entre o relógio do corte e o da linha do tempo não é exata
  // num trecho aparado, e o item pularia sem batida nenhuma perto
  const gruda = (r) => {
    const a = renderedToDraft(r), b = imaPonto(a, it.id);
    return b === a ? 0 : draftToRendered(b) - r;
  };
  if (L.kind === 'move') {
    const s = o.inicio + dt, a = renderedToDraft(s);
    const desl = imaDesloca([a, renderedToDraft(s + o.duracao)], it.id);
    if (desl) dt += draftToRendered(a + desl) - s;
    it.inicio = +Math.max(0, Math.min(o.inicio + dt, fim - 0.2)).toFixed(3);
  } else if (L.side === 'r') {
    dt += gruda(o.inicio + o.duracao + dt);
    let d = Math.max(0.2, o.duracao + dt);
    const tot = aud && S.midiaDur[it.arquivo];
    if (tot) d = Math.min(d, tot - it.corte);
    it.duracao = +d.toFixed(3);
  } else { // a ponta esquerda anda; a direita fica onde está
    dt += gruda(o.inicio + dt);
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
  S.selected = -1; S.layerSel = null; S.fxSel = null; S.cenaSel = -1; S.zoomSel = -1;
  const b = S.insertsDraft[S.insSel];
  // fora do bloco, ou na entrada/saída dele (o texto ainda surgindo): a agulha vai para o meio
  if (b && destaqueDoBloco(b) && !(S.t >= b.start + 0.35 && S.t < b.end - 0.35)) {
    video.pause(); S.t = clampT(b.start + (b.end - b.start) * 0.6); positionTimeline(); preciseSeek();
  }
  renderTimeline();
  renderToolbar();
  drawCenaBox();
}
function startInsDrag(x, kind, side) {
  const c = S.insertsDraft[S.insSel];
  if (!c || S.view !== 'final' || (kind === 'move' && c.kind === 'hook')) return false;
  G.mode = 'ins';
  G.ins = { i: S.insSel, kind, side, x0: x, c0: { start: c.start, end: c.end }, before: snap() };
  video.pause();
  G.ultX = x;
  bordaRola();
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

// ---------- efeitos e zoom do agente na linha do tempo (vista Final) ----------
/* Tudo o que o agente pôs no vídeo final aparece numa faixa e se ajusta sem conversa.
 * Cada efeito (`cenas[]` do edit-data.json) liga e desliga, tem o texto trocado e o bloco
 * (texto, cartão, celular) arrastado sobre o vídeo — ou empurrado pelas setas, 2 px por
 * toque. O tempo de um efeito segue a tomada (o recorte da pessoa nasce no começo dela):
 * ele não anda nem apara. O zoom de cada tomada (`camera.zooms`) sobe e desce. A prévia
 * continua sendo o vídeo de agora: a moldura mostra para onde o bloco vai, e o Salvar
 * leva as mudanças pelo `ref` para o agente refazer só os trechos tocados. */
const CENA_NOME = {
  fundo: 'Fundo', corteZoom: 'Corte no zoom', revelacao: 'Revelação', papel: 'Recorte de papel', mural: 'Mural', parede: 'Parede de fotos',
  capa: 'Capa de revista', grafico: 'Gráfico', app: 'App', checklist: 'Checklist', zoomDigital: 'Zoom digital',
  saindo: 'Saindo da tela', rabisco: 'Rabisco', vertigem: 'Vertigem', celular: 'Celular', vidro: 'Vidro', orbita: 'Órbita', chroma: 'Site',
};
// o véu e o desfoque do Fundo quando o item não diz (src/cenas/fundo.tsx): mudou lá, muda aqui
const FUNDO_PADRAO = { escurecer: 0.25, desfoque: 0 };
// os campos de texto que a pessoa pode trocar (texto solto ou uma lista de linhas)
const CENA_TEXTOS = { titulo: 'Título', pergunta: 'Pergunta', frase: 'Frase', palavra: 'Palavra', pequeno: 'Faixa de cima',
  gigante: 'Palavra grande', etiqueta: 'Etiqueta', botao: 'Botão', nome: 'Nome', batidas: 'Palavras (uma por batida)',
  text: 'Texto', prefixo: 'Antes do número', valor: 'Número', sufixo: 'Depois do número', rotulo: 'Linha de baixo' };
const linhasDe = (v) => (Array.isArray(v) ? v : [v || '']).map(String);
const maisLonga = (v) => linhasDe(v).reduce((a, s) => (s.length > a.length ? s : a), '');
const largo = (s, px) => Math.min(1040, Math.max(160, String(s || '').length * px));
/* O bloco que se arrasta em cada efeito, em px do quadro 1080x1920: centro padrão e tamanho.
 * O centro espelha o padrão do componente (src/cenas/*.tsx, `centro(c, [x, y])`): mudou lá,
 * muda aqui. Nos efeitos que tiram a pessoa do fundo, o padrão é o `layout` que o helper mediu
 * na pessoa (cenas.py); os números fixos são só a reserva do componente para um item sem ele.
 * O tamanho é só a moldura que a pessoa pega. Efeito sem bloco móvel não entra. */
const lay = (c) => c.layout || {};
const CENA_BLOCO = {
  // a palavra de vidro é esticada até `largura` (textLength no vidro.tsx), qualquer que seja o tamanho dela
  vidro: (c) => { const tam = lay(c).tamanho ?? 300; return { x: 540, y: lay(c).y ?? 700, w: c.largura ?? 1000, h: tam * 0.74 }; },
  zoomDigital: (c, t) => ({ x: 540, y: c.y ?? 960, w: largo(maisLonga(t.batidas), (c.tamanho ?? 330) * 0.42), h: (c.tamanho ?? 330) * 0.74 }),
  parede: (c, t) => { const b = lay(c).bloco || { x: 540, y: 245 }; return { x: b.x, y: b.y, w: Math.max(largo(t.gigante, 116), largo(t.pequeno, 30)), h: 316 }; },
  capa: (c) => { const tam = lay(c).tamanho ?? 330; return { x: 540, y: (lay(c).baseline ?? 690) - tam * 0.355, w: c.largura ?? 1010, h: tam * 0.72 }; },
  grafico: (c, t) => { const b = lay(c).bloco || { x: 751, y: 411 }; return { x: b.x, y: b.y, w: largo(t.etiqueta || 'ESCALA', 42) + 128, h: 130 }; },
  chroma: (c) => { const b = lay(c).bloco || { x: 514, y: 590 }; return { x: b.x, y: b.y, w: 900, h: 680 }; },
  papel: (c, t) => ({ x: 540, y: 268, w: largo(maisLonga(t.frase), 96), h: 296 }),
  rabisco: (c, t) => ({ x: 540, y: 184, w: largo(t.frase, 48), h: 124 }),
  checklist: (c) => ({ x: 540, y: (c.top ?? 108) + 234, w: 908, h: 468 }),
  celular: () => ({ x: 778, y: 795, w: 452, h: 930 }),
  orbita: (c, t) => ({ x: 540, y: 252, w: largo(maisLonga(t.titulo), 46), h: 104 * linhasDe(t.titulo).length }),
  saindo: (c, t) => ({ x: 540, y: 213, w: largo(t.titulo, 66), h: 150 }),
  vertigem: (c, t) => ({ x: 540, y: 226, w: largo(t.pergunta, 70), h: 132 }),
  hook: (c) => {
    const g = GANCHO[c.style] || GANCHO.outline, h = 2 * g.cap * (c.lineHeight ?? g.lh);
    return { x: 540, y: (c.paddingTop ?? g.top) + h / 2, w: c.safeWidth ?? g.w, h };
  },
  numero: (c) => { const h = 190 + (c.rotulo ? 10 + 48 * 1.15 : 0); return { x: 540, y: 230 + h / 2, w: 860, h }; },
};
/* O texto de destaque de cada efeito: o padrão do componente (src/cenas/*.tsx, `estiloDe(c, {...})`:
 * mudou lá, muda aqui), o que o painel de Texto deixa mudar (`sem`/`so`), o tamanho da letra no
 * quadro (`px`), a largura fixa quando o texto é esticado (`esticar`) e o que aparece escrito. */
const CENA_ESTILO = {
  vidro: { fonte: 'poppins', contorno: 6, corContorno: '#ffffff', sem: ['cor'], px: (c) => lay(c).tamanho ?? 300, esticar: (c) => c.largura ?? 1000, linhas: (t) => [t.palavra || 'GARGALO'] },
  zoomDigital: { fonte: 'bebas', cor: (c) => c.cor || '#ffe500', contorno: 8, corContorno: '#000000', px: (c) => c.tamanho ?? 330, linhas: (t) => [maisLonga(t.batidas)] },
  parede: { fonte: 'anton', cor: '#ff5200', contorno: 10, corContorno: '#ffffff', px: () => 230, linhas: (t) => [t.gigante || ''] },
  capa: { fonte: 'playfair', cor: (c) => c.cor || '#b0101b', contorno: 0, corContorno: '#000000', px: (c) => lay(c).tamanho ?? 330, esticar: (c) => c.largura ?? 1010, linhas: (t) => [t.nome || 'EQUIPE'] },
  grafico: { fonte: 'poppins', cor: '#063322', contorno: 0, corContorno: '#ffffff', px: () => 52, linhas: (t) => [t.etiqueta || 'ESCALA'] },
  chroma: { fonte: 'poppins', cor: '#ffffff', contorno: 0, corContorno: '#3a0ca3', px: () => 94, linhas: (t) => [t.titulo || ''] },
  papel: { so: ['tamanho'], cor: '#ffffff', contorno: 4, corContorno: '#000000', px: () => 109, linhas: (t) => linhasDe(t.frase) },
  rabisco: { fonte: 'caveat', cor: '#fdfdf8', contorno: 0, corContorno: '#000000', px: () => 112, linhas: (t) => [t.frase || ''] },
  orbita: { fonte: 'instrument', cor: '#ffffff', contorno: 0, corContorno: '#000000', px: () => 104, linhas: (t) => linhasDe(t.titulo) },
  saindo: { fonte: 'bebas', cor: (c) => c.cor || '#c6ff3d', contorno: 0, corContorno: '#000000', px: () => 150, linhas: (t) => [t.titulo || ''] },
  vertigem: { fonte: 'oswald', cor: '#ffffff', contorno: 0, corContorno: '#000000', px: () => 132, linhas: (t) => [t.pergunta || ''] },
  // o gancho (Main.tsx, HookInner) e o número (CustomGraphics, NumeroNaTela): o padrão de cada estilo
  hook: { fonte: 'poppins', cor: (c) => (['misto', 'realce'].includes(c.style) ? '#ff5200' : '#ffffff'),
    contorno: (c) => ((c.style || 'outline') === 'outline' ? c.strokePx ?? 7 : 0), corContorno: '#000000',
    px: (c) => GANCHO[c.style] ? GANCHO[c.style].cap : GANCHO.outline.cap, linhas: (t) => duasLinhas(t.text || ''),
    corDaLinha: (i, e, c) => (c.style === 'misto' && i === 0 ? '#ffffff' : c.style === 'realce' ? '#ffffff' : e.cor) },
  numero: { fonte: 'poppins', cor: '#ff5200', contorno: 8, corContorno: '#000000', px: () => 190,
    linhas: (t) => [`${t.prefixo || ''}${t.valor || ''}${t.sufixo || ''}`] },
};
// os estilos do gancho (HL_STYLES em Main.tsx): o teto da letra, a largura, a linha e o topo
const GANCHO = { outline: { cap: 51, w: 900, lh: 1.02, top: 330 }, card: { cap: 46, w: 820, lh: 1.06, top: 120 },
  realce: { cap: 48, w: 830, lh: 1.04, top: 300 }, misto: { cap: 55, w: 900, lh: 0.98, top: 300 } };
// as duas linhas do gancho, partidas no meio pelo número de letras (o render parte pela largura medida)
function duasLinhas(txt) {
  const ps = String(txt).trim().split(/\s+/).filter(Boolean);
  if (ps.length < 2) return [ps.join(' ')];
  let melhor = 1, dif = Infinity;
  for (let i = 1; i < ps.length; i++) {
    const d = Math.abs(ps.slice(0, i).join(' ').length - ps.slice(i).join(' ').length);
    if (d < dif) { dif = d; melhor = i; }
  }
  return [ps.slice(0, melhor).join(' '), ps.slice(melhor).join(' ')];
}
// o estilo que vale agora: o escolhido no painel por cima do padrão do efeito
function estiloEfetivo(c) {
  const d = c && CENA_ESTILO[c.tipo];
  if (!d) return null;
  const val = (x) => (typeof x === 'function' ? x(c.cena) : x);
  const e = c.estilo || {};
  const fonte = e.fonte ? CutMindFontes.familiaDe(e.fonte) : d.fonte ? CutMindFontes.familiaDe(d.fonte) : null;
  return {
    fonte,
    peso: +e.peso || (fonte ? CutMindFontes.pesoDe(fonte) : 400),
    italico: !e.fonte && d.fonte === 'instrument',
    cor: e.cor || val(d.cor) || '#ffffff',
    tamanho: +e.tamanho > 0 ? +e.tamanho : 1,
    contorno: e.contorno != null ? +e.contorno : +val(d.contorno) || 0,
    corContorno: e.corContorno || val(d.corContorno) || '#000000',
  };
}
// o que a pessoa muda num efeito, copiado (foto do desfazer, `orig`, o que vai no Salvar).
// Funções declaradas (e não const): o cabeçalho e o desfazer as chamam antes desta linha rodar
function cenaValor(v) {
  const est = v.estilo && typeof v.estilo === 'object' && Object.keys(v.estilo).length ? JSON.parse(JSON.stringify(v.estilo)) : null;
  const out = { desligada: !!v.desligada, texto: v.texto ? { x: +v.texto.x, y: +v.texto.y } : null, textos: JSON.parse(JSON.stringify(v.textos || {})), estilo: est };
  // só o Fundo tem `campos`: a imagem, o véu e o desfoque (os outros efeitos saem como sempre saíram)
  if (v.campos) out.campos = { fundo: String(v.campos.fundo), escurecer: +v.campos.escurecer, desfoque: +v.campos.desfoque };
  return out;
}
function cenaValores(c) {
  const textos = {};
  for (const k of Object.keys(CENA_TEXTOS)) {
    const v = c[k];
    if (typeof v === 'string') textos[k] = v;
    else if (k !== 'batidas' && Array.isArray(v) && v.every((x) => typeof x === 'string')) textos[k] = [...v];
  }
  if (Array.isArray(c.batidas)) textos.batidas = c.batidas.map((b) => String((b && b.palavra) || ''));
  const t = c.texto;
  return cenaValor({ desligada: c.desligada, texto: t && isFinite(t.x) && isFinite(t.y) ? t : null, textos, estilo: c.estilo,
    campos: c.tipo === 'fundo' ? { fundo: c.fundo || '', escurecer: c.escurecer ?? FUNDO_PADRAO.escurecer, desfoque: c.desfoque ?? FUNDO_PADRAO.desfoque } : null });
}
// um Fundo criado no editor, copiado para o desfazer: o item inteiro, porque ele entra e sai da lista
function copiaNova(c) { return { ...c, ...cenaValor(c), cena: { ...c.cena }, orig: c.orig ? cenaValor(c.orig) : null }; }
function cenaSig(v) { return JSON.stringify([!!v.desligada, v.texto || null, v.textos, v.estilo || null, v.campos || null]); }
// o Fundo criado no editor (`nova`) e nunca salvo é uma mudança enquanto está ligado; desligado, não é nada
function cenaMudou(c) { return c.nova && !c.orig ? !c.desligada : cenaSig(c) !== cenaSig(c.orig); }
function zoomMudados() { return S.zoomDraft ? S.zoomDraft.filter((z, i) => z !== S.zoomOrig[i]).length : 0; }
function buildCenasDraft(d) {
  S.cenasDraft = (d.cenas || []).map((c, i) => {
    const v = cenaValores(c);
    return { ref: i, tipo: c.tipo, start: +c.start, end: +c.end, nome: CENA_NOME[c.tipo] || c.tipo, cena: c, ...v, orig: cenaValor(v) };
  });
  S.cenaSel = -1;
  // o template usa zooms[i % zooms.length]: aberto um por tomada, cada uma muda sozinha
  const cam = d.camera, n = S.rendered.length;
  const zs = cam && cam.enabled !== false && Array.isArray(cam.zooms) && cam.zooms.length ? cam.zooms : null;
  S.zoomDraft = zs && n ? Array.from({ length: n }, (_, i) => +zs[i % zs.length] || 1) : null;
  S.zoomOrig = S.zoomDraft ? [...S.zoomDraft] : null;
  S.zoomSel = -1;
}
// o gancho e os números: o mesmo formato de um efeito, achados pelo bloco da faixa de texto
function destaqueDe(tipo, ref, nome, obj, textos) {
  const t = obj.texto;
  const v = cenaValor({ texto: t && isFinite(t.x) && isFinite(t.y) ? t : null, textos, estilo: obj.estilo });
  return { tipo, ref, nome, cena: obj, ...v, orig: cenaValor(v) };
}
function buildDestaques(d) {
  const h = d.hook && d.hook.enabled ? d.hook : null;
  S.destaques = {
    hook: h ? destaqueDe('hook', 0, 'Gancho', h, { text: h.text != null ? String(h.text) : (h.lines || []).join(' ') }) : null,
    numeros: (d.numeros || []).map((n, i) => destaqueDe('numero', i, 'Número', n,
      { prefixo: n.prefixo || '', valor: String(n.valor ?? ''), sufixo: n.sufixo || '', rotulo: n.rotulo || '' })),
  };
}
function listaDestaques() { return [S.destaques.hook, ...S.destaques.numeros].filter(Boolean); }
function destaquesMudados() { return listaDestaques().filter(cenaMudou); }
function destaqueDoBloco(b) {
  if (!b) return null;
  if (b.kind === 'hook') return S.destaques.hook;
  if (b.kind === 'numero') return S.destaques.numeros[b.ref] || null;
  return null;
}
// o nome do bloco na faixa segue o texto novo
function rotulosDestaques() {
  for (const b of S.insertsDraft) {
    const dq = destaqueDoBloco(b);
    if (!dq) continue;
    b.label = b.kind === 'hook' ? (dq.textos.text || 'Gancho') : `${dq.textos.prefixo || ''}${dq.textos.valor || ''}${dq.textos.sufixo || ''}`;
  }
}
function blocoDaCena(c) {
  const f = c && CENA_BLOCO[c.tipo];
  if (!f) return null;
  const b = f(c.cena, c.textos);
  const k = CENA_ESTILO[c.tipo] ? estiloEfetivo(c).tamanho : 1; // a moldura cresce com a letra
  const t = { ...b, w: b.w * k, h: b.h * k };
  return c.texto ? { ...t, x: c.texto.x, y: c.texto.y } : t;
}
function renderCenas(lane) {
  S.cenasDraft.forEach((c, i) => {
    const a = renderedToDraft(c.start), b = renderedToDraft(c.end);
    const chip = el('div', 'chip cena', lane);
    chip.dataset.c = i;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps - 2, 6)}px`;
    el('span', 'l-name', chip).textContent = c.nome;
    chip.title = c.desligada ? `${c.nome} (desligado)` : c.nome;
    if (c.desligada) chip.classList.add('off');
    if (cenaMudou(c)) chip.classList.add('dirty');
    if (i === S.cenaSel) chip.classList.add('sel');
  });
}
function renderZoom(lane) {
  const rl = renderedLayout();
  S.zoomDraft.forEach((z, i) => {
    const L = rl[i];
    if (!L) return;
    const a = renderedToDraft(L.out), b = renderedToDraft(L.out + L.dur);
    const chip = el('div', 'chip zoom', lane);
    chip.dataset.z = i;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps - 2, 4)}px`;
    chip.textContent = `${Math.round(z * 100)}%`;
    if (Math.abs(z - 1) < 0.005) chip.classList.add('neutro');
    if (z !== S.zoomOrig[i]) chip.classList.add('dirty');
    if (i === S.zoomSel) chip.classList.add('sel');
  });
}
function tapCena(i) {
  const c = S.cenasDraft[i];
  if (!c) return;
  S.cenaSel = S.cenaSel === i ? -1 : i;
  S.zoomSel = -1; S.insSel = -1; S.selected = -1; S.layerSel = null; S.fxSel = null;
  if (S.cenaSel >= 0) {
    // escolhido, o vídeo vai até o efeito (se a agulha estava fora dele): a moldura aparece pronta
    const a = renderedToDraft(c.start), b = renderedToDraft(c.end);
    if (!(S.t >= a && S.t < b)) { video.pause(); S.t = clampT(a + (b - a) * 0.65); positionTimeline(); preciseSeek(); }
    if (blocoDaCena(c) && !c.desligada && !S.cenaEnsinou) {
      S.cenaEnsinou = true;
      flashName(`<span>${isDesk() ? 'Arraste a moldura no vídeo, ou use as setas' : 'Arraste a moldura no vídeo'}</span>`, 2400);
    }
  }
  renderTimeline(); renderToolbar(); drawCenaBox();
}
function tapZoom(i) {
  if (!S.zoomDraft || S.zoomDraft[i] == null) return;
  S.zoomSel = S.zoomSel === i ? -1 : i;
  S.cenaSel = -1; S.insSel = -1; S.selected = -1; S.layerSel = null; S.fxSel = null;
  renderTimeline(); renderToolbar(); drawCenaBox();
}
// o que está escolhido para o painel de Texto: um efeito, ou o gancho/número do bloco escolhido
function alvoSel() {
  if (S.view !== 'final') return null;
  if (S.cenaSel >= 0) return S.cenasDraft[S.cenaSel] || null;
  return S.insSel >= 0 ? destaqueDoBloco(S.insertsDraft[S.insSel]) : null;
}
// a moldura do escolhido, só enquanto a agulha está dentro dele
function cenaNaTela() {
  const c = alvoSel();
  if (!c || c.desligada || !CENA_BLOCO[c.tipo]) return null;
  const bl = S.cenaSel >= 0 ? null : S.insertsDraft[S.insSel];
  const a = bl ? bl.start : renderedToDraft(c.start), b = bl ? bl.end : renderedToDraft(c.end);
  return S.t >= a - 0.01 && S.t < b ? c : null;
}
function drawCenaBox() {
  const box = $('ovCena');
  if (!box) return;
  const c = cenaNaTela();
  const b = c && blocoDaCena(c);
  if (!b) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  box.style.left = pct(b.x / FRAME_W);
  box.style.top = pct(b.y / FRAME_H);
  box.style.width = pct(b.w / FRAME_W);
  box.style.height = pct(b.h / FRAME_H);
  box.classList.toggle('own', !!c.texto);
  $('ovCenaNome').textContent = c.texto ? `${c.nome}: lugar novo` : c.nome;
  desenhaFantasma(c, b);
}
/* A prévia do texto novo dentro da moldura, num SVG do tamanho dela no quadro: só quando o
 * texto, o estilo ou o lugar mudaram (sem mudança, o vídeo já mostra o texto de verdade). */
const escSvg = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
function desenhaFantasma(c, b) {
  const g = $('ovCenaTxt');
  const d = CENA_ESTILO[c.tipo];
  const o = c.orig || {};
  const mudou = JSON.stringify([c.texto, c.textos, c.estilo || null]) !== JSON.stringify([o.texto || null, o.textos, o.estilo || null]);
  if (!d || !mudou) { g.innerHTML = ''; return; }
  const e = estiloEfetivo(c);
  const linhas = d.linhas(c.textos).filter((l) => l !== '');
  const px = d.px(c.cena) * e.tamanho;
  const esticar = d.esticar ? d.esticar(c.cena) * e.tamanho : 0;
  const vidro = c.tipo === 'vidro';
  const fam = c.tipo === 'papel' ? 'Anton' : e.fonte;
  const txt = linhas.map((l, i) => {
    const y = b.h / 2 + (i - (linhas.length - 1) / 2) * px * 1.04;
    return `<text x="${b.w / 2}" y="${y}" text-anchor="middle" dominant-baseline="central" font-family="${escSvg(`"${fam}"`)}"`
      + ` font-weight="${e.peso}" font-style="${e.italico ? 'italic' : 'normal'}" font-size="${px}"`
      + ` fill="${vidro ? 'rgba(225,238,250,.6)' : escSvg(d.corDaLinha ? d.corDaLinha(i, e, c.cena) : e.cor)}" stroke="${escSvg(e.corContorno)}" stroke-width="${e.contorno}" paint-order="stroke fill"`
      + (esticar ? ` textLength="${esticar}" lengthAdjust="spacingAndGlyphs"` : '') + `>${escSvg(l)}</text>`;
  }).join('');
  g.innerHTML = `<svg viewBox="0 0 ${b.w} ${b.h}" preserveAspectRatio="xMidYMid meet">${txt}</svg>`;
}
// muda o efeito escolhido com uma foto para o desfazer
function cenaMuda(fn) {
  const c = alvoSel();
  if (!c) return;
  remember();
  fn(c);
  renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
}
const cenaLugar = (c, x, y) => {
  const nx = Math.round(Math.min(FRAME_W, Math.max(0, x))), ny = Math.round(Math.min(FRAME_H, Math.max(0, y)));
  c.texto = { x: Math.abs(nx - FRAME_W / 2) < 12 ? FRAME_W / 2 : nx, y: ny }; // perto do meio, encaixa no meio
};
function cenaCentraliza() { cenaMuda((c) => { const b = blocoDaCena(c); c.texto = { x: FRAME_W / 2, y: Math.round(b.y) }; }); }
// setas: vários toques seguidos viram um passo só do desfazer
function cenaEmpurra(dx, dy) {
  const c = cenaNaTela();
  const b = c && blocoDaCena(c);
  if (!b) return;
  const agora = performance.now();
  if (!(S.empurrouEm && agora - S.empurrouEm < 900)) remember();
  S.empurrouEm = agora;
  c.texto = { x: Math.round(Math.min(FRAME_W, Math.max(0, b.x + dx))), y: Math.round(Math.min(FRAME_H, Math.max(0, b.y + dy))) };
  drawCenaBox();
  if (!S.empurraFila) {
    S.empurraFila = true;
    requestAnimationFrame(() => { S.empurraFila = false; renderTimeline(); renderToolbar(); refreshHeader(); });
  }
}
// arrastar a moldura: o centro do bloco anda com o dedo (ou o mouse), em px do quadro
const cenaDrag = { id: null };
$('ovCena').addEventListener('pointerdown', (e) => {
  const c = cenaNaTela();
  const b = c && blocoDaCena(c);
  if (!b) return;
  e.preventDefault();
  e.stopPropagation();
  try { $('ovCena').setPointerCapture(e.pointerId); } catch (err) { /* toque sintético */ }
  const P = player.getBoundingClientRect();
  Object.assign(cenaDrag, { id: e.pointerId, x0: e.clientX, y0: e.clientY, bx: b.x, by: b.y, k: FRAME_W / P.width, moved: false, before: snap() });
  video.pause();
});
$('ovCena').addEventListener('pointermove', (e) => {
  if (e.pointerId !== cenaDrag.id) return;
  const dx = e.clientX - cenaDrag.x0, dy = e.clientY - cenaDrag.y0;
  if (!cenaDrag.moved && Math.hypot(dx, dy) < 4) return;
  const c = alvoSel();
  if (!c) return;
  cenaDrag.moved = true;
  cenaLugar(c, cenaDrag.bx + dx * cenaDrag.k, cenaDrag.by + dy * cenaDrag.k);
  drawCenaBox();
});
function fimCenaDrag(e) {
  if (e.pointerId !== cenaDrag.id) return;
  cenaDrag.id = null;
  tapGuard.until = performance.now() + 400; // pegar a moldura não dá play
  if (!cenaDrag.moved) return;
  remember(cenaDrag.before);
  renderTimeline(); renderToolbar(); refreshHeader();
}
$('ovCena').addEventListener('pointerup', fimCenaDrag);
$('ovCena').addEventListener('pointercancel', fimCenaDrag);
/* O painel de Texto do efeito escolhido, como o de qualquer editor: o que está escrito, a
 * fonte, a cor, o tamanho, o contorno e a altura. Tudo muda ao vivo no rascunho, e a moldura
 * sobre o vídeo mostra o texto novo com a fonte e a cor escolhidas (uma prévia aproximada: o
 * vidro, o brilho e a perspectiva só aparecem quando o agente refaz o trecho). Pronto guarda um
 * passo do desfazer; Cancelar volta ao que estava quando o painel abriu. */
const CORES_TEXTO = ['#ffffff', '#000000', '#ffe500', '#e8ff5a', '#c6ff3d', '#34e3c0', '#2f6bff', '#7a3cff', '#ff2d55', '#ff8a3d', '#b0101b'];
// `c`: o efeito, gancho ou número aberto; `camada`: o id da camada de texto aberta;
// `legenda`: o painel é o da legenda (um dos três por vez)
const painel = { c: null, camada: null, legenda: false, antes: null, valor: null, cat: null, vista: null };
function campoTexto(box, rotulo) {
  const sec = el('div', 'tx-sec', box);
  el('div', 'tx-rot', sec).textContent = rotulo;
  return sec;
}
function paletaCores(host, atual, extra, muda) {
  const linha = el('div', 'tx-cores', host);
  const cores = [...new Set([extra, ...CORES_TEXTO].filter(Boolean).map((c) => c.toLowerCase()))];
  for (const cor of cores) {
    const b = el('button', `tx-cor${cor === String(atual).toLowerCase() ? ' on' : ''}`, linha);
    b.type = 'button';
    b.style.background = cor;
    b.title = cor;
    b.addEventListener('click', () => { muda(cor); for (const x of linha.children) x.classList.toggle('on', x === b); });
  }
  const livre = el('input', 'tx-cor-livre', linha);
  livre.type = 'color';
  livre.value = /^#[0-9a-f]{6}$/i.test(atual) ? atual : '#ffffff';
  livre.title = 'Outra cor';
  livre.addEventListener('input', () => { muda(livre.value); for (const x of linha.children) if (x !== livre) x.classList.remove('on'); });
}
function regua(host, min, max, passo, valor, mostra, muda) {
  const linha = el('div', 'tx-regua', host);
  const r = el('input', '', linha);
  r.type = 'range'; r.min = min; r.max = max; r.step = passo; r.value = valor;
  const v = el('span', 'tx-val', linha);
  v.textContent = mostra(valor);
  r.addEventListener('input', () => { v.textContent = mostra(+r.value); muda(+r.value); });
  r.mostra = mostra;
  return r;
}
// a régua anda quando outro controle muda o mesmo valor (a alça do texto, a cor do contorno)
function reguaPoe(r, v) {
  r.value = v;
  r.nextElementSibling.textContent = r.mostra(+r.value);
}
/* Contorno: a largura e a cor. Escolher a cor com o contorno desligado, ou fino demais para
 * aparecer, já liga um que se vê: 1 px do quadro de 1080 é um terço de pixel na prévia, e no
 * vídeo final também some (aconteceu no teste: amarelo a 1 px, e "a cor não aparece"). */
const CONTORNO_VISIVEL = 6;
function campoContorno(box, e, mudaLargura, mudaCor) {
  const sec = campoTexto(box, 'Contorno');
  const r = regua(sec, 0, 30, 1, e.contorno, (v) => (v ? `${v} px` : 'sem'), mudaLargura);
  paletaCores(sec, e.corContorno, null, (cor) => {
    mudaCor(cor);
    if (+r.value < 3) { reguaPoe(r, CONTORNO_VISIVEL); mudaLargura(CONTORNO_VISIVEL); }
  });
}
// a mudança ao vivo: o rascunho do efeito muda e a moldura redesenha; a linha do tempo, no quadro seguinte
function textoMuda(fn) {
  const c = painel.c;
  if (!c) return;
  fn(c);
  if (c.estilo && !Object.keys(c.estilo).length) c.estilo = null;
  if (c.tipo === 'hook' || c.tipo === 'numero') rotulosDestaques();
  drawCenaBox();
  if (!S.textoFila) {
    S.textoFila = true;
    requestAnimationFrame(() => { S.textoFila = false; renderTimeline(); refreshHeader(); });
  }
}
const mudaEstilo = (k, v) => textoMuda((c) => { c.estilo = { ...(c.estilo || {}), [k]: v }; });
// a grade de fontes por aba, aberta na aba da fonte de agora (Em alta, se ela está lá)
function fonteGrade(box, atual, escolhe) {
  const sec = campoTexto(box, 'Fonte');
  const abas = el('div', 'tx-abas', sec);
  const grade = el('div', 'tx-fontes', sec);
  const f0 = CutMindFontes.FONTES.find((f) => f.familia === atual);
  painel.cat = f0 ? (f0.alta ? 'alta' : f0.cat) : painel.cat || 'alta';
  let escolhida = atual;
  const mostra = () => {
    grade.innerHTML = '';
    for (const a of abas.children) a.classList.toggle('on', a.dataset.cat === painel.cat);
    for (const f of CutMindFontes.daAba(painel.cat)) {
      const b = el('button', `tx-fonte${f.familia === escolhida ? ' on' : ''}`, grade);
      b.type = 'button';
      b.textContent = f.familia;
      b.style.fontFamily = `"${f.familia}"`;
      b.style.fontWeight = f.peso;
      b.addEventListener('click', () => {
        escolhida = f.familia;
        escolhe(f);
        for (const y of grade.children) y.classList.toggle('on', y === b);
      });
    }
  };
  for (const [id, nome] of CutMindFontes.CATEGORIAS) {
    const a = el('button', 'tx-aba', abas);
    a.type = 'button'; a.dataset.cat = id; a.textContent = nome;
    a.addEventListener('click', () => { painel.cat = id; mostra(); });
  }
  mostra();
}
function openCenaTexto() {
  const c = alvoSel();
  if (!c) return;
  painel.c = c; painel.camada = null; painel.legenda = false; painel.antes = snap(); painel.valor = cenaValor(c);
  const d = CENA_ESTILO[c.tipo];
  const pode = (k) => !!d && (d.so ? d.so.includes(k) : !(d.sem || []).includes(k));
  if (d && pode('fonte')) CutMindFontes.carregarTodas();
  $('cenaSheetNome').textContent = `Texto · ${c.nome}`;
  const box = $('cenaCampos');
  box.innerHTML = '';
  // o que está escrito: um campo por texto; lista de linhas numa caixa, uma por linha
  for (const [k, v] of Object.entries(c.textos)) {
    const lab = el('label', 'cena-campo', box);
    el('span', '', lab).textContent = CENA_TEXTOS[k] || k;
    const lista = Array.isArray(v);
    const inp = el(lista ? 'textarea' : 'input', '', lab);
    if (lista) inp.rows = Math.max(2, v.length);
    else inp.type = 'text';
    inp.value = lista ? v.join('\n') : v;
    inp.addEventListener('input', () => textoMuda((x) => {
      if (!lista) { x.textos = { ...x.textos, [k]: inp.value }; return; }
      const ls = inp.value.split('\n').map((t) => t.trim());
      const velho = painel.valor.textos[k] || [];
      // as batidas têm hora e zoom próprios: a quantidade fica; numa lista de linhas, linha vazia sai
      x.textos = { ...x.textos, [k]: k === 'batidas' ? velho.map((w, i) => (ls[i] ? ls[i] : w)) : ls.filter(Boolean) };
    }));
  }
  // tamanho, cor e contorno em cima, as fontes por último: a grade é alta, e na coluna do
  // computador ela escondia o resto (no teste, "não tem como mudar o tamanho")
  const e = estiloEfetivo(c);
  if (e && pode('tamanho')) {
    regua(campoTexto(box, 'Tamanho'), 40, 200, 5, Math.round(e.tamanho * 100), (v) => `${v}%`, (v) => mudaEstilo('tamanho', +(v / 100).toFixed(2)));
  }
  if (e && pode('cor')) paletaCores(campoTexto(box, 'Cor'), e.cor, S.style && S.style.accent, (cor) => mudaEstilo('cor', cor));
  if (e && pode('contorno')) campoContorno(box, e, (v) => mudaEstilo('contorno', v), (cor) => mudaEstilo('corContorno', cor));
  const b = CENA_BLOCO[c.tipo] && blocoDaCena(c);
  if (b) {
    const sec = campoTexto(box, 'Altura');
    regua(sec, 0, 100, 1, Math.round((b.y / FRAME_H) * 100), (v) => `${v}%`, (v) => textoMuda((x) => {
      const bx = blocoDaCena(x);
      x.texto = { x: Math.round(bx.x), y: Math.round((v / 100) * FRAME_H) };
    }));
    el('p', 'tx-dica', sec).textContent = isDesk() ? 'Para o lado, arraste a moldura no vídeo ou use as setas do teclado.' : 'Para o lado, arraste a moldura no vídeo.';
  }
  if (e && pode('fonte')) fonteGrade(box, e.fonte, (f) => textoMuda((x) => { x.estilo = { ...(x.estilo || {}), fonte: f.familia, peso: f.peso }; }));
  showSheet($('cenaSheet'), true);
}
function fechaTexto(guarda) {
  showSheet($('cenaSheet'), false);
  if (painel.camada) { fechaTextoCamada(guarda); return; }
  if (painel.legenda) { fechaLegenda(guarda); return; }
  const c = painel.c;
  painel.c = null;
  if (!c) return;
  if (!guarda) Object.assign(c, cenaValor(painel.valor));
  else if (cenaSig(c) !== cenaSig(painel.valor)) remember(painel.antes);
  renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
}
$('cenaCancel').addEventListener('click', () => fechaTexto(false));
$('cenaOk').addEventListener('click', () => fechaTexto(true));
// zoom da tomada: a régua de 100% a 200%; a prévia segue o vídeo de agora
let zoomBefore = null;
function openZoom() {
  if (!S.zoomDraft || S.zoomSel < 0) return;
  zoomBefore = snap();
  $('tomZoomRange').value = Math.round(S.zoomDraft[S.zoomSel] * 100);
  $('tomZoomVal').textContent = `${$('tomZoomRange').value}%`;
  showSheet($('tomZoomSheet'), true);
}
$('tomZoomRange').addEventListener('input', () => {
  if (!S.zoomDraft || S.zoomSel < 0) return;
  S.zoomDraft[S.zoomSel] = +($('tomZoomRange').value / 100).toFixed(2);
  $('tomZoomVal').textContent = `${$('tomZoomRange').value}%`;
  if (!S.zoomFila) {
    S.zoomFila = true;
    requestAnimationFrame(() => { S.zoomFila = false; renderTimeline(); refreshHeader(); });
  }
});
$('tomZoomOk').addEventListener('click', () => {
  showSheet($('tomZoomSheet'), false);
  if (zoomBefore && zoomBefore.zooms && S.zoomDraft && zoomBefore.zooms.some((z, i) => z !== S.zoomDraft[i])) remember(zoomBefore);
  zoomBefore = null;
  renderTimeline(); renderToolbar(); refreshHeader();
});
function zoomPara(z) {
  if (!S.zoomDraft || S.zoomSel < 0 || S.zoomDraft[S.zoomSel] === z) return;
  remember();
  S.zoomDraft[S.zoomSel] = z;
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
// Duplicar uma camada (texto, imagem ou áudio): a cópia vai numa faixa nova, logo acima da
// original e no mesmo tempo, já escolhida
function duplicateLayerSel() {
  const hit = camItem(S.layerSel);
  if (!hit) return;
  remember();
  const fid = newFaixaId(hit.f.tipo === 'audio' ? 'a' : hit.f.tipo === 'texto' ? 't' : 'i');
  const item = { ...JSON.parse(JSON.stringify(hit.it)), id: `${fid}-1` };
  S.camadas.faixas.splice(S.camadas.faixas.indexOf(hit.f) + 1, 0, { ...hit.f, id: fid, travado: false, itens: [item] });
  S.layerSel = item.id;
  renderTimeline(); renderToolbar(); refreshHeader();
  toast(hit.f.tipo === 'audio' ? 'Cópia numa camada nova' : 'Cópia numa camada nova, por cima da original', 2000);
}

/* ---------- camadas de texto ----------
 * "Texto" na barra põe um texto na agulha, numa faixa própria, e abre o painel de Texto. O
 * texto aparece sobre o vídeo como vai sair no final (src/CamadasTexto.tsx: centro em x/y do
 * quadro 1080x1920, `tamanho` 1 = 96 px, Poppins branca sem contorno): tocar escolhe, arrastar
 * leva, tocar no escolhido abre o painel. "Atrás da pessoa" e "Acompanhar" valem no vídeo
 * final, onde o agente faz o recorte e o rastreio; a prévia segue o rosto quando o rastreio já
 * existe. No Corte a prévia mostra os textos; no Final, só os que o vídeo ainda não tem. */
const TEXTO_PX = 96;
const TEXTO_PADRAO = { fonte: 'Poppins', cor: '#ffffff', corContorno: '#000000' };
function estiloTexto(it) {
  const e = it.estilo || {};
  const fonte = e.fonte && CutMindFontes.FONTES.some((f) => f.familia === e.fonte) ? e.fonte : TEXTO_PADRAO.fonte;
  return {
    fonte,
    peso: +e.peso || CutMindFontes.pesoDe(fonte),
    cor: e.cor || TEXTO_PADRAO.cor,
    tamanho: +e.tamanho > 0 ? +e.tamanho : 1,
    contorno: +e.contorno > 0 ? +e.contorno : 0,
    corContorno: e.corContorno || TEXTO_PADRAO.corContorno,
  };
}
// o arco da linha de um texto curvo, em px do quadro: a mesma conta do arcoDoTexto do template
function arcoDoTexto(x, y, size, largura, curva) {
  const theta = (Math.abs(curva) / 100) * Math.PI;
  const r = Math.max(1, largura) / theta;
  const meio = Math.min(Math.PI * 0.999, theta / 2 + 0.25);
  const by = y + size * 0.35;
  const sx = r * Math.sin(meio), sy = r * (1 - Math.cos(meio));
  const grande = 2 * meio > Math.PI ? 1 : 0;
  return curva > 0
    ? `M ${x - sx} ${by + sy} A ${r} ${r} 0 ${grande} 1 ${x + sx} ${by + sy}`
    : `M ${x - sx} ${by - sy} A ${r} ${r} 0 ${grande} 0 ${x + sx} ${by - sy}`;
}
// tab vira espaço e os outros caracteres de controle saem: o servidor recusaria o texto
const semControle = (s) => [...String(s)].map((ch) => (ch === '\t' ? ' ' : ch)).filter((ch) => ch === '\n' || ch.charCodeAt(0) >= 32).join('');
// texto vazio não vai: o servidor recusaria o Salvar inteiro
function camadasParaSalvar() {
  const c = JSON.parse(JSON.stringify(S.camadas));
  for (const f of c.faixas) if (f.tipo === 'texto') f.itens = f.itens.filter((it) => String(it.texto).trim());
  c.faixas = c.faixas.filter((f) => f.tipo !== 'texto' || f.itens.length);
  return c;
}
// o começo de uma camada nova na agulha, arredondado para BAIXO: para cima, ela nascia uma
// fração de milissegundo depois da agulha e não aparecia na prévia
const inicioNaAgulha = (total) => Math.floor(Math.min(draftToRendered(S.t), Math.max(0, total - 0.5)) * 1000) / 1000;
function addTexto() {
  const total = S.videoDuration || totalT();
  const inicio = inicioNaAgulha(total);
  remember();
  const fid = newFaixaId('t');
  const item = { id: `${fid}-1`, texto: 'Seu texto', inicio, duracao: +Math.min(3, Math.max(0.5, total - inicio)).toFixed(3),
    x: FRAME_W / 2, y: FRAME_H / 2, estilo: {}, atras: false, acompanhar: false, curva: 0 };
  S.camadas.faixas.push({ id: fid, tipo: 'texto', oculto: false, travado: false, itens: [item] });
  S.layerSel = item.id;
  S.fxSel = null; S.selected = -1; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1;
  S.audioMenu = false; S.importMenu = false; S.fxMenu = false; S.textMenu = false;
  CutMindFontes.carregarTodas();
  renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
  openTextoCamada(true);
}

/* Modelos de texto: dois ou três textos de uma vez, em fontes misturadas (o "Zoom / do seu /
 * vídeo" da referência). Cada linha vira uma camada de texto própria, no mesmo tempo, e se
 * troca como qualquer texto. O cartão mostra o modelo desenhado sobre o quadro da agulha, nas
 * mesmas contas do vídeo final. `dy` é a distância da linha até MODELO_Y, em px do quadro; o
 * peso de cada fonte vem do catálogo (é o que o render carrega). */
const MODELO_Y = 900;
const MODELOS_TEXTO = [
  { nome: 'Mistura', linhas: [
    { texto: 'Zoom', dy: -150, estilo: { fonte: 'Archivo Black', cor: '#ffffff', tamanho: 2.2 } },
    { texto: 'do seu', dy: -20, estilo: { fonte: 'Playfair Display', cor: '#d9d9d9', tamanho: 0.75 } },
    { texto: 'vídeo', dy: 115, estilo: { fonte: 'Pacifico', cor: '#ff4fa3', tamanho: 1.6 } }] },
  { nome: 'Chamada', linhas: [
    { texto: 'O SEGREDO', dy: -75, estilo: { fonte: 'Oswald', cor: '#ffe500', tamanho: 0.8 } },
    { texto: 'QUE NINGUÉM CONTA', dy: 30, estilo: { fonte: 'Anton', cor: '#ffffff', tamanho: 1.2, contorno: 8, corContorno: '#000000' } }] },
  { nome: 'Número', linhas: [
    { texto: '3', dy: -150, estilo: { fonte: 'Bebas Neue', cor: '#ffe500', tamanho: 4 } },
    { texto: 'erros que', dy: 55, estilo: { fonte: 'Poppins', cor: '#ffffff', tamanho: 0.75 } },
    { texto: 'custam caro', dy: 150, estilo: { fonte: 'Permanent Marker', cor: '#ff3b30', tamanho: 1.15 } }] },
  { nome: 'Elegante', linhas: [
    { texto: 'menos', dy: -125, estilo: { fonte: 'Cormorant Garamond', cor: '#ffffff', tamanho: 1.6 } },
    { texto: 'é', dy: 0, estilo: { fonte: 'Great Vibes', cor: '#f2c14e', tamanho: 1.4 } },
    { texto: 'mais', dy: 125, estilo: { fonte: 'Cormorant Garamond', cor: '#ffffff', tamanho: 1.6 } }] },
  { nome: 'Retrô', linhas: [
    { texto: 'GAME', dy: -70, estilo: { fonte: 'Press Start 2P', cor: '#39e5ff', tamanho: 0.9 } },
    { texto: 'OVER', dy: 70, estilo: { fonte: 'Monoton', cor: '#ff3fd8', tamanho: 1.5 } }] },
  { nome: 'Manchete', linhas: [
    { texto: 'URGENTE', dy: -60, estilo: { fonte: 'Archivo Black', cor: '#ff2d2d', tamanho: 1.3, contorno: 6, corContorno: '#ffffff' } },
    { texto: 'leia antes de comprar', dy: 55, estilo: { fonte: 'Caveat', cor: '#ffffff', tamanho: 1 } }] },
];
const linhaDoModelo = (l) => ({ texto: l.texto, x: FRAME_W / 2, y: Math.round((MODELO_Y * FRAME_H) / 1920) + l.dy, curva: 0,
  estilo: { ...l.estilo, peso: CutMindFontes.pesoDe(l.estilo.fonte) } });
function openModelos() {
  video.pause();
  CutMindFontes.carregarTodas();
  const box = $('modeloLista');
  box.innerHTML = '';
  el('p', 'sheet-hint', box).textContent = 'Dois ou três textos de uma vez, em fontes misturadas. Cada linha vira uma camada: depois, toque em uma para trocar o que está escrito.';
  const grade = el('div', 'mod-grade', box);
  const idx = Math.min(S.thumbCount || 1, Math.floor(draftToRendered(S.t) / THUMB_EVERY) + 1); // o quadro da agulha
  const fundo = S.thumbCount > 0 ? `url("/gen/thumbs/${String(idx).padStart(4, '0')}.jpg")` : 'none';
  MODELOS_TEXTO.forEach((m, k) => {
    const card = el('button', 'mod-card', grade);
    card.type = 'button';
    card.style.backgroundImage = fundo;
    m.linhas.forEach((l, j) => desenhaTexto(card, { it: { id: `modelo-${k}-${j}`, ...linhaDoModelo(l) }, sel: false, fantasma: false, d: [0, 0], trav: true }));
    el('span', 'mod-nome', card).textContent = m.nome;
    card.addEventListener('click', () => aplicaModelo(m));
  });
  showSheet($('modeloSheet'), true);
}
function fechaModelos() { showSheet($('modeloSheet'), false); }
function aplicaModelo(m) {
  const total = S.videoDuration || totalT();
  const inicio = inicioNaAgulha(total);
  const duracao = +Math.min(3, Math.max(0.5, total - inicio)).toFixed(3);
  remember();
  let primeiro = null;
  for (const l of m.linhas) {
    const fid = newFaixaId('t');
    const item = { id: `${fid}-1`, inicio, duracao, atras: false, acompanhar: false, ...linhaDoModelo(l) };
    S.camadas.faixas.push({ id: fid, tipo: 'texto', oculto: false, travado: false, itens: [item] });
    primeiro = primeiro || item.id;
  }
  S.layerSel = primeiro;
  S.fxSel = null; S.selected = -1; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1; S.legSel = false;
  fechaModelos();
  renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
  toast(`${m.linhas.length} textos, cada um numa camada: toque em um para trocar o que está escrito`, 2800);
}
$('modeloClose').innerHTML = ICON.fechar;
$('modeloClose').addEventListener('click', fechaModelos);
// liga e desliga `atras` (texto ou imagem) e `acompanhar` (texto) da camada escolhida
function textoLiga(k) {
  const hit = camItem(S.layerSel);
  if (!hit || !(hit.f.tipo === 'texto' || (hit.f.tipo === 'imagem' && k === 'atras'))) return;
  remember();
  hit.it[k] = !hit.it[k];
  const liga = hit.it[k];
  // efeito de tela inteira no mesmo trecho (tela dividida, efeito do agente) cobre o que fica atrás da pessoa
  const a = hit.it.inicio, b = hit.it.inicio + hit.it.duracao;
  const cobre = k === 'atras' && liga && [...S.cenasDraft.filter((c) => !c.desligada), ...S.insertsDraft.filter((c) => c.kind === 'split' || c.kind === 'splitvideo')]
    .find((c) => isFinite(c.start) && isFinite(c.end) && c.start < b && c.end > a);
  if (cobre) { toast(`Atenção: ${cobre.nome || 'a tela dividida'} ocupa a tela inteira nesse trecho e cobre o que fica atrás da pessoa`, 4200); renderTimeline(); renderToolbar(); refreshHeader(); return; }
  if (hit.f.tipo === 'imagem') toast(liga ? 'No vídeo final a imagem vira o cartão grande atrás da pessoa (a prévia mostra por cima, transparente)' : 'A imagem volta para o cartão de cima', 3200);
  else if (k === 'atras') toast(liga ? 'No vídeo final o texto passa atrás da pessoa (a prévia mostra na frente)' : 'O texto volta para a frente', 2800);
  else toast(liga ? (S.rastreio ? 'O texto anda junto com a pessoa' : 'O texto anda junto com a pessoa no vídeo final (o agente rastreia o rosto)') : 'O texto fica parado', 2800);
  renderTimeline(); renderToolbar(); refreshHeader();
}

// o rosto rastreado no corte (rastreio.json, ao lado do edit-data): a prévia de "Acompanhar"
async function loadRastreio() {
  S.rastreio = null;
  const ed = S.state && S.state.editData;
  if (!ed) return;
  try {
    const r = await fetch(`/media/${ed.slice(0, ed.lastIndexOf('/') + 1)}rastreio.json?v=${Date.now()}`);
    const j = r.ok ? await r.json() : null;
    if (j && Array.isArray(j.points) && j.points.length) S.rastreio = { fps: +j.fps || S.fps || 30, pontos: j.points };
  } catch (e) { /* ainda não existe */ }
}
// quanto o rosto andou desde que o texto entrou, em px do quadro (o vídeo final soma o zoom da câmera)
function segueDesloc(it, rt) {
  const R = S.rastreio;
  if (!it.acompanhar || !R) return [0, 0];
  const p = (t) => R.pontos[Math.max(0, Math.min(R.pontos.length - 1, Math.round(t * R.fps)))];
  const a = p(it.inicio), b = p(rt);
  return [(b[0] - a[0]) * FRAME_W, (b[1] - a[1]) * FRAME_H];
}
// o texto já está no vídeo final quando o edit-data tem ele igual (camadas_edit_data.py)
function textoJaNoFinal(it) {
  const t = S.editData && Array.isArray(S.editData.textos) ? S.editData.textos.find((x) => x.id === it.id) : null;
  if (!t) return false;
  const perto = (a, b) => Math.abs(+a - +b) < 0.0015;
  const ord = (o) => JSON.stringify(Object.keys(o || {}).sort().map((k) => [k, o[k]]));
  return t.texto === it.texto && perto(t.start, it.inicio) && perto(t.end, it.inicio + it.duracao) && perto(t.x, it.x) && perto(t.y, it.y)
    && ord(t.estilo) === ord(it.estilo) && perto(t.curva || 0, it.curva || 0) && !!t.matte === !!it.atras && !!t.acompanhar === !!it.acompanhar;
}
const medidor = document.createElement('canvas').getContext('2d');
S.fontesVersao = 0;
// fonte que acabou de chegar muda a largura: o texto curvo se mede de novo
if (document.fonts) document.fonts.addEventListener('loadingdone', () => { S.fontesVersao++; });
let txSig = '';
function desenhaTextos() {
  const box = $('ovTextos');
  if (!box) return;
  const rt = draftToRendered(S.t);
  const lista = [];
  if (!S.styling && !S.posMode && S.camadas) {
    for (const f of S.camadas.faixas) {
      if (f.tipo !== 'texto' || f.oculto) continue;
      for (const it of f.itens) {
        if (!(rt >= it.inicio && rt < it.inicio + it.duracao) || !String(it.texto).trim()) continue;
        if (formatoPrevia()) { // na prévia do formato, o texto vai ao lugar relativo do quadro novo e só se vê
          lista.push({ it: { ...it, ...levarPonto(it.x, it.y, S.formatoAtual, S.formato) }, sel: false, fantasma: false,
            d: [0, 0], trav: true });
          continue;
        }
        const sel = it.id === S.layerSel;
        const noFinal = S.view === 'final' && !S.quadroCobre && textoJaNoFinal(it);
        if (noFinal && !sel) continue; // o vídeo final já mostra este texto
        lista.push({ it, sel, fantasma: noFinal, d: segueDesloc(it, rt), trav: f.travado });
      }
    }
  }
  const sig = JSON.stringify([lista.map((x) => [x.it, x.sel, x.fantasma, x.d.map(Math.round), x.trav]), S.fontesVersao,
    FRAME_W, FRAME_H]);
  if (sig === txSig) return;
  txSig = sig;
  box.innerHTML = '';
  for (const x of lista) desenhaTexto(box, x);
}
function desenhaTexto(box, { it, sel, fantasma, d, trav }) {
  const e = estiloTexto(it);
  const px = TEXTO_PX * e.tamanho;
  const cq = (v) => `${((v / FRAME_W) * 100).toFixed(4)}cqw`; // px do quadro em largura da prévia
  const w = el('div', `ov-tx-w${fantasma ? ' fantasma' : ''}${trav ? ' trav' : ''}`, box);
  w.style.translate = `${cq(d[0])} ${cq(d[1])}`;
  const curva = Math.max(-100, Math.min(100, +it.curva || 0));
  if (!curva) {
    const t = el('div', `ov-tx${sel ? ' sel' : ''}`, w);
    t.dataset.tx = it.id;
    t.textContent = it.texto;
    Object.assign(t.style, { left: pct(it.x / FRAME_W), top: pct(it.y / FRAME_H), fontFamily: `"${e.fonte}"`, fontWeight: e.peso, fontSize: cq(px), color: e.cor });
    if (e.contorno > 0) { t.style.webkitTextStroke = `${cq(e.contorno)} ${e.corContorno}`; t.style.paintOrder = 'stroke fill'; }
    // o escolhido ganha a bolinha do canto: puxar para fora aumenta, para dentro diminui (CapCut)
    if (sel && !trav) el('span', 'ov-tx-tam', t).dataset.tam = it.id;
    return;
  }
  const linha = String(it.texto).split('\n').map((s) => s.trim()).filter(Boolean).join(' ');
  medidor.font = `${e.peso} ${px}px "${e.fonte}"`;
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${FRAME_W} ${FRAME_H}`);
  svg.setAttribute('class', 'ov-tx-svg');
  w.appendChild(svg);
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('id', `ovtx-${it.id}`);
  path.setAttribute('d', arcoDoTexto(it.x, it.y, px, medidor.measureText(linha).width, curva));
  path.setAttribute('fill', 'none');
  svg.appendChild(path);
  const t = document.createElementNS(ns, 'text');
  const at = { 'font-family': `"${e.fonte}"`, 'font-weight': e.peso, 'font-size': px, fill: e.cor, 'text-anchor': 'middle',
    stroke: e.contorno > 0 ? e.corContorno : 'none', 'stroke-width': e.contorno, 'stroke-linejoin': 'round', 'paint-order': 'stroke' };
  for (const [k, v] of Object.entries(at)) t.setAttribute(k, v);
  t.dataset.tx = it.id;
  const tp = document.createElementNS(ns, 'textPath');
  tp.setAttribute('href', `#ovtx-${it.id}`);
  tp.setAttribute('startOffset', '50%');
  tp.textContent = linha;
  t.appendChild(tp);
  svg.appendChild(t);
  if (!sel) return;
  // a caixa de quem está escolhido: o contorno do arco, que também se pega para arrastar
  const b = t.getBBox(), m = 10;
  const r = document.createElementNS(ns, 'rect');
  for (const [k, v] of Object.entries({ x: b.x - m, y: b.y - m, width: b.width + 2 * m, height: b.height + 2 * m, class: 'ov-tx-caixa' })) r.setAttribute(k, v);
  r.dataset.tx = it.id;
  svg.insertBefore(r, t);
  if (trav) return;
  const bola = document.createElementNS(ns, 'circle'); // a mesma bolinha do texto reto
  for (const [k, v] of Object.entries({ cx: b.x + b.width + m, cy: b.y + b.height + m, r: 20, class: 'ov-tx-tam-svg' })) bola.setAttribute(k, v);
  bola.dataset.tam = it.id;
  svg.appendChild(bola);
}
// o texto escolhido, quando a agulha está nele: as setas o empurram
function textoSelNaTela() {
  const hit = S.layerSel && camItem(S.layerSel);
  if (!hit || hit.f.tipo !== 'texto' || hit.f.travado || S.styling || S.posMode) return null;
  const rt = draftToRendered(S.t);
  return rt >= hit.it.inicio && rt < hit.it.inicio + hit.it.duracao ? hit.it : null;
}
// perto do meio, encaixa no meio (nos dois eixos)
function textoLugar(it, x, y) {
  const nx = Math.round(Math.min(FRAME_W, Math.max(0, x))), ny = Math.round(Math.min(FRAME_H, Math.max(0, y)));
  it.x = Math.abs(nx - FRAME_W / 2) < 12 ? FRAME_W / 2 : nx;
  it.y = Math.abs(ny - FRAME_H / 2) < 12 ? FRAME_H / 2 : ny;
}
function textoEmpurra(dx, dy) {
  const it = textoSelNaTela();
  if (!it) return;
  const agora = performance.now();
  if (!(S.empurrouEm && agora - S.empurrouEm < 900)) remember();
  S.empurrouEm = agora;
  it.x = Math.round(Math.min(FRAME_W, Math.max(0, it.x + dx)));
  it.y = Math.round(Math.min(FRAME_H, Math.max(0, it.y + dy)));
  desenhaTextos();
  if (!S.empurraFila) {
    S.empurraFila = true;
    requestAnimationFrame(() => { S.empurraFila = false; renderTimeline(); renderToolbar(); refreshHeader(); });
  }
}
// arrastar o texto no vídeo: o centro anda com o dedo (ou o mouse). Tocar num texto o escolhe;
// tocar no que já estava escolhido abre o painel, como no CapCut
const txDrag = { id: null };
$('ovTextos').addEventListener('pointerdown', (e) => {
  if (formatoPrevia()) { toast('Na prévia do formato os textos só aparecem. Salve o formato para mexer neles.', 3200); return; }
  const bola = e.target.closest('[data-tam]');
  if (bola) { comecaTamanho(e, bola.dataset.tam); return; }
  const alvo = e.target.closest('[data-tx]');
  const hit = alvo && camItem(alvo.dataset.tx);
  if (!hit || hit.f.travado) return;
  e.preventDefault();
  e.stopPropagation();
  const P = player.getBoundingClientRect();
  Object.assign(txDrag, { id: e.pointerId, alvo: hit.it.id, x0: e.clientX, y0: e.clientY, ix: hit.it.x, iy: hit.it.y,
    k: FRAME_W / P.width, moved: false, jaEscolhido: S.layerSel === hit.it.id, before: snap() });
  video.pause();
  if (!txDrag.jaEscolhido) {
    S.layerSel = hit.it.id;
    S.selected = -1; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1; S.fxSel = null; S.legSel = false;
    renderTimeline(); renderToolbar(); drawCenaBox();
  }
  window.addEventListener('pointermove', txMove);
  window.addEventListener('pointerup', txFim);
  window.addEventListener('pointercancel', txFim);
});
function txMove(e) {
  if (e.pointerId !== txDrag.id) return;
  const dx = e.clientX - txDrag.x0, dy = e.clientY - txDrag.y0;
  if (!txDrag.moved && Math.hypot(dx, dy) < 4) return;
  const hit = camItem(txDrag.alvo);
  if (!hit) return;
  txDrag.moved = true;
  textoLugar(hit.it, txDrag.ix + dx * txDrag.k, txDrag.iy + dy * txDrag.k);
  if (painel.camada === hit.it.id && painel.reguaAlt) reguaPoe(painel.reguaAlt, Math.round((hit.it.y / FRAME_H) * 100));
  desenhaTextos();
}
/* A bolinha do canto: a distância do ponteiro até o centro do texto, sobre a do toque, multiplica
 * o tamanho (de 20% a 500%, a régua do painel). Com o painel aberto a régua anda junto e o Pronto
 * guarda o passo do desfazer; sem ele, o próprio gesto guarda. */
const txTam = { id: null };
function comecaTamanho(e, id) {
  const hit = camItem(id);
  if (!hit || hit.f.travado) return;
  e.preventDefault();
  e.stopPropagation();
  const P = player.getBoundingClientRect();
  const d = segueDesloc(hit.it, draftToRendered(S.t));
  const cx = P.left + ((hit.it.x + d[0]) / FRAME_W) * P.width, cy = P.top + ((hit.it.y + d[1]) / FRAME_H) * P.height;
  Object.assign(txTam, { id: e.pointerId, alvo: id, cx, cy, d0: Math.max(6, Math.hypot(e.clientX - cx, e.clientY - cy)),
    t0: estiloTexto(hit.it).tamanho, before: snap() });
  video.pause();
  window.addEventListener('pointermove', tamMove);
  window.addEventListener('pointerup', tamFim);
  window.addEventListener('pointercancel', tamFim);
}
function tamMove(e) {
  if (e.pointerId !== txTam.id) return;
  const hit = camItem(txTam.alvo);
  if (!hit) return;
  const k = Math.hypot(e.clientX - txTam.cx, e.clientY - txTam.cy) / txTam.d0;
  const v = Math.round(Math.max(0.2, Math.min(5, txTam.t0 * k)) * 100) / 100;
  if (v === estiloTexto(hit.it).tamanho) return;
  hit.it.estilo = { ...(hit.it.estilo || {}), tamanho: v };
  if (painel.camada === hit.it.id && painel.reguaTam) reguaPoe(painel.reguaTam, Math.round(v * 100));
  desenhaTextos();
}
function tamFim(e) {
  if (e.pointerId !== txTam.id) return;
  window.removeEventListener('pointermove', tamMove);
  window.removeEventListener('pointerup', tamFim);
  window.removeEventListener('pointercancel', tamFim);
  txTam.id = null;
  tapGuard.until = performance.now() + 400; // puxar a bolinha não dá play
  const hit = camItem(txTam.alvo);
  if (!hit || estiloTexto(hit.it).tamanho === txTam.t0) return;
  if (painel.camada !== hit.it.id) remember(txTam.before);
  renderTimeline(); renderToolbar(); refreshHeader();
}
function txFim(e) {
  if (e.pointerId !== txDrag.id) return;
  window.removeEventListener('pointermove', txMove);
  window.removeEventListener('pointerup', txFim);
  window.removeEventListener('pointercancel', txFim);
  txDrag.id = null;
  tapGuard.until = performance.now() + 400; // pegar o texto não dá play
  if (txDrag.moved) { remember(txDrag.before); renderTimeline(); renderToolbar(); refreshHeader(); return; }
  if (txDrag.jaEscolhido && e.type === 'pointerup') openTextoCamada(false);
}

// o painel de Texto da camada: o que está escrito, a fonte, a cor, o tamanho, o contorno, a
// curva e a altura, tudo ao vivo na prévia. Pronto guarda um passo do desfazer; Cancelar volta
// ao que estava quando o painel abriu; texto apagado tira a camada, como no CapCut
function txMuda(fn) {
  const hit = painel.camada && camItem(painel.camada);
  if (!hit) return;
  fn(hit.it);
  desenhaTextos();
  if (!S.textoFila) {
    S.textoFila = true;
    requestAnimationFrame(() => { S.textoFila = false; renderTimeline(); refreshHeader(); });
  }
}
const txEstilo = (k, v) => txMuda((x) => { x.estilo = { ...(x.estilo || {}), [k]: v }; });
function openTextoCamada(novo) {
  const hit = camItem(S.layerSel);
  if (!hit || hit.f.tipo !== 'texto') return;
  const it = hit.it;
  painel.c = null;
  painel.legenda = false;
  painel.camada = it.id;
  painel.antes = snap();
  painel.valor = JSON.parse(JSON.stringify(it));
  CutMindFontes.carregarTodas();
  $('cenaSheetNome').textContent = it.nome || 'Texto'; // o texto de um modelo de montagem diz qual é ("Título")
  const box = $('cenaCampos');
  box.innerHTML = '';
  const lab = el('label', 'cena-campo', box);
  el('span', '', lab).textContent = 'O que está escrito';
  const inp = el('textarea', '', lab);
  inp.rows = Math.max(2, Math.min(5, String(it.texto).split('\n').length));
  inp.maxLength = 400;
  inp.value = it.texto;
  inp.addEventListener('input', () => txMuda((x) => { x.texto = semControle(inp.value); }));
  // tamanho, cor e contorno logo abaixo do texto; as fontes por último (a grade é alta e, na
  // coluna do computador, empurrava o resto para fora da vista)
  const e = estiloTexto(it);
  const tam = campoTexto(box, 'Tamanho');
  painel.reguaTam = regua(tam, 20, 500, 5, Math.round(e.tamanho * 100), (v) => `${v}%`, (v) => txEstilo('tamanho', +(v / 100).toFixed(2)));
  el('p', 'tx-dica', tam).textContent = 'Ou puxe a bolinha no canto do texto, no vídeo.';
  paletaCores(campoTexto(box, 'Cor'), e.cor, S.style && S.style.accent, (cor) => txEstilo('cor', cor));
  campoContorno(box, e, (v) => txEstilo('contorno', v), (cor) => txEstilo('corContorno', cor));
  regua(campoTexto(box, 'Curva'), -100, 100, 1, Math.round(+it.curva || 0), (v) => (v ? `${v > 0 ? '+' : ''}${v}` : 'reto'), (v) => txMuda((x) => { x.curva = v; }));
  const alt = campoTexto(box, 'Altura');
  painel.reguaAlt = regua(alt, 0, 100, 1, Math.round((it.y / FRAME_H) * 100), (v) => `${v}%`, (v) => txMuda((x) => { x.y = Math.round((v / 100) * FRAME_H); }));
  el('p', 'tx-dica', alt).textContent = isDesk() ? 'Para o lado, arraste o texto no vídeo ou use as setas do teclado.' : 'Para o lado, arraste o texto no vídeo.';
  fonteGrade(box, e.fonte, (f) => txMuda((x) => { x.estilo = { ...(x.estilo || {}), fonte: f.familia, peso: f.peso }; }));
  showSheet($('cenaSheet'), true);
  // texto novo: já é só digitar por cima (depois que o painel sobe, como o da nota)
  if (novo) setTimeout(() => { if (painel.camada === it.id) { inp.focus(); inp.select(); } }, 280);
}
function fechaTextoCamada(guarda) {
  const hit = camItem(painel.camada);
  painel.camada = null;
  if (hit) {
    if (!guarda) Object.assign(hit.it, JSON.parse(JSON.stringify(painel.valor)));
    else if (!String(hit.it.texto).trim()) {
      remember(painel.antes);
      hit.f.itens = hit.f.itens.filter((x) => x !== hit.it);
      if (!hit.f.itens.length) S.camadas.faixas = S.camadas.faixas.filter((f) => f !== hit.f);
      S.layerSel = null;
      toast('Texto vazio: a camada saiu', 1800);
    } else if (JSON.stringify(hit.it) !== JSON.stringify(painel.valor)) remember(painel.antes);
  }
  renderTimeline(); renderToolbar(); refreshHeader(); desenhaTextos();
}

/* ---------- a legenda do vídeo final ----------
 * Tocar na faixa de legenda (vista Final) escolhe a legenda inteira: o painel de Texto muda a
 * fonte, a cor, o tamanho e o contorno de todas as frases (`captions.estilo` no edit-data; na
 * empilhada e na espalhada, só o tamanho: as fontes e as cores SÃO o estilo), "Acompanhar" faz
 * a legenda andar com a pessoa (`captions.acompanhar`) e "Posição" abre o lugar das frases.
 * Com o painel aberto, a prévia vai para o Corte (sem a legenda queimada) e mostra a frase da
 * agulha com o estilo novo. */
const LEG_PADRAO = {
  karaoke: { fonte: 'Poppins', peso: 900, cor: '#ffffff', px: () => +capsCfg().fontSize || KARAOKE_LINE },
  simples: { fonte: 'Poppins', peso: 600, cor: '#f4f1e9', px: () => STATIC_VARIANTS.simples.size },
  serifada: { fonte: 'Libre Baskerville', peso: 700, cor: '#f4f1e9', px: () => STATIC_VARIANTS.serifada.size },
  classica: { fonte: 'Inter', peso: 500, cor: '#f4f1e9', px: () => STATIC_VARIANTS.classica.size },
};
const estiloDaLegenda = () => capsCfg().style || 'karaoke';
function buildLegenda(d) {
  const c = d.captions;
  S.legenda = c && c.enabled ? { estilo: c.estilo ? JSON.parse(JSON.stringify(c.estilo)) : null, acompanhar: !!c.acompanhar } : null;
  S.legendaOrig = S.legenda ? JSON.parse(JSON.stringify(S.legenda)) : null;
  S.legSel = false;
}
function legendaMudou() { return !!S.legenda && JSON.stringify(S.legenda) !== JSON.stringify(S.legendaOrig); }
// o estilo e o acompanhar (o que vale para todas as frases), sem os pedaços arrastados
const semTempos = (L) => (L ? JSON.stringify({ ...L, tempos: undefined }) : '');
const legendaEstiloMudou = () => !!S.legenda && semTempos(S.legenda) !== semTempos(S.legendaOrig);

/* Arrastar um pedaço da faixa de legenda (vista Final) o leva no tempo: segundos a mais ou a
 * menos em `S.legenda.tempos[i0]`, sem passar por cima do pedaço vizinho. Tocar sem arrastar
 * continua escolhendo a legenda inteira. O Salvar manda o começo de antes e o de agora; o
 * agente desloca as palavras no captions.json com o legenda_tempos.py e refaz o vídeo. */
const deslocCap = (c) => (S.legenda && S.legenda.tempos && S.legenda.tempos[c.i0]) || 0;
function limitesCap(k) {
  const c = S.captions[k], p = S.captions[k - 1], q = S.captions[k + 1];
  const lo = (p ? p.end + deslocCap(p) : 0) - c.start;
  const hi = (q ? q.start + deslocCap(q) : S.videoDuration || totalT()) - c.end;
  return [Math.min(0, lo), Math.max(0, hi)];
}
function holdCap(k, x) {
  if (G.mode !== 'pan' || G.moved || !S.captions[k] || !S.legenda) return;
  const before = snap();
  const [lo, hi] = limitesCap(k);
  G.mode = 'cap';
  G.cap = { k, x0: x, d0: deslocCap(S.captions[k]), lo, hi, before };
  S.legSel = true; S.selected = -1; S.layerSel = null; S.fxSel = null; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1;
  if (navigator.vibrate) navigator.vibrate(12);
  video.pause();
  G.ultX = x;
  bordaRola();
  drawCenaBox(); renderTimeline(); renderToolbar();
}
function dragCap(x) {
  const D = G.cap, c = S.captions[D.k];
  if (!c) return;
  // no quadro, e só então no limite: arredondar depois passava da vizinha (0,067 s numa folga de 0,060)
  const fps = S.fps || 30;
  const d = +Math.max(D.lo, Math.min(D.hi, Math.round((D.d0 + (x - D.x0) / S.pps) * fps) / fps)).toFixed(3);
  const t = { ...(S.legenda.tempos || {}) };
  if (Math.abs(d) < 0.001) delete t[c.i0]; else t[c.i0] = d;
  if (Object.keys(t).length) S.legenda.tempos = t; else delete S.legenda.tempos;
  const tip = $('trimTip');
  const encostou = d && (d <= D.lo + 1e-6 || d >= D.hi - 1e-6) ? ' (encostou na frase vizinha)' : '';
  tip.textContent = d ? `"${c.text}" ${d > 0 ? '+' : ''}${d.toFixed(2)} s${encostou}` : `"${c.text}" no lugar`;
  tip.classList.remove('hidden');
  if (!G.capQueued) {
    G.capQueued = true;
    requestAnimationFrame(() => { G.capQueued = false; renderTimeline(); refreshHeader(); });
  }
}
function endCap() {
  const D = G.cap, c = S.captions[D.k];
  G.mode = null;
  $('trimTip').classList.add('hidden');
  if (c && deslocCap(c) !== D.d0) remember(D.before); // tocar sem arrastar não conta
  renderTimeline(); renderToolbar(); refreshHeader();
}
// para o Salvar: cada pedaço arrastado, pelas palavras do captions.json, com o começo de antes e o novo
function temposLegenda() {
  const T = (S.legenda && S.legenda.tempos) || {};
  return Object.keys(T).map((i0) => S.captions.find((c) => c.i0 === +i0)).filter(Boolean)
    .map((c) => ({ palavra: c.i0, palavras: c.n, deMs: c.ms, paraMs: Math.round(c.ms + deslocCap(c) * 1000) }));
}
function tapLegenda() {
  S.legSel = !S.legSel;
  S.selected = -1; S.layerSel = null; S.fxSel = null; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1;
  drawCenaBox(); renderTimeline(); renderToolbar();
}
function legendaSegue() {
  if (!S.legenda) return;
  remember();
  S.legenda.acompanhar = !S.legenda.acompanhar;
  toast(S.legenda.acompanhar ? 'A legenda anda junto com a pessoa no vídeo final (o agente rastreia o rosto)' : 'A legenda fica parada', 2800);
  renderTimeline(); renderToolbar(); refreshHeader();
}
// o que vale agora: o escolhido no painel por cima do desenho do estilo
function legendaEfetiva() {
  const d = LEG_PADRAO[estiloDaLegenda()] || LEG_PADRAO.karaoke;
  const e = (S.legenda && S.legenda.estilo) || {};
  const C = capsCfg();
  return {
    fonte: e.fonte || d.fonte,
    peso: +e.peso || (e.fonte ? CutMindFontes.pesoDe(e.fonte) : d.peso),
    cor: e.cor || d.cor,
    tamanho: +e.tamanho > 0 ? +e.tamanho : 1,
    contorno: e.contorno != null ? +e.contorno : estiloDaLegenda() === 'karaoke' ? 0 : +C.strokePx || 0,
    corContorno: e.corContorno || '#000000',
    px: d.px(),
  };
}
function legMuda(fn) {
  if (!S.legenda) return;
  fn(S.legenda);
  if (S.legenda.estilo && !Object.keys(S.legenda.estilo).length) S.legenda.estilo = null;
  desenhaLegendaPrevia(true);
  if (!S.textoFila) {
    S.textoFila = true;
    requestAnimationFrame(() => { S.textoFila = false; renderTimeline(); refreshHeader(); });
  }
}
const legEstilo = (k, v) => legMuda((L) => { L.estilo = { ...(L.estilo || {}), [k]: v }; });
function openLegendaTexto() {
  if (!S.legenda) return;
  const so = LEG_PADRAO[estiloDaLegenda()] ? null : ['tamanho']; // empilhada e espalhada: só o tamanho
  painel.c = null; painel.camada = null; painel.legenda = true;
  painel.antes = snap();
  painel.valor = JSON.parse(JSON.stringify(S.legenda));
  painel.vista = S.view;
  if (S.view !== 'corte') switchView('corte'); // o corte não tem a legenda queimada: a prévia não sai dobrada
  CutMindFontes.carregarTodas();
  $('cenaSheetNome').textContent = 'Texto da legenda';
  const box = $('cenaCampos');
  box.innerHTML = '';
  const e = legendaEfetiva();
  // como no texto: tamanho, cor e contorno em cima, as fontes por último
  regua(campoTexto(box, 'Tamanho'), 30, 300, 5, Math.round(e.tamanho * 100), (v) => `${v}%`, (v) => legEstilo('tamanho', +(v / 100).toFixed(2)));
  if (!so) {
    paletaCores(campoTexto(box, 'Cor'), e.cor, S.style && S.style.accent, (cor) => legEstilo('cor', cor));
    campoContorno(box, e, (v) => legEstilo('contorno', v), (cor) => legEstilo('corContorno', cor));
  }
  el('p', 'tx-dica', box).textContent = so
    ? 'Neste estilo as fontes e as cores fazem parte do desenho: aqui muda o tamanho. A altura de cada frase fica em "Posição".'
    : 'Vale para todas as frases. A altura de cada frase fica em "Posição".';
  if (!so) fonteGrade(box, e.fonte, (f) => legMuda((L) => { L.estilo = { ...(L.estilo || {}), fonte: f.familia, peso: f.peso }; }));
  showSheet($('cenaSheet'), true);
  desenhaLegendaPrevia(true);
}
function fechaLegenda(guarda) {
  painel.legenda = false;
  if (!guarda) S.legenda = JSON.parse(JSON.stringify(painel.valor));
  else if (JSON.stringify(S.legenda) !== JSON.stringify(painel.valor)) remember(painel.antes);
  desenhaLegendaPrevia(true);
  if (painel.vista === 'final' && S.view !== 'final') switchView('final');
  S.legSel = S.view === 'final';
  renderTimeline(); renderToolbar(); refreshHeader();
}
// a frase da agulha com o estilo escolhido, no lugar do estilo (a prévia aproximada do painel)
let legSig = '';
function desenhaLegendaPrevia(forca) {
  const box = $('ovLeg');
  if (!box) return;
  if (!painel.legenda || !S.legenda || !S.captions.length) { if (box.innerHTML) { box.innerHTML = ''; legSig = ''; } return; }
  const rt = draftToRendered(S.t);
  const c = S.captions.find((x) => rt >= x.start - 0.05 && rt < x.end + 0.4) || S.captions.find((x) => x.start >= rt) || S.captions[S.captions.length - 1];
  const e = legendaEfetiva();
  const sig = JSON.stringify([c.text, e, estiloDaLegenda()]);
  if (!forca && sig === legSig) return;
  legSig = sig;
  box.innerHTML = '';
  const t = el('div', 'ov-leg-txt', box);
  t.textContent = c.text;
  const cq = (v) => `${((v / FRAME_W) * 100).toFixed(4)}cqw`;
  const y = S.style ? capCenter({ ...S.style, captions: estiloDaLegenda() }, 'abertura') : 0.76;
  Object.assign(t.style, { top: pct(y), fontFamily: `"${e.fonte}"`, fontWeight: e.peso, fontSize: cq(e.px * e.tamanho), color: e.cor });
  if (e.contorno > 0) { t.style.webkitTextStroke = `${cq(e.contorno)} ${e.corContorno}`; t.style.paintOrder = 'stroke fill'; }
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
  if (VF.on) { velFaixaInput(); return; } // a régua é da seleção em massa
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
  if (VF.on) { fechaVelFaixa(); return; }
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

/* ---------- seleção em massa e velocidade do vídeo final (vista Final) ----------
 * Como no CapCut desktop: Ctrl+A (ou Selecionar) escolhe tudo, arrastar no vão escolhe um
 * trecho, e as pontas laranja da faixa ajustam. Escolhido é o trecho de TODAS as faixas
 * (imagem, som, legenda, efeitos, camadas), e a Velocidade acelera tudo junto: o agente aplica
 * no vídeo final já montado (velocidade_final.py), então nada sai do lugar. A linha do tempo
 * segue no relógio do final; o trecho ganha um bloco com o fator na faixa de velocidade, a
 * prévia toca nele mais rápido ou mais devagar (playbackRate, o tom da voz fica) e o topo
 * mostra quanto o vídeo vai durar. Tempos no relógio do final.mp4, como o velocidade.json. */
const VEL_MIN_FAIXA = 0.2; // segundos: menos que isso é clique, não seleção
const velSig = () => JSON.stringify(S.vel.trechos);
const velDirty = () => velSig() !== S.velBase;
S.velBase = velSig();
async function loadVelocidade() {
  let v = null;
  try {
    const r = await fetch(`/media/velocidade.json?v=${Date.now()}`);
    if (r.ok) v = await r.json();
  } catch (e) { /* ainda não existe */ }
  const tr = v && Array.isArray(v.trechos) ? v.trechos : [];
  S.vel = { versao: 1, trechos: tr.map((t) => ({ inicio: +t.inicio, fim: +t.fim, fator: +t.fator })) };
  S.velBase = velSig();
}
const fimFinal = () => S.videoDuration || totalT();
const noQuadro = (t) => { const fps = S.fps || 30; return Math.round(t * fps) / fps; };
// quanto o vídeo dura com os trechos (a conta do velocidade.py)
function duracaoEntregue() {
  const total = fimFinal();
  let menos = 0;
  for (const t of S.vel.trechos) {
    const a = Math.max(0, t.inicio), b = Math.min(total, t.fim);
    if (b > a) menos += (b - a) - (b - a) / t.fator;
  }
  return total - menos;
}
// o fator no instante t do final (1 fora dos trechos)
function fatorEm(t) {
  const s = S.vel.trechos.find((x) => t >= x.inicio && t < x.fim);
  return s ? s.fator : 1;
}
// os trechos com o pedaço [a, b] no fator f (1 tira); vizinhos de mesmo fator viram um só
function comFator(trechos, a, b, f) {
  const out = [];
  for (const s of trechos) {
    if (s.fim <= a + 1e-6 || s.inicio >= b - 1e-6) { out.push({ ...s }); continue; }
    if (s.inicio < a - 1e-6) out.push({ ...s, fim: a });
    if (s.fim > b + 1e-6) out.push({ ...s, inicio: b });
  }
  if (Math.abs(f - 1) > 1e-6) out.push({ inicio: a, fim: b, fator: f });
  out.sort((x, y) => x.inicio - y.inicio);
  const junto = [];
  for (const s of out) {
    const u = junto[junto.length - 1];
    if (u && Math.abs(u.fim - s.inicio) < 1e-6 && u.fator === s.fator) u.fim = s.fim;
    else junto.push(s);
  }
  // pedaço com menos de 0,1 s (o mínimo do velocidade.py) não fica
  return junto.filter((s) => s.fim - s.inicio >= 0.1 - 1e-6)
    .map((s) => ({ inicio: +s.inicio.toFixed(3), fim: +s.fim.toFixed(3), fator: s.fator }));
}
// o fator que vale na faixa inteira (null quando ela mistura fatores)
function fatorDaFaixa(F) {
  const dentro = S.vel.trechos.filter((s) => s.fim > F.a + 1e-6 && s.inicio < F.b - 1e-6);
  if (!dentro.length) return 1;
  const s = dentro[0];
  return dentro.length === 1 && s.inicio <= F.a + 1e-6 && s.fim >= F.b - 1e-6 ? s.fator : null;
}
const faixaETudo = (F) => F.a <= 1e-3 && F.b >= noQuadro(fimFinal()) - 1e-3;
function escolheFaixa(a, b) {
  const lo = Math.max(0, noQuadro(Math.min(a, b))), hi = Math.min(fimFinal(), noQuadro(Math.max(a, b)));
  S.faixa = hi - lo >= VEL_MIN_FAIXA ? { a: lo, b: hi } : null;
}
function selecionaTudo() {
  if (!hasFinal()) { toast('A seleção de tudo é no vídeo final, que ainda não existe', 2600); return; }
  if (S.view !== 'final') switchView('final');
  soltaEscolha();
  S.faixa = { a: 0, b: noQuadro(fimFinal()) };
  renderTimeline(); renderToolbar();
  if (!S.faixaEnsinou) {
    S.faixaEnsinou = true;
    flashName('<span>Tudo escolhido. Puxe as pontas laranja</span>', 2600);
  }
}
// o tempo do rascunho debaixo de um x da tela (o mesmo nas duas agulhas)
const tempoNoX = (x) => (x - timeline.getBoundingClientRect().left - origemEm(timeline.clientWidth)) / S.pps;
const finalNoX = (x) => Math.max(0, Math.min(fimFinal(), draftToRendered(Math.max(0, tempoNoX(x)))));
function comecaMarquee() {
  S.selected = -1; S.layerSel = null; S.fxSel = null; S.insSel = -1; S.cenaSel = -1; S.zoomSel = -1; S.legSel = false;
  S.audioMenu = false; S.importMenu = false; S.fxMenu = false; S.textMenu = false;
  drawCenaBox();
  G.mode = 'faixa';
  G.fa = finalNoX(G.x0);
  video.pause();
  G.ultX = G.x0;
  bordaRola();
}
// o arraste da caixa (do ponto onde começou até o ponteiro) ou de uma ponta da faixa
function puxaFaixa(x) {
  const t = finalNoX(x);
  if (G.mode === 'faixa') escolheFaixa(G.fa, t);
  else if (S.faixa) {
    const F = S.faixa;
    if (G.fb.borda === 'a') F.a = Math.max(0, Math.min(noQuadro(t), F.b - VEL_MIN_FAIXA));
    else F.b = Math.min(fimFinal(), Math.max(noQuadro(t), F.a + VEL_MIN_FAIXA));
    // a agulha vai junto da ponta: a prévia mostra o quadro onde o trecho começa ou termina
    S.t = clampT(renderedToDraft(G.fb.borda === 'a' ? F.a : Math.max(F.a, F.b - 1 / (S.fps || 30))));
    scheduleSeek(true);
  }
  if (!G.faixaFila) {
    G.faixaFila = true;
    requestAnimationFrame(() => { G.faixaFila = false; renderTimeline(); renderToolbar(); });
  }
}
// a faixa laranja, por cima de todas as faixas; anda com elas (entra em `lanes`)
function renderFaixa() {
  if (!S.faixa || S.view !== 'final') return;
  const tr = [...tracksEl.querySelectorAll('.track')];
  if (!tr.length) return;
  const ult = tr[tr.length - 1];
  const topo = tr[0].offsetTop, base = ult.offsetTop + ult.offsetHeight;
  const lane = el('div', 'lane faixa-lane', tracksEl);
  Object.assign(lane.style, { top: `${topo - 3}px`, bottom: 'auto', height: `${base - topo + 6}px` });
  lanes.push(lane);
  const a = renderedToDraft(S.faixa.a), b = renderedToDraft(S.faixa.b);
  const band = el('div', 'faixa-sel', lane);
  band.style.left = `${a * S.pps}px`;
  band.style.width = `${Math.max((b - a) * S.pps, 2)}px`;
  el('div', 'fh l', band).dataset.borda = 'a';
  el('div', 'fh r', band).dataset.borda = 'b';
  const f = fatorDaFaixa(S.faixa), d = S.faixa.b - S.faixa.a;
  el('span', 'faixa-rot', band).textContent = f && f !== 1 ? `${fmtSeg(d)} → ${fmtSeg(d / f)} · ${fmtVel(f)}` : fmtSeg(d);
}
// a faixa de velocidade: um bloco por trecho, com o fator
function renderVelTrack(lane) {
  const mudou = velDirty();
  S.vel.trechos.forEach((s, k) => {
    const a = renderedToDraft(s.inicio), b = renderedToDraft(s.fim);
    const chip = el('div', `chip velc${mudou ? ' dirty' : ''}`, lane);
    chip.dataset.v = k;
    chip.style.left = `${a * S.pps}px`;
    chip.style.width = `${Math.max((b - a) * S.pps - 2, 6)}px`;
    chip.textContent = fmtVel(s.fator);
    chip.title = `${fmtVel(s.fator)}: ${fmtSeg(s.fim - s.inicio)} viram ${fmtSeg((s.fim - s.inicio) / s.fator)}`;
    if (S.faixa && Math.abs(S.faixa.a - s.inicio) < 1e-3 && Math.abs(S.faixa.b - s.fim) < 1e-3) chip.classList.add('sel');
  });
}
/* O painel de Velocidade, o mesmo da tomada, sem a Curva: a régua muda o fator da faixa toda
 * ao vivo; os trechos de fora ficam como estavam (VF.base). Pronto guarda um passo do desfazer. */
const VF = { on: false, base: null, before: null };
function velFaixaMostra(f) {
  const F = S.faixa, d = F.b - F.a;
  $('velVal').textContent = fmtVel(f);
  $('velDur').textContent = `Trecho: ${f !== 1 ? `${fmtSeg(d)} → ${fmtSeg(d / f)}` : fmtSeg(d)} · vídeo: `
    + `${fmtShort(fimFinal())} → ${fmtShort(duracaoEntregue())}. Tudo no trecho acelera junto.`;
}
function openVelFaixa() {
  const F = S.faixa;
  if (!F) return;
  video.pause();
  VF.on = true;
  VF.before = snap();
  VF.base = comFator(S.vel.trechos, F.a, F.b, 1); // os outros trechos, sem o desta faixa
  const f = fatorDaFaixa(F) || 1;
  $('velRange').value = Math.log2(f).toFixed(2);
  $('velModos').hidden = true;
  $('velNormal').hidden = false;
  $('velCurva').hidden = true;
  S.t = clampT(renderedToDraft(F.a)); // a agulha no começo do trecho: o play mostra o ritmo novo
  positionTimeline();
  preciseSeek();
  velFaixaMostra(f);
  showSheet($('velSheet'), true);
}
function velFaixaInput() {
  const F = S.faixa;
  if (!F) return;
  const p = +$('velRange').value;
  const marca = VEL_MARCAS.find((m) => Math.abs(Math.log2(m) - p) < 0.06); // perto de uma marca: encosta nela
  const f = marca || +Math.pow(2, p).toFixed(2);
  S.vel.trechos = comFator(VF.base, F.a, F.b, f);
  velFaixaMostra(f);
  if (!G.velQueued) {
    G.velQueued = true;
    requestAnimationFrame(() => { G.velQueued = false; renderTimeline(); refreshHeader(); });
  }
}
function fechaVelFaixa() {
  showSheet($('velSheet'), false);
  $('velModos').hidden = false;
  VF.on = false;
  if (VF.before && JSON.stringify(VF.before.vel.trechos) !== velSig()) remember(VF.before);
  VF.before = null;
  VF.base = null;
  renderTimeline(); renderToolbar(); refreshHeader();
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
/* ---------- Melhorar voz: a voz do próprio vídeo, com o regulador do Adobe Podcast ----------
 * O preparo é uma vez por corte, no computador (helpers/melhorar_voz.py, que o servidor roda num
 * processo à parte): voz limpa, fundo e 5 degraus de Voz, todos com a mesma fase. Com o painel
 * aberto o vídeo fica mudo e o Web Audio toca a mistura aprovada na escuta, presa ao relógio do
 * vídeo: dois degraus vizinhos por vez (mesma fase: misturar não dobra a voz) mais o fundo.
 * Pronto guarda a escolha no rascunho; o Salvar leva `melhorar` ao agente, que aplica no cut.mp4. */
const VOZ_FAIXAS = ['voz-000', 'voz-025', 'voz-050', 'voz-075', 'voz-100', 'fundo', 'original'];
const VOZ_PREVIA_MAX = 180; // s: acima disso a prévia decodificada pesa demais no celular
const VOZ = { aberto: false, info: null, buf: null, preparado: null, ac: null, master: null, nos: null, fontes: [],
  off: 0, t0: 0, rate: 1, original: false, antes: null, vistaAntes: null, timer: 0, regs: false, voz: 50, fundo: 20 };
const vozAberto = () => VOZ.aberto;
const vozNumeros = (x) => (x && Number.isFinite(x.voz) ? { voz: x.voz, fundo: x.fundo } : null);
// o que o vídeo tem, ou terá quando o agente aplicar: o salvo e ainda não aplicado, senão o aplicado
const vozBase = (info) => (info && (info.pendente || info.aplicado)) || null;
const melhorarDirty = () => S.melhorar != null && JSON.stringify(S.melhorar) !== S.melhorarBase;
async function vozCarregaInfo() {
  try {
    const r = await fetch('/api/melhorar');
    if (!r.ok) return null;
    VOZ.info = await r.json();
  } catch (e) { return null; }
  S.melhorarBase = JSON.stringify(vozBase(VOZ.info));
  return VOZ.info;
}
function vozRotulo() {
  const v = S.melhorar || vozBase(VOZ.info);
  if (!v) return '';
  return v.desligar ? 'Voz original' : `Voz ${v.voz} · Fundo ${v.fundo}`;
}
function vozEtiqueta(track) {
  const rot = vozRotulo();
  if (!rot || S.posMode) return;
  const th = track.querySelector('.th') || el('div', 'th', track);
  const b = el('button', `voz-tag${melhorarDirty() ? ' dirty' : ''}`, th);
  b.type = 'button';
  b.innerHTML = `${ICON.voz}<span>${rot}</span>`;
  b.title = melhorarDirty() ? 'Melhorar voz (falta salvar)' : 'Melhorar voz';
}
document.addEventListener('click', (e) => { if (e.target.closest('.voz-tag')) openVoz(); });

function vozValores() {
  $('vozVoz').value = VOZ.voz;
  $('vozFundo').value = VOZ.fundo;
  $('vozVozVal').textContent = `${VOZ.voz}%`;
  $('vozFundoVal').textContent = `${VOZ.fundo}%`;
  $('vozOriginal').setAttribute('aria-pressed', String(VOZ.original));
}
function vozRegs(on) {
  VOZ.regs = on;
  $('vozRegs').classList.toggle('off', !on);
  $('vozOriginal').disabled = !on || !VOZ.buf;
}
/* a barra pesa cada etapa pelo tempo que ela leva (medido em 23/10 num vídeo de 82 s: limpar 9 s,
 * estúdio 96 s, degraus 4 s); o download dos modelos, na 1ª vez, tem a barra dele */
const VOZ_PESO = { limpar: 0.08, estudio: 0.88, degraus: 0.04 };
function vozFracao(a) {
  if (a.etapa === 'baixar') return a.fracao || 0;
  let f = 0;
  for (const e of Object.keys(VOZ_PESO)) {
    if (e === a.etapa) return f + VOZ_PESO[e] * (a.fracao || 0);
    f += VOZ_PESO[e];
  }
  return 0;
}
/* o andamento do preparo (`a`), um erro, ou só um aviso; sem nada, esconde */
function vozMostra({ a = null, erro = '', texto = '', nota = '' } = {}) {
  const box = $('vozPrep');
  const algo = a || erro || texto || nota;
  box.classList.toggle('hidden', !algo);
  box.classList.toggle('erro', !!erro);
  $('vozDeNovo').classList.toggle('hidden', !erro);
  $('vozPrepTexto').textContent = erro ? `Não deu: ${erro}`
    : a ? `${a.texto || 'Preparando a voz'}…` : texto;
  $('vozPrepBarra').style.width = a && a.de ? `${Math.round(vozFracao(a) * 100)}%` : '0%';
  $('vozPrepNota').textContent = nota;
  $('vozPrepNota').classList.toggle('hidden', !nota);
  $('vozEstado').textContent = a ? 'preparando' : '';
}
function vozNotaPreparo() {
  const m = (VOZ.info && VOZ.info.modelos) || {};
  const min = Math.max(1, Math.round((((VOZ.info && VOZ.info.duracao) || S.videoDuration) * 1.3) / 60));
  return (m.prontos === false && m.faltam_mb ? `Na primeira vez o computador baixa os modelos de voz (${m.faltam_mb} MB). ` : '')
    + `O preparo leva cerca de ${min} min e é uma vez por corte. Pode fechar: ele continua no computador.`;
}
async function openVoz() {
  if (VOZ.aberto || !S.videoDuration) return;
  soltaEscolha();
  VOZ.aberto = true;
  VOZ.antes = snap();
  VOZ.vistaAntes = S.view;
  if (S.view === 'final') switchView('corte'); // a prévia segue o relógio do corte
  if (!VOZ.ac) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) VOZ.ac = new AC();
  }
  if (VOZ.ac && VOZ.ac.state === 'suspended') VOZ.ac.resume(); // no toque: o navegador deixa
  const v = vozNumeros(S.melhorar) || vozNumeros(vozBase(VOZ.info)) || vozNumeros(VOZ.info && VOZ.info.escolha) || { voz: 50, fundo: 20 };
  VOZ.voz = v.voz; VOZ.fundo = v.fundo; VOZ.original = false;
  vozValores();
  vozRegs(false);
  vozMostra({ texto: 'Conferindo a voz deste vídeo…' });
  showSheet($('vozSheet'), true);
  await vozCarregaInfo();
  vozSegue(false);
}
async function vozSegue(deNovo) {
  if (!VOZ.aberto) return;
  const i = VOZ.info;
  if (!i) { vozMostra({ erro: 'o editor não respondeu. Ele ainda está ligado no computador?' }); return; }
  if (i.preparo === 'pronto') {
    if ((i.duracao || S.videoDuration) > VOZ_PREVIA_MAX) { // escolhe sem ouvir: os números valem igual
      vozMostra({ nota: 'Vídeo longo: a prévia toca até 3 min de vídeo. A Voz e o Fundo escolhidos valem do mesmo jeito.' });
      vozRegs(true);
      return;
    }
    if (VOZ.preparado !== i.preparado || !VOZ.buf) await vozBaixaFaixas(i);
    else vozPronto();
    return;
  }
  const a = i.andamento;
  if (!deNovo && a && a.etapa === 'falhou') { vozMostra({ erro: a.erro || 'o preparo parou' }); return; }
  if (i.preparo !== 'preparando') { // nenhum, ou o corte mudou desde o último preparo
    try {
      const r = await fetch('/api/melhorar/preparar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const out = await r.json();
      if (!r.ok) { vozMostra({ erro: out.error || 'não consegui começar o preparo' }); return; }
      if (out.pronto) { await vozCarregaInfo(); vozSegue(false); return; }
    } catch (e) { vozMostra({ erro: 'não consegui começar o preparo' }); return; }
  }
  vozAcompanha();
}
function vozAcompanha() {
  clearTimeout(VOZ.timer);
  const passo = async () => {
    if (!VOZ.aberto) return;
    let a = null;
    try { a = await (await fetch('/api/melhorar/andamento')).json(); } catch (e) { /* servidor reiniciando */ }
    if (!VOZ.aberto) return;
    if (a && a.etapa === 'pronto') { await vozCarregaInfo(); vozSegue(false); return; }
    if (a && a.etapa === 'falhou') { vozMostra({ erro: a.erro || 'o preparo parou' }); return; }
    vozMostra({ a: a && a.etapa ? a : { texto: 'Começando o preparo', n: 0, de: 0 }, nota: vozNotaPreparo() });
    VOZ.timer = setTimeout(passo, 700);
  };
  passo();
}
async function vozBaixaFaixas(i) {
  const prep = i.preparado;
  vozMostra({ texto: 'Carregando a prévia…' });
  try {
    const bufs = await Promise.all(VOZ_FAIXAS.map(async (k) => {
      const r = await fetch(`/media/${i.previa[k].split('/').map(encodeURIComponent).join('/')}`);
      if (!r.ok) throw new Error(`${k}: ${r.status}`);
      return VOZ.ac.decodeAudioData(await r.arrayBuffer());
    }));
    if (!VOZ.aberto || !VOZ.info || VOZ.info.preparado !== prep) return;
    VOZ.buf = bufs;
    VOZ.preparado = prep;
  } catch (e) {
    vozMostra({ erro: `não consegui carregar a prévia (${e.message})` });
    return;
  }
  vozPronto();
}
function vozPronto() {
  vozMostra();
  vozRegs(true);
  applyMute();
  vozSincroniza();
}
/* o som: as 7 faixas começam juntas no ponto do vídeo, e cada uma tem um ganho */
// suave: as faixas que estavam tocando saem em ~10 ms (uma correção de desvio sem estalo)
function vozPara(suave) {
  const t = VOZ.ac ? VOZ.ac.currentTime : 0;
  if (suave && VOZ.nos) VOZ.nos.forEach((no) => no.gain.setTargetAtTime(0, t, 0.004));
  VOZ.fontes.forEach((s) => { try { s.stop(suave ? t + 0.04 : 0); } catch (e) { /* já parou */ } });
  VOZ.fontes = [];
  VOZ.nos = null;
}
function vozGanhos() {
  const n = 5, g = new Array(n).fill(0);
  if (VOZ.original) return [...g, 0, 1];
  const v = (VOZ.voz / 100) * (n - 1), i = Math.min(n - 2, Math.floor(v)), f = v - i;
  g[i] = 1 - f; g[i + 1] = f;
  return [...g, VOZ.fundo / 100, 0];
}
function vozAplica(imediato) {
  if (!VOZ.nos) return;
  const g = vozGanhos(), t = VOZ.ac.currentTime;
  VOZ.nos.forEach((no, k) => { if (imediato) no.gain.value = g[k]; else no.gain.setTargetAtTime(g[k], t, 0.015); });
}
// o volume da tomada e os dois silenciar, como no som do próprio vídeo
function vozVolume() {
  if (!VOZ.master) return;
  const mudo = S.mudoUsuario || (S.view === 'corte' && S.camadas.video.mudo);
  VOZ.master.gain.setTargetAtTime(mudo ? 0 : video.volume, VOZ.ac.currentTime, 0.01);
}
function vozSincroniza(correcao) {
  vozPara(correcao);
  if (!correcao) VOZ.correcoes = 0;
  if (!VOZ.aberto || !VOZ.buf || !VOZ.ac || video.paused || video.seeking || video.ended) return;
  if (VOZ.ac.state === 'suspended') VOZ.ac.resume();
  if (!VOZ.master) { VOZ.master = VOZ.ac.createGain(); VOZ.master.connect(VOZ.ac.destination); }
  // o que sai na caixa de som atrasa a latência do áudio: começa à frente, para cair com a imagem
  const lat = VOZ.ac.outputLatency || VOZ.ac.baseLatency || 0;
  const quando = VOZ.ac.currentTime + 0.03;
  VOZ.rate = video.playbackRate || 1;
  VOZ.off = video.currentTime + (quando - VOZ.ac.currentTime + lat) * VOZ.rate;
  VOZ.t0 = quando + lat;
  if (VOZ.off >= VOZ.buf[0].duration) return;
  VOZ.nos = VOZ.buf.map((b) => {
    const g = VOZ.ac.createGain();
    if (correcao) g.gain.value = 0; // entra junto com a saída das antigas
    g.connect(VOZ.master);
    const s = VOZ.ac.createBufferSource();
    s.buffer = b;
    s.playbackRate.value = VOZ.rate;
    s.connect(g);
    s.start(quando, Math.max(0, VOZ.off));
    VOZ.fontes.push(s);
    return g;
  });
  if (correcao) {
    const g = vozGanhos();
    VOZ.nos.forEach((no, k) => no.gain.setTargetAtTime(g[k], quando, 0.004));
  } else vozAplica(true);
  vozVolume();
}
['playing', 'seeked', 'ratechange'].forEach((ev) => video.addEventListener(ev, () => { if (VOZ.aberto) vozSincroniza(); }));
['pause', 'seeking', 'waiting', 'ended', 'emptied'].forEach((ev) => video.addEventListener(ev, () => { if (VOZ.nos) vozPara(); }));
video.addEventListener('volumechange', vozVolume);
// o relógio do áudio e o do vídeo andam juntos, mas não são o mesmo: passou de 45 ms, recomeça.
// Logo depois do play o vídeo ainda está assentando (medido: ~40 ms no 1º segundo), então ali a
// correção vale a partir de 15 ms, duas vezes no máximo
video.addEventListener('timeupdate', () => {
  if (!VOZ.nos || video.paused) return;
  const d = VOZ.off + (VOZ.ac.currentTime - VOZ.t0) * VOZ.rate - video.currentTime;
  const comeco = VOZ.ac.currentTime - VOZ.t0 < 1.5 && (VOZ.correcoes || 0) < 2;
  if (Math.abs(d) > (comeco ? 0.015 : 0.045)) {
    VOZ.correcoes = (VOZ.correcoes || 0) + 1;
    vozSincroniza(true);
  }
});
$('vozVoz').addEventListener('input', () => { VOZ.voz = +$('vozVoz').value; VOZ.original = false; vozValores(); vozAplica(false); });
$('vozFundo').addEventListener('input', () => { VOZ.fundo = +$('vozFundo').value; VOZ.original = false; vozValores(); vozAplica(false); });
$('vozOriginal').addEventListener('click', () => { VOZ.original = !VOZ.original; vozValores(); vozAplica(false); });
$('vozDeNovo').addEventListener('click', () => { vozMostra({ texto: 'Começando de novo…' }); vozSegue(true); });
$('vozOk').addEventListener('click', () => closeVoz('pronto'));
$('vozTirar').addEventListener('click', () => closeVoz('tirar'));
document.addEventListener('keydown', (e) => { if (VOZ.aberto && e.key === 'Escape') { e.preventDefault(); closeVoz(null); } });
/* Pronto guarda a escolha; Tirar volta o vídeo ao som original; fechar sem nada (Esc) não muda */
function closeVoz(acao) {
  if (!VOZ.aberto) return;
  clearTimeout(VOZ.timer);
  VOZ.aberto = false;
  vozPara();
  showSheet($('vozSheet'), false);
  const antes = JSON.stringify(S.melhorar);
  const base = vozBase(VOZ.info);
  if (acao === 'tirar') S.melhorar = base && !base.desligar ? { desligar: true } : null;
  else if (acao === 'pronto' && VOZ.regs) S.melhorar = { voz: VOZ.voz, fundo: VOZ.fundo };
  if (S.melhorar && JSON.stringify(S.melhorar) === S.melhorarBase) S.melhorar = null; // é o que o vídeo já tem
  if (JSON.stringify(S.melhorar) !== antes) remember(VOZ.antes);
  VOZ.original = false;
  applyMute();
  if (VOZ.vistaAntes === 'final' && S.view !== 'final' && hasFinal()) switchView('final');
  renderTimeline(); renderToolbar(); refreshHeader();
}

function applyMute() {
  // com a prévia do Melhorar voz tocando, o som é dela: o do vídeo sai
  video.muted = (VOZ.aberto && !!VOZ.buf) || S.mudoUsuario || (S.view === 'corte' && S.camadas.video.mudo);
  vozVolume();
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
/* Prévia do formato da montagem: o player toma o quadro do formato escolhido e cada lugar é desenhado
 * aqui, com um quadro da mídia original, pela mesma regra do montagem.py (_enquadrar): a mídia com
 * proporção a menos de 16/9 vezes da tela enche; mais longe, entra inteira sobre ela mesma desfocada
 * (o mesmo desfoque). A foto ganha o zoom do lugar. O clipe aparece parado no quadro em
 * que entra. É só para ver: o vídeo de verdade sai quando o agente refaz, no Salvar. */
const formatoPrevia = () => !!(S.montagem && S.formato && FORMATOS[S.formato] && S.formato !== S.formatoAtual);
// o mesmo levar_ponto do montagem.py: o ponto no mesmo lugar relativo do outro quadro, com duas casas
function levarPonto(x, y, de, para) {
  const [w0, h0] = FORMATOS[de].px, [w1, h1] = FORMATOS[para].px;
  const r2 = (v) => Math.round(v * 100) / 100;
  return { x: r2(Math.min(2160, Math.max(-1080, (x * w1) / w0))), y: r2(Math.min(3840, Math.max(-1920, (y * h1) / h0))) };
}
const ehFoto = (m) => /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(String(m || ''));
// a mídia e o trecho de um lugar: a troca ainda não feita vale
function midiaDoLugar(r) {
  const lg = lugarDe(r);
  if (!lg) return null;
  const t = r.troca || {};
  const midia = t.midia || lg.midia;
  const de = t.de != null ? +t.de : t.midia ? 0 : +(lg.de || 0);
  return { midia, de, foto: ehFoto(midia), movimento: lg.movimento || 'zoom-in' };
}
const quadroDoLugar = (m) => quadroDaMidia(m.midia, m.foto ? 0 : m.de, 720);
const OQ = { cache: new Map(), geo: null };
// o automático do montagem.py (_enquadrar) como escala de caber: enche quando a proporção está a menos de
// 16/9 vezes da tela, senão cabe inteira
function enqAuto(mw, mh, W, H) {
  const r0 = (mw / mh) / (W / H);
  return r0 < 16 / 9 && 1 / r0 < 16 / 9 ? Math.max(W / mw, H / mh) / Math.min(W / mw, H / mh) : 1;
}
function preCarregaQuadros() {
  for (const r of S.draft) {
    const m = r.vaga != null && midiaDoLugar(r);
    if (!m) continue;
    const src = quadroDoLugar(m);
    if (OQ.cache.has(src)) continue;
    const im = new Image();
    im.src = src;
    OQ.cache.set(src, im);
  }
}
function syncQuadro() {
  const box = $('ovQuadro');
  const dl = draftLayout();
  const k = itemAt(dl, S.t);
  const r = k >= 0 ? S.draft[k] : null;
  const escolhido = !!(r && r.vaga != null && S.view === 'corte' && S.selected === k);
  const mudou = !!(r && r.troca && 'enq' in r.troca);
  const m = r && r.vaga != null && (formatoPrevia() || escolhido || mudou) ? midiaDoLugar(r) : null;
  const im = m && OQ.cache.get(quadroDoLugar(m));
  const pronto = !!(im && im.complete && im.naturalWidth);
  box.classList.toggle('hidden', !m);
  S.quadroCobre = !!m;
  OQ.geo = null;
  $('oqCaixa').classList.add('hidden');
  const selo = m && formatoPrevia() ? `Prévia · ${FORMATOS[S.formato].nome} (${S.formato})` : m && mudou ? 'Prévia do enquadramento' : '';
  if ($('oqSelo').textContent !== selo) $('oqSelo').textContent = selo;
  if (!m) return;
  if (!pronto) { if (im) return; preCarregaQuadros(); return; }
  const img = $('oqImg'), fundo = $('oqFundo');
  if (img.dataset.src !== im.src) {
    img.src = im.src;
    img.dataset.src = im.src;
    fundo.style.backgroundImage = `url("${im.src}")`;
  }
  const W = FRAME_W, H = FRAME_H, mw = im.naturalWidth, mh = im.naturalHeight;
  // o enquadre do lugar, ou o automático escrito como um: a escala é em relação a caber inteira
  const caber = Math.min(W / mw, H / mh);
  const enq = enqDoLugar(r) || { escala: enqAuto(mw, mh, W, H), x: 0.5, y: 0.5 };
  const kk = caber * enq.escala;
  const dw = mw * kk, dh = mh * kk, x0 = enq.x * W - dw / 2, y0 = enq.y * H - dh / 2;
  Object.assign(img.style, { left: pct(x0 / W), top: pct(y0 / H), width: pct(dw / W), height: pct(dh / H) });
  OQ.geo = { vaga: r.vaga, W, H, mw, mh, enq, cobrir: Math.max(W / mw, H / mh) / caber };
  if (escolhido) { // a moldura: a parte da mídia que fica na tela, com a bolinha no canto
    const vx0 = Math.max(0, x0), vy0 = Math.max(0, y0), vx1 = Math.min(W, x0 + dw), vy1 = Math.min(H, y0 + dh);
    Object.assign($('oqCaixa').style, { left: pct(vx0 / W), top: pct(vy0 / H), width: pct((vx1 - vx0) / W), height: pct((vy1 - vy0) / H) });
    $('oqCaixa').classList.remove('hidden');
  }
  // o desfoque do montagem.py: 12 px no fundo feito em 1/4; a foto é montada no dobro do quadro (para o
  // zoom andar liso), então no quadro final o dela é metade do do clipe
  const P = player.getBoundingClientRect();
  fundo.style.filter = `blur(${(((m.foto ? 24 : 48) * P.width) / W).toFixed(2)}px)`;
  // o zoom da foto: o do montagem.py, 4% por segundo até 10%, no lugar inteiro
  let z = 1;
  const d = dl[k];
  if (m.foto && d && d.dur > 0 && !escolhido) { // escolhido, fica parado para o ajuste ser exato
    const extra = Math.min(0.10, 0.04 * d.dur), p = Math.max(0, Math.min(1, (S.t - d.out) / d.dur));
    z = m.movimento === 'parado' ? 1 : m.movimento === 'zoom-out' ? 1 + extra - extra * p : 1 + extra * p;
  }
  $('oqCena').style.transform = `scale(${z.toFixed(5)})`;
}
function poeEnq(r, enq) {
  const lg = lugarDe(r) || {};
  const t = { ...(r.troca || {}) };
  const salvo = t.midia || formatoPrevia() ? null : lg.enquadre || null;
  if (mesmoEnq(enq, salvo)) delete t.enq; else t.enq = enq;
  r.troca = Object.keys(t).length ? t : null;
}
const oqDrag = { id: null };
$('oqCaixa').addEventListener('pointerdown', (e) => {
  const r = S.draft[S.selected], g = OQ.geo;
  if (!r || !g || g.vaga !== r.vaga) return;
  e.preventDefault();
  e.stopPropagation();
  const P = player.getBoundingClientRect();
  const cx = P.left + g.enq.x * P.width, cy = P.top + g.enq.y * P.height;
  Object.assign(oqDrag, { id: e.pointerId, r, P, modo: e.target.closest('[data-oq-tam]') ? 'tam' : 'mover', x0: e.clientX,
    y0: e.clientY, cx, cy, d0: Math.max(6, Math.hypot(e.clientX - cx, e.clientY - cy)), e0: { ...g.enq }, cobrir: g.cobrir,
    before: snap(), mudou: false });
  video.pause();
  window.addEventListener('pointermove', oqMove);
  window.addEventListener('pointerup', oqFim);
  window.addEventListener('pointercancel', oqFim);
});
function oqMove(e) {
  if (e.pointerId !== oqDrag.id) return;
  const d = oqDrag, r4 = (v) => Math.round(v * 10000) / 10000;
  let { escala, x, y } = d.e0;
  if (d.modo === 'tam') { // longe do centro aumenta; gruda em caber inteira e em encher a tela
    escala = Math.max(0.25, Math.min(6, d.e0.escala * (Math.hypot(e.clientX - d.cx, e.clientY - d.cy) / d.d0)));
    for (const alvo of [1, d.cobrir]) if (Math.abs(escala / alvo - 1) < 0.04) escala = alvo;
  } else { // o centro anda com o dedo; perto do meio, encaixa no meio
    x = Math.max(0, Math.min(1, d.e0.x + (e.clientX - d.x0) / d.P.width));
    y = Math.max(0, Math.min(1, d.e0.y + (e.clientY - d.y0) / d.P.height));
    if (Math.abs(x - 0.5) < 0.015) x = 0.5;
    if (Math.abs(y - 0.5) < 0.015) y = 0.5;
  }
  d.mudou = true;
  poeEnq(d.r, { escala: r4(escala), x: r4(x), y: r4(y) });
}
function oqFim(e) {
  if (e.pointerId !== oqDrag.id) return;
  window.removeEventListener('pointermove', oqMove);
  window.removeEventListener('pointerup', oqFim);
  window.removeEventListener('pointercancel', oqFim);
  oqDrag.id = null;
  tapGuard.until = performance.now() + 400; // arrastar a foto não dá play
  if (!oqDrag.mudou) return;
  remember(oqDrag.before);
  renderTimeline(); renderToolbar(); refreshHeader();
}
// Caber (inteira), Encher (cobre a tela), Automático (a regra do montagem.py) e o mesmo nas outras vezes da mídia
function enqRapido(qual) {
  const r = S.draft[S.selected], g = OQ.geo;
  if (!r || r.vaga == null) return;
  if (qual !== 'auto' && !(g && g.vaga === r.vaga)) { toast('Ponha a agulha neste lugar para ver o enquadramento.', 2600); return; }
  remember();
  if (qual === 'auto') poeEnq(r, null);
  else poeEnq(r, { escala: qual === 'caber' ? 1 : Math.round(g.cobrir * 10000) / 10000, x: 0.5, y: 0.5 });
  renderTimeline(); renderToolbar(); refreshHeader();
}
const outrasVezes = (r) => S.draft.filter((o) => o !== r && o.vaga != null && (lugarAgora(o).midia === lugarAgora(r).midia));
function enqNasOutras() {
  const r = S.draft[S.selected];
  if (!r || r.vaga == null) return;
  const outras = outrasVezes(r);
  if (!outras.length) return;
  remember();
  const enq = enqDoLugar(r);
  for (const o of outras) poeEnq(o, enq ? { ...enq } : null);
  toast(`O mesmo enquadramento em mais ${outras.length} ${outras.length === 1 ? 'lugar' : 'lugares'} com esta mídia.`, 2600);
  renderTimeline(); renderToolbar(); refreshHeader();
}
function syncLayers() {
  const corte = S.view === 'corte';
  const playing = !video.paused && !video.ended && !G.mode;
  const rt = corte ? draftToRendered(S.t) : 0;
  const vivos = new Set();
  let img = '', imgAtras = false;
  if (corte && S.camadas) {
    for (const f of S.camadas.faixas) {
      for (const it of f.itens) {
        const dentro = rt >= it.inicio && rt < it.inicio + it.duracao;
        if (!dentro) continue;
        // a camada mais nova fica por cima, como no vídeo final (os inserts dela entram por último)
        if (f.tipo === 'imagem') { if (!f.oculto) { img = it.arquivo; imgAtras = !!it.atras; } continue; }
        if (f.tipo === 'texto') continue; // os textos: desenhaTextos
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
  $('ovImg').classList.toggle('atras', imgAtras); // o cartão grande de trás, no lugar dele no vídeo final
  syncQuadro();
  desenhaTextos();
  desenhaLegendaPrevia(false);
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
  btn.textContent = `Escolher música ${isDesk() ? 'do computador' : 'do celular'}`;
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
// cruzar é passar mais que a sobra do arredondamento (ENCOSTA no efeitos.py): duas tomadas
// vizinhas se encostam com até 1 ms de sobra, e sem a folga o filtro de uma apagava o da
// outra no Usar, e o Ajustar de uma abria o ajuste da vizinha
const FX_ENCOSTA = 1.5e-3;
const fxCruzam = (x, y) => { const [a, b] = fxJanela(x), [c, d] = fxJanela(y); return a < d - FX_ENCOSTA && c < b - FX_ENCOSTA; };

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
        tempo_ms: (t - (tr.corte - tr.duracao / 2)) * 1000, duracao_ms: tr.duracao * 1000 });
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
  S.cenaSel = -1; S.zoomSel = -1; drawCenaBox();
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
  // filtros e transições moram no corte: no Final o vídeo já vem pronto, a prévia não
  // desenha por cima e a faixa de efeitos não aparece; o "Usar" ficava invisível
  if (S.view === 'final') {
    switchView('corte');
    toast('Efeitos no corte: a prévia toca aqui', 2600);
  }
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

/* ---------- Fundo: um fundo novo atrás da pessoa (o efeito `fundo` do vídeo final) ----------
 * Vale para a tomada debaixo da agulha, ou para o Fundo escolhido na faixa de efeitos. Cada
 * cartão é um fundo com a pessoa recortada no quadro da agulha por cima: o mesmo recorte do
 * vídeo final (/gen/recorte), o véu de Escurecer entre os dois e o Desfoque na escala do
 * cartão. O primeiro cartão é o vídeo como está. Pronto cria o efeito, troca o Fundo que a
 * tomada já tem ou o desliga; o agente recorta a janela e refaz só esse trecho. A prévia grande
 * mostra o escolhido parado no quadro da agulha: o vídeo de agora segue com o fundo de antes. */
const FUNDOS_PRONTOS = [['concreto', 'Concreto'], ['parede', 'Parede'], ['kraft', 'Papel kraft'], ['lousa', 'Lousa'], ['estudio', 'Estúdio'], ['neon', 'Neon']];
const FU = { aberto: false, alvo: -1, a: 0, b: 0, t: -1, escolha: '', escurecer: FUNDO_PADRAO.escurecer, desfoque: FUNDO_PADRAO.desfoque,
  quadro: null, recorte: null, erro: null, midia: [], outro: null, pedido: null, espera: null };
const fundoPode = () => hasFinal() && !!S.editData; // o Fundo é um efeito do vídeo final (edit-data.json)
const fundoUrl = (f) => (f.startsWith('fundos/') ? `/assets/${f}.jpg` : `/media/${f.split('/').map(encodeURIComponent).join('/')}`);
const cruzaFundo = (x) => x.start < FU.b - 0.01 && x.end > FU.a + 0.01;
const naJanela = () => { const rt = draftToRendered(S.t); return rt >= FU.a - 0.01 && rt < FU.b; };
const fundoVars = (n) => { n.style.setProperty('--veu', FU.escurecer); n.style.setProperty('--desfoque', FU.desfoque); };
// o que impede o Pronto de pôr um fundo: outro efeito ligado na janela, ou uma tomada curta demais
const fundoBloqueio = () => (FU.outro ? `Esta tomada já tem o efeito ${FU.outro.nome}: desligue ele na faixa de efeitos para pôr um fundo aqui.`
  : FU.b - FU.a < 0.3 ? 'Esta tomada é curta demais para um fundo novo.' : null);
function novoFundo(a, b, campos) {
  return { ref: null, nova: true, tipo: 'fundo', start: a, end: b, nome: CENA_NOME.fundo, cena: { tipo: 'fundo', start: a, end: b },
    desligada: false, texto: null, textos: {}, estilo: null, campos, orig: null };
}
async function openFundo(i) {
  if (!fundoPode()) { toast('O Fundo entra no vídeo final: ele aparece depois que o agente fizer a Fase 2', 3200); return; }
  if (S.view !== 'final') switchView('final');
  video.pause();
  let c = i != null ? S.cenasDraft[i] : null;
  if (c) { FU.a = c.start; FU.b = c.end; } else {
    const tk = tomadaEm(draftToRendered(S.t));
    if (!tk) return;
    FU.a = +tk.out.toFixed(3); FU.b = +(tk.out + tk.dur).toFixed(3);
    i = S.cenasDraft.findIndex((x) => x.tipo === 'fundo' && cruzaFundo(x)); // a tomada já tem um Fundo: é ele que muda
    c = i >= 0 ? S.cenasDraft[i] : null;
    if (c) { FU.a = c.start; FU.b = c.end; }
  }
  FU.alvo = c ? i : -1;
  FU.escolha = c && !c.desligada ? c.campos.fundo : '';
  FU.escurecer = c ? c.campos.escurecer : FUNDO_PADRAO.escurecer;
  FU.desfoque = c ? c.campos.desfoque : FUNDO_PADRAO.desfoque;
  FU.outro = S.cenasDraft.find((x) => x.tipo !== 'fundo' && !x.desligada && cruzaFundo(x)) || null;
  FU.quadro = captureFrame(); // o cartão "Original": o quadro como o vídeo está
  FU.t = -1;
  FU.erro = null;
  FU.aberto = true;
  $('fundoTitulo').textContent = c ? 'Fundo da tomada' : 'Fundo novo';
  $('fundoEscurecer').value = Math.round(FU.escurecer * 100);
  $('fundoDesfoque').value = FU.desfoque;
  app.classList.add('efeitando');
  showSheet($('fundoSheet'), true);
  renderFundo();
  fundoMidia();
  fundoRecorte();
}
function closeFundo() {
  FU.aberto = false;
  clearTimeout(FU.espera);
  if (FU.pedido) { FU.pedido.abort(); FU.pedido = null; }
  if (FU.recorte) { URL.revokeObjectURL(FU.recorte); FU.recorte = null; }
  $('ovFundo').classList.add('hidden');
  app.classList.remove('efeitando');
  showSheet($('fundoSheet'), false);
  sizeCanvases(); positionTimeline(); // a linha do tempo volta a aparecer
}
function renderFundo() {
  const box = $('fundoLista');
  box.innerHTML = '';
  el('p', 'sheet-hint', box).id = 'fundoDica';
  const grade = el('div', 'mod-grade fundo-grade', box);
  fundoVars(grade);
  const cartao = (f, nome) => {
    const b = el('button', 'mod-card fundo-card', grade);
    b.type = 'button';
    b.dataset.fundo = f;
    if (f) {
      el('div', 'fundo-bg', b).style.backgroundImage = `url("${fundoUrl(f)}")`;
      el('div', 'fundo-veu', b);
      if (FU.recorte) { const im = el('img', 'fundo-pessoa', b); im.src = FU.recorte; im.alt = ''; }
    } else if (FU.quadro) b.style.backgroundImage = `url("${FU.quadro}")`;
    el('span', 'mod-nome', b).textContent = nome;
  };
  cartao('', 'Original');
  for (const [id, nome] of FUNDOS_PRONTOS) cartao(`fundos/${id}`, nome);
  for (const m of FU.midia) cartao(m.arquivo, m.nome.replace(/\.[^.]+$/, ''));
  const mais = el('button', 'mod-card fundo-mais', grade); // uma foto do aparelho vira fundo (vai para midia/)
  mais.type = 'button';
  mais.dataset.fundoMais = '1';
  mais.innerHTML = ICON.mais;
  el('span', 'mod-nome', mais).textContent = 'Sua imagem';
  fundoEstado();
}
// o que muda sem redesenhar os cartões: o escolhido, a dica, as réguas e o Pronto
function fundoEstado() {
  for (const b of $('fundoLista').querySelectorAll('.fundo-card')) b.classList.toggle('on', b.dataset.fundo === FU.escolha);
  const bloqueio = FU.escolha ? fundoBloqueio() : null;
  const dica = $('fundoDica');
  if (dica) {
    dica.textContent = bloqueio || (FU.erro ? `Os cartões estão sem você: ${FU.erro}`
      : !FU.recorte ? 'Recortando você do quadro da agulha…'
        : 'Toque num fundo: ele entra atrás de você nesta tomada.');
  }
  $('fundoRegs').classList.toggle('off', !FU.escolha);
  $('fundoEscurecerVal').textContent = `${Math.round(FU.escurecer * 100)}%`;
  $('fundoDesfoqueVal').textContent = String(FU.desfoque);
  $('fundoOk').disabled = !!bloqueio;
  fundoPrevia();
}
// o cartão "Original" nasce com a miniatura da faixa quando o vídeo ainda não tem quadro (acabou de
// trocar para o Final): assim que ele tiver, o cartão passa para o quadro nítido
function fundoQuadroNitido() {
  if (String(FU.quadro || '').startsWith('data:')) return;
  const q = captureFrame();
  if (!q.startsWith('data:')) return;
  FU.quadro = q;
  const b = document.querySelector('#fundoLista .fundo-card[data-fundo=""]');
  if (b) b.style.backgroundImage = `url("${q}")`;
}
// a prévia grande: o fundo escolhido atrás do recorte, só parada e com a agulha na janela
function fundoPrevia() {
  const ov = $('ovFundo');
  const mostra = FU.aberto && !!FU.escolha && !!FU.recorte && video.paused && naJanela();
  ov.classList.toggle('hidden', !mostra);
  if (!mostra) return;
  fundoVars(ov);
  $('ovFundoBg').style.backgroundImage = `url("${fundoUrl(FU.escolha)}")`;
  if ($('ovFundoPessoa').getAttribute('src') !== FU.recorte) $('ovFundoPessoa').src = FU.recorte;
}
// a pessoa recortada no quadro da agulha (dentro da janela), no relógio do corte
async function fundoRecorte() {
  const fps = S.state.fps || 30;
  const rt = Math.min(Math.max(draftToRendered(S.t), FU.a), FU.b - 1 / fps);
  const t = Math.round(rt * fps) / fps;
  if (t === FU.t && (FU.recorte || FU.pedido)) return;
  FU.t = t;
  if (FU.pedido) FU.pedido.abort();
  const pedido = new AbortController();
  FU.pedido = pedido;
  try {
    const r = await fetch(`/gen/recorte?t=${t.toFixed(3)}&v=${S.mtimes.video || 0}`, { signal: pedido.signal });
    if (!r.ok) {
      let msg = `erro ${r.status}`;
      try { msg = (await r.json()).error || msg; } catch (e) { /* sem JSON */ }
      throw new Error(msg);
    }
    const url = URL.createObjectURL(await r.blob());
    if (FU.pedido !== pedido || !FU.aberto) { URL.revokeObjectURL(url); return; }
    if (FU.recorte) URL.revokeObjectURL(FU.recorte);
    FU.recorte = url;
    FU.erro = null;
  } catch (e) {
    if (e.name === 'AbortError' || FU.pedido !== pedido) return;
    FU.erro = e.message;
  }
  FU.pedido = null;
  if (FU.aberto) { renderFundo(); fundoQuadroNitido(); }
}
// as imagens do projeto (midia/): cada uma é um cartão
async function fundoMidia() {
  try {
    const d = await (await fetch('/api/midia')).json();
    FU.midia = (d.midia || []).filter((m) => m.tipo === 'imagem');
  } catch (e) { return; } // sem a lista: só os prontos do kit
  if (FU.aberto) renderFundo();
}
const cenasSig = () => JSON.stringify(S.cenasDraft.map((c) => [c.nova ? 'nova' : c.ref, c.start, cenaSig(c)]));
function fundoPronto() {
  if (FU.escolha && fundoBloqueio()) return;
  const antes = snap(), sig = cenasSig();
  const campos = FU.escolha ? { fundo: FU.escolha, escurecer: +FU.escurecer.toFixed(2), desfoque: FU.desfoque } : null;
  const c = FU.alvo >= 0 ? S.cenasDraft[FU.alvo] : null;
  let sel = FU.alvo;
  if (c && campos) { c.campos = campos; c.desligada = false; } else if (c) {
    // "Original": o Fundo novo nunca salvo sai; o do agente (ou o novo já enviado) vai desligado
    if (c.nova && !c.orig) { S.cenasDraft.splice(FU.alvo, 1); sel = -1; } else c.desligada = true;
  } else if (campos) {
    S.cenasDraft.push(novoFundo(FU.a, FU.b, campos));
    sel = S.cenasDraft.length - 1;
  }
  const mudou = cenasSig() !== sig;
  if (mudou) remember(antes);
  closeFundo();
  S.cenaSel = sel; // o Fundo fica escolhido na faixa, com as ferramentas dele
  S.zoomSel = -1; S.insSel = -1; S.selected = -1; S.layerSel = null; S.fxSel = null; S.legSel = false;
  renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
  if (mudou) {
    toast(!campos ? 'A tomada volta ao fundo do vídeo' : c ? 'Fundo trocado. Salve: o agente refaz só esta tomada'
      : 'Fundo novo nesta tomada. Salve: o agente recorta você e refaz só este trecho', 3200);
  }
}
// o Fundo criado aqui, na faixa: nunca salvo, sai; já enviado, vai desligado (o agente não acrescenta)
function cenaExclui() {
  const c = S.cenasDraft[S.cenaSel];
  if (!c || !c.nova) return;
  remember();
  if (c.orig) c.desligada = true;
  else { S.cenasDraft.splice(S.cenaSel, 1); S.cenaSel = -1; }
  renderTimeline(); renderToolbar(); refreshHeader(); drawCenaBox();
}
$('fundoClose').innerHTML = ICON.fechar;
$('fundoClose').addEventListener('click', closeFundo);
$('fundoOk').addEventListener('click', fundoPronto);
$('fundoLista').addEventListener('click', (e) => {
  const b = e.target.closest('.mod-card');
  if (!b) return;
  if (b.dataset.fundoMais) { $('fileFundo').click(); return; }
  FU.escolha = b.dataset.fundo;
  fundoEstado();
});
$('fundoEscurecer').addEventListener('input', (e) => { FU.escurecer = +e.target.value / 100; fundoReguas(); });
$('fundoDesfoque').addEventListener('input', (e) => { FU.desfoque = +e.target.value; fundoReguas(); });
function fundoReguas() {
  const g = document.querySelector('#fundoLista .fundo-grade');
  if (g) fundoVars(g);
  fundoEstado();
}
$('fileFundo').addEventListener('change', (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (f) sendVideo(f, (res) => { FU.escolha = res.arquivo; if (FU.aberto) fundoMidia(); });
});
// tocar ou mover a agulha com o painel aberto: a prévia grande some tocando e volta parada, com o
// recorte do quadro novo (um pedido por parada, não um por quadro arrastado)
['play', 'pause', 'seeked'].forEach((ev) => video.addEventListener(ev, () => {
  if (!FU.aberto) return;
  if (ev === 'seeked') fundoQuadroNitido();
  fundoPrevia();
  clearTimeout(FU.espera);
  if (ev !== 'play') FU.espera = setTimeout(() => { if (FU.aberto && video.paused && naJanela()) fundoRecorte(); }, 450);
}));

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
