#!/usr/bin/env python3
"""Confere os gráficos animados (`graficos[]` do edit-data.json) antes do render.

O template desenha cada tipo (assets/shortform/src/graficos/), com as cores do Estilo e os lugares
padrão dentro da zona segura; o referências/graficos.md diz quando usar cada um. Aqui fica o que o
agente erra sem perceber: um campo que falta, um instante fora da janela (o gráfico some antes da
batida), um ícone que o template não tem e uma imagem que não está no public/ (o render cai).

    uv run python -X utf8 helpers/graficos.py <edit> [--edit-data <caminho>]

Sem --edit-data, usa o `editData` do state.json. Sai com 1 se houver erro, e nada é gravado.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from remapear import INSTANTE  # mesma pasta deste arquivo: os instantes que o re-corte leva

KIT_GRAFICOS = Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "graficos"

# os tipos do template (TIPOS em src/graficos/index.tsx; tests/test_graficos.py confere os dois) e os
# campos de cada um que não podem faltar
TIPOS = {
    "palavras": ("itens",),
    "botoes": ("itens",),
    "celular": ("src",),
    "objecao": ("usuario", "texto"),
    "grande": ("t",),
    "lista": ("titulo", "itens"),
    "selo": ("src",),
    "ajuste": (),
    "progresso": ("titulo", "fimAt", "fim"),
    "comenta": ("texto", "digitaAt", "digitaFimAt"),
    "pula": ("itens",),
    "partes": ("itens",),
    "danca": ("t",),
    "glitch": ("t",),
    "marca": ("texto", "marcaAt", "marcaFimAt"),
    "contador": ("valor", "fimAt"),
    "nome": ("nome",),
    "chat": ("itens",),
    "maquina": ("texto", "digitaAt", "digitaFimAt"),
    "prompt": ("texto", "digitaAt", "digitaFimAt"),
    "emoji": ("itens",),
}
ICONES =("rec", "ia", "corte", "cenario", "trilha", "cc", "check", "play", "mic", "texto", "raio", "estrela")
IMAGENS = ("src",)  # os campos que são um arquivo do public/

# o que um gráfico criado no painel do editor pode trazer (o tipo em src/graficos/index.tsx)
_COMUNS = ("tipo", "start", "end", "y", "desligada")
CAMPOS = {
    "palavras": ("itens", "tamanho", "cor"),
    "botoes": ("itens",),
    "celular": ("src", "x", "w", "rot"),
    "objecao": ("usuario", "texto", "quando", "cinza"),
    "grande": ("t", "at", "tamanho", "cor", "contorno", "riscoAt", "sub", "troca", "trocaAt"),
    "lista": ("titulo", "itens", "icone"),
    "selo": ("src", "fundo"),
    "ajuste": ("titulo", "src"),
    "progresso": ("titulo", "fimAt", "fim"),
    "comenta": ("texto", "digitaAt", "digitaFimAt", "dmAt", "dm", "placeholder", "publicar", "seta"),
    "pula": ("itens", "tamanho"),
    "partes": ("itens", "tamanho"),
    "danca": ("t", "sub", "at", "tamanho"),
    "glitch": ("t", "at", "tamanho"),
    "marca": ("texto", "frase", "marcaAt", "marcaFimAt", "cor"),
    "contador": ("valor", "inicio", "casas", "prefixo", "sufixo", "rotulo", "fimAt", "tamanho", "local"),
    "nome": ("nome", "cargo"),
    "chat": ("itens",),
    "maquina": ("texto", "digitaAt", "digitaFimAt", "som"),
    "prompt": ("texto", "titulo", "digitaAt", "digitaFimAt", "som"),
    "emoji": ("itens", "tamanho"),
}
_CAMPOS_ITEM = ("t", "icone", "at", "ate", "cor", "contorno", "selecao", "pilula", "lado", "x", "y")
_TEXTO_MAX = 200
_ITENS_MAX = 12


class GraficosInvalidos(ValueError):
    pass


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _instantes(d: dict, onde: str = ""):
    """(caminho, valor) de cada instante do item, nas listas e objetos de dentro também."""
    for k, v in d.items():
        if INSTANTE.match(k):
            yield f"{onde}{k}", v
        elif isinstance(v, dict):
            yield from _instantes(v, f"{onde}{k}.")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                if isinstance(x, dict):
                    yield from _instantes(x, f"{onde}{k}[{i}].")


def validar(g) -> list[str]:
    """O que está errado no item, uma frase por problema (vazio = pode seguir)."""
    if not isinstance(g, dict):
        return ["o item não é um objeto"]
    tipo = g.get("tipo")
    if tipo not in TIPOS:
        return [f"tipo `{tipo}` não existe no template; os que existem: {', '.join(TIPOS)}"]
    erros = []
    ini, fim = g.get("start"), g.get("end")
    janela = _num(ini) and _num(fim) and ini >= 0 and fim - ini >= 0.2
    if not janela:
        erros.append("`start` e `end` são segundos do corte, com `end` pelo menos 0,2 s depois de `start`")
    erros += [f"falta `{k}`" for k in TIPOS[tipo] if g.get(k) in (None, "", [])]
    if "itens" in TIPOS[tipo] and isinstance(g.get("itens"), list):
        for i, it in enumerate(g["itens"]):
            if not isinstance(it, dict) or not _num(it.get("at")):
                erros.append(f"`itens[{i}]` precisa de `at` (segundo do corte)")
            elif tipo == "botoes" and it.get("icone") not in (None, *ICONES):
                erros.append(f"`itens[{i}].icone` `{it['icone']}` não existe; os que existem: {', '.join(ICONES)}")
    if g.get("y") is not None and not (_num(g["y"]) and 0 <= g["y"] <= 1920):
        erros.append("`y` é px do quadro 1080x1920")
    if tipo == "contador" and g.get("valor") is not None and not _num(g["valor"]):
        erros.append("`valor` é um número (é até onde o contador sobe)")
    if tipo == "grande" and bool(g.get("troca")) != (g.get("trocaAt") is not None):
        erros.append("`troca` e `trocaAt` andam juntos: a palavra nova e o instante da troca")
    if tipo == "lista" and g.get("icone") not in (None, "x", "check"):
        erros.append("`icone` da lista é `x` ou `check`")
    if tipo == "chat":
        for i, it in enumerate(g.get("itens") or []):
            if isinstance(it, dict) and it.get("lado") not in (None, "eu", "outro"):
                erros.append(f"`itens[{i}].lado` é `eu` ou `outro`")
    seta = g.get("seta")
    if seta is not None and not (isinstance(seta, dict) and _num(seta.get("x")) and _num(seta.get("y"))):
        erros.append("`seta` é {x, y}: a ponta, em px do quadro")
    if janela:
        erros += [f"`{k}` ({v}) fica fora da janela ({ini} a {fim})" for k, v in _instantes(g)
                  if not (_num(v) and ini <= v <= fim)]
    return erros


def conferir(edit_data: Path) -> list[str]:
    """Os erros de todos os gráficos do edit-data, com as imagens procuradas no public/ dele."""
    ed = json.loads(Path(edit_data).read_text(encoding="utf-8"))
    public = Path(edit_data).parent
    erros = []
    for i, g in enumerate(ed.get("graficos") or []):
        nome = f"graficos[{i}] ({g.get('tipo') if isinstance(g, dict) else '?'})"
        erros += [f"{nome}: {e}" for e in validar(g)]
        for k in IMAGENS if isinstance(g, dict) else ():
            if isinstance(g.get(k), str) and g[k] and not (public / g[k]).is_file():
                erros.append(f"{nome}: `{k}` {g[k]} não está em {public} (copie a imagem para lá)")
    return erros


def _textos(v) -> list[str]:
    """Todos os textos de dentro de um item, nas listas e objetos também."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _textos(x)]
    if isinstance(v, list):
        return [s for x in v for s in _textos(x)]
    return []


