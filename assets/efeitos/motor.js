// Motor de efeitos do kit: o MESMO arquivo desenha filtros e transições na prévia do editor
// e no vídeo final (Remotion). Mesma resolução nos dois, para o desfoque em pixels bater.
//
//   const ef = await carregarEfeito('/gen/pacote/filme-pb/', { largura: 1080, altura: 1920 });
//   ef.desenhar({ quadro: video, intensidade: 0.8 });           // filtro
//   ef.desenhar({ a: videoA, b: quadroB, tempo_ms: 300 });       // transição
//   ef.canvas  → o resultado; ef.destruir() libera o WebGL.
//   const aj = criarAjuste({ largura: 1080, altura: 1920 });   // Ajustar da tomada, sem pacote
//   aj.desenhar({ quadro: video, ajustes: { brilho: 20, vinheta: -35 } });
//
// Fontes aceitas: <video>, <img>, <canvas>. Cor sem conversão: entra e sai nos mesmos valores.
import * as THREE from './vendor/three.module.min.js';
import { EffectComposer } from './vendor/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './vendor/jsm/postprocessing/RenderPass.js';
import { ShaderPass } from './vendor/jsm/postprocessing/ShaderPass.js';

const FORMATO = 1;

const juntar = (base, arquivo) => (base.endsWith('/') ? base : base + '/') + arquivo;

async function buscar(url, como) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`efeito: ${url} → ${r.status}`);
  return como === 'json' ? r.json() : r.text();
}

async function imagem(url) {
  const i = new Image();
  i.src = url;
  await i.decode();
  return i;
}

function texturaDeEntrada(largura, altura) {
  // começa com um quadro vazio do tamanho certo: a cena mede a proporção na montagem, e o
  // 1º envio ao WebGL (renderer.initTexture) reserva a memória por ele. Um <video> tem
  // width 0 (o tamanho fica em videoWidth): reservada por ele, a textura sai preta.
  const vazio = document.createElement('canvas');
  vazio.width = largura;
  vazio.height = altura;
  const t = new THREE.Texture(vazio);
  t.colorSpace = THREE.LinearSRGBColorSpace;
  t.needsUpdate = true;
  return t;
}

function trocar(textura, fonte) {
  if (!fonte) return;
  textura.image = fonte;
  textura.needsUpdate = true;
}

export async function carregarEfeito(base, { largura, altura }) {
  if (!(largura > 0 && altura > 0)) throw new Error('efeito: largura e altura são obrigatórias');
  const manifesto = await buscar(juntar(base, 'efeito.json'), 'json');
  if (manifesto.formato !== FORMATO) throw new Error(`efeito: formato ${manifesto.formato} não suportado`);
  if (manifesto.motor === 'shader') return motorShader(base, manifesto, largura, altura);
  if (manifesto.motor === 'cena') return motorCena(base, manifesto, largura, altura);
  throw new Error(`efeito: motor "${manifesto.motor}" não existe`);
}

// ---------- filtro: um shader no quadro inteiro ----------

