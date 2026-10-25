// A grade e a página de um modelo: o post entra quando a pessoa toca (até lá a plataforma do post
// não recebe nada de quem só olha o mural) e a denúncia vai por um pedido ao próprio mural, com o
// anti-robô carregado só quando a pessoa abre "Denunciar".
document.addEventListener('click', (e) => {
  const b = e.target.closest('.post-tocar');
  if (!b) return;
  const caixa = document.createElement('div');
  caixa.className = `post ${b.dataset.plataforma || ''}`;
  const f = document.createElement('iframe');
  // o player roda isolado: sem acesso à página do mural, só o que um player precisa
  f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-presentation');
  f.referrerPolicy = 'strict-origin-when-cross-origin';
  f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
  f.src = b.dataset.embed;
  f.allowFullscreen = true;
  f.title = 'O post';
  caixa.appendChild(f);
  b.replaceWith(caixa);
});

// o Turnstile pela API explícita: o script entra uma vez, na primeira denúncia aberta
let turnstilePronto = null;
function carregaTurnstile() {
  if (!turnstilePronto) {
    turnstilePronto = new Promise((ok, falha) => {
      window.muralTurnstilePronto = ok;
      const s = document.createElement('script');
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=muralTurnstilePronto';
      s.async = true;
      s.onerror = () => { turnstilePronto = null; falha(new Error('o anti-robô não carregou')); };
      document.head.appendChild(s);
    });
  }
  return turnstilePronto;
}

document.addEventListener('toggle', async (e) => {
  const d = e.target;
  if (!(d instanceof HTMLDetailsElement) || !d.open || !d.classList.contains('denunciar')) return;
  const lugar = d.querySelector('.anti-robo');
  if (!lugar || lugar.dataset.pronto) return;
  lugar.dataset.pronto = '1';
  try {
    await carregaTurnstile();
    lugar.dataset.widget = window.turnstile.render(lugar, { sitekey: lugar.dataset.sitekey });
  } catch (err) {
    lugar.dataset.pronto = '';
    d.querySelector('.aviso').textContent = `Não deu para abrir a denúncia agora: ${err.message}.`;
  }
}, true);

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('form[data-denunciar]');
  if (!form) return;
  e.preventDefault();
  const aviso = form.querySelector('.aviso');
  const botao = form.querySelector('button');
  const lugar = form.querySelector('.anti-robo');
  const token = form.querySelector('[name="cf-turnstile-response"]');
  botao.disabled = true;
  aviso.classList.remove('erro');
  aviso.textContent = 'Enviando…';
  try {
    const r = await fetch(`/api/modelos/${encodeURIComponent(form.dataset.denunciar)}/denunciar`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ motivo: form.motivo.value, turnstile: token ? token.value : '' }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || 'não deu');
    aviso.textContent = 'Denúncia enviada. Obrigado: o modelo vai ser revisado.';
  } catch (err) {
    aviso.classList.add('erro');
    aviso.textContent = `Não enviei: ${err.message}`;
    botao.disabled = false;
    if (window.turnstile && lugar && lugar.dataset.widget) window.turnstile.reset(lugar.dataset.widget); // o token vale uma vez só
  }
});