def imagem_do_projeto(raiz: Path, public: Path, src: object) -> bool:
    """A imagem é um arquivo do public/ ou da midia/ do projeto (nunca de fora deles)."""
    if not isinstance(src, str) or not src:
        return False
    for base, p in ((public, public / src), (raiz / "midia", raiz / src)):
        try:
            p = p.resolve()
        except OSError:
            return False
        if p.is_file() and p.is_relative_to(base.resolve()):
            return True
    return False


def conferir_do_editor(raiz: Path, public: Path, itens: object) -> None:
    """Os gráficos que o editor manda no Salvar: `nova` (criado no painel) ou `ref` com o `item` mudado, como o
    editdata_aplicar.py vai gravar. O Baixar desenha com eles como chegaram: o que está errado para aqui."""
    if not isinstance(itens, list):
        raise GraficosInvalidos("uma lista")
    for i, b in enumerate(itens):
        if not isinstance(b, dict):
            raise GraficosInvalidos(f"[{i}]: um objeto")
        g = b.get("item")
        if g is None:
            if b.get("nova"):
                raise GraficosInvalidos(f"[{i}]: um gráfico novo precisa do `item`")
            continue
        erros = validar(g)
        if erros:
            raise GraficosInvalidos(f"[{i}]: {'; '.join(erros)}")
        if b.get("nova"):
            fora = [k for k in g if k not in (*_COMUNS, *CAMPOS[g["tipo"]])]
            fora += [k for x in g.get("itens") or [] for k in x if k not in _CAMPOS_ITEM]
            if fora:
                raise GraficosInvalidos(f"[{i}]: o gráfico `{g['tipo']}` novo não leva {', '.join(sorted(set(fora)))}")
        if len(g.get("itens") or []) > _ITENS_MAX:
            raise GraficosInvalidos(f"[{i}]: até {_ITENS_MAX} itens num gráfico")
        if any(len(s) > _TEXTO_MAX for s in _textos(g)):
            raise GraficosInvalidos(f"[{i}]: os textos são frases de até {_TEXTO_MAX} letras")
        for k in IMAGENS:
            if g.get(k) and not imagem_do_projeto(raiz, public, g[k]):
                raise GraficosInvalidos(f"[{i}]: a imagem não está no projeto ({g[k]})")


