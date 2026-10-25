// A grade e a lista: só os publicados, do mais novo para o mais velho, e a página seguinte começa
// exatamente depois da anterior, mesmo com modelos publicados no mesmo segundo.
import { env } from 'cloudflare:workers';
import { beforeAll, describe, expect, it } from 'vitest';
import { pedido } from './ajuda.js';

const MODELO = JSON.stringify({ versao: 1, comeca: 'forte', drop_na_vaga: null, golpe: true, formato: '1:1', vagas: [{ batidas: 2 }], textos: [], transicoes: [] });
const linha = (id, criado, status = 'publicado') => env.DB.prepare(
  'INSERT INTO modelos (id, nome, modelo, criado, status, ip_hash) VALUES (?1, ?2, ?3, ?4, ?5, ?6)',
).bind(id, `Modelo ${id}`, MODELO, criado, status, 'x'.repeat(64));

beforeAll(async () => {
  await env.DB.batch([
    linha('aaaaaaaaaaa1', 1000), linha('aaaaaaaaaaa2', 1000), linha('aaaaaaaaaaa3', 1000),
    linha('bbbbbbbbbbb1', 2000), linha('ccccccccccc1', 3000, 'removido'), linha('ddddddddddd1', 500),
  ]);
});

describe('lista', () => {
  it('pagina sem pular nem repetir, e deixa o tirado de fora', async () => {
    const vistos = [];
    let antes = '';
    for (let volta = 0; volta < 5; volta++) {
      const d = await (await pedido(`/api/modelos?n=2${antes ? `&antes=${antes}` : ''}`)).json();
      vistos.push(...d.modelos.map((m) => m.id));
      if (!d.seguinte) break;
      antes = d.seguinte;
    }
    expect(vistos).toEqual(['bbbbbbbbbbb1', 'aaaaaaaaaaa1', 'aaaaaaaaaaa2', 'aaaaaaaaaaa3', 'ddddddddddd1']);
  });

  it('cursor torto vira a primeira página, não erro', async () => {
    const r = await pedido('/api/modelos?antes=1000.%27%20OR%201=1&n=999');
    expect(r.status).toBe(200);
    expect((await r.json()).modelos).toHaveLength(5);
  });

  it('a grade mostra os cartões e não mostra o tirado', async () => {
    const html = await (await pedido('/')).text();
    expect(html).toContain('/m/bbbbbbbbbbb1');
    expect(html).not.toContain('ccccccccccc1');
    expect(html).toContain('1 lugar · 2 batidas · 1:1');
  });
});
