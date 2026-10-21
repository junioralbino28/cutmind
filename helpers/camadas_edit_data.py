#!/usr/bin/env python3
"""Leva as imagens das camadas (camadas.json do editor) para o edit-data.json da Fase 2.

Cada imagem visível vira um item de `inserts[]` — o cartão arredondado da zona de cima,
o mesmo dos inserts do agente — com `"camada": <id do item>`. Só esses são mexidos: os
inserts do agente ficam como estão, e as camadas entram por último (ficam por cima, como
no editor). O arquivo é copiado para `public/midia/camada-<id>.<ext>`, um nome sem espaço
nem acento para o `staticFile` do Remotion. Rodar de novo refaz do zero: o que a pessoa
excluiu ou escondeu sai do edit-data e a cópia antiga é apagada.

    python camadas_edit_data.py <edit> [--edit-data <caminho do edit-data.json>]

Sem --edit-data, usa o `editData` do state.json. Depois, renderize de novo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import camadas as cam  # mesma pasta deste arquivo

PREFIXO = "camada-"


def edit_data_do_projeto(edit: Path) -> Path:
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    if not state.get("editData"):
        raise SystemExit("state.json sem editData: passe --edit-data")
    return edit / state["editData"]


def aplicar(edit: Path, edit_data: Path | None = None) -> dict:
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
    tmp = ed_p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ed_p)
    return {"inserts": sum(1 for i in inserts if "camada" in i), "faltando": faltando}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--edit-data", type=Path)
    a = ap.parse_args()
    r = aplicar(a.edit.resolve(), a.edit_data)
    print(f"{r['inserts']} imagem(ns) de camada no edit-data.json")
    for f in r["faltando"]:
        print(f"  FALTA {f} — o arquivo não está em midia/; a camada ficou fora", file=sys.stderr)
    return 1 if r["faltando"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
