"""Decide se o Baixar precisa desenhar o vídeo inteiro de novo, ou só o trecho que mudou.

Num Reels de 3 min, mover um mural levou 6,6 min pelo render_janelas.py + mixar_final.py, contra ~35 min do
vídeo inteiro (edição real de 01/11), e mudar só o volume de um som nem precisa desenhar nada. Depois de
cada render fica uma foto do que ele desenhou (`out/render.dados.json`): o edit-data, os arquivos do
public/ e o template. No Baixar seguinte, `o_que_mudou` compara com a foto e devolve:

- `None`: render inteiro. É a resposta de toda dúvida: sem foto, render mexido, arquivo ou template diferente,
  qualquer campo fora das listas com tempo (legenda, gancho, câmera, enquadre), ordem das camadas mudada, item
  sem janela conhecida, ou trecho grande demais para valer a pena;
- `[]`: a imagem não mudou, o render fica como está;
- `[(início, fim), ...]`: em segundos do corte, as janelas a refazer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOTO = "render.dados.json"
# as listas em que cada item só aparece na própria janela
JANELADOS = ("cenas", "graficos", "textos", "inserts", "behind", "splitInserts", "numeros", "atras")
SO_SOM = ("soundtrack",)  # entra no mixar_final, a imagem não depende dele
SONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
MARGEM = 0.25  # s de cada lado: o que entra e sai na borda (o render_janelas ainda põe 2 quadros de folga)
LIMITE = 0.6  # acima desta fração do vídeo, o render inteiro: a emenda recodifica a imagem toda de qualquer jeito


def _marca(p: Path) -> list[int]:
    st = p.stat()
    return [st.st_size, st.st_mtime_ns]


def _arquivos(public: Path) -> dict:
    """O que o template lê do public/: json por conteúdo (o helper regrava igual), o resto por tamanho e data."""
    out = {}
    for p in public.rglob("*"):
        rel = p.relative_to(public).as_posix()
        if not p.is_file() or rel == "edit-data.json" or rel.startswith("cenas/medidas") or p.suffix.lower() in SONS:
            continue
        out[rel] = hashlib.sha1(p.read_bytes()).hexdigest() if p.suffix.lower() == ".json" else _marca(p)
    return out


def _template(rem: Path) -> str:
    h = hashlib.sha1()
    for p in sorted([*(rem / "src").rglob("*"), rem / "package.json"]):
        if p.is_file():
            h.update(p.relative_to(rem).as_posix().encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def _foto(rem: Path) -> dict:
    return {"ed": json.loads((rem / "public" / "edit-data.json").read_text(encoding="utf-8")),
            "arquivos": _arquivos(rem / "public"), "template": _template(rem)}


def guardar(rem: Path) -> None:
    """Depois de um render que terminou: o que ele desenhou, preso ao arquivo que saiu."""
    rem = Path(rem)
    render = rem / "out" / "render.mp4"
    (rem / "out" / FOTO).write_text(json.dumps({**_foto(rem), "render": _marca(render)}, ensure_ascii=False), encoding="utf-8")


def _janela(it) -> tuple[float, float] | None:
    if not isinstance(it, dict) or not isinstance(it.get("start"), (int, float)):
        return None
    a = float(it["start"])
    if isinstance(it.get("end"), (int, float)):
        return a, float(it["end"])
    return (a, a + float(it["dur"])) if isinstance(it.get("dur"), (int, float)) else None


def _canon(it) -> str:
    return json.dumps(it, ensure_ascii=False, sort_keys=True)


def _da_lista(antes: list, depois: list) -> list[tuple[float, float]] | None:
    """As janelas dos itens que saíram, entraram ou mudaram; None se um deles não tem janela, ou se os que
    ficaram trocaram de ordem (a de cima passaria para baixo em toda a duração deles)."""
    a, b = [_canon(x) for x in antes], [_canon(x) for x in depois]
    fica_a, fica_b = list(a), list(b)
    for s in a:
        if s in fica_b:
            fica_b.remove(s)
    for s in b:
        if s in fica_a:
            fica_a.remove(s)
    # agora fica_a = só em `antes`, fica_b = só em `depois`
    so_a, so_b = list(fica_a), list(fica_b)
    resto_a, resto_b = list(a), list(b)
    for s in so_a:
        resto_a.remove(s)
    for s in so_b:
        resto_b.remove(s)
    if resto_a != resto_b:
        return None
    out = []
    for s in [*so_a, *so_b]:
        j = _janela(json.loads(s))
        if j is None:
            return None
        out.append(j)
    return out


def janelas(antes: dict, depois: dict, duracao: float | None = None) -> list[tuple[float, float]] | None:
    """O que mudou entre dois edit-data, como no topo deste arquivo."""
    out: list[tuple[float, float]] = []
    for k in {*antes, *depois}:
        va, vd = antes.get(k), depois.get(k)
        if k in SO_SOM or va == vd:
            continue
        if k in JANELADOS and isinstance(va or [], list) and isinstance(vd or [], list):
            r = _da_lista(va or [], vd or [])
            if r is None:
                return None
            out += r
        elif k == "captions" and isinstance(va, dict) and isinstance(vd, dict):
            # a legenda só muda por trechos quando o que mudou é onde ela some (o texto em destaque)
            if {x: y for x, y in va.items() if x != "ocultarTextos"} != {x: y for x, y in vd.items() if x != "ocultarTextos"}:
                return None
            r = _da_lista(va.get("ocultarTextos") or [], vd.get("ocultarTextos") or [])
            if r is None:
                return None
            out += r
        else:
            return None
    juntas: list[list[float]] = []
    for a, b in sorted((max(0.0, a - MARGEM), b + MARGEM) for a, b in out):
        if juntas and a <= juntas[-1][1]:
            juntas[-1][1] = max(juntas[-1][1], b)
        else:
            juntas.append([a, b])
    if duracao and sum(b - a for a, b in juntas) > LIMITE * duracao:
        return None
    return [(round(a, 3), round(b, 3)) for a, b in juntas]


def o_que_mudou(rem: Path) -> list[tuple[float, float]] | None:
    rem = Path(rem)
    render = rem / "out" / "render.mp4"
    try:
        velha = json.loads((rem / "out" / FOTO).read_text(encoding="utf-8"))
        if not render.is_file() or velha.get("render") != _marca(render):
            return None
        agora = _foto(rem)
    except (OSError, ValueError):
        return None
    if velha.get("template") != agora["template"]:
        return None
    # arquivo novo é de um item novo (e o item diz a janela); um que já existia e mudou vale para o vídeo inteiro
    va = velha.get("arquivos") or {}
    if any(k in va and va[k] != v for k, v in agora["arquivos"].items()):
        return None
    return janelas(velha.get("ed") or {}, agora["ed"], agora["ed"].get("durationSec"))
