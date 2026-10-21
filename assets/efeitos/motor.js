// Motor de efeitos do kit: o MESMO arquivo desenha filtros e transições na prévia do editor
// e no vídeo final (Remotion). Mesma resolução nos dois, para o desfoque em pixels bater.
//
//   const ef = await carregarEfeito('/gen/pacote/filme-pb/', { largura: 1080, altura: 1920 });
//   ef.desenhar({ quadro: video, intensidade: 0.8 });           // filtro
//   ef.desenhar({ a: videoA, b: quadroB, tempo_ms: 300 });       // transição
//   ef.canvas  → o resultado; ef.destruir() libera o WebGL.
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
      if (typeof cena.destroy === 'function') cena.destroy();
      if (r) { r.dispose(); r.forceContextLoss(); }
    },
  };
}
