// O modelo de montagem conferido como o kit confere (helpers/montagem.py `carregar_modelo` e
// helpers/montagens.py `normalize`): só os campos conhecidos, nos mesmos limites. O kit confere de
// novo quando a pessoa usa o modelo; aqui é para o mural nunca guardar nem mostrar o que o kit
// recusaria. O objeto devolvido é montado campo a campo: nada do que chegou passa sem ser lido.

export class ModeloInvalido extends Error {}

const MOVIMENTOS = ['zoom-in', 'zoom-out', 'parado'];
const FORMATOS = { '9:16': [1080, 1920], '16:9': [1920, 1080], '1:1': [1080, 1080] };
const MAX_VAGAS = 400;
const MAX_TEXTOS = 20;
const MAX_BYTES = 20000;
const MAX_TEXTO = 400;
const MAX_NOME_TEXTO = 40;
const TRANSICAO = [0.1, 5.0];
const PACOTE = /^[a-z0-9][a-z0-9-]{0,60}$/;
const COR = /^#[0-9a-fA-F]{6}$/;
const FONTE = /^[A-Za-z0-9 ]{1,60}$/;

const ehObjeto = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

function inteiro(v, nome, lo, hi) {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < lo || v > hi) {
    throw new ModeloInvalido(`${nome}: um número inteiro de ${lo} a ${hi}`);
  }
  return v;
}

function numero(v, nome, lo, hi) {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi) {
    throw new ModeloInvalido(`${nome}: um número de ${lo} a ${hi}`);
  }
  return v;
}

// caractere de controle: só a quebra de linha passa, e só onde `quebra` deixa
function semControle(s, quebra) {
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if ((c < 32 && !(quebra && c === 10)) || c === 127) return false;
  }
  return true;
}

function estilo(e) {
  if (e === undefined || e === null) return {};
  if (!ehObjeto(e)) throw new ModeloInvalido('estilo: um objeto');
  const out = {};
  if (e.fonte != null) {
    if (typeof e.fonte !== 'string' || !FONTE.test(e.fonte)) throw new ModeloInvalido('fonte: só letras, números e espaço');
    out.fonte = e.fonte;
  }
  if (e.peso != null) out.peso = Math.trunc(numero(e.peso, 'peso', 100, 900));
  for (const k of ['cor', 'corContorno']) {
    if (e[k] != null) {
      if (typeof e[k] !== 'string' || !COR.test(e[k])) throw new ModeloInvalido(`${k}: uma cor #rrggbb`);
      out[k] = e[k];
    }
  }
  if (e.tamanho != null) out.tamanho = numero(e.tamanho, 'tamanho', 0.2, 5.0);
  if (e.contorno != null) out.contorno = numero(e.contorno, 'contorno', 0, 60);
  return out;
}

