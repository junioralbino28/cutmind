// O painel do dono: tirar, devolver e editar, por pedidos ao próprio mural (admin.js do Worker
// confere o Access em cada um).
const aviso = document.querySelector('.admin .aviso');

for (const t of document.querySelectorAll('.admin time[datetime]')) {
  t.textContent = new Date(t.dateTime).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

async function acao(id, corpo) {
  const r = await fetch('/admin/acao', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, ...corpo }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erro || `erro ${r.status}`);
  return d;
}

document.addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-acao]');
  if (!b) return;
  const tr = b.closest('tr');
  const id = tr.dataset.id;
  try {
    if (b.dataset.acao === 'editar') {
      const nome = prompt('Nome do modelo', tr.dataset.nome);
      if (nome == null) return;
      const autor = prompt('@ de quem publicou (vazio para nenhum)', tr.dataset.autor);
      if (autor == null) return;
      await acao(id, { acao: 'editar', nome, autor });
    } else {
      await acao(id, { acao: b.dataset.acao });
    }
    location.reload();
  } catch (err) {
    aviso.textContent = `Não deu: ${err.message}`;
  }
});
