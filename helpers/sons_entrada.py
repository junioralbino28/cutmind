#!/usr/bin/env python3
"""Som na entrada dos textos grandes e das fotos, como camadas de áudio editáveis.

Numa edição real (01/11) os textos entraram mudos e cada som foi posto à mão. O volume também: a 55-60% os sons ficavam de 3 a
16 dB abaixo do pico da voz e sumiam. Aqui cada som é medido contra a fala do próprio trecho: o pico do som fica MARGEM_DB
abaixo do pico da voz numa janela de 0,5 s em volta da entrada.

    uv run python -X utf8 helpers/sons_entrada.py <edit> [--texto v-whoosh] [--foto g-camera]
    uv run python -X utf8 helpers/sons_entrada.py <edit> --remover

Os sons ficam numa faixa de áudio própria do `camadas.json` (FAIXA), e rodar de novo a refaz. Depois disso a pessoa move, apaga
e muda o volume de cada um no editor, como qualquer camada. Só o som da faixa que a pessoa não mexeu volta a ser medido.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import camadas as cam  # mesma pasta deste arquivo
import efeitos_sonoros as es  # mesma pasta deste arquivo

FAIXA = "sons-entrada"
SOM_TEXTO = "v-whoosh"  # o que o usuário escolheu de ouvido, numa edição real, entre gravados e gerados
RESERVA_TEXTO = "g-whoosh-rapido"  # sem internet para o viral, ou para quem vai usar em anúncio
SOM_FOTO = "g-camera"
RESERVA_FOTO = "clique"
MARGEM_DB = 4.0  # o nível que ele aprovou de ouvido: aparece por cima da fala sem competir com ela
JANELA = 0.25  # s para cada lado da entrada
MIN_ENTRE = 0.25  # dois sons a menos que isso viram um
SEM_VOZ_DB = -45.0
SR = 16000

# os gráficos: o instante de entrada de cada um; os de digitar já têm o som de tecla, o `pula` é um som só
_NO_AT = {"grande", "danca", "glitch"}
_NO_START = {"contador", "marca", "nome", "objecao", "selo", "celular", "progresso", "ajuste", "pula", "lista", "chat"}
_POR_ITEM = {"palavras", "partes", "botoes", "emoji"}


class SonsInvalidos(ValueError):
    pass


def _ler(p: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    if r.returncode != 0:
        raise SonsInvalidos(f"não deu para ler o áudio de {p.name}")
    return np.frombuffer(r.stdout, dtype=np.float32)


def _db(x: float) -> float:
    return 20 * float(np.log10(max(x, 1e-9)))


def entradas(camadas: dict, ed: dict) -> list[tuple[float, str]]:
    """(segundo do corte, 'texto' ou 'foto'), em ordem, sem dois colados. Texto pequeno não entra (o mesmo limite de "texto em
    destaque" que esconde a legenda); vídeo por cima também não, porque costuma trazer o próprio som."""
    ev: list[tuple[float, str]] = []
    for f in camadas.get("faixas") or []:
        if f.get("tipo") == "texto" and not f.get("oculto"):
            ev += [(float(it["inicio"]), "texto") for it in f["itens"] if float((it.get("estilo") or {}).get("tamanho", 1.0)) >= cam.TAMANHO_DESTAQUE]
        elif f.get("tipo") == "imagem" and not f.get("oculto"):
            ev += [(float(it["inicio"]), "foto") for it in f["itens"] if not cam.eh_video(it["arquivo"])]
    for g in ed.get("graficos") or []:
        if not isinstance(g, dict) or g.get("desligada"):
            continue
        t = g.get("tipo")
        if t in _NO_AT:
            ev.append((float(g.get("at", g["start"])), "texto"))
        elif t in _NO_START:
            ev.append((float(g["start"]), "texto"))
        elif t in _POR_ITEM:
            ev += [(float(it["at"]), "texto") for it in g.get("itens") or [] if isinstance(it, dict) and "at" in it]
    out: list[tuple[float, str]] = []
    for t, k in sorted(ev):
        if not out or t - out[-1][0] >= MIN_ENTRE:
            out.append((t, k))
    return out


def volume_contra_a_voz(voz: np.ndarray, t: float, pico_som_db: float, padrao: float) -> float:
    """O volume da camada que deixa o pico do som MARGEM_DB abaixo do pico da voz em volta de `t`. Sem fala por perto, o do catálogo."""
    a, b = max(0, int((t - JANELA) * SR)), int((t + JANELA) * SR)
    trecho = voz[a:b]
    pico = _db(float(np.abs(trecho).max())) if trecho.size else -120.0
    if pico < SEM_VOZ_DB:
        return padrao
    return round(float(np.clip(10 ** ((pico - MARGEM_DB - pico_som_db) / 20), 0.05, 2.0)), 3)


def _do_catalogo(sid: str) -> dict:
    x = next((s for s in es.todos() if s["id"] == sid), None)
    if x is None:
        raise SonsInvalidos(f"o som `{sid}` não existe; os que existem: {', '.join(s['id'] for s in es.todos())}")
    return x


def _preparar(edit: Path, sid: str, reserva: str | None) -> tuple[dict, Path]:
    """O som copiado para midia/. O viral desce da internet: sem ela, vale a reserva, que o editor mostra pelo nome."""
    try:
        return _do_catalogo(sid), es.usar(edit, sid)
    except es.pk.PacoteErro:
        if reserva is None:
            raise
    return _do_catalogo(reserva), es.usar(edit, reserva)


def aplicar(edit: Path, som_texto: str = SOM_TEXTO, som_foto: str = SOM_FOTO) -> dict:
    """Refaz a faixa de sons. Devolve {sons, textos, fotos}; grava o camadas.json só no fim."""
    edit = Path(edit)
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    ed = json.loads((edit / state["editData"]).read_text(encoding="utf-8")) if state.get("editData") and (edit / state["editData"]).is_file() else {}
    camadas = cam.load(edit / "camadas.json")
    ev = entradas(camadas, ed)
    camadas["faixas"] = [f for f in camadas["faixas"] if f.get("id") != FAIXA]
    if not ev:
        cam.save(edit / "camadas.json", camadas)
        return {"sons": 0, "textos": 0, "fotos": 0}
    voz = _ler(edit / (state.get("video") or "cut.mp4"))
    dur = len(voz) / SR
    prontos: dict[str, tuple[dict, Path, float]] = {}

    def som(tipo: str) -> tuple[dict, Path, float]:
        if tipo not in prontos:
            info, arq = _preparar(edit, *((som_foto, RESERVA_FOTO if som_foto == SOM_FOTO else None) if tipo == "foto" else (som_texto, RESERVA_TEXTO if som_texto == SOM_TEXTO else None)))
            prontos[tipo] = (info, arq, _db(float(np.abs(_ler(arq)).max())))
        return prontos[tipo]

    itens = []
    for n, (t, tipo) in enumerate(ev):
        if t >= dur:
            continue
        info, arq, pico = som(tipo)
        ini = max(0.0, t - float(info["golpe"]))
        itens.append({"id": f"se-{n}", "arquivo": f"midia/{arq.name}", "inicio": round(ini, 3), "corte": 0.0,
                      "duracao": round(min(float(info["duracao"]), dur - ini), 3),
                      "volume": volume_contra_a_voz(voz, t, pico, float(info["volume"])), "melhorar": False})
    camadas["faixas"].append({"id": FAIXA, "tipo": "audio", "mudo": False, "travado": False, "itens": itens})
    cam.save(edit / "camadas.json", cam.normalize(camadas))
    return {"sons": len(itens), "textos": sum(1 for _, k in ev if k == "texto"), "fotos": sum(1 for _, k in ev if k == "foto")}


def remover(edit: Path) -> None:
    camadas = cam.load(Path(edit) / "camadas.json")
    camadas["faixas"] = [f for f in camadas["faixas"] if f.get("id") != FAIXA]
    cam.save(Path(edit) / "camadas.json", camadas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--texto", default=SOM_TEXTO)
    ap.add_argument("--foto", default=SOM_FOTO)
    ap.add_argument("--remover", action="store_true")
    a = ap.parse_args()
    if a.remover:
        remover(a.edit)
        print("faixa de sons de entrada removida")
        return 0
    try:
        r = aplicar(a.edit, a.texto, a.foto)
    except (SonsInvalidos, es.pk.PacoteErro) as e:
        print(f"ERRO {e}", file=sys.stderr)
        return 1
    print(f"{r['sons']} sons: {r['textos']} em textos, {r['fotos']} em fotos. Ficam na faixa `{FAIXA}` do camadas.json: refaça o som final (mixar_final.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