def levar_imagens(raiz: Path, public: Path, ed: dict) -> None:
    """A imagem escolhida na midia/ vai para o public/, onde o template a procura (`src` relativo a ele)."""
    for g in ed.get("graficos") or []:
        for k in IMAGENS if isinstance(g, dict) else ():
            src = g.get(k)
            if not (isinstance(src, str) and src) or (public / src).is_file():
                continue
            origem = (raiz / src).resolve()
            if origem.is_file() and origem.is_relative_to((raiz / "midia").resolve()):
                (public / src).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origem, public / src)


def template_falta(remotion: Path) -> list[str]:
    """O que o template do projeto não tem para desenhar os gráficos (vazio = desenha). Um projeto
    montado com um kit anterior não tem `src/graficos/` e o render sairia sem eles, sem erro nenhum."""
    src = Path(remotion) / "src"
    if not (src / "Main.tsx").is_file():
        return []
    texto = lambda q: q.read_bytes().replace(b"\r\n", b"\n")  # noqa: E731 (o fim de linha não conta)
    falta = [f"src/graficos/{q.name}" for q in sorted(KIT_GRAFICOS.iterdir()) if q.is_file()
             and (not (src / "graficos" / q.name).is_file() or texto(src / "graficos" / q.name) != texto(q))]
    if "<Graficos />" not in (src / "Main.tsx").read_text(encoding="utf-8"):
        falta.append("src/Main.tsx")
    return falta


def desenha_por_conta(remotion: Path) -> bool:
    """O `CustomGraphics.tsx` do projeto já desenha `graficos` sozinho (feito antes de o kit ter os
    tipos): com o template novo, cada gráfico sairia duas vezes."""
    cg = Path(remotion) / "src" / "CustomGraphics.tsx"
    return cg.is_file() and "graficos" in cg.read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--edit-data", type=Path)
    a = ap.parse_args()
    if a.edit_data:
        caminho = a.edit_data
    else:
        state = json.loads((a.edit / "state.json").read_text(encoding="utf-8"))
        if not state.get("editData"):
            raise SystemExit("state.json sem editData: passe --edit-data")
        caminho = a.edit / state["editData"]
    erros = conferir(caminho)
    remotion = caminho.parent.parent
    falta = template_falta(remotion)
    if falta:
        erros.append(f"o template do projeto não desenha os gráficos ({', '.join(falta)}): rode "
                     f"`atualizar_template.py {a.edit}` (troca só o código do template) e depois este de novo")
    if desenha_por_conta(remotion):
        erros.append("o src/CustomGraphics.tsx do projeto já desenha `graficos` por conta própria: com o "
                     "template do kit cada gráfico sairia duas vezes. Tire de lá a montagem dos gráficos")
    n = len(json.loads(caminho.read_text(encoding="utf-8")).get("graficos") or [])
    for e in erros:
        print(f"  ERRO {e}", file=sys.stderr)
    print(f"{n} gráfico(s) no edit-data.json, {'nenhum erro' if not erros else f'{len(erros)} erro(s)'}")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
