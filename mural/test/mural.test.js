// Publicar, ver e denunciar, de ponta a ponta no Worker com o banco local.
import { createExecutionContext } from 'cloudflare:test';
import { env } from 'cloudflare:workers';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import worker, { apagarHashesVelhos, chaveDoIp } from '../src/index.js';
import { envio, novoIp, ORIGEM, pedido, publicar, redeFalsa } from './ajuda.js';

let rede;
beforeEach(() => { rede = redeFalsa(); });
afterEach(() => vi.restoreAllMocks());

const contar = async () => (await env.DB.prepare('SELECT COUNT(*) AS n FROM modelos').first()).n;

describe('publicar', () => {
  it('publica e guarda só o modelo conferido, o post canônico e o @ sem arroba', async () => {
    const ip = novoIp();
    const { r, d } = await publicar({}, { ip });
    expect(r.status).toBe(201);
    expect(d.id).toMatch(/^[A-Za-z0-9_-]{12}$/);
    expect(d.url).toBe(`${ORIGEM}/m/${d.id}`);

    const m = await (await pedido(`/api/modelos/${d.id}`)).json();
    expect(m.modelo).not.toHaveProperty('extra_que_nao_existe');
    expect(m.modelo.nome).toBe('Drop na praia');
    expect(m).toMatchObject({ autor: 'exemplo.teste', plataforma: 'instagram', post: 'https://www.instagram.com/reel/ABCdef12345/' });

    expect(rede.verificados).toEqual([{ secret: env.TURNSTILE_SECRET, response: 'XXXX.DUMMY.TOKEN.XXXX', remoteip: ip }]);
    const linha = await env.DB.prepare('SELECT ip_hash FROM modelos WHERE id = ?1').bind(d.id).first();
    expect(linha.ip_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(linha.ip_hash).not.toContain(ip);
  });

  it('recusa pedido que não sai da página do mural', async () => {
    const antes = await contar();
    expect((await publicar({}, { origem: null })).r.status).toBe(403);
    expect((await publicar({}, { origem: 'https://outro.example' })).r.status).toBe(403);
    expect(await contar()).toBe(antes);
  });

  it('recusa quando o Turnstile não confirma, e nem pergunta quando não veio token', async () => {
    rede.turnstile = { success: false, 'error-codes': ['invalid-input-response'] };
    const antes = await contar();
    const a = await publicar();
    expect(a.r.status).toBe(403);
    expect(a.d.erro).toMatch(/robô/);
    expect(rede.verificados).toHaveLength(1);

    const b = await publicar({ turnstile: '' });
    expect(b.r.status).toBe(403);
    expect(rede.verificados).toHaveLength(1);
    expect(await contar()).toBe(antes);
  });

  it.each([
    ['post de outro site', { post: 'https://evil.example/reel/x' }, /Instagram, TikTok ou YouTube/],
    ['link curto do TikTok', { post: 'https://vm.tiktok.com/ZMabc/' }, /link inteiro/],
    ['@ com espaço', { autor: 'fu lana' }, /o @/],
    ['nome vazio', { nome: '   ' }, /nome do modelo/],
    ['nome longo', { nome: 'x'.repeat(61) }, /nome do modelo/],
    ['modelo inválido', { modelo: { vagas: [{ batidas: 1 }], formato: '4:3' } }, /formato/],
  ])('recusa %s com 400', async (_n, mais, msg) => {
    const { r, d } = await publicar(mais);
    expect(r.status).toBe(400);
    expect(d.erro).toMatch(msg);
  });

  it('recusa corpo grande demais e corpo que não é JSON', async () => {
    const grande = await pedido('/api/modelos', { metodo: 'POST', corpo: JSON.stringify({ ...envio(), lixo: 'x'.repeat(70000) }) });
    expect(grande.status).toBe(400);
    expect((await grande.json()).erro).toMatch(/grande demais/);
    const torto = await pedido('/api/modelos', { metodo: 'POST', corpo: '{isto não' });
    expect(torto.status).toBe(400);
  });

  it('com o segredo de verdade, o token tem que ter sido resolvido neste site', async () => {
    // as ligações (banco, limites) vêm do env de teste; só o segredo muda
    const env2 = Object.create(env, { TURNSTILE_SECRET: { value: 'segredo-de-verdade-do-teste' } });
    const enviar = () => worker.fetch(new Request(`${ORIGEM}/api/modelos`, {
      method: 'POST', body: JSON.stringify(envio()),
      headers: { 'Content-Type': 'application/json', Origin: ORIGEM, 'CF-Connecting-IP': novoIp() },
    }), env2, createExecutionContext());
    rede.turnstile = { success: true, hostname: 'outro-site.example' };
    expect((await enviar()).status).toBe(403);
    rede.turnstile = { success: true, hostname: new URL(ORIGEM).hostname };
    expect((await enviar()).status).toBe(201);
  });

  it('para no teto de modelos por dia da mesma pessoa', async () => {
    const ip = novoIp();
    expect((await publicar({}, { ip })).r.status).toBe(201);
    expect((await publicar({}, { ip })).r.status).toBe(201);
    const terceiro = await publicar({}, { ip });
    expect(terceiro.r.status).toBe(429);
    expect(terceiro.d.erro).toMatch(/limite de 2 modelos por dia/);
    expect((await publicar({}, { ip: novoIp() })).r.status).toBe(201);
  });

  it('segura a rajada de envios antes de ler o pedido', async () => {
    const ip = novoIp();
    const status = [];
    for (let i = 0; i < 4; i++) status.push((await publicar({ nome: '' }, { ip })).r.status);
    expect(status).toEqual([400, 400, 400, 429]);
  });

  it('escapa tudo o que veio de quem publicou', async () => {
    const xss = '<img src=x onerror=alert(1)>';
    const { d } = await publicar({ nome: xss, modelo: { vagas: [{ batidas: 1 }], textos: [{ texto: xss, nome: '"><b>' }] } });
    const html = await (await pedido(`/m/${d.id}`)).text();
    expect(html).not.toContain('<img src=x');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
  });
});

describe('o IP', () => {
  it.each([
    ['203.0.113.7', '203.0.113.7'],
    ['::ffff:203.0.113.7', '203.0.113.7'],
    ['2001:db8:1:2::5', '2001:db8:1:2::/64'],
    ['2001:0db8:0001:0002:aaaa:bbbb:cccc:dddd', '2001:db8:1:2::/64'],
    ['2001:db8::1', '2001:db8:0:0::/64'],
    ['::1', '0:0:0:0::/64'],
  ])('%s conta como %s', (ip, chave) => {
    expect(chaveDoIp(ip)).toBe(chave);
  });

  it('o hash some depois de 2 dias, e a denúncia continua uma por linha', async () => {
    const { d } = await publicar();
    const ip = novoIp();
    await pedido(`/api/modelos/${d.id}/denunciar`, { metodo: 'POST', corpo: { motivo: 'spam', turnstile: 'x' }, ip });
    const daqui3dias = Math.floor(Date.now() / 1000) + 3 * 86400;
    await apagarHashesVelhos(env, daqui3dias);
    expect((await env.DB.prepare('SELECT ip_hash FROM modelos WHERE id = ?1').bind(d.id).first()).ip_hash).toBe('');
    const dn = await env.DB.prepare('SELECT id, ip_hash FROM denuncias WHERE modelo_id = ?1').bind(d.id).all();
    expect(dn.results.map((x) => x.ip_hash)).toEqual(dn.results.map((x) => `apagado-${x.id}`));
    await apagarHashesVelhos(env, daqui3dias); // de novo: nada muda
    // o recente fica
    const novo = await publicar();
    await apagarHashesVelhos(env);
    expect((await env.DB.prepare('SELECT ip_hash FROM modelos WHERE id = ?1').bind(novo.d.id).first()).ip_hash).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe('ver', () => {
  it('a página do modelo sai com a política de segurança e o post embutido', async () => {
    const { d } = await publicar();
    const r = await pedido(`/m/${d.id}`);
    expect(r.status).toBe(200);
    expect(r.headers.get('Content-Security-Policy')).toContain("frame-ancestors 'none'");
    expect(r.headers.get('X-Content-Type-Options')).toBe('nosniff');
    const html = await r.text();
    // o player só entra no toque: até lá, nenhum iframe de terceiro na página
    expect(html).toContain('data-embed="https://www.instagram.com/reel/ABCdef12345/embed/"');
    expect(html).not.toContain('<iframe');
    expect(html).toContain('href="https://www.instagram.com/exemplo.teste/"');
    expect(html).toContain('informados por quem publicou');
    expect(html).not.toMatch(/<script>|style="/);
  });

  it('o HEAD responde como o GET, sem corpo', async () => {
    const { d } = await publicar();
    const r = await pedido(`/m/${d.id}`, { metodo: 'HEAD' });
    expect(r.status).toBe(200);
    expect(r.headers.get('Content-Security-Policy')).toBeTruthy();
    expect(await r.text()).toBe('');
  });

  it('o arquivo do modelo baixa com nome e sem o IP', async () => {
    const { d } = await publicar();
    const r = await pedido(`/api/modelos/${d.id}?baixar=1`);
    expect(r.headers.get('Content-Disposition')).toBe(`attachment; filename="modelo-${d.id}.json"`);
    const corpo = await r.text();
    expect(corpo).not.toMatch(/ip_hash|denuncias|status/);
  });

  it('modelo que não existe é 404, na página e na API', async () => {
    expect((await pedido('/m/AAAAAAAAAAAA')).status).toBe(404);
    expect((await pedido('/api/modelos/AAAAAAAAAAAA')).status).toBe(404);
    expect((await pedido('/m/curto')).status).toBe(404);
  });
});

describe('denunciar', () => {
  const denunciar = (id, motivo, { corpo, ...opcoes } = {}) => pedido(`/api/modelos/${id}/denunciar`,
    { metodo: 'POST', corpo: { motivo, turnstile: 'XXXX.DUMMY.TOKEN.XXXX', ...corpo }, ...opcoes });
  const denuncias = async (id) => (await env.DB.prepare('SELECT denuncias FROM modelos WHERE id = ?1').bind(id).first()).denuncias;

  it('conta uma denúncia por pessoa em cada modelo', async () => {
    const { d } = await publicar();
    const ip = novoIp();
    expect((await denunciar(d.id, 'spam', { ip })).status).toBe(200);
    expect((await denunciar(d.id, 'ofensivo', { ip })).status).toBe(200);
    expect(await denuncias(d.id)).toBe(1);
    await denunciar(d.id, 'direitos', { ip: novoIp() });
    expect(await denuncias(d.id)).toBe(2);
  });

  it('o mesmo bloco IPv6 conta como uma pessoa só', async () => {
    const { d } = await publicar();
    for (let i = 1; i <= 5; i++) await denunciar(d.id, 'spam', { ip: `2001:db8:1:2::${i}` });
    await denunciar(d.id, 'spam', { ip: '2001:db8:1:2:ffff:ffff:ffff:ffff' });
    expect(await denuncias(d.id)).toBe(1);
    await denunciar(d.id, 'spam', { ip: '2001:db8:1:3::1' });
    expect(await denuncias(d.id)).toBe(2);
  });

  it('pede o anti-robô, e nem pergunta a ele quando o motivo já não vale', async () => {
    const { d } = await publicar();
    const antes = rede.verificados.length;
    expect((await denunciar(d.id, 'spam', { corpo: { turnstile: '' } })).status).toBe(403);
    rede.turnstile = { success: false };
    expect((await denunciar(d.id, 'spam')).status).toBe(403);
    expect((await denunciar(d.id, ['spam'])).status).toBe(400); // lista não é motivo (antes dava 500)
    expect(rede.verificados.length).toBe(antes + 1);
    expect(await denuncias(d.id)).toBe(0);
    rede.turnstile = { success: true };
    expect((await denunciar(d.id, 'perfil')).status).toBe(200);
  });

  it('recusa motivo desconhecido, outra origem e modelo tirado', async () => {
    const { d } = await publicar();
    expect((await denunciar(d.id, 'qualquer')).status).toBe(400);
    expect((await denunciar(d.id, 'spam', { origem: null })).status).toBe(403);
    await env.DB.prepare("UPDATE modelos SET status = 'removido' WHERE id = ?1").bind(d.id).run();
    expect((await denunciar(d.id, 'spam')).status).toBe(404);
    expect((await pedido(`/m/${d.id}`)).status).toBe(404);
  });
});
