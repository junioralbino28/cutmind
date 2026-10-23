#!/usr/bin/env python3
"""Pedaços da legenda levados no tempo pelo editor: desloca as palavras no captions.json.

Na vista Final a pessoa arrasta um pedaço da faixa de legenda. O Salvar manda, em
`editData.legenda.tempos`, cada pedaço pelas palavras do captions.json:

    [{"palavra": 12, "palavras": 3, "deMs": 8540, "paraMs": 8040}]

`palavra` é o índice da primeira palavra, `palavras` quantas são, `deMs` onde a primeira
começava quando a pessoa arrastou e `paraMs` onde ela começa agora. Todas as palavras do
pedaço andam o mesmo tanto (início, fim e meio), e os estilos de legenda leem o arquivo
como sempre. Rodar duas vezes não desloca duas vezes: palavra que já está em `paraMs` fica.
Pedaço que passaria por cima da palavra vizinha, ou cujo começo não é mais o `deMs` (a
legenda foi refeita depois do arraste), fica de fora e é avisado.

    python legenda_tempos.py <edit> [--de <edit>/preview_edits.json] [--tempos '<json>']

`--tempos` recebe a lista direto (pedido pelo chat). Depois, renderize de novo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class TemposInvalidos(ValueError):
    pass


def _int(v: object, nome: str, lo: int = 0) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or v < lo:
        raise TemposInvalidos(f"{nome} inválido: {v!r}")
    return int(v)


def aplicar(caps: list[dict], tempos: list[dict]) -> tuple[list[str], list[str]]:
    """Desloca os pedaços em `caps` (no lugar). Devolve (o que foi feito, o que ficou de fora)."""
    feitos, fora = [], []
    for t in sorted(tempos, key=lambda x: x.get("palavra", 0)):
        try:
            i0 = _int(t.get("palavra"), "palavra")
            n = _int(t.get("palavras"), "palavras", 1)
            de, para = _int(t.get("deMs"), "deMs"), _int(t.get("paraMs"), "paraMs")
        except TemposInvalidos as e:
            fora.append(str(e))
            continue
        if i0 + n > len(caps):
            fora.append(f"palavras {i0}–{i0 + n - 1}: a legenda tem {len(caps)}")
            continue
        texto = " ".join(c["text"] for c in caps[i0:i0 + n])
        agora = caps[i0]["startMs"]
        if agora == para:
            feitos.append(f'"{texto}": já estava em {para / 1000:.2f} s')
            continue
        if agora != de:
            fora.append(f'"{texto}": começa em {agora / 1000:.2f} s, não em {de / 1000:.2f} s (a legenda mudou depois do arraste)')
            continue
        d = para - de
        antes = caps[i0 - 1]["endMs"] if i0 > 0 else 0
        depois = caps[i0 + n]["startMs"] if i0 + n < len(caps) else None
        if caps[i0]["startMs"] + d < antes or (depois is not None and caps[i0 + n - 1]["endMs"] + d > depois):
            fora.append(f'"{texto}": {d / 1000:+.2f} s passaria por cima da palavra vizinha')
            continue
        for c in caps[i0:i0 + n]:
            c["startMs"] += d
            c["endMs"] += d
            if c.get("timestampMs") is not None:
                c["timestampMs"] += d
        feitos.append(f'"{texto}": {de / 1000:.2f} s → {para / 1000:.2f} s ({d / 1000:+.2f} s)')
    return feitos, fora


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--de", type=Path, help="padrão: <edit>/preview_edits.json")
    ap.add_argument("--tempos", help="a lista em JSON, no lugar do preview_edits.json")
    a = ap.parse_args()
    edit = a.edit.resolve()
    if a.tempos:
        tempos = json.loads(a.tempos)
    else:
        origem = a.de or edit / "preview_edits.json"
        dados = json.loads(origem.read_text(encoding="utf-8"))
        tempos = ((dados.get("editData") or {}).get("legenda") or {}).get("tempos") or []
    if not isinstance(tempos, list) or not tempos:
        print("nenhum pedaço da legenda para mover")
        return 0
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    arq = edit / (state.get("captions") or "remotion/public/captions.json")
    caps = json.loads(arq.read_text(encoding="utf-8"))
    feitos, fora = aplicar(caps, tempos)
    if any("→" in f for f in feitos):
        tmp = arq.with_suffix(".tmp")
        tmp.write_bytes(json.dumps(caps, ensure_ascii=False, indent=2).encode("utf-8"))
        tmp.replace(arq)
    for f in feitos:
        print(f"  ok  {f}")
    for f in fora:
        print(f"  FORA {f}", file=sys.stderr)
    print(f"{arq.name}: {len(feitos)} pedaço(s) no lugar, {len(fora)} de fora")
    return 1 if fora else 0


if __name__ == "__main__":
    sys.exit(main())
