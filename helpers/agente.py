#!/usr/bin/env python3
"""O agente avisa o editor que está mexendo no projeto, e quando terminou.

Enquanto o `state.json` tiver `"agente": {"trabalhando": true, "desde": <segundos>}`, o editor segura o
Salvar do corte e o "Gerar e baixar": os dois mexeriam nos mesmos arquivos. No teste de 28/10 o agente montava
a Fase 2 a pedido da conversa, sem esse aviso, e o Gerar instalou o Remotion na mesma pasta ao mesmo tempo: o
npm perdeu arquivos e o vídeo não saiu. Vale por 30 min (o editor solta depois disso, caso o agente caia);
rodar `trabalhando` de novo renova.

E o agente aprende o jeito da pessoa (aprender.py): o `livre` guarda o que ele entregou, e o `trabalhando` que
COMEÇA um trabalho (não o que só renova) mostra o que a pessoa mudou à mão desde então, para ele gravar os hábitos
na skill dela.

    uv run python -X utf8 helpers/agente.py trabalhando <edit>
    uv run python -X utf8 helpers/agente.py livre <edit>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PRAZO = 30 * 60  # o mesmo do editor: depois disso a marca não vale mais


def _gravar(p: Path, dados: dict) -> None:
    tmp = p.with_name(p.name + ".agente.tmp")
    tmp.write_bytes((json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    for _ in range(40):  # o editor lê o state.json a cada segundo; no Windows a troca falha enquanto ele lê
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)
    raise OSError(f"não consegui gravar {p}: o arquivo está preso")


def marcar(edit: Path, trabalhando: bool, agora: float | None = None) -> dict:
    """Grava (ou tira) a marca no state.json, sem mexer no resto. Devolve o state.json novo."""
    p = Path(edit) / "state.json"
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st = {}
    if not isinstance(st, dict):
        raise ValueError(f"{p} não é um objeto JSON")
    if trabalhando:
        st["agente"] = {"trabalhando": True, "desde": time.time() if agora is None else agora}
    elif "agente" in st:
        del st["agente"]
    else:
        return st
    _gravar(p, st)
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=("trabalhando", "livre"))
    ap.add_argument("edit", type=Path)
    a = ap.parse_args()
    if not (a.edit / "state.json").is_file():
        print(f"não achei o state.json em {a.edit}", file=sys.stderr)
        return 1
    antes = (json.loads((a.edit / "state.json").read_text(encoding="utf-8")) or {}).get("agente") or {}
    renovando = bool(antes.get("trabalhando")) and time.time() - float(antes.get("desde") or 0) < PRAZO
    marcar(a.edit, a.acao == "trabalhando")
    print("o editor espera você terminar" if a.acao == "trabalhando" else "o editor está livre de novo")
    try:
        import aprender  # mesma pasta deste arquivo
        if a.acao == "livre":
            print(f"aprender: entrega {aprender.guardar(a.edit)} guardada (o que a pessoa mudar depois vira aprendizado)")
        elif not renovando:
            texto = aprender.texto_diferenca(aprender.diferenca(a.edit))
            if texto:
                print(texto)
    except Exception as e:  # noqa: BLE001 (aprender nunca atrapalha a marca do editor)
        print(f"aprender: não deu desta vez ({e})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
