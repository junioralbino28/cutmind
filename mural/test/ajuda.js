// O que os testes do mural dividem: o pedido ao Worker, um modelo de exemplo e o Turnstile falso.
import { exports } from 'cloudflare:workers';
import { vi } from 'vitest';

export const ORIGEM = 'https://mural.example';
export const SITEVERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

let n = 0;
// um IP por teste: os limites contam por pessoa, e um teste não gasta o limite do outro
export const novoIp = () => `203.0.113.${++n}`;

export function pedido(caminho, { metodo = 'GET', corpo, ip = novoIp(), origem = ORIGEM, base = ORIGEM } = {}) {
  const headers = { 'CF-Connecting-IP': ip };
  if (origem) headers.Origin = origem;
  if (corpo !== undefined) headers['Content-Type'] = 'application/json';
  const body = corpo === undefined ? undefined : (typeof corpo === 'string' ? corpo : JSON.stringify(corpo));
  return exports.default.fetch(new Request(`${base}${caminho}`, { method: metodo, headers, body }));
}

export const modelo = () => ({
  versao: 1, comeca: 'forte', drop_na_vaga: 5, golpe: true, formato: '9:16',
  vagas: [{ batidas: 4, repetir: 4, movimento: 'zoom-in' }, { batidas: 1, repetir: 8 }],
  textos: [{ nome: 'Título', texto: 'Fim de semana', vaga: 1, batidas: 8, x: 540, y: 760 }],
  transicoes: [{ vaga: 5, pacote: 'flash-branco', duracao: 0.4 }],
  extra_que_nao_existe: 'não pode passar',
});

export const envio = (mais = {}) => ({
  modelo: modelo(), nome: 'Drop na praia', autor: '@exemplo.teste',
  post: 'https://www.instagram.com/reel/ABCdef12345/?igsh=xyz', turnstile: 'XXXX.DUMMY.TOKEN.XXXX', ...mais,
});

// troca a rede do Worker: o siteverify responde `estado.turnstile`; o resto da rede é erro
export function redeFalsa(outras = {}) {
  const estado = { turnstile: { success: true }, verificados: [] };
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    const u = url instanceof Request ? url.url : String(url);
    if (u === SITEVERIFY) {
      estado.verificados.push(JSON.parse(init.body));
      return Response.json(estado.turnstile);
    }
    if (Object.hasOwn(outras, u)) return outras[u]();
    throw new Error(`pedido de rede inesperado: ${u}`);
  });
  return estado;
}

export async function publicar(mais = {}, opcoes = {}) {
  const r = await pedido('/api/modelos', { metodo: 'POST', corpo: envio(mais), ...opcoes });
  return { r, d: await r.json() };
}