async function motorShader(base, manifesto, largura, altura) {
  const nomes = Object.entries(manifesto.texturas || {});
  const [vert, frag, ...imgs] = await Promise.all([
    buscar(juntar(base, manifesto.vert)),
    buscar(juntar(base, manifesto.frag)),
    ...nomes.map(([, arq]) => imagem(juntar(base, arq))),
  ]);
  const renderer = new THREE.WebGLRenderer({ preserveDrawingBuffer: true, alpha: false });
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.setPixelRatio(1);
  renderer.setSize(largura, altura, false);

  const quadro = texturaDeEntrada(largura, altura);
  quadro.flipY = false;
  quadro.generateMipmaps = false;
  quadro.minFilter = THREE.LinearFilter;
  const uniforms = {
    u_quadro: { value: quadro },
    u_intensidade: { value: 1 },
    u_largura: { value: largura },
    u_altura: { value: altura },
  };
  nomes.forEach(([uniform], i) => {
    const t = new THREE.Texture(imgs[i]);
    t.flipY = false;
    t.colorSpace = THREE.LinearSRGBColorSpace;
    // sem mipmap: numa tabela de cor a coordenada salta de célula entre pixels vizinhos, a GPU
    // escolhe um nível borrado e o filtro sai pontilhado (medido no "Luz solar")
    t.generateMipmaps = false;
    t.minFilter = THREE.LinearFilter;
    t.needsUpdate = true;
    uniforms[uniform] = { value: t };
  });

  // quadro inteiro; o v=0 é o topo da imagem, como no motor de origem
  const g = new THREE.BufferGeometry();
  g.setAttribute('a_posicao', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 1, -1, 0, -1, 1, 0, 1, 1, 0]), 3));
  g.setAttribute('a_uv', new THREE.BufferAttribute(new Float32Array([0, 1, 1, 1, 0, 0, 1, 0]), 2));
  g.setIndex([0, 1, 2, 2, 1, 3]);
  const material = new THREE.RawShaderMaterial({ vertexShader: vert, fragmentShader: frag, uniforms });
  const malha = new THREE.Mesh(g, material);
  malha.frustumCulled = false;
  const cena = new THREE.Scene();
  cena.add(malha);
  const camera = new THREE.Camera();
  const faixa = manifesto.intensidade || { padrao: 1, min: 0, max: 1 };
  Object.values(uniforms).forEach((u) => u.value && u.value.isTexture && renderer.initTexture(u.value));

  return {
    manifesto,
    tipo: manifesto.tipo,
    canvas: renderer.domElement,
    // sem intensidade, a do pacote: nunca a do desenho anterior
    desenhar({ quadro: fonte, intensidade }) {
      trocar(quadro, fonte);
      const v = typeof intensidade === 'number' ? intensidade : faixa.padrao;
      uniforms.u_intensidade.value = Math.min(faixa.max, Math.max(faixa.min, v));
      renderer.render(cena, camera);
    },
    destruir() {
      g.dispose();
      material.dispose();
      Object.values(uniforms).forEach((u) => u.value && u.value.dispose && u.value.dispose());
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}

// ---------- transição: script de cena (CommonJS) sobre o Three.js ----------

const MODULOS_FIXOS = {
  three: { THREE, ...THREE },
  'three/EffectComposer': { EffectComposer },
  'three/RenderPass': { RenderPass },
  'three/ShaderPass': { ShaderPass },
};

async function motorCena(base, manifesto, largura, altura) {
  const fontes = { cena: await buscar(juntar(base, manifesto.script)) };
  await Promise.all(Object.entries(manifesto.modulos || {}).map(async ([nome, arq]) => {
    fontes[nome] = await buscar(juntar(base, arq));
  }));
  // o script lê window.innerWidth/devicePixelRatio e registra "resize": recebe um window só dele,
  // para não mexer no da página
  const janela = {
    innerWidth: largura, innerHeight: altura, devicePixelRatio: 1,
    addEventListener() {}, removeEventListener() {},
  };
  const prontos = {};
  const requerer = (pedido) => {
    if (pedido in MODULOS_FIXOS) return MODULOS_FIXOS[pedido];
    const nome = pedido.replace(/^\.\//, '').replace(/\.js$/, '');
    if (prontos[nome]) return prontos[nome].exports;
    if (!(nome in fontes)) throw new Error(`efeito: módulo não previsto "${pedido}"`);
    const module = { exports: {} };
    prontos[nome] = module;
    new Function('module', 'exports', 'require', 'window', fontes[nome])(module, module.exports, requerer, janela);
    return module.exports;
  };
  const { Cena } = requerer('./cena');
  if (typeof Cena !== 'function') throw new Error('efeito: a cena não exporta Cena');

  const cena = new Cena(null, null);
  const a = texturaDeEntrada(largura, altura);
  const b = texturaDeEntrada(largura, altura);
  for (const t of [a, b]) {
    t.wrapS = THREE.RepeatWrapping; // como o próprio script prepara as amostras dele
    t.wrapT = THREE.RepeatWrapping;
  }
  cena.texture1 = a;
  cena.texture2 = b;
  cena.setupScene();
  cena.renderer.initTexture(a);
  cena.renderer.initTexture(b);
  const duracao = Number(cena.Duration) || manifesto.duracao_ms;

  // o seekToTime já desenha, menos quando a cena não tem animação; nesse caso desenha aqui
  let desenhou = false;
  const atualizar = cena.update.bind(cena);
  cena.update = () => { desenhou = true; atualizar(); };

  const saida = document.createElement('canvas');
  saida.width = largura;
  saida.height = altura;
  const ctx = saida.getContext('2d');

  return {
    manifesto,
    tipo: manifesto.tipo,
    duracao_ms: duracao,
    canvas: saida,
    desenhar({ a: fonteA, b: fonteB, tempo_ms }) {
      trocar(a, fonteA);
      trocar(b, fonteB);
      desenhou = false;
      cena.seekToTime(Math.max(0, Math.min(duracao, tempo_ms)));
      if (!desenhou) cena.update();
      // o WebGL do script não preserva o buffer: copia já, no mesmo passo, para a captura ser estável
      ctx.drawImage(cena.renderer.domElement, 0, 0, largura, altura);
    },
    destruir() {
      const r = cena.renderer;
      // o destroy do script pode chamar o que o Three.js oficial não tem (scene.dispose, medido
      // na "Zoom central"): o contexto WebGL é liberado mesmo assim, senão fica preso
      try {
        if (typeof cena.destroy === 'function') cena.destroy();
      } catch (e) { /* segue para liberar o contexto */ }
      if (r) { r.dispose(); r.forceContextLoss(); }
    },
  };
}

// ---------- ajuste: a ferramenta Ajustar da tomada, um shader nosso, sem pacote ----------
// As chaves e a faixa (−100 a 100, 0 neutro) são as do helpers/efeitos.py (AJUSTES). Cada
// passo só roda com o valor dele diferente de zero: tudo neutro devolve o quadro como entrou.
// Ordem: exposição, brilho, contraste, realces e sombras, saturação, temperatura e matiz,
// vinheta. Cores no valor do arquivo (sem conversão), como nos filtros.

export const AJUSTES = ['brilho', 'contraste', 'saturacao', 'exposicao', 'temperatura', 'matiz', 'realces', 'sombras', 'vinheta'];

const AJUSTE_VERT = `precision highp float;
attribute vec3 a_posicao;
attribute vec2 a_uv;
varying vec2 uv0;
void main() { gl_Position = vec4(a_posicao, 1.0); uv0 = a_uv; }`;

const AJUSTE_FRAG = `precision highp float;
varying vec2 uv0;
uniform sampler2D u_quadro;
uniform float u_brilho, u_contraste, u_saturacao, u_exposicao, u_temperatura, u_matiz, u_realces, u_sombras, u_vinheta;
const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
void main() {
  vec3 c = texture2D(u_quadro, uv0).rgb;
  // exposição: ±1 ponto de luz, contado na luz (desfaz a curva do arquivo, multiplica, refaz)
  if (u_exposicao != 0.0) c = pow(pow(c, vec3(2.2)) * exp2(u_exposicao), vec3(1.0 / 2.2));
  // brilho: curva que mexe nos meios e deixa o preto e o branco no lugar
  if (u_brilho != 0.0) c = pow(c, vec3(exp2(-0.7 * u_brilho)));
  // contraste: em volta do cinza médio, de 0,5× a 2×
  if (u_contraste != 0.0) c = (c - 0.5) * exp2(u_contraste) + 0.5;
  // realces e sombras: subir puxa para o branco, descer multiplica (aprofunda sem esmagar no preto)
  if (u_realces != 0.0 || u_sombras != 0.0) {
    float y = clamp(dot(c, LUMA), 0.0, 1.0);
    float wc = smoothstep(0.5, 1.0, y), we = 1.0 - smoothstep(0.0, 0.5, y);
    c = u_realces > 0.0 ? mix(c, vec3(1.0), 0.4 * u_realces * wc) : c * (1.0 + 0.4 * u_realces * wc);
    c = u_sombras > 0.0 ? mix(c, vec3(1.0), 0.3 * u_sombras * we) : c * (1.0 + 0.5 * u_sombras * we);
  }
  // saturação: −100 é preto e branco, 100 é o dobro
  if (u_saturacao != 0.0) c = mix(vec3(dot(c, LUMA)), c, 1.0 + u_saturacao);
  // temperatura: mais quente puxa o vermelho e tira o azul; matiz: mais é magenta, menos é verde
  if (u_temperatura != 0.0) c *= vec3(1.0 + 0.2 * u_temperatura, 1.0, 1.0 - 0.2 * u_temperatura);
  if (u_matiz != 0.0) c *= vec3(1.0, 1.0 - 0.2 * u_matiz, 1.0);
  // vinheta: escurece (ou clareia, abaixo de zero) as bordas, na forma do quadro
  if (u_vinheta != 0.0) {
    float w = smoothstep(0.35, 1.0, length(uv0 - 0.5) * 1.41421356);
    c = u_vinheta > 0.0 ? c * (1.0 - 0.8 * u_vinheta * w) : mix(c, vec3(1.0), -0.5 * u_vinheta * w);
  }
  gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}`;

export function criarAjuste({ largura, altura }) {
  if (!(largura > 0 && altura > 0)) throw new Error('ajuste: largura e altura são obrigatórias');
  const renderer = new THREE.WebGLRenderer({ preserveDrawingBuffer: true, alpha: false });
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.setPixelRatio(1);
  renderer.setSize(largura, altura, false);
  const quadro = texturaDeEntrada(largura, altura);
  quadro.flipY = false;
  quadro.generateMipmaps = false;
  quadro.minFilter = THREE.LinearFilter;
  const uniforms = { u_quadro: { value: quadro } };
  for (const k of AJUSTES) uniforms[`u_${k}`] = { value: 0 };
  const g = new THREE.BufferGeometry();
  g.setAttribute('a_posicao', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 1, -1, 0, -1, 1, 0, 1, 1, 0]), 3));
  g.setAttribute('a_uv', new THREE.BufferAttribute(new Float32Array([0, 1, 1, 1, 0, 0, 1, 0]), 2));
  g.setIndex([0, 1, 2, 2, 1, 3]);
  const material = new THREE.RawShaderMaterial({ vertexShader: AJUSTE_VERT, fragmentShader: AJUSTE_FRAG, uniforms });
  const malha = new THREE.Mesh(g, material);
  malha.frustumCulled = false;
  const cena = new THREE.Scene();
  cena.add(malha);
  const camera = new THREE.Camera();
  renderer.initTexture(quadro);
  return {
    tipo: 'ajuste',
    canvas: renderer.domElement,
    desenhar({ quadro: fonte, ajustes }) {
      trocar(quadro, fonte);
      for (const k of AJUSTES) {
        const v = Number((ajustes || {})[k]) || 0;
        uniforms[`u_${k}`].value = Math.max(-100, Math.min(100, v)) / 100;
      }
      renderer.render(cena, camera);
    },
    destruir() {
      g.dispose();
      material.dispose();
      quadro.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
