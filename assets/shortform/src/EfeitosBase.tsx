import {useEffect, useMemo, useRef} from 'react';
import {AbsoluteFill, cancelRender, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';

// Os filtros e as transições do editor, quadro a quadro, com o MESMO motor da prévia
// (public/efeitos/motor.js). Quem monta e chama é o helpers/efeitos_render.py: ele põe em
// public/efeitos/ o motor, os pacotes abertos e os quadros do cut.mp4, e cola o resultado
// num cut.mp4 novo. Cada quadro desta composição é uma "receita":
//   n   o quadro do cut.mp4 que sai daqui
//   tr  transição: pacote, tempo_ms e os quadros dos lados a e b
//   fi  filtro: pacote e intensidade (sem ela, a do pacote)
//   aj  ajuste (Ajustar da tomada): os valores, num shader do próprio motor
// Primeiro a transição, depois o filtro por cima e o ajuste por último: a mesma ordem da prévia.

export type Receita = {
  n: number;
  tr?: {pacote: string; tempo_ms: number; a: number; b: number};
  fi?: {pacote: string; intensidade?: number | null};
  aj?: {ajustes: Record<string, number>};
};
export type EfeitosProps = {largura: number; altura: number; receitas: Receita[]};

type Efeito = {canvas: HTMLCanvasElement; desenhar: (o: Record<string, unknown>) => void};

// import() de verdade, fora do webpack: o motor é o arquivo de public/, não uma cópia empacotada
const importar = new Function('u', 'return import(u)') as (u: string) => Promise<{
  carregarEfeito: (base: string, tam: {largura: number; altura: number}) => Promise<Efeito>;
  criarAjuste: (tam: {largura: number; altura: number}) => Efeito;
}>;
let motorMod: ReturnType<typeof importar> | null = null;
const motores = new Map<string, Promise<Efeito>>();
let ajusteMotor: Promise<Efeito> | null = null;
const pasta = (arquivo: string) => staticFile(arquivo).replace(/[^/]*$/, '');

const motor = (pacote: string, largura: number, altura: number) => {
  let m = motores.get(pacote);
  if (!m) {
    motorMod = motorMod || importar(staticFile('efeitos/motor.js'));
    m = motorMod.then((mod) => mod.carregarEfeito(pasta(`efeitos/pacotes/${pacote}/efeito.json`), {largura, altura}));
    motores.set(pacote, m);
  }
  return m;
};

const ajuste = (largura: number, altura: number) => {
  motorMod = motorMod || importar(staticFile('efeitos/motor.js'));
  ajusteMotor = ajusteMotor || motorMod.then((mod) => mod.criarAjuste({largura, altura}));
  return ajusteMotor;
};

const imagem = async (n: number) => {
  const i = new Image();
  i.src = staticFile(`efeitos/quadros/${n}.png`);
  await i.decode();
  return i;
};

export const EfeitosBase: React.FC<EfeitosProps> = ({largura, altura, receitas}) => {
  const frame = useCurrentFrame();
  const ref = useRef<HTMLCanvasElement>(null);
  // um pedido de espera por quadro: a captura só sai depois do desenho
  const espera = useMemo(() => delayRender(`efeito do quadro ${frame}`), [frame]);
  useEffect(() => {
    const r = receitas[frame];
    (async () => {
      let fonte: CanvasImageSource = await imagem(r.n);
      let saida: CanvasImageSource = fonte;
      if (r.tr) {
        const [m, a, b] = await Promise.all([motor(r.tr.pacote, largura, altura), imagem(r.tr.a), imagem(r.tr.b)]);
        m.desenhar({a, b, tempo_ms: r.tr.tempo_ms});
        fonte = saida = m.canvas;
      }
      if (r.fi) {
        const m = await motor(r.fi.pacote, largura, altura);
        m.desenhar({quadro: fonte, intensidade: r.fi.intensidade ?? undefined});
        fonte = saida = m.canvas;
      }
      if (r.aj) {
        const m = await ajuste(largura, altura);
        m.desenhar({quadro: fonte, ajustes: r.aj.ajustes});
        saida = m.canvas;
      }
      ref.current!.getContext('2d')!.drawImage(saida, 0, 0, largura, altura);
      continueRender(espera);
    })().catch((e) => cancelRender(e));
  }, [frame, espera, receitas, largura, altura]);
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <canvas ref={ref} width={largura} height={altura} style={{width: '100%', height: '100%'}} />
    </AbsoluteFill>
  );
};
