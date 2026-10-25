// A grade e a página de um modelo: o post entra quando a pessoa toca (na grade, para não carregar
// dezenas de players de uma vez) e a denúncia vai por um pedido ao próprio mural.
document.addEventListener('click', (e) => {
  const b = e.target.closest('.post-tocar');
  if (!b) return;
  const caixa = document.createElement('div');
  caixa.className = `post ${b.dataset.plataforma || ''}`;
  const f = document.createElement('iframe');
  f.src = b.dataset.embed;
  f.loading = 'lazy';
  f.allowFullscreen = true;
  f.title = 'O post';
  caixa.appendChild(f);
  b.replaceWith(caixa);
});

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('form[data-denunciar]');
  if (!form) return;
  e.preventDefault();
  const aviso = form.querySelector('.aviso');
  const botao = form.querySelector('button');
  botao.disabled = true;
  aviso.classList.remove('erro');
  aviso.textContent = 'Enviando…';
  try {
    const r = await fetch(`/api/modelos/${encodeURIComponent(form.dataset.denunciar)}/denunciar`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ motivo: form.motivo.value }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || 'não deu');
    aviso.textContent = 'Denúncia enviada. Obrigado: o modelo vai ser revisado.';
  } catch (err) {
    aviso.classList.add('erro');
    aviso.textContent = `Não enviei: ${err.message}`;
    botao.disabled = false;
  }
});
