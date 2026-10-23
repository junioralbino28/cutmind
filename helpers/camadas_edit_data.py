#!/usr/bin/env python3
"""Leva as camadas do editor (camadas.json) para o edit-data.json da Fase 2.

Imagens: cada imagem visível vira um item de `inserts[]` — o cartão arredondado da zona de
cima, o mesmo dos inserts do agente — com `"camada": <id do item>`. Só esses são mexidos: os
inserts do agente ficam como estão, e as camadas entram por último (ficam por cima, como no
editor). O arquivo é copiado para `public/midia/camada-<id>.<ext>`, um nome sem espaço nem
acento para o `staticFile` do Remotion.

Textos: cada texto visível vira um item de `textos[]` (src/CamadasTexto.tsx desenha), na
ordem das faixas. A lista inteira é deste helper. Um texto "atrás da pessoa" precisa do
recorte dela na janela dele, `public/pessoa-<id>-<quadro inicial>-<quadros>.mov`
(person_matte.py); um texto que "acompanha" precisa do rosto rastreado no corte,
`public/rastreio.json` (face_track.py). O helper faz os dois quando faltam ou ficaram velhos
(mudou a janela, mudou o cut.mp4) e apaga os recortes que não servem mais. Com
--sem-recorte, só avisa o comando, e o texto sai na frente até o recorte existir.

Rodar de novo refaz do zero: o que a pessoa excluiu ou escondeu sai do edit-data e a
cópia antiga é apagada.

    python camadas_edit_data.py <edit> [--edit-data <caminho do edit-data.json>] [--sem-recorte]

Sem --edit-data, usa o `editData` do state.json. Depois, renderize de novo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import camadas as cam  # mesma pasta deste arquivo

PREFIXO = "camada-"
RECORTE = "pessoa-"
RASTREIO = "rastreio.json"
HELPERS = Path(__file__).resolve().parent


def edit_data_do_projeto(edit: Path) -> Path:
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    if not state.get("editData"):
        raise SystemExit("state.json sem editData: passe --edit-data")
    return edit / state["editData"]


def _rodar(cmd: list[str]) -> bool:
    """Roda um helper do kit com o mesmo Python; a saída dele passa direto."""
    return subprocess.run(cmd).returncode == 0


def _linha(cmd: list[str]) -> str:
    """O comando para colar no terminal, com aspas onde o caminho tem espaço."""
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)


def _cmd_recorte(cut: Path, saida: Path, ini_f: int, n_f: int, fps: float) -> list[str]:
    # em quadros, para o quadro 0 do recorte cair no quadro em que o texto entra
    return [sys.executable, "-X", "utf8", str(HELPERS / "person_matte.py"), str(cut), "-o", str(saida),
            "--start", f"{ini_f / fps:.6f}", "--duration", f"{n_f / fps:.6f}"]


def _rastreio_serve(arq: Path, cut: Path) -> bool:
    try:
        r = json.loads(arq.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False
    if r.get("neutral") or not r.get("points"):
        return False
    return not cut.is_file() or arq.stat().st_mtime >= cut.stat().st_mtime


def _textos(edit: Path, public: Path, d: dict, camadas: dict, recortar: bool) -> tuple[list, list, list]:
    """Os textos do edit-data, os comandos que ficaram por rodar e os arquivos feitos agora."""
    fps = float(d.get("fps") or 30)
    cut = public / "cut.mp4"
    pendentes: list[str] = []
    feitos: list[str] = []
    # os recortes que valem agora, por id (um texto escondido guarda o dele), com a janela
    # em quadros no nome: mudou a janela, o recorte velho não serve mais
    validos: dict[str, tuple[str, int, int]] = {}
    for f in camadas["faixas"]:
        if f["tipo"] != "texto":
            continue
        for it in f["itens"]:
            if it["atras"]:
                ini_f = round(it["inicio"] * fps)
                n_f = max(1, round((it["inicio"] + it["duracao"]) * fps) - ini_f)
                validos[it["id"]] = (f"{RECORTE}{it['id']}-{ini_f}-{n_f}.mov", ini_f, n_f)
    nomes = {v[0] for v in validos.values()}
    for velho in public.glob(f"{RECORTE}*.mov"):  # só os recortes que este helper fez
        if velho.name not in nomes:
            velho.unlink()

    textos = []
    for it in cam.textos(camadas):
        t = {"id": it["id"], "texto": it["texto"], "start": it["inicio"],
             "end": round(it["inicio"] + it["duracao"], 3), "x": it["x"], "y": it["y"]}
        if it["estilo"]:
            t["estilo"] = it["estilo"]
        if it["curva"]:
            t["curva"] = it["curva"]
        if it["acompanhar"]:
            t["acompanhar"] = True
        if it["atras"]:
            nome, ini_f, n_f = validos[it["id"]]
            if not (public / nome).is_file():
                cmd = _cmd_recorte(cut, public / nome, ini_f, n_f, fps)
                if recortar and cut.is_file() and _rodar(cmd) and (public / nome).is_file():
                    feitos.append(nome)
                else:
                    pendentes.append(_linha(cmd))
            if (public / nome).is_file():
                t["matte"] = nome
        textos.append(t)

    rastreio = public / RASTREIO
    if any(t.get("acompanhar") for t in textos) and not _rastreio_serve(rastreio, cut):
        cmd = [sys.executable, "-X", "utf8", str(HELPERS / "face_track.py"), str(cut), "-o", str(rastreio)]
        if recortar and cut.is_file() and _rodar(cmd) and _rastreio_serve(rastreio, cut):
            feitos.append(RASTREIO)
        else:
            pendentes.append(_linha(cmd))
    if not rastreio.is_file():  # o template importa o arquivo: sem rastreio, ele fica neutro
        rastreio.write_text(json.dumps({"neutral": True, "points": []}), encoding="utf-8")
    return textos, pendentes, feitos


def aplicar(edit: Path, edit_data: Path | None = None, recortar: bool = True) -> dict:
    edit = Path(edit)
    ed_p = Path(edit_data) if edit_data else edit_data_do_projeto(edit)
    d = json.loads(ed_p.read_text(encoding="utf-8"))
    camadas = cam.load(edit / "camadas.json")
    destino = ed_p.parent / cam.MIDIA_DIR
    destino.mkdir(exist_ok=True)
    for velho in destino.glob(f"{PREFIXO}*"):  # só as cópias que este helper fez
        velho.unlink()
    inserts = [i for i in d.get("inserts") or [] if "camada" not in i]
    faltando = []
    for it in cam.aparecem(camadas):
        origem = edit / it["arquivo"]
        if not origem.is_file():
            faltando.append(it["arquivo"])
            continue
        nome = f"{PREFIXO}{it['id']}{origem.suffix.lower()}"
        shutil.copy2(origem, destino / nome)
        inserts.append({"src": f"{cam.MIDIA_DIR}/{nome}", "start": it["inicio"],
                        "end": round(it["inicio"] + it["duracao"], 3), "camada": it["id"]})
    d["inserts"] = inserts
    textos, pendentes, feitos = _textos(edit, ed_p.parent, d, camadas, recortar)
    if textos or "textos" in d:
        d["textos"] = textos
    tmp = ed_p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ed_p)
    return {"inserts": sum(1 for i in inserts if "camada" in i), "textos": len(textos),
            "faltando": faltando, "pendentes": pendentes, "feitos": feitos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--edit-data", type=Path)
    ap.add_argument("--sem-recorte", action="store_true",
                    help="não roda o recorte da pessoa nem o rastreio do rosto; só avisa o comando")
    a = ap.parse_args()
    r = aplicar(a.edit.resolve(), a.edit_data, recortar=not a.sem_recorte)
    print(f"{r['inserts']} imagem(ns) e {r['textos']} texto(s) de camada no edit-data.json")
    for f in r["feitos"]:
        print(f"  feito: {f}")
    for f in r["faltando"]:
        print(f"  FALTA {f} — o arquivo não está em midia/; a camada ficou fora", file=sys.stderr)
    for c in r["pendentes"]:
        print(f"  FALTA rodar (o texto sai na frente da pessoa ou parado até lá): {c}", file=sys.stderr)
    return 1 if r["faltando"] or r["pendentes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
