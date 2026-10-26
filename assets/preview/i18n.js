/* CutMind — o idioma do editor.
 *
 * O texto em português é a chave: `t('Salvar')` devolve "Save" em inglês e "Salvar" em português.
 * Sem tradução no dicionário (`i18n-en.js`), sai o português, e nada some da tela. Texto com número
 * ou nome usa marcador: `t('Lugar {n}', {n: 3})`. O que a pessoa digita (legenda, nome de projeto,
 * texto de camada) nunca passa por aqui.
 *
 * O idioma vem do botão PT | EN (guardado neste navegador) e, sem escolha, do navegador: `pt*` é
 * português, qualquer outro é inglês. Trocar recarrega a página (com ajuste por salvar, o editor
 * avisa antes), então cada texto é calculado uma vez, já no idioma certo.
 *
 * Carrega antes dos outros scripts: o `estilos.js` monta o catálogo com `t()` na carga.
 */
(function () {
  const CHAVE = 'cutmind-idioma';
  let escolhido = null;
  try { escolhido = localStorage.getItem(CHAVE); } catch (e) { /* sem armazenamento: vale o navegador */ }
  const nav = (navigator.languages && navigator.languages[0]) || navigator.language || 'pt';
  const IDIOMA = escolhido === 'pt' || escolhido === 'en' ? escolhido : (/^pt\b/i.test(nav) ? 'pt' : 'en');
  const EN = window.I18N_EN || {};
  document.documentElement.lang = IDIOMA === 'pt' ? 'pt-BR' : 'en';

  // Uma palavra com dois sentidos ganha contexto depois do §: t('Ajustar§cor') é "Adjust" e o botão de zoom
  // "Ajustar" é "Fit". Em português a tela mostra só o que vem antes do §.
  function t(texto, valores) {
    let s = IDIOMA === 'en' && Object.prototype.hasOwnProperty.call(EN, texto) ? EN[texto] : texto.split('§')[0];
    if (valores) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in valores ? String(valores[k]) : m));
    return s;
  }

  function trocarIdioma(novo) {
    try { localStorage.setItem(CHAVE, novo); } catch (e) { /* sem armazenamento: vale só até recarregar */ }
  }

  // O HTML estático: os textos e os atributos de ajuda. Roda uma vez, na carga, quando a página ainda
  // não tem nada da pessoa; o espaço em volta do texto fica como está ("Salvar <b>0</b>").
  const ATRIBUTOS = ['title', 'aria-label', 'placeholder', 'alt'];
  function traduzirHtml(raiz) {
    if (IDIOMA === 'pt') return;
    const andar = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
    const nos = [];
    while (andar.nextNode()) nos.push(andar.currentNode);
    for (const n of nos) {
      const p = n.parentNode;
      if (!p || p.nodeName === 'SCRIPT' || p.nodeName === 'STYLE') continue;
      const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(n.nodeValue);
      if (m[2] && Object.prototype.hasOwnProperty.call(EN, m[2])) n.nodeValue = m[1] + EN[m[2]] + m[3];
    }
    for (const a of ATRIBUTOS) {
      raiz.querySelectorAll(`[${a}]`).forEach((e) => {
        const v = e.getAttribute(a);
        if (Object.prototype.hasOwnProperty.call(EN, v)) e.setAttribute(a, EN[v]);
      });
    }
  }

  // O servidor do editor responde no idioma da tela (os erros, helpers/idioma.py): todo pedido para ele
  // leva o idioma num cabeçalho. Pedido para outro endereço (mural, fontes) sai como está.
  const CABECALHO = 'X-CutMind-Idioma';
  const doEditor = (url) => { try { return new URL(url, location.href).origin === location.origin; } catch (e) { return false; } };
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = (entrada, opcoes) => {
    if (!doEditor(entrada instanceof Request ? entrada.url : String(entrada))) return fetchOriginal(entrada, opcoes);
    const cab = new Headers((opcoes && opcoes.headers) || (entrada instanceof Request ? entrada.headers : undefined));
    cab.set(CABECALHO, IDIOMA);
    return fetchOriginal(entrada, { ...(opcoes || {}), headers: cab });
  };
  const abrir = XMLHttpRequest.prototype.open;
  const enviar = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (metodo, url, ...resto) {
    this.cutmindDoEditor = doEditor(url);
    return abrir.call(this, metodo, url, ...resto);
  };
  XMLHttpRequest.prototype.send = function (corpo) {
    if (this.cutmindDoEditor) this.setRequestHeader(CABECALHO, IDIOMA);
    return enviar.call(this, corpo);
  };

  window.t = t;
  window.IDIOMA = IDIOMA;
  window.trocarIdioma = trocarIdioma;
  if (Object.prototype.hasOwnProperty.call(EN, document.title)) document.title = EN[document.title];
  traduzirHtml(document.body);
})();
