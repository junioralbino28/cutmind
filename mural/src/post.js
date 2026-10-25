// O post em que a pessoa usou o modelo e o @ dela. Só links de post do Instagram, do TikTok e do
// YouTube, em formato conhecido: o mural monta ele mesmo o endereço do post e o do player embutido a
// partir do código do post, e nunca devolve o texto colado (nada de link para outro site).

export class PostInvalido extends Error {}

const CODIGO_IG = /^[A-Za-z0-9_-]{5,40}$/;
const ID_TIKTOK = /^\d{8,25}$/;
const ID_YOUTUBE = /^[A-Za-z0-9_-]{11}$/;
const HANDLE = /^[A-Za-z0-9._]{1,30}$/;

export function lerPost(texto) {
  if (texto == null || texto === '') return null;
  if (typeof texto !== 'string' || texto.length > 500) throw new PostInvalido('o link do post');
  let u;
  try {
    u = new URL(texto.trim());
  } catch {
    throw new PostInvalido('o link do post não é um endereço');
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') throw new PostInvalido('o link do post não é um endereço');
  const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, '');
  const partes = u.pathname.split('/').filter(Boolean);
  if (host === 'instagram.com') {
    // /p/<código>, /reel/<código>, /reels/<código>, e os mesmos depois do nome da conta
    const i = partes.findIndex((p) => p === 'p' || p === 'reel' || p === 'reels');
    const codigo = i >= 0 ? partes[i + 1] : null;
    if (!codigo || !CODIGO_IG.test(codigo)) throw new PostInvalido('link do Instagram: o de um post ou de um reel');
    const tipo = partes[i] === 'p' ? 'p' : 'reel';
    return { plataforma: 'instagram', url: `https://www.instagram.com/${tipo}/${codigo}/`,
      embed: `https://www.instagram.com/${tipo}/${codigo}/embed/` };
  }
  if (host === 'tiktok.com' || host === 'vm.tiktok.com' || host === 'vt.tiktok.com') {
    // /@conta/video/<id>; o link curto (vm.tiktok.com) não diz o vídeo: pede o link inteiro
    const i = host === 'tiktok.com' ? partes.indexOf('video') : -1;
    const id = i === 1 ? partes[2] : null;
    const conta = partes[0] || '';
    if (!id || !ID_TIKTOK.test(id) || !conta.startsWith('@') || !HANDLE.test(conta.slice(1))) {
      throw new PostInvalido('link do TikTok: o link inteiro do vídeo (tiktok.com/@conta/video/...)');
    }
    return { plataforma: 'tiktok', url: `https://www.tiktok.com/${conta}/video/${id}`,
      embed: `https://www.tiktok.com/embed/v2/${id}` };
  }
  if (host === 'youtube.com' || host === 'youtu.be') {
    let id = null;
    if (host === 'youtu.be') id = partes[0];
    else if (partes[0] === 'shorts') id = partes[1];
    else if (partes[0] === 'watch') id = u.searchParams.get('v');
    if (!id || !ID_YOUTUBE.test(id)) throw new PostInvalido('link do YouTube: o de um Short ou de um vídeo');
    return { plataforma: 'youtube', url: `https://www.youtube.com/shorts/${id}`,
      embed: `https://www.youtube-nocookie.com/embed/${id}` };
  }
  throw new PostInvalido('o post: Instagram, TikTok ou YouTube');
}

export function lerAutor(texto) {
  if (texto == null || texto === '') return null;
  if (typeof texto !== 'string') throw new PostInvalido('o @');
  const h = texto.trim().replace(/^@/, '');
  if (!HANDLE.test(h)) throw new PostInvalido('o @: letras, números, ponto e sublinhado, até 30');
  return h;
}

// o perfil, na plataforma do post (sem post, o Instagram)
export function perfil(autor, plataforma) {
  if (!autor) return null;
  if (plataforma === 'tiktok') return `https://www.tiktok.com/@${autor}`;
  if (plataforma === 'youtube') return `https://www.youtube.com/@${autor}`;
  return `https://www.instagram.com/${autor}/`;
}

// o player do post guardado (a página monta de novo a partir do link canônico)
export function embedDo(post) {
  try {
    return post ? lerPost(post).embed : null;
  } catch {
    return null;
  }
}
