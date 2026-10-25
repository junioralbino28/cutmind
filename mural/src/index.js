// O mural de modelos de montagem do CutMind. Rotas:
//   GET  /                         a grade (os mais novos primeiro; ?antes=<criado>.<id> pagina)
//   GET  /m/<id>                   a página de um modelo: o link que se compartilha
//   GET  /publicar                 publicar (o editor abre com o modelo no fragmento: #m=<base64url>)
//   GET  /api/modelos              a lista em JSON (?antes=<o "seguinte" da página anterior>&n=<até 48>)
//   GET  /api/modelos/<id>         um modelo em JSON (?baixar=1: como arquivo)
//   POST /api/modelos              publicar {modelo, nome, autor?, post?, turnstile}
//   POST /api/modelos/<id>/denunciar  {motivo}
//   GET  /admin, POST /admin/acao  o painel do dono (Cloudflare Access; admin.js)
// O que é estático (CSS e JS das páginas) sai de public/, antes de chegar aqui.

import { adminDe, painel } from './admin.js';
import { CABECALHOS, cartao, esc, linhaResumo, pagina } from './html.js';
import { conferirModelo, ModeloInvalido, resumoDoModelo } from './modelo.js';
import { lerAutor, lerPost, PostInvalido } from './post.js';

const MAX_CORPO = 64 * 1024;
const NOME_MAX = 60;
const MOTIVOS = { ofensivo: 'Conteúdo ofensivo', direitos: 'Usa conteúdo de outra pessoa', spam: 'Spam ou propaganda', outro: 'Outro motivo' };

const json = (dados, status = 200, extra = {}) => new Response(JSON.stringify(dados), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store', ...extra },
});
const erro = (msg, status = 400) => json({ erro: msg }, status);

export class PedidoInvalido extends Error {}

// o corpo do pedido, lido até `max` bytes: um corpo maior é recusado sem ser lido inteiro
async function lerJson(request, max = MAX_CORPO) {
  const declarado = Number(request.headers.get('Content-Length') || 0);
  if (declarado > max) throw new PedidoInvalido('pedido grande demais');
  if (!request.body) throw new PedidoInvalido('pedido vazio');
  const leitor = request.body.getReader();
  const partes = [];
  let total = 0;
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) {
      await leitor.cancel();
      throw new PedidoInvalido('pedido grande demais');
    }
    partes.push(value);
  }
  const bytes = new Uint8Array(total);
  let pos = 0;
  for (const p of partes) { bytes.set(p, pos); pos += p.byteLength; }
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new PedidoInvalido('o pedido não é um JSON');
  }
}

const mesmaOrigem = (request) => request.headers.get('Origin') === new URL(request.url).origin;

