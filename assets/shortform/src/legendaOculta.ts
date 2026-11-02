/**
 * The stretches where the caption steps aside and only the highlighted text stays on screen:
 * `captions.ocultar` (written by the agent) and `captions.ocultarTextos` (camadas_edit_data.py, from
 * the user's text layers with "hide the caption" on). Seconds, on the cut's clock.
 *
 * Dropping the words is not enough: the karaoke holds the previous line on screen until the next one
 * starts, so it would sit under the highlighted text the whole time. An EMPTY item covering the stretch
 * closes that line; every grouping keeps an empty item on a line of its own (nothing to draw). Windows
 * less than 0.6 s apart become one, so the caption does not blink between two texts.
 */
import editData from '../public/edit-data.json';

export type Janela = {start: number; end: number};
type Palavra = {text: string; startMs: number; endMs: number};

const C = (editData as unknown as {captions?: {ocultar?: unknown; ocultarTextos?: unknown}}).captions ?? {};
const VAO = 0.6;

const lista = (v: unknown): Janela[] =>
  Array.isArray(v)
    ? v
        .map((j) => ({start: Number((j as Janela)?.start), end: Number((j as Janela)?.end)}))
        .filter((j) => Number.isFinite(j.start) && Number.isFinite(j.end) && j.end > j.start)
    : [];

const juntar = (js: Janela[]): Janela[] => {
  const out: Janela[] = [];
  for (const j of [...js].sort((a, b) => a.start - b.start)) {
    const ult = out[out.length - 1];
    if (ult && j.start - ult.end < VAO) ult.end = Math.max(ult.end, j.end);
    else out.push({...j});
  }
  return out;
};

export const JANELAS_OCULTAS: Janela[] = juntar([...lista(C.ocultar), ...lista(C.ocultarTextos)]);

/** An item with no text: it only holds the screen (empty), so it is a line of its own. */
export const vazia = (w: {text: string}): boolean => !String(w.text ?? '').trim();

/** The span [aMs, bMs) touches a hidden stretch. */
export const tocaOculta = (aMs: number, bMs: number): boolean =>
  JANELAS_OCULTAS.some((j) => aMs < j.end * 1000 && bMs > j.start * 1000);

/** The words without the ones spoken in a hidden stretch, plus one empty item covering each stretch. */
export function semAsOcultas<T extends Palavra>(words: T[]): T[] {
  if (!JANELAS_OCULTAS.length) return words;
  const ficam = words.filter((w) => vazia(w) || !tocaOculta(w.startMs, w.endMs));
  const vazios = JANELAS_OCULTAS.map(
    (j) =>
      ({
        text: ' ',
        startMs: Math.round(j.start * 1000),
        endMs: Math.round(j.end * 1000),
        timestampMs: Math.round(j.start * 1000),
        confidence: null,
      }) as unknown as T,
  );
  return [...ficam, ...vazios].sort((a, b) => a.startMs - b.startMs);
}
