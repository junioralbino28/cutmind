// O painel do dono do mural: os modelos denunciados primeiro; tirar, devolver, editar o nome e o @.
// Fica atrás do Cloudflare Access, e o Worker confere o token do Access de novo antes de qualquer
// coisa (a autorização não depende só da borda). No teste local (`wrangler dev`, sem o Access
// configurado), ADMIN_LOCAL=1 no .dev.vars abre o painel para pedidos a 127.0.0.1 ou localhost.

import { createRemoteJWKSet, jwtVerify } from 'jose';
import { esc, pagina } from './html.js';
import { lerAutor } from './post.js';

export async function adminDe(request, env) {
  const host = new URL(request.url).hostname;
  if (env.ADMIN_LOCAL === '1' && !env.TEAM_DOMAIN && (host === '127.0.0.1' || host === 'localhost')) {
    return { email: 'teste local' };
  }
  if (!env.TEAM_DOMAIN || !env.POLICY_AUD) return null;
  const permitidos = String(env.ADMIN_EMAILS || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
  const token = request.headers.get('cf-access-jwt-assertion');
  if (!token || !permitidos.length) return null;
  try {
    const jwks = createRemoteJWKSet(new URL(`${env.TEAM_DOMAIN}/cdn-cgi/access/certs`));
    const { payload } = await jwtVerify(token, jwks, { issuer: env.TEAM_DOMAIN, audience: env.POLICY_AUD });
    const email = String(payload.email || '').toLowerCase();
    return permitidos.includes(email) ? { email } : null;
  } catch {
    return null;
  }
}

// em UTC no HTML; o admin.js da página troca pelo fuso de quem abre
const quando = (s) => {
  const iso = new Date(s * 1000).toISOString();
  return `<time datetime="${iso}">${iso.slice(0, 16).replace('T', ' ')} UTC</time>`;
};

function linha(m, linhaResumo) {
  return `<tr data-id="${esc(m.id)}" data-nome="${esc(m.nome)}" data-autor="${esc(m.autor || '')}" class="${m.status === 'removido' ? 'removido' : ''}">
  <td><a href="/m/${esc(m.id)}" target="_blank" rel="noopener">${esc(m.nome)}</a><br><small>${esc(linhaResumo(m.resumo))}</small></td>
  <td>${m.autor ? `@${esc(m.autor)}` : '—'}${m.post ? `<br><a href="${esc(m.post)}" target="_blank" rel="noopener nofollow ugc">post</a>` : ''}</td>
  <td class="num${m.denuncias > 0 ? ' alerta' : ''}">${m.denuncias}</td>
  <td>${esc(m.status)}<br><small>${quando(m.criado)}</small></td>
  <td class="acoes">
    ${m.status === 'publicado' ? '<button data-acao="tirar">Tirar</button>' : '<button data-acao="devolver">Devolver</button>'}
    <button data-acao="editar">Editar</button>
  </td>
</tr>`;
}

export async function painel(request, env, quem, { doBanco, linhaResumo, mesmaOrigem, lerJson, nomeDoModelo }) {
  const p = new URL(request.url).pathname;
  if (p === '/admin' && request.method === 'GET') {
    const { results } = await env.DB.prepare(
      'SELECT * FROM modelos ORDER BY (status = \'publicado\' AND denuncias > 0) DESC, denuncias DESC, criado DESC LIMIT 200',
    ).all();
    const modelos = results.map(doBanco);
    const { results: motivos } = await env.DB.prepare(
      'SELECT modelo_id, motivo, COUNT(*) AS n FROM denuncias GROUP BY modelo_id, motivo',
    ).all();
    const porModelo = {};
    for (const x of motivos) (porModelo[x.modelo_id] ||= []).push(`${x.motivo} (${x.n})`);
    const corpo = `<section class="admin"><h1>Painel do mural</h1><p class="nota">Entrou como ${esc(quem.email)}.</p>
<table><thead><tr><th>Modelo</th><th>Quem</th><th>Denúncias</th><th>Situação</th><th></th></tr></thead>
<tbody>${modelos.map((m) => linha(m, linhaResumo).replace('<td class="num', `<td title="${esc((porModelo[m.id] || []).join(', '))}" class="num`)).join('')}</tbody></table>
<p class="aviso" role="status"></p></section>`;
    return pagina({ titulo: 'Painel', corpo, scripts: ['/static/admin.js'], semIndice: true });
  }
  if (p === '/admin/acao' && request.method === 'POST') {
    if (!mesmaOrigem(request)) return new Response('Origem recusada', { status: 403 });
    const c = await lerJson(request, 4096);
    const l = c && typeof c.id === 'string' ? await env.DB.prepare('SELECT * FROM modelos WHERE id = ?1').bind(c.id).first() : null;
    if (!l) return Response.json({ erro: 'modelo não encontrado' }, { status: 404 });
    if (c.acao === 'tirar' || c.acao === 'devolver') {
      const status = c.acao === 'tirar' ? 'removido' : 'publicado';
      await env.DB.prepare('UPDATE modelos SET status = ?1 WHERE id = ?2').bind(status, l.id).run();
      console.log(JSON.stringify({ evento: `admin-${c.acao}`, id: l.id, quem: quem.email }));
      return Response.json({ ok: true, status });
    }
    if (c.acao === 'editar') {
      const nome = nomeDoModelo(c.nome); // a mesma conferência de quem publica (erro vira 400)
      let autor;
      try {
        autor = lerAutor(c.autor);
      } catch (e) {
        return Response.json({ erro: e.message }, { status: 400 });
      }
      await env.DB.prepare('UPDATE modelos SET nome = ?1, autor = ?2 WHERE id = ?3').bind(nome, autor, l.id).run();
      console.log(JSON.stringify({ evento: 'admin-editar', id: l.id, quem: quem.email }));
      return Response.json({ ok: true });
    }
    return Response.json({ erro: 'ação desconhecida' }, { status: 400 });
  }
  return new Response('Não encontrado', { status: 404 });
}
