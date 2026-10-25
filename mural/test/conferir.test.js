// A conferência do modelo e do link do post: o que o mural aceita guardar e mostrar.
import { describe, expect, it } from 'vitest';
import { conferirModelo, ModeloInvalido, resumoDoModelo } from '../src/modelo.js';
import { embedDo, lerAutor, lerPost, perfil, PostInvalido } from '../src/post.js';

const base = () => ({
  versao: 1, comeca: 'forte', drop_na_vaga: 3, golpe: true, formato: '9:16',
  vagas: [{ batidas: 4, repetir: 2, movimento: 'zoom-in' }, { batidas: 1, repetir: 4 }],
  textos: [{ nome: 'Título', texto: 'Oi\nmundo', vaga: 1, batidas: 4, x: 540, y: 700, estilo: { fonte: 'Montserrat', peso: 800, cor: '#ffffff' } }],
  transicoes: [{ vaga: 3, pacote: 'flash-branco', duracao: 0.4 }],
});

describe('conferirModelo', () => {
  it('monta o modelo campo a campo: o que não existe no kit não passa', () => {
    const m = { ...base(), extra: 'x', __proto__: { veneno: 1 } };
    m.vagas[0].lixo = 1;
    m.textos[0].estilo.script = '<x>';
    const out = conferirModelo(m);
    expect(Object.keys(out).sort()).toEqual(['comeca', 'drop_na_vaga', 'formato', 'golpe', 'textos', 'transicoes', 'vagas', 'versao']);
    expect(out.vagas[0]).toEqual({ batidas: 4, repetir: 2, movimento: 'zoom-in' });
    expect(out.textos[0].estilo).toEqual({ fonte: 'Montserrat', peso: 800, cor: '#ffffff' });
  });

  it('completa o que falta com o padrão do kit', () => {
    const out = conferirModelo({ vagas: [{ batidas: 2 }] });
    expect(out).toMatchObject({ versao: 1, comeca: 'forte', golpe: true, formato: '9:16', drop_na_vaga: null, textos: [], transicoes: [] });
  });

  it('o texto sem posição nasce no centro do formato dele', () => {
    const out = conferirModelo({ formato: '16:9', vagas: [{ batidas: 1 }], textos: [{ texto: 'a' }] });
    expect(out.textos[0]).toMatchObject({ x: 960, y: 540, vaga: 1, nome: 'Texto 1' });
  });

  it.each([
    ['formato desconhecido', { formato: '4:3' }],
    ['sem lugares', { vagas: [] }],
    ['batidas fora da faixa', { vagas: [{ batidas: 65 }] }],
    ['batidas quebradas', { vagas: [{ batidas: 1.5 }] }],
    ['lugares demais', { vagas: [{ batidas: 1, repetir: 401 }] }],
    ['movimento desconhecido', { vagas: [{ batidas: 1, movimento: 'girar' }] }],
    ['drop depois do último lugar', { drop_na_vaga: 99 }],
    ['transição no primeiro lugar', { transicoes: [{ vaga: 1, pacote: 'x' }] }],
    ['duas transições na mesma troca', { transicoes: [{ vaga: 3, pacote: 'a' }, { vaga: 3, pacote: 'b' }] }],
    ['pacote com caminho', { transicoes: [{ vaga: 3, pacote: '../x' }] }],
    ['texto com caractere de controle', { textos: [{ texto: 'a\u0007b' }] }],
    ['texto vazio', { textos: [{ texto: '   ' }] }],
    ['cor que não é #rrggbb', { textos: [{ texto: 'a', estilo: { cor: 'red' } }] }],
    ['fonte com símbolo', { textos: [{ texto: 'a', estilo: { fonte: 'x;}' } }] }],
    ['versão desconhecida', { versao: 2 }],
    ['não é objeto', null],
  ])('recusa: %s', (_nome, mudanca) => {
    const m = mudanca === null ? null : { ...base(), ...mudanca };
    expect(() => conferirModelo(m)).toThrow(ModeloInvalido);
  });

  it('recusa o modelo que passa de 20 KB', () => {
    const textos = Array.from({ length: 20 }, (_, i) => ({ texto: 'x'.repeat(400), nome: `t${i}`.padEnd(40, 'y') }));
    const vagas = Array.from({ length: 400 }, () => ({ batidas: 64, movimento: 'zoom-out' }));
    expect(() => conferirModelo({ vagas, textos })).toThrow(/20 KB/);
  });

  it('o resumo abre os lugares repetidos', () => {
    const r = resumoDoModelo(conferirModelo(base()));
    expect(r).toMatchObject({ lugares: 6, batidas: 12, ritmo: [4, 4, 1, 1, 1, 1], drop_na_vaga: 3, transicoes: 1 });
  });
});