// o IP só como sha-256 com sal: conta o limite por dia sem guardar o IP de ninguém
async function hashDoIp(request, env) {
  if (!env.SAL_IP) throw new Error('SAL_IP não configurado');
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${env.SAL_IP}|${ip}`));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function turnstileOk(token, request, env) {
  if (!env.TURNSTILE_SECRET || typeof token !== 'string' || !token || token.length > 4096) return false;
  const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ secret: env.TURNSTILE_SECRET, response: token, remoteip: request.headers.get('CF-Connecting-IP') || undefined }),
  });
  if (!r.ok) return false;
  const d = await r.json();
  return d.success === true;
}

function novoId() {
  const b = crypto.getRandomValues(new Uint8Array(9));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_');
}

function nomeDoModelo(v) {
  if (typeof v !== 'string') throw new PedidoInvalido('o nome do modelo');
  const s = v.replace(/\s+/g, ' ').trim();
  if (!s || [...s].length > NOME_MAX || /[\u0000-\u001f\u007f]/.test(s)) {
    throw new PedidoInvalido(`o nome do modelo: de 1 a ${NOME_MAX} letras`);
  }
  return s;
}

// a linha do banco como o mural mostra
function doBanco(l) {
  const modelo = JSON.parse(l.modelo);
  return { id: l.id, nome: l.nome, autor: l.autor, post: l.post, plataforma: l.plataforma, criado: l.criado,
    modelo, resumo: resumoDoModelo(modelo), status: l.status, denuncias: l.denuncias };
}

// a página seguinte começa depois do último modelo da anterior: `antes` é "<criado>.<id>" dele (o
// id desempata os publicados no mesmo segundo, que só pelo horário pulariam de uma página à outra)
function lerCursor(v) {
  const r = typeof v === 'string' ? v.match(/^(\d{1,12})\.([A-Za-z0-9_-]{12})$/) : null;
  return r ? { criado: Number(r[1]), id: r[2] } : null;
}
const cursorDe = (m) => `${m.criado}.${m.id}`;

async function listar(env, cursor, n) {
  const { results } = cursor
    ? await env.DB.prepare(
      'SELECT * FROM modelos WHERE status = ?1 AND (criado < ?2 OR (criado = ?2 AND id > ?3)) ORDER BY criado DESC, id LIMIT ?4',
    ).bind('publicado', cursor.criado, cursor.id, n).all()
    : await env.DB.prepare('SELECT * FROM modelos WHERE status = ?1 ORDER BY criado DESC, id LIMIT ?2')
      .bind('publicado', n).all();
  return results.map(doBanco);
}

async function um(env, id) {
  if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{12}$/.test(id)) return null;
  const l = await env.DB.prepare('SELECT * FROM modelos WHERE id = ?1').bind(id).first();
  return l ? doBanco(l) : null;
}

const agora = () => Math.floor(Date.now() / 1000);
const publico = (m) => ({ id: m.id, nome: m.nome, autor: m.autor, post: m.post, plataforma: m.plataforma, criado: m.criado, resumo: m.resumo });

async function publicar(request, env) {
  if (!mesmaOrigem(request)) return erro('publique pela página do mural', 403);
  const ipHash = await hashDoIp(request, env);
  if (env.LIMITE_PUBLICAR) {
    const { success } = await env.LIMITE_PUBLICAR.limit({ key: `publicar:${ipHash}` });
    if (!success) return erro('muitos envios seguidos: espere um minuto', 429);
  }
  const corpo = await lerJson(request);
  if (!corpo || typeof corpo !== 'object') throw new PedidoInvalido('o pedido');
  const modelo = conferirModelo(corpo.modelo);
  const nome = nomeDoModelo(corpo.nome);
  const autor = lerAutor(corpo.autor);
  const post = lerPost(corpo.post);
  const porDia = Number(env.PUBLICAR_POR_DIA || 10);
  const { n } = await env.DB.prepare('SELECT COUNT(*) AS n FROM modelos WHERE ip_hash = ?1 AND criado > ?2')
    .bind(ipHash, agora() - 86400).first();
  if (n >= porDia) return erro(`limite de ${porDia} modelos por dia`, 429);
  if (!(await turnstileOk(corpo.turnstile, request, env))) return erro('confirme que você não é um robô', 403);
  const id = novoId();
  await env.DB.prepare(
    'INSERT INTO modelos (id, nome, autor, post, plataforma, modelo, criado, ip_hash) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)',
  ).bind(id, nome, autor, post ? post.url : null, post ? post.plataforma : null, JSON.stringify(modelo), agora(), ipHash).run();
  console.log(JSON.stringify({ evento: 'publicado', id }));
  return json({ id, url: `${new URL(request.url).origin}/m/${id}` }, 201);
}

async function denunciar(request, env, id) {
  if (!mesmaOrigem(request)) return erro('denuncie pela página do mural', 403);
  const ipHash = await hashDoIp(request, env);
  if (env.LIMITE_DENUNCIAR) {
    const { success } = await env.LIMITE_DENUNCIAR.limit({ key: `denunciar:${ipHash}` });
    if (!success) return erro('muitas denúncias seguidas: espere um minuto', 429);
  }
  const corpo = await lerJson(request, 2048);
  const motivo = corpo && Object.hasOwn(MOTIVOS, corpo.motivo) ? corpo.motivo : null;
  if (!motivo) throw new PedidoInvalido('o motivo da denúncia');
  const m = await um(env, id);
  if (!m || m.status !== 'publicado') return erro('modelo não encontrado', 404);
  const porDia = Number(env.DENUNCIAR_POR_DIA || 30);
  const { n } = await env.DB.prepare('SELECT COUNT(*) AS n FROM denuncias WHERE ip_hash = ?1 AND criado > ?2')
    .bind(ipHash, agora() - 86400).first();
  if (n >= porDia) return erro('limite de denúncias por dia', 429);
  await env.DB.batch([
    env.DB.prepare('INSERT OR IGNORE INTO denuncias (modelo_id, motivo, criado, ip_hash) VALUES (?1, ?2, ?3, ?4)').bind(m.id, motivo, agora(), ipHash),
    env.DB.prepare('UPDATE modelos SET denuncias = (SELECT COUNT(*) FROM denuncias WHERE modelo_id = ?1) WHERE id = ?1').bind(m.id),
  ]);
  console.log(JSON.stringify({ evento: 'denunciado', id: m.id, motivo }));
  return json({ ok: true });
}

function paginaGrade(modelos, antes) {
  const mais = modelos.length === 24 ? `<a class="mais" href="/?antes=${esc(cursorDe(modelos[modelos.length - 1]))}">Ver mais</a>` : '';
  const corpo = `<section class="intro"><h1>Modelos de montagem</h1>
<p>Montagens na batida feitas no CutMind. Escolha uma e use no seu editor: você troca só as fotos, os vídeos e a música.</p></section>
${modelos.length ? `<section class="grade">${modelos.map((m) => cartao(m)).join('\n')}</section>${mais}`
    : `<p class="vazio">${antes ? 'Não tem mais modelos.' : 'Nenhum modelo publicado ainda.'}</p>`}`;
  return pagina({ titulo: 'Modelos de montagem', corpo, scripts: ['/static/mural.js'] });
}

function paginaModelo(m) {
  const motivos = Object.entries(MOTIVOS).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
  const corpo = `<div class="pagina-modelo">${cartao(m, { grande: true })}
<div class="lado">
<section class="usar">
  <h2>Usar no CutMind</h2>
  <ol>
    <li>No editor do CutMind, abra <b>Montagem</b> e vá em <b>Da comunidade</b>.</li>
    <li>Procure <b>${esc(m.nome)}</b> e toque em <b>Usar</b>.</li>
    <li>Escolha a música e as suas fotos e vídeos.</li>
  </ol>
  <p class="codigo">Código do modelo: <code>${esc(m.id)}</code> · <a href="/api/modelos/${esc(m.id)}?baixar=1">baixar o arquivo</a></p>
</section>
<details class="denunciar">
  <summary>Denunciar este modelo</summary>
  <form data-denunciar="${esc(m.id)}">
    <select name="motivo" required>${motivos}</select>
    <button type="submit">Enviar denúncia</button>
    <p class="aviso" role="status"></p>
  </form>
</details>
</div></div>`;
  return pagina({ titulo: m.nome, corpo, scripts: ['/static/mural.js'] });
}

function paginaPublicar(env) {
  const corpo = `<section class="publicar">
<h1>Publicar no mural</h1>
<div id="previa" class="cartao grande"><p class="vazio">Carregando o modelo…</p></div>
<form id="formPublicar" hidden>
  <label><span>Nome do modelo</span><input name="nome" required maxlength="${NOME_MAX}" autocomplete="off"></label>
  <label><span>Seu @ <span class="opc">(opcional)</span></span><input name="autor" maxlength="31" placeholder="@seuperfil" autocomplete="off"></label>
  <label><span>Link do post em que você usou a montagem <span class="opc">(opcional: Instagram, TikTok ou YouTube)</span></span>
    <input name="post" type="url" maxlength="500" placeholder="https://www.instagram.com/reel/..."></label>
  <p class="nota">O modelo leva só o ritmo, os textos, as transições e o formato. Nenhuma foto, vídeo ou música sua sai do seu computador.</p>
  <div class="cf-turnstile" data-sitekey="${esc(env.TURNSTILE_SITEKEY)}"></div>
  <button type="submit">Publicar</button>
  <p class="aviso" role="status"></p>
</form>
<div id="pronto" hidden><p>Publicado! O link do seu modelo:</p><p><a id="linkPronto" href="/"></a></p>
  <button type="button" id="copiar">Copiar o link</button></div>
</section>`;
  return pagina({ titulo: 'Publicar', corpo, semIndice: true,
    scripts: ['/static/publicar.js', 'https://challenges.cloudflare.com/turnstile/v0/api.js'] });
}

const naoAchei = () => pagina({ titulo: 'Não encontrado', status: 404,
  corpo: '<section class="intro"><h1>Não achei esse modelo</h1><p><a href="/">Voltar ao mural</a></p></section>' });

async function rotear(request, env) {
  const url = new URL(request.url);
  const p = url.pathname;
  const metodo = request.method === 'HEAD' ? 'GET' : request.method; // o HEAD sai sem o corpo
  if (p === '/' && metodo === 'GET') {
    return paginaGrade(await listar(env, lerCursor(url.searchParams.get('antes')), 24), url.searchParams.has('antes'));
  }
  let r;
  if ((r = p.match(/^\/m\/([A-Za-z0-9_-]{12})$/)) && metodo === 'GET') {
    const m = await um(env, r[1]);
    return m && m.status === 'publicado' ? paginaModelo(m) : naoAchei();
  }
  if (p === '/publicar' && metodo === 'GET') return paginaPublicar(env);
  if (p === '/api/modelos' && metodo === 'GET') {
    const n = Math.min(48, Math.max(1, Math.trunc(Number(url.searchParams.get('n'))) || 24));
    const modelos = await listar(env, lerCursor(url.searchParams.get('antes')), n);
    return json({ modelos: modelos.map(publico), seguinte: modelos.length === n ? cursorDe(modelos[n - 1]) : null });
  }
  if (p === '/api/modelos' && metodo === 'POST') return publicar(request, env);
  if ((r = p.match(/^\/api\/modelos\/([A-Za-z0-9_-]{12})$/)) && metodo === 'GET') {
    const m = await um(env, r[1]);
    if (!m || m.status !== 'publicado') return erro('modelo não encontrado', 404);
    const dados = { ...publico(m), modelo: { ...m.modelo, nome: m.nome } };
    const extra = url.searchParams.get('baixar') === '1'
      ? { 'Content-Disposition': `attachment; filename="modelo-${m.id}.json"` } : {};
    return json(dados, 200, extra);
  }
  if ((r = p.match(/^\/api\/modelos\/([A-Za-z0-9_-]{12})\/denunciar$/)) && metodo === 'POST') return denunciar(request, env, r[1]);
  if (p === '/admin' || p.startsWith('/admin/')) {
    const quem = await adminDe(request, env);
    if (!quem) return new Response('Acesso negado', { status: 403, headers: CABECALHOS });
    return painel(request, env, quem, { doBanco, linhaResumo, mesmaOrigem, lerJson });
  }
  return metodo === 'GET' ? naoAchei() : erro('não encontrado', 404);
}

export default {
  async fetch(request, env) {
    try {
      return await rotear(request, env);
    } catch (e) {
      if (e instanceof ModeloInvalido || e instanceof PostInvalido || e instanceof PedidoInvalido) return erro(e.message, 400);
      console.error(JSON.stringify({ evento: 'erro', mensagem: String(e && e.message), rota: new URL(request.url).pathname }));
      return erro('algo deu errado do nosso lado', 500);
    }
  },
};
