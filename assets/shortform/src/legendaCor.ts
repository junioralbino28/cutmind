/**
 * Keywords in another colour on the captions. `captions.estilo.destaques` (the editor's "Texto da
 * legenda" panel, or the agent) lists words; every time one of them is said, it shows in
 * `captions.estilo.corDestaque`, or in the accent the user picked. Comparison ignores case, accents
 * and punctuation, as celular.js does in its preview.
 */
import editData from '../public/edit-data.json';

const D = editData as unknown as {
  hook?: {accent?: string};
  captions?: {accent?: string; estilo?: {destaques?: unknown; corDestaque?: string}};
};
const E = D.captions?.estilo ?? {};

const norma = (s: string) =>
  s
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]/gu, '');

const PALAVRAS = new Set(
  (Array.isArray(E.destaques) ? E.destaques : [])
    .flatMap((x) => String(x).split(/\s+/))
    .map(norma)
    .filter(Boolean),
);
const COR = E.corDestaque || D.captions?.accent || D.hook?.accent || '#ff5200';

export const corDaPalavra = (texto: string): string | undefined => (PALAVRAS.has(norma(texto)) ? COR : undefined);
