// O lado Node do efeitos_render.py: empacota a composição EfeitosBase do projeto Remotion
// uma vez e desenha, a cada chamada, um bloco de quadros. Usa o Remotion instalado NO
// PROJETO (o kit não tem node_modules): os módulos são achados pelo package.json dele.
// O empacotamento não usa cache, então nada é gravado dentro do node_modules.
//
//   node efeitos_render.mjs bundle <projeto_remotion> <public_dos_efeitos> <saida_bundle>
//   node efeitos_render.mjs render <projeto_remotion> <bundle> <props.json> <de> <ate> <saida>
//
// CUTMIND_GL troca o WebGL do Chrome do render (padrão: o do Remotion).
import fs from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [modo, projeto, ...resto] = process.argv.slice(2);
const req = createRequire(path.join(path.resolve(projeto || '.'), 'package.json'));
const carregar = (nome) => import(pathToFileURL(req.resolve(nome)).href);

async function empacotar([publicDir, outDir]) {
  const {bundle} = await carregar('@remotion/bundler');
  fs.rmSync(outDir, {recursive: true, force: true});
  await bundle({
    entryPoint: path.join(projeto, 'src', 'index.ts'),
    rootDir: projeto,
    publicDir,
    outDir,
    enableCaching: false,
  });
  console.log(outDir);
}

async function desenhar([serveUrl, propsFile, de, ate, saida]) {
  const {openBrowser, renderFrames, selectComposition} = await carregar('@remotion/renderer');
  const inputProps = JSON.parse(fs.readFileSync(propsFile, 'utf8'));
  const chromiumOptions = process.env.CUTMIND_GL ? {gl: process.env.CUTMIND_GL} : {};
  const browser = await openBrowser('chrome', {chromiumOptions});
  try {
    const composition = await selectComposition({serveUrl, id: 'EfeitosBase', inputProps, puppeteerInstance: browser});
    fs.mkdirSync(saida, {recursive: true});
    await renderFrames({
      composition,
      serveUrl,
      inputProps,
      imageFormat: 'png',
      outputDir: saida,
      frameRange: [Number(de), Number(ate)],
      onStart: () => {},
      onFrameUpdate: () => {},
      puppeteerInstance: browser,
      chromiumOptions,
      concurrency: Number(process.env.CUTMIND_EFEITOS_CONCORRENCIA || 2),
    });
  } finally {
    await browser.close({silent: true});
  }
}

try {
  if (modo === 'bundle') await empacotar(resto);
  else if (modo === 'render') await desenhar(resto);
  else throw new Error(`modo desconhecido: ${modo}`);
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  process.exitCode = 1; // sem process.exit: no Windows ele corta a saída antes de drenar
}
