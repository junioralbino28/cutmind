// A zona segura do Reels/TikTok/Shorts num quadro 1080×1920, medida em 29/10/2026 com os gabaritos do
// Instagram: a grade do perfil mostra só 1080×1440 do meio (somem 240 px em cima e 240 embaixo), o cabeçalho
// do Reels fica em cima, a coluna de botões (curtir, comentar, compartilhar, áudio) à direita e o nome e a
// descrição do post embaixo. Texto e gráfico ficam DENTRO: de `topo` a `legendaPost`, à esquerda de `colunaX`
// entre `colunaY0` e `colunaY1`. O editor tem a mesma régua (celular.js, ZONA_SEGURA) e um teste confere as duas.
export const ZONA_SEGURA = {topo: 240, base: 1680, legendaPost: 1560, colunaX: 930, colunaY0: 880, colunaY1: 1680} as const;
