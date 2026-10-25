// O painel do dono: o atalho do teste local e o caminho de verdade, pelo token do Cloudflare Access.
import { env } from 'cloudflare:workers';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminDe } from '../src/admin.js';
import { pedido, publicar, redeFalsa } from './ajuda.js';

const LOCAL = 'http://localhost';
afterEach(() => vi.restoreAllMocks());

describe('painel no teste local', () => {
  beforeEach(() => { redeFalsa(); });
  const acao = (corpo, origem = LOCAL) => pedido('/admin/acao', { metodo: 'POST', corpo, base: LOCAL, origem });

  it('abre só em localhost; em outro endereço nega', async () => {
    expect((await pedido('/admin', { base: LOCAL })).status).toBe(200);
    expect((await pedido('/admin')).status).toBe(403);
    expect((await pedido('/admin/acao', { metodo: 'POST', corpo: {} })).status).toBe(403);
  });

  it('tira e devolve um modelo', async () => {
    const { d } = await publicar();
    expect((await acao({ id: d.id, acao: 'tirar' })).status).toBe(200);
    expect((await pedido(`/m/${d.id}`)).status).toBe(404);
    const painel = await (await pedido('/admin', { base: LOCAL })).text();
    expect(painel).toContain(`data-id="${d.id}"`);
    expect((await acao({ id: d.id, acao: 'devolver' })).status).toBe(200);
    expect((await pedido(`/m/${d.id}`)).status).toBe(200);
  });

  it('edita o nome e o @, com a mesma conferência de quem publica', async () => {
    const { d } = await publicar();
    expect((await acao({ id: d.id, acao: 'editar', nome: '', autor: '' })).status).toBe(400);
    expect((await acao({ id: d.id, acao: 'editar', nome: 'Novo', autor: 'com espaço' })).status).toBe(400);
    expect((await acao({ id: d.id, acao: 'editar', nome: 'Novo nome', autor: '@outra' })).status).toBe(200);
    const l = await env.DB.prepare('SELECT nome, autor FROM modelos WHERE id = ?1').bind(d.id).first();
    expect(l).toEqual({ nome: 'Novo nome', autor: 'outra' });
  });

  it('recusa ação vinda de outra origem, ação desconhecida e modelo que não existe', async () => {
    const { d } = await publicar();
    expect((await acao({ id: d.id, acao: 'tirar' }, 'https://outro.example')).status).toBe(403);
    expect((await acao({ id: d.id, acao: 'apagar-tudo' })).status).toBe(400);
    expect((await acao({ id: 'AAAAAAAAAAAA', acao: 'tirar' })).status).toBe(404);
  });
});

describe('Cloudflare Access', () => {
  const EQUIPE = 'https://equipe-teste.cloudflareaccess.com';
  const AUD = 'aud-do-teste';
  const config = (mais = {}) => ({ TEAM_DOMAIN: EQUIPE, POLICY_AUD: AUD, ADMIN_EMAILS: 'dono@example.com, outro@example.com', ...mais });
  let chave;
  let assinar;

  beforeEach(async () => {
    const { publicKey, privateKey } = await generateKeyPair('RS256');
    const jwk = { ...(await exportJWK(publicKey)), kid: 'k1', alg: 'RS256', use: 'sig' };
    chave = jwk;
    assinar = (claims, { aud = AUD, iss = EQUIPE, exp = '5m' } = {}) => new SignJWT(claims)
      .setProtectedHeader({ alg: 'RS256', kid: 'k1' }).setIssuer(iss).setAudience(aud).setIssuedAt().setExpirationTime(exp)
      .sign(privateKey);
    redeFalsa({ [`${EQUIPE}/cdn-cgi/access/certs`]: () => Response.json({ keys: [chave] }) });
  });

  const req = (token, host = 'mural.example') => new Request(`https://${host}/admin`, token ? { headers: { 'cf-access-jwt-assertion': token } } : {});

  it('aceita o token certo de um e-mail da lista', async () => {
    expect(await adminDe(req(await assinar({ email: 'DONO@example.com' })), config())).toEqual({ email: 'dono@example.com' });
  });

  it.each([
    ['sem token', async () => null, {}],
    ['outro público', async () => assinar({ email: 'dono@example.com' }, { aud: 'outro' }), {}],
    ['outro emissor', async () => assinar({ email: 'dono@example.com' }, { iss: 'https://falso.cloudflareaccess.com' }), {}],
    ['vencido', async () => assinar({ email: 'dono@example.com' }, { exp: Math.floor(Date.now() / 1000) - 60 }), {}],
    ['e-mail fora da lista', async () => assinar({ email: 'intruso@example.com' }), {}],
    ['lista vazia', async () => assinar({ email: 'dono@example.com' }), { ADMIN_EMAILS: '' }],
  ])('nega: %s', async (_n, token, mais) => {
    expect(await adminDe(req(await token()), config(mais))).toBeNull();
  });

  it('nega token assinado por outra chave', async () => {
    const { privateKey } = await generateKeyPair('RS256');
    const falso = await new SignJWT({ email: 'dono@example.com' }).setProtectedHeader({ alg: 'RS256', kid: 'k1' })
      .setIssuer(EQUIPE).setAudience(AUD).setExpirationTime('5m').sign(privateKey);
    expect(await adminDe(req(falso), config())).toBeNull();
  });

  it('com o Access configurado, o atalho local não abre nada', async () => {
    expect(await adminDe(req(null, 'localhost'), config({ ADMIN_LOCAL: '1' }))).toBeNull();
  });

  it('sem o Access e fora de localhost, nega tudo', async () => {
    expect(await adminDe(req(null), { ADMIN_LOCAL: '1' })).toBeNull();
    expect(await adminDe(req(null, 'localhost'), {})).toBeNull();
  });
});
