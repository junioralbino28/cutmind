/* Fontes do painel de Texto (efeitos, e depois gancho e número): o catálogo que o editor mostra.
 * Nenhum arquivo de fonte vem no kit. A prévia pede ao Google Fonts uma folha com todas quando o
 * painel abre (cada arquivo só desce quando a fonte aparece na tela), e o render baixa só a que o
 * vídeo usa: o src/fontes.ts do Remotion tem a mesma lista, conferida no @remotion/google-fonts
 * (família e o peso em que cada uma é desenhada). Mudou aqui, muda lá.
 * A escolha segue o painel de fontes do CapCut: o 1 no fim marca as da aba "Em alta" (as que
 * estão nos Êxitos dele, ou a parecida no Google Fonts quando a dele é própria). */
(function () {
  const LISTA = [
    // impacto
    ["Anton", 400, "impacto", 1],
    ["Bebas Neue", 400, "impacto", 1],
    ["Oswald", 700, "impacto", 1],
    ["Luckiest Guy", 400, "impacto", 1],
    ["Ultra", 400, "impacto", 1],
    ["Chewy", 400, "impacto", 1],
    ["Antonio", 700, "impacto"],
    ["Staatliches", 400, "impacto"],
    ["Archivo Black", 400, "impacto"],
    ["Bangers", 400, "impacto"],
    ["Bevan", 400, "impacto"],
    ["Calistoga", 400, "impacto"],
    ["DynaPuff", 700, "impacto"],
    ["Bowlby One", 400, "impacto"],
    ["Shrikhand", 400, "impacto"],
    ["Alfa Slab One", 400, "impacto"],
    ["Bungee", 400, "impacto"],
    ["Titan One", 400, "impacto"],
    ["Teko", 700, "impacto"],
    ["League Gothic", 400, "impacto"],
    // sem serifa
    ["Montserrat", 900, "sem serifa", 1],
    ["Poppins", 900, "sem serifa", 1],
    ["Rubik", 900, "sem serifa", 1],
    ["Roboto", 900, "sem serifa", 1],
    ["Open Sans", 800, "sem serifa", 1],
    ["Outfit", 900, "sem serifa", 1],
    ["Fredoka", 700, "sem serifa", 1],
    ["Inter", 900, "sem serifa"],
    ["Lato", 900, "sem serifa"],
    ["Quicksand", 700, "sem serifa"],
    ["Public Sans", 900, "sem serifa"],
    ["Raleway", 900, "sem serifa"],
    ["Work Sans", 900, "sem serifa"],
    ["Space Grotesk", 700, "sem serifa"],
    ["Cabin", 700, "sem serifa"],
    ["Prompt", 900, "sem serifa"],
    ["DM Sans", 900, "sem serifa"],
    ["Nunito", 900, "sem serifa"],
    ["Baloo 2", 800, "sem serifa"],
    ["Archivo", 900, "sem serifa"],
    ["Barlow Condensed", 900, "sem serifa"],
    ["Playpen Sans", 800, "sem serifa"],
    ["IBM Plex Sans", 700, "sem serifa"],
    ["Readex Pro", 700, "sem serifa"],
    ["Noto Sans", 900, "sem serifa"],
    // serifa
    ["Playfair Display", 900, "serifa", 1],
    ["Cormorant Garamond", 700, "serifa", 1],
    ["Cardo", 700, "serifa", 1],
    ["Abril Fatface", 400, "serifa"],
    ["DM Serif Display", 400, "serifa"],
    ["Instrument Serif", 400, "serifa"],
    ["Bodoni Moda", 900, "serifa"],
    ["Old Standard TT", 700, "serifa"],
    ["Cinzel", 700, "serifa"],
    ["Lora", 700, "serifa"],
    ["Merriweather", 900, "serifa"],
    ["Fraunces", 900, "serifa"],
    ["Aleo", 700, "serifa"],
    ["Aboreto", 400, "serifa"],
    ["Gloock", 400, "serifa"],
    ["Young Serif", 400, "serifa"],
    ["Noto Serif", 900, "serifa"],
    // manuscrita
    ["Caveat Brush", 400, "manuscrita", 1],
    ["Story Script", 400, "manuscrita", 1],
    ["Satisfy", 400, "manuscrita", 1],
    ["Oregano", 400, "manuscrita", 1],
    ["Rock Salt", 400, "manuscrita", 1],
    ["Allura", 400, "manuscrita", 1],
    ["Arizonia", 400, "manuscrita", 1],
    ["Parisienne", 400, "manuscrita", 1],
    ["The Nautigal", 700, "manuscrita", 1],
    ["Great Vibes", 400, "manuscrita", 1],
    ["Caveat", 700, "manuscrita"],
    ["Pacifico", 400, "manuscrita"],
    ["Dancing Script", 700, "manuscrita"],
    ["Permanent Marker", 400, "manuscrita"],
    ["Kalam", 700, "manuscrita"],
    ["Shadows Into Light", 400, "manuscrita"],
    ["Italianno", 400, "manuscrita"],
    ["Alex Brush", 400, "manuscrita"],
    ["Cookie", 400, "manuscrita"],
    ["Merienda", 700, "manuscrita"],
    // retrô
    ["Nosifer", 400, "retrô", 1],
    ["Special Elite", 400, "retrô"],
    ["Lobster", 400, "retrô"],
    ["Righteous", 400, "retrô"],
    ["Monoton", 400, "retrô"],
    ["Press Start 2P", 400, "retrô"],
    ["VT323", 400, "retrô"],
    ["Trade Winds", 400, "retrô"],
    ["Rubik Mono One", 400, "retrô"],
    ["Orbitron", 900, "retrô"],
    ["Chango", 400, "retrô"],
    ["Rye", 400, "retrô"],
  ];
  const CATEGORIAS = [['alta', t('Em alta')], ['impacto', t('Impacto')], ['sem serifa', t('Sem serifa')], ['serifa', t('Serifa')], ['manuscrita', t('Manuscrita')], ['retrô', t('Retrô')]];
  // as chaves com que os efeitos foram desenhados (FONTE em src/cenas/comum.tsx)
  const LEGADO = { poppins: 'Poppins', anton: 'Anton', bebas: 'Bebas Neue', oswald: 'Oswald', playfair: 'Playfair Display', caveat: 'Caveat',
    marker: 'Permanent Marker', elite: 'Special Elite', instrument: 'Instrument Serif', abril: 'Abril Fatface', oldstd: 'Old Standard TT' };
  const FONTES = LISTA.map(([familia, peso, cat, alta]) => ({ familia, peso, cat, alta: !!alta }));
  const familiaDe = (k) => LEGADO[k] || k;
  const pesoDe = (k) => { const f = FONTES.find((x) => x.familia === familiaDe(k)); return f ? f.peso : 400; };
  const daAba = (aba) => FONTES.filter((f) => (aba === 'alta' ? f.alta : f.cat === aba));
  let pedida = false;
  function carregarTodas() {
    if (pedida) return;
    pedida = true;
    const fam = FONTES.map((f) => `family=${f.familia.replace(/ /g, '+')}${f.peso !== 400 ? `:wght@${f.peso}` : ''}`).join('&');
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `https://fonts.googleapis.com/css2?${fam}&display=swap`;
    document.head.appendChild(link);
  }
  window.CutMindFontes = { FONTES, CATEGORIAS, LEGADO, familiaDe, pesoDe, daAba, carregarTodas };
})();