describe('lerPost', () => {
  it.each([
    ['https://www.instagram.com/reel/ABCdef12345/?igsh=xyz', 'https://www.instagram.com/reel/ABCdef12345/', 'https://www.instagram.com/reel/ABCdef12345/embed/'],
    ['https://instagram.com/reels/ABCdef12345', 'https://www.instagram.com/reel/ABCdef12345/', 'https://www.instagram.com/reel/ABCdef12345/embed/'],
    ['https://www.instagram.com/alguem/p/ABCdef12345/', 'https://www.instagram.com/p/ABCdef12345/', 'https://www.instagram.com/p/ABCdef12345/embed/'],
    ['https://www.tiktok.com/@conta.x/video/7300000000000000000?lang=pt', 'https://www.tiktok.com/@conta.x/video/7300000000000000000', 'https://www.tiktok.com/embed/v2/7300000000000000000'],
    ['https://youtube.com/shorts/abcdefghijk?si=1', 'https://www.youtube.com/shorts/abcdefghijk', 'https://www.youtube-nocookie.com/embed/abcdefghijk'],
    ['https://youtu.be/abcdefghijk', 'https://www.youtube.com/shorts/abcdefghijk', 'https://www.youtube-nocookie.com/embed/abcdefghijk'],
    ['https://m.youtube.com/watch?v=abcdefghijk', 'https://www.youtube.com/shorts/abcdefghijk', 'https://www.youtube-nocookie.com/embed/abcdefghijk'],
  ])('%s', (texto, url, embed) => {
    expect(lerPost(texto)).toMatchObject({ url, embed });
  });

  it.each([
    'https://instagram.evil.example/reel/ABCdef12345/',
    'https://evil.example/www.instagram.com/reel/ABCdef12345/',
    'javascript:alert(1)//instagram.com/reel/ABCdef12345',
    'https://www.instagram.com/alguem/',
    'https://vm.tiktok.com/ZMabc123/',
    'https://www.tiktok.com/video/7300000000000000000',
    'https://www.youtube.com/watch?v=curto',
    'não é um link',
  ])('recusa %s', (texto) => {
    expect(() => lerPost(texto)).toThrow(PostInvalido);
  });

  it('sem post é nada, não erro', () => {
    expect(lerPost('')).toBeNull();
    expect(lerPost(null)).toBeNull();
    expect(embedDo(null)).toBeNull();
  });
});

describe('lerAutor e perfil', () => {
  it('tira o @ e confere os caracteres', () => {
    expect(lerAutor(' @fulana.cria_ ')).toBe('fulana.cria_');
    expect(() => lerAutor('fu lana')).toThrow(PostInvalido);
    expect(() => lerAutor('a'.repeat(31))).toThrow(PostInvalido);
    expect(lerAutor('')).toBeNull();
  });

  it('o perfil vai para a plataforma do post', () => {
    expect(perfil('x', 'tiktok')).toBe('https://www.tiktok.com/@x');
    expect(perfil('x', 'youtube')).toBe('https://www.youtube.com/@x');
    expect(perfil('x', null)).toBe('https://www.instagram.com/x/');
    expect(perfil(null, 'instagram')).toBeNull();
  });
});
