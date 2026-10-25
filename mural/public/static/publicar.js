// Publicar: o editor do CutMind abre esta página com o modelo no fragmento (#m=<base64url do JSON>).
// O fragmento não vai ao servidor: o modelo só sai do navegador quando a pessoa aperta Publicar.
const $ = (id) => document.getElementById(id);

function lerFragmento() {
  const m = new URLSearchParams(location.hash.slice(1)).get('m');
  if (!m) return null;
  try {
    const b64 = m.replace(/-/g, '+').replace(/_/g, '/');
    const bytes = Uint8Array.from(atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4)), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

const svg = (tag, attrs, pai) => {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (pai) pai.appendChild(e);
  return e;
};

// a mesma capa do mural (src/html.js capaRitmo), desenhada aqui
function capa(modelo, pai) {
  const ritmo = (modelo.vagas || []).flatMap((v) => Array(v.repetir || 1).fill(v.batidas));
  const total = Math.max(1, ritmo.reduce((a, b) => a + b, 0));
  const drop = modelo.drop_na_vaga;
  const s = svg('svg', { class: 'ritmo', viewBox: `0 0 ${total} 88`, preserveAspectRatio: 'none' });
  for (const t of modelo.textos || []) {
    const ini = ritmo.slice(0, (t.vaga || 1) - 1).reduce((a, b) => a + b, 0);
    if (ini < total) svg('rect', { x: ini, y: 6, width: Math.min(t.batidas || ritmo[(t.vaga || 1) - 1] || 1, total - ini), height: 5, class: 't' }, s);
  }
  let x = 0;
  ritmo.forEach((nb, i) => {
    const noDrop = drop && i + 1 >= drop;
    const h = drop ? (noDrop ? 60 : 26) : 42;
    svg('rect', { x, y: 82 - h, width: Math.max(0.0001, nb - 0.06), height: h, class: noDrop ? 'b-drop' : 'b' }, s);
    x += nb;
  });
  const a = document.createElement('div');
  a.className = 'capa';
  a.appendChild(s);
  const f = document.createElement('span');
  f.className = 'fmt';
  f.textContent = modelo.formato || '9:16';
  a.appendChild(f);
  pai.appendChild(a);
  const meta = document.createElement('p');
  meta.className = 'meta';
  const n = ritmo.length;
  meta.textContent = `${n} ${n === 1 ? 'lugar' : 'lugares'} · ${total} batidas · ${modelo.formato || '9:16'}`
    + ((modelo.textos || []).length ? ` · ${modelo.textos.length} ${modelo.textos.length === 1 ? 'texto' : 'textos'}` : '');
  pai.appendChild(meta);
}

const modelo = lerFragmento();
const previa = $('previa');
previa.textContent = '';
if (!modelo) {
  const p = document.createElement('p');
  p.className = 'vazio';
  p.textContent = 'Abra esta página pelo botão Compartilhar do CutMind: ela chega com o modelo.';
  previa.appendChild(p);
} else {
  capa(modelo, previa);
  const form = $('formPublicar');
  form.hidden = false;
  if (typeof modelo.nome === 'string') form.nome.value = modelo.nome.slice(0, 60);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const aviso = form.querySelector('.aviso');
    const botao = form.querySelector('button[type=submit]');
    const token = form.querySelector('[name="cf-turnstile-response"]');
    aviso.classList.remove('erro');
    aviso.textContent = 'Publicando…';
    botao.disabled = true;
    try {
      const { nome: _n, id: _i, criado: _c, ...somenteModelo } = modelo;
      const r = await fetch('/api/modelos', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modelo: somenteModelo, nome: form.nome.value, autor: form.autor.value,
          post: form.post.value, turnstile: token ? token.value : '' }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.erro || 'não deu');
      form.hidden = true;
      $('linkPronto').href = d.url;
      $('linkPronto').textContent = d.url;
      $('pronto').hidden = false;
      history.replaceState(null, '', location.pathname); // o modelo sai da barra de endereço
    } catch (err) {
      aviso.classList.add('erro');
      aviso.textContent = `Não publiquei: ${err.message}`;
      botao.disabled = false;
      if (window.turnstile) window.turnstile.reset(); // o token do anti-robô vale uma vez só
    }
  });
}
$('copiar').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('linkPronto').href);
    $('copiar').textContent = 'Copiado';
  } catch {
    $('copiar').textContent = 'Copie o link acima';
  }
});
