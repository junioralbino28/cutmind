#!/usr/bin/env python3
"""A ponte do editor com o mural de modelos (a pasta `mural/` deste repositório): a lista da
comunidade, pegar um modelo de lá para os seus e o link para publicar um modelo seu.

O editor fala só com o servidor local; quem fala com o mural é este módulo, no endereço da variável
`CUTMIND_MURAL` (sem ela, o mural fica de fora do editor). O que vem do mural é de qualquer pessoa:
cada campo é conferido de novo, e o modelo passa pela mesma conferência dos modelos da pessoa
(montagens.normalize). Publicar nunca passa por aqui: o link abre a página de publicar do mural,
com o modelo no fragmento (#m=), e a pessoa confirma lá.

    python mural.py lista
    python mural.py pegar <código>
    python mural.py link <id do modelo>
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import modelos  # mesma pasta deste arquivo
import montagem as mt  # mesma pasta deste arquivo
import montagens as mg  # mesma pasta deste arquivo

TEMPO = 8  # segundos por pedido ao mural
MAX_RESPOSTA = 512_000
POR_PAGINA = 24
CODIGO = re.compile(r"[A-Za-z0-9_-]{12}")
CURSOR = re.compile(r"\d{1,12}\.[A-Za-z0-9_-]{12}")
HANDLE = re.compile(r"[A-Za-z0-9._]{1,30}")
# os posts que o mural guarda, já na forma que ele remonta (mural/src/post.js)
POST = {
    "instagram": re.compile(r"https://www\.instagram\.com/(p|reel)/[A-Za-z0-9_-]{5,40}/"),
    "tiktok": re.compile(r"https://www\.tiktok\.com/@[A-Za-z0-9._]{1,30}/video/\d{8,25}"),
    "youtube": re.compile(r"https://www\.youtube\.com/shorts/[A-Za-z0-9_-]{11}"),
}


class MuralIndisponivel(RuntimeError):
    """Sem endereço, fora do ar ou com uma resposta que não é a do mural."""


class MuralRecusou(ValueError):
    """O pedido não vale: código torto, modelo que não existe, modelo do kit."""


def endereco() -> str | None:
    v = (os.environ.get("CUTMIND_MURAL") or "").strip().rstrip("/")
    u = urllib.parse.urlsplit(v)
    if u.scheme not in ("http", "https") or not u.netloc or u.query or u.fragment:
        return None
    return v


def _pedir(caminho: str) -> dict:
    base = endereco()
    if not base:
        raise MuralIndisponivel("o mural não está ligado neste kit (falta CUTMIND_MURAL)")
    pedido = urllib.request.Request(base + caminho, headers={"Accept": "application/json", "User-Agent": "CutMind"})
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO) as r:
            dados = r.read(MAX_RESPOSTA + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise MuralRecusou("esse modelo não está no mural (pode ter sido tirado)") from None
        raise MuralIndisponivel(f"o mural respondeu {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise MuralIndisponivel(f"não consegui falar com o mural ({getattr(e, 'reason', e)})") from None
    if len(dados) > MAX_RESPOSTA:
        raise MuralIndisponivel("o mural mandou uma resposta grande demais")
    try:
        d = json.loads(dados)
    except ValueError:
        raise MuralIndisponivel("o mural respondeu algo que não é JSON") from None
    if not isinstance(d, dict):
        raise MuralIndisponivel("o mural respondeu algo inesperado")
    return d


def _inteiro(v: object, lo: int, hi: int) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else None


def _perfil(autor: str, plataforma: str | None) -> str:
    if plataforma == "tiktok":
        return f"https://www.tiktok.com/@{autor}"
    if plataforma == "youtube":
        return f"https://www.youtube.com/@{autor}"
    return f"https://www.instagram.com/{autor}/"


def cartao(x: object) -> dict | None:
    """Um item da lista do mural no formato do cartão do painel (montagens.resumo), refeito campo a
    campo; o que não fecha some da lista em vez de chegar torto ao editor."""
    if not isinstance(x, dict) or not isinstance(x.get("resumo"), dict):
        return None
    ident, nome, r = x.get("id"), x.get("nome"), x["resumo"]
    if not (isinstance(ident, str) and CODIGO.fullmatch(ident) and isinstance(nome, str) and 0 < len(nome) <= 60):
        return None
    ritmo = r.get("ritmo")
    if not isinstance(ritmo, list) or not 0 < len(ritmo) <= 400 or any(_inteiro(b, 1, 64) is None for b in ritmo):
        return None
    textos = [{"nome": t["nome"][:40] if isinstance(t.get("nome"), str) else "", "vaga": t["vaga"],
               "batidas": _inteiro(t.get("batidas"), 1, 64 * 400)}
              for t in (r.get("textos") if isinstance(r.get("textos"), list) else [])[:20]
              if isinstance(t, dict) and _inteiro(t.get("vaga"), 1, len(ritmo))]
    plataforma = x.get("plataforma") if x.get("plataforma") in POST else None
    post = x.get("post") if plataforma and isinstance(x.get("post"), str) and POST[plataforma].fullmatch(x["post"]) else None
    autor = x.get("autor") if isinstance(x.get("autor"), str) and HANDLE.fullmatch(x["autor"]) else None
    return {"id": ident, "nome": nome, "doMural": True,
            "autor": autor, "perfil": _perfil(autor, plataforma if post else None) if autor else None,
            "post": post, "plataforma": plataforma if post else None,
            "lugares": len(ritmo), "batidas": sum(ritmo), "ritmo": ritmo,
            "drop_na_vaga": _inteiro(r.get("drop_na_vaga"), 1, len(ritmo)),
            "formato": r.get("formato") if r.get("formato") in mt.FORMATOS else mt.FORMATO_PADRAO,
            "textos": textos, "transicoes": _inteiro(r.get("transicoes"), 0, 400) or 0}


def lista(antes: str | None = None) -> dict:
    """Uma página da grade do mural (os mais novos primeiro); `seguinte` pede a próxima."""
    q = f"?n={POR_PAGINA}" + (f"&antes={antes}" if isinstance(antes, str) and CURSOR.fullmatch(antes) else "")
    d = _pedir(f"/api/modelos{q}")
    itens = d.get("modelos")
    if not isinstance(itens, list):
        raise MuralIndisponivel("o mural respondeu algo inesperado")
    seguinte = d.get("seguinte")
    return {"modelos": [c for c in map(cartao, itens[:48]) if c],
            "seguinte": seguinte if isinstance(seguinte, str) and CURSOR.fullmatch(seguinte) else None}


_SEM = ("id", "nome", "criado", "doKit")


def _mesmo(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k not in _SEM} == {k: v for k, v in b.items() if k not in _SEM}


def pegar(codigo: object) -> dict:
    """Traz um modelo do mural para os da pessoa e devolve o modelo gravado. Um nome que já é de
    outro modelo (dela ou do kit) ganha um número: pegar nunca troca um modelo que já existe."""
    if not isinstance(codigo, str) or not CODIGO.fullmatch(codigo):
        raise MuralRecusou("código de modelo inválido")
    m = _pedir(f"/api/modelos/{codigo}").get("modelo")
    if not isinstance(m, dict):
        raise MuralIndisponivel("o mural respondeu algo inesperado")
    try:
        base = mg.normalize(m)
    except mg.MontagemInvalida:
        # o nome sem letra nem número (só emoji, outro alfabeto) não vira id: o modelo leva o código
        base = mg.normalize({**m, "nome": f"Modelo {codigo}"})
    nome, n = base["nome"], 2
    while (outro := mg.obter(modelos.id_do_nome(nome))) is not None:
        if _mesmo(outro, base):
            return outro
        sufixo = f" ({n})"
        nome, n = base["nome"][: modelos.NOME_MAX - len(sufixo)] + sufixo, n + 1
    return mg.salvar({**base, "nome": nome, "criado": time.time()})


def link_publicar(mid: object) -> str:
    """O endereço da página de publicar do mural com um modelo da pessoa no fragmento: o
    fragmento não vai a servidor nenhum, e o modelo só sai quando ela aperta Publicar lá."""
    base = endereco()
    if not base:
        raise MuralIndisponivel("o mural não está ligado neste kit (falta CUTMIND_MURAL)")
    m = mg.obter(mid)
    if not m:
        raise MuralRecusou("modelo não encontrado")
    if m.get("doKit"):
        raise MuralRecusou("os modelos que vêm com o kit já estão no kit de todo mundo")
    dados = {k: v for k, v in m.items() if k not in ("id", "criado", "doKit")}
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{base}/publicar#m={base64.urlsafe_b64encode(texto).decode('ascii').rstrip('=')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lista").add_argument("--antes")
    sub.add_parser("pegar").add_argument("codigo")
    sub.add_parser("link").add_argument("id")
    a = ap.parse_args()
    try:
        if a.cmd == "lista":
            d = lista(a.antes)
            for c in d["modelos"]:
                print(f"{c['id']}  {c['nome']}  · {c['lugares']} lugares, {c['batidas']} batidas, {c['formato']}"
                      + (f"  @{c['autor']}" if c["autor"] else ""))
            if d["seguinte"]:
                print(f"(mais: --antes {d['seguinte']})")
        elif a.cmd == "pegar":
            m = pegar(a.codigo)
            print(f"nos seus modelos: {m['id']}  {m['nome']}")
        else:
            print(link_publicar(a.id))
    except (MuralIndisponivel, MuralRecusou, mg.MontagemInvalida) as e:
        print(f"não deu: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
