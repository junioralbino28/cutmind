/**
 * Fonts the editor offers for highlight texts (the kit's assets/preview/fontes.js has the same
 * list, with the category of each). Nothing ships with the project: each family is a lazy chunk
 * of @remotion/google-fonts and its file downloads from Google only when a video uses it, with
 * the one weight it is drawn with. Generated from the verified catalog: edit the list, not by hand.
 */
import {useEffect, useState} from 'react';
import {cancelRender, continueRender, delayRender} from 'remotion';

type Fonte = {peso: number; subsets: string[]; load: () => Promise<unknown>};
export const CATALOGO: Record<string, Fonte> = {
  "Anton": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Anton')},
  "Bebas Neue": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/BebasNeue')},
  "Oswald": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Oswald')},
  "Luckiest Guy": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/LuckiestGuy')},
  "Ultra": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Ultra')},
  "Chewy": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/Chewy')},
  "Antonio": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Antonio')},
  "Staatliches": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Staatliches')},
  "Archivo Black": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/ArchivoBlack')},
  "Bangers": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Bangers')},
  "Bevan": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Bevan')},
  "Calistoga": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Calistoga')},
  "DynaPuff": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/DynaPuff')},
  "Bowlby One": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/BowlbyOne')},
  "Shrikhand": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Shrikhand')},
  "Alfa Slab One": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/AlfaSlabOne')},
  "Bungee": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Bungee')},
  "Titan One": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/TitanOne')},
  "Teko": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Teko')},
  "League Gothic": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/LeagueGothic')},
  "Montserrat": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Montserrat')},
  "Poppins": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Poppins')},
  "Rubik": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Rubik')},
  "Roboto": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Roboto')},
  "Open Sans": {peso: 800, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/OpenSans')},
  "Outfit": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Outfit')},
  "Fredoka": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Fredoka')},
  "Inter": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Inter')},
  "Lato": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Lato')},
  "Quicksand": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Quicksand')},
  "Public Sans": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/PublicSans')},
  "Raleway": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Raleway')},
  "Work Sans": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/WorkSans')},
  "Space Grotesk": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/SpaceGrotesk')},
  "Cabin": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Cabin')},
  "Prompt": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Prompt')},
  "DM Sans": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/DMSans')},
  "Nunito": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Nunito')},
  "Baloo 2": {peso: 800, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Baloo2')},
  "Archivo": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Archivo')},
  "Barlow Condensed": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/BarlowCondensed')},
  "Playpen Sans": {peso: 800, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/PlaypenSans')},
  "IBM Plex Sans": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/IBMPlexSans')},
  "Readex Pro": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/ReadexPro')},
  "Noto Sans": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/NotoSans')},
  "Playfair Display": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/PlayfairDisplay')},
  "Cormorant Garamond": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/CormorantGaramond')},
  "Cardo": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Cardo')},
  "Abril Fatface": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/AbrilFatface')},
  "DM Serif Display": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/DMSerifDisplay')},
  "Instrument Serif": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/InstrumentSerif')},
  "Bodoni Moda": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/BodoniModa')},
  "Old Standard TT": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/OldStandardTT')},
  "Cinzel": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Cinzel')},
  "Lora": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Lora')},
  "Merriweather": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Merriweather')},
  "Fraunces": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Fraunces')},
  "Aleo": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Aleo')},
  "Aboreto": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Aboreto')},
  "Gloock": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Gloock')},
  "Young Serif": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/YoungSerif')},
  "Noto Serif": {peso: 900, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/NotoSerif')},
  "Caveat Brush": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/CaveatBrush')},
  "Story Script": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/StoryScript')},
  "Satisfy": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/Satisfy')},
  "Oregano": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Oregano')},
  "Rock Salt": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/RockSalt')},
  "Allura": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Allura')},
  "Arizonia": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Arizonia')},
  "Parisienne": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Parisienne')},
  "The Nautigal": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/TheNautigal')},
  "Great Vibes": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/GreatVibes')},
  "Caveat": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Caveat')},
  "Pacifico": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Pacifico')},
  "Dancing Script": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/DancingScript')},
  "Permanent Marker": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/PermanentMarker')},
  "Kalam": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Kalam')},
  "Shadows Into Light": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/ShadowsIntoLight')},
  "Italianno": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Italianno')},
  "Alex Brush": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/AlexBrush')},
  "Cookie": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/Cookie')},
  "Merienda": {peso: 700, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Merienda')},
  "Nosifer": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Nosifer')},
  "Special Elite": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/SpecialElite')},
  "Lobster": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Lobster')},
  "Righteous": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Righteous')},
  "Monoton": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Monoton')},
  "Press Start 2P": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/PressStart2P')},
  "VT323": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/VT323')},
  "Trade Winds": {peso: 400, subsets: ["latin"], load: () => import('@remotion/google-fonts/TradeWinds')},
  "Rubik Mono One": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/RubikMonoOne')},
  "Orbitron": {peso: 900, subsets: ["latin"], load: () => import('@remotion/google-fonts/Orbitron')},
  "Chango": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Chango')},
  "Rye": {peso: 400, subsets: ["latin", "latin-ext"], load: () => import('@remotion/google-fonts/Rye')},
};

/** CSS/SVG font-family for a catalog family (quoted: "Press Start 2P" is not a bare identifier). */
export const familiaCss = (nome: string) => `"${nome}"`;

const pedidas = new Set<string>();
const carregando: Promise<unknown>[] = [];
/** Loads a catalog family once, before the first frame; a font that fails stops the render
 * with its name instead of drawing the text in a fallback font nobody chose. */
export const carregarFonte = (nome: string, peso?: number) => {
  const f = CATALOGO[nome];
  if (!f) return;
  const w = String(peso && peso > 0 ? peso : f.peso);
  if (pedidas.has(`${nome}:${w}`)) return;
  pedidas.add(`${nome}:${w}`);
  const h = delayRender(`fonte ${nome} ${w}`);
  carregando.push(f.load()
    .then((m) => (m as {loadFont: (s: string, o: object) => {waitUntilDone: () => Promise<unknown>}}).loadFont('normal', {weights: [w], subsets: f.subsets}).waitUntilDone())
    .then(() => continueRender(h))
    .catch((err) => cancelRender(new Error(`a fonte ${nome} (${w}) não carregou: ${err}`))));
};

/** Settles once every family asked for so far has loaded. Measure text only after it:
 * measureText() keeps the first width it sees, and before the load that is the fallback font's. */
export const fontesProntas = () => Promise.all(carregando).then(() => undefined);

/** For a component that MEASURES text in a catalog font: false until the fonts loaded (the
 * frame waits meanwhile), then true. Without `precisa` it is true from the start. */
export const useFontesProntas = (precisa: boolean) => {
  const [prontas, setProntas] = useState(!precisa);
  const [h] = useState(() => (precisa ? delayRender('fontes antes de medir o texto') : null));
  useEffect(() => {
    if (h === null) return;
    fontesProntas().then(() => {
      setProntas(true);
      continueRender(h);
    });
  }, [h]);
  return prontas;
};

/** Every `estilo.fonte` in edit-data.json (effects, hook, numbers…): each family loads once. */
export const carregarFontesUsadas = (dados: unknown) => {
  const visita = (v: unknown): void => {
    if (Array.isArray(v)) {
      v.forEach(visita);
      return;
    }
    if (!v || typeof v !== 'object') return;
    const o = v as Record<string, unknown>;
    const e = o.estilo as {fonte?: unknown; peso?: unknown} | null | undefined;
    if (e && typeof e.fonte === 'string' && e.fonte in CATALOGO) carregarFonte(e.fonte, Number(e.peso) || undefined);
    Object.values(o).forEach(visita);
  };
  visita(dados);
};