export function conferirModelo(m) {
  if (!ehObjeto(m)) throw new ModeloInvalido('o modelo precisa ser um objeto');
  if ((m.versao ?? 1) !== 1) throw new ModeloInvalido('versão de modelo desconhecida');
  const comeca = m.comeca ?? 'forte';
  if (comeca !== 'forte' && comeca !== 'batida') throw new ModeloInvalido('"comeca" é "forte" ou "batida"');
  const formato = m.formato ?? '9:16';
  if (typeof formato !== 'string' || !Object.hasOwn(FORMATOS, formato)) throw new ModeloInvalido('formato desconhecido');
  const golpe = m.golpe ?? true;
  if (typeof golpe !== 'boolean') throw new ModeloInvalido('"golpe" é true ou false');

  if (!Array.isArray(m.vagas) || !m.vagas.length) throw new ModeloInvalido('o modelo precisa de lugares');
  const vagas = [];
  let total = 0;
  for (const [i, v] of m.vagas.entries()) {
    if (!ehObjeto(v)) throw new ModeloInvalido(`lugar ${i + 1}: um objeto`);
    const batidas = inteiro(v.batidas, `lugar ${i + 1}, batidas`, 1, 64);
    const repetir = inteiro(v.repetir ?? 1, `lugar ${i + 1}, repetir`, 1, MAX_VAGAS);
    if (v.movimento != null && !MOVIMENTOS.includes(v.movimento)) throw new ModeloInvalido(`lugar ${i + 1}: movimento desconhecido`);
    total += repetir;
    if (total > MAX_VAGAS) throw new ModeloInvalido(`mais de ${MAX_VAGAS} lugares`);
    vagas.push({ batidas, ...(repetir > 1 ? { repetir } : {}), ...(v.movimento ? { movimento: v.movimento } : {}) });
  }
  const drop = m.drop_na_vaga == null ? null : inteiro(m.drop_na_vaga, 'drop_na_vaga', 1, total);

  const textosIn = m.textos ?? [];
  if (!Array.isArray(textosIn) || textosIn.length > MAX_TEXTOS) throw new ModeloInvalido(`textos: até ${MAX_TEXTOS}`);
  const [fw, fh] = FORMATOS[formato];
  const textos = textosIn.map((t, i) => {
    const k = i + 1;
    if (!ehObjeto(t)) throw new ModeloInvalido(`texto ${k}: um objeto`);
    if (typeof t.texto !== 'string') throw new ModeloInvalido(`texto ${k}: o texto`);
    const tx = t.texto.replace(/\r\n?/g, '\n');
    if (!tx.trim() || [...tx].length > MAX_TEXTO || !semControle(tx, true)) {
      throw new ModeloInvalido(`texto ${k}: de 1 a ${MAX_TEXTO} letras`);
    }
    const nome = t.nome == null ? `Texto ${k}` : t.nome;
    if (typeof nome !== 'string' || !nome.trim() || [...nome].length > MAX_NOME_TEXTO || !semControle(nome, false)) {
      throw new ModeloInvalido(`texto ${k}: o nome tem de 1 a ${MAX_NOME_TEXTO} letras`);
    }
    return {
      nome: nome.trim(),
      texto: tx,
      vaga: inteiro(t.vaga ?? 1, `texto ${k}, vaga`, 1, total),
      batidas: t.batidas == null ? null : inteiro(t.batidas, `texto ${k}, batidas`, 1, 64 * MAX_VAGAS),
      x: numero(t.x ?? fw / 2, `texto ${k}, x`, -1080, 2160),
      y: numero(t.y ?? fh / 2, `texto ${k}, y`, -1920, 3840),
      estilo: estilo(t.estilo),
    };
  });

  const transIn = m.transicoes ?? [];
  if (!Array.isArray(transIn) || transIn.length > MAX_VAGAS) throw new ModeloInvalido('transições demais');
  if (transIn.length && total < 2) throw new ModeloInvalido('transição precisa de uma troca');
  const porVaga = new Map();
  for (const [i, t] of transIn.entries()) {
    const k = i + 1;
    if (!ehObjeto(t)) throw new ModeloInvalido(`transição ${k}: um objeto`);
    const vaga = inteiro(t.vaga, `transição ${k}, vaga`, 2, total);
    if (porVaga.has(vaga)) throw new ModeloInvalido(`transição ${k}: a troca do lugar ${vaga} já tem transição`);
    if (typeof t.pacote !== 'string' || !PACOTE.test(t.pacote)) throw new ModeloInvalido(`transição ${k}: pacote desconhecido`);
    const duracao = numero(t.duracao ?? 0.5, `transição ${k}, duração`, TRANSICAO[0], TRANSICAO[1]);
    porVaga.set(vaga, { vaga, pacote: t.pacote, duracao: Math.round(duracao * 1000) / 1000 });
  }
  const transicoes = [...porVaga.keys()].sort((a, b) => a - b).map((v) => porVaga.get(v));

  const out = { versao: 1, comeca, drop_na_vaga: drop, golpe, formato, vagas, textos, transicoes };
  if (new TextEncoder().encode(JSON.stringify(out)).length > MAX_BYTES) {
    throw new ModeloInvalido(`o modelo passa de ${MAX_BYTES / 1000} KB`);
  }
  return out;
}

// o que o cartão mostra: o ritmo (as batidas de cada lugar), os textos e o drop (montagens.resumo)
export function resumoDoModelo(m) {
  const ritmo = m.vagas.flatMap((v) => Array(v.repetir ?? 1).fill(v.batidas));
  return {
    lugares: ritmo.length,
    batidas: ritmo.reduce((a, b) => a + b, 0),
    ritmo,
    drop_na_vaga: m.drop_na_vaga,
    formato: m.formato,
    textos: m.textos.map((t) => ({ nome: t.nome, vaga: t.vaga, batidas: t.batidas })),
    transicoes: m.transicoes.length,
  };
}
