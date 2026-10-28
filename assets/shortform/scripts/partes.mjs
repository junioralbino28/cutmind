// Renders only some frame ranges of the Reels composition (helpers/render_janelas.py runs it
// from the project's remotion/ folder and splices the parts into out/render.mp4).
// usage: node scripts/partes.mjs <outDir> a-b [a-b ...]   (global frames, b exclusive)
import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia} from '@remotion/renderer';
import path from 'node:path';
import os from 'node:os';
import {readdir, rm, stat} from 'node:fs/promises';

const inicio = Date.now();
const [outDir, ...faixas] = process.argv.slice(2);
// Windows, project in a deep folder: Chrome and the compositor run from short copies (helpers/aquecer_navegador.py)
const curto = {
  ...(process.env.CUTMIND_CHROME ? {browserExecutable: process.env.CUTMIND_CHROME} : {}),
  ...(process.env.CUTMIND_BINARIOS ? {binariesDirectory: process.env.CUTMIND_BINARIOS} : {}),
};
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
try {
  const composition = await selectComposition({serveUrl, id: 'Reels', ...curto});
  for (const fx of faixas) {
    const [a, b] = fx.split('-').map(Number);
    const t0 = Date.now();
    await renderMedia({
      serveUrl, composition, codec: 'h264', frameRange: [a, b - 1], timeoutInMilliseconds: 180000,
      outputLocation: path.join(outDir, `parte_${a}_${b}.mp4`), ...curto,
    });
    console.log(`parte ${a}-${b}: ${b - a} quadros em ${Math.round((Date.now() - t0) / 1000)} s`);
  }
} finally {
  // bundle() copies the whole public/ (person mattes in ProRes, ~20 MB per second) to the temp
  // folder on every run and never deletes it; renders leave remotion-v*-assets* behind. Left
  // there, a few runs fill the disk.
  await rm(serveUrl, {recursive: true, force: true});
  const tmp = os.tmpdir();
  for (const n of await readdir(tmp)) {
    if (!n.startsWith('remotion-v')) continue;
    const p = path.join(tmp, n);
    try {
      if ((await stat(p)).birthtimeMs >= inicio) await rm(p, {recursive: true, force: true});
    } catch {}
  }
}
