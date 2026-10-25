// As páginas do mural: a casca (com a política de segurança), o cartão de um modelo e a capa do
// ritmo. Todo texto que veio de quem publicou passa por `esc`; a capa é SVG com atributos, sem
// estilo em linha (a política não deixa estilo nem script em linha).

import { embedDo, perfil } from './post.js';

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const CSP = [
  "default-src 'self'",
  "script-src 'self' https://challenges.cloudflare.com",
  "style-src 'self' https://fonts.googleapis.com",
  'font-src https://fonts.gstatic.com',
  "img-src 'self' data:",
  'frame-src https://www.instagram.com https://www.tiktok.com https://www.youtube-nocookie.com https://challenges.cloudflare.com',
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "object-src 'none'",
].join('; ');

export const CABECALHOS = {
  'Content-Security-Policy': CSP,
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
};

export function pagina({ titulo, corpo, scripts = [], status = 200, semIndice = false }) {
  const html = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(titulo)} · Mural CutMind</title>
${semIndice ? '<meta name="robots" content="noindex">' : ''}
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="apple-touch-icon" href="/icone-192.png">
<meta name="theme-color" content="#101010">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700;800&display=swap">
<link rel="stylesheet" href="/static/mural.css">
</head>
<body>
<header class="topo"><a class="marca" href="/">CutMind <span>Mural</span></a></header>
<main>${corpo}</main>
${scripts.map((s) => `<script src="${esc(s)}" defer></script>`).join('\n')}
</body>
</html>`;
  return new Response(html, { status, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CABECALHOS } });
}

// a capa: uma barra por lugar, na largura das batidas dele, mais alta do drop em diante; em cima, a
// janela de cada texto (o mesmo desenho do painel Modelos de montagem do editor)
export function capaRitmo(r) {
  const total = Math.max(1, r.batidas);
  let x = 0;
  const barras = r.ritmo.map((nb, i) => {
    const drop = r.drop_na_vaga && i + 1 >= r.drop_na_vaga;
    const h = r.drop_na_vaga ? (drop ? 60 : 26) : 42;
    const rect = `<rect x="${x}" y="${82 - h}" width="${Math.max(0.0001, nb - 0.06 * Math.min(nb, 1))}" height="${h}" class="${drop ? 'b-drop' : 'b'}"/>`;
    x += nb;
    return rect;
  });
  const textos = r.textos.map((t) => {
    const ini = r.ritmo.slice(0, t.vaga - 1).reduce((a, b) => a + b, 0);
    if (ini >= total) return '';
    const larg = Math.min(t.batidas || r.ritmo[t.vaga - 1] || 1, total - ini);
    return `<rect x="${ini}" y="6" width="${larg}" height="5" class="t"/>`;
  });
  return `<svg class="ritmo" viewBox="0 0 ${total} 88" preserveAspectRatio="none" aria-hidden="true">${textos.join('')}${barras.join('')}</svg>`;
}

const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

export function linhaResumo(r) {
  const b = [plural(r.lugares, 'lugar', 'lugares'), `${r.batidas} batidas`, r.formato];
  if (r.textos.length) b.push(plural(r.textos.length, 'texto', 'textos'));
  if (r.transicoes) b.push(plural(r.transicoes, 'transição', 'transições'));
  return b.join(' · ');
}

const NOME_PLATAFORMA = { instagram: 'Instagram', tiktok: 'TikTok', youtube: 'YouTube' };

// `grande`: a página do modelo (o post já embutido); na grade, o post entra quando a pessoa toca
export function cartao(m, { grande = false } = {}) {
  const r = m.resumo;
  const embed = embedDo(m.post);
  const link = perfil(m.autor, m.plataforma);
  const autor = m.autor
    ? `<a class="autor" href="${esc(link)}" target="_blank" rel="noopener nofollow ugc">@${esc(m.autor)}</a>`
    : '';
  const verPost = m.post
    ? `<a href="${esc(m.post)}" target="_blank" rel="noopener nofollow ugc">ver no ${esc(NOME_PLATAFORMA[m.plataforma] || 'post')}</a>`
    : '';
  const quem = [autor, verPost].filter(Boolean).join(' · ');
  const player = embed
    ? (grande
      ? `<div class="post ${esc(m.plataforma)}"><iframe src="${esc(embed)}" loading="lazy" allowfullscreen title="O post de ${esc(m.autor || 'quem publicou')}"></iframe></div>`
      : `<button class="post-tocar" type="button" data-embed="${esc(embed)}" data-plataforma="${esc(m.plataforma)}">Ver o post aqui</button>`)
    : '';
  return `<article class="cartao${grande ? ' grande' : ''}">
  <a class="capa" href="/m/${esc(m.id)}">${capaRitmo(r)}<span class="fmt">${esc(r.formato)}</span></a>
  ${player}
  <h2><a href="/m/${esc(m.id)}">${esc(m.nome)}</a></h2>
  <p class="meta">${esc(linhaResumo(r))}</p>
  ${quem ? `<p class="quem">${quem}</p>` : ''}
</article>`;
}
