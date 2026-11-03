#!/usr/bin/env python3
"""A legenda em outro idioma, no tempo da fala. Quem traduz é o agente: sem chave e sem serviço de fora.

    uv run python -X utf8 helpers/legenda_traduzida.py frases <edit>
    uv run python -X utf8 helpers/legenda_traduzida.py aplicar <edit> <traducao.json> --idioma en
    uv run python -X utf8 helpers/legenda_traduzida.py voltar <edit>

`frases` imprime as frases da legenda, uma por linha, como JSON: {"i", "start", "end", "texto"}. Traduza cada uma
com sentido de frase (não palavra por palavra) e grave uma lista de textos na mesma ordem, em `traducao.json`.
`aplicar` reparte cada frase traduzida no tempo em que a original é dita, pelo tamanho das palavras, e grava o
`captions.json`; o original fica ao lado (`captions.original.json`) e `voltar` o devolve. As frases sempre saem do
original: dá para trocar de idioma sem voltar antes.

Um novo corte refaz a legenda a partir da fala: depois dele, rode `frases` e `aplicar` de novo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PAUSA_MS = 500  # acima disso, outra frase
MAX_PALAVRAS = 14


class LegendaInvalida(ValueError):
    pass


def _caminhos(edit: Path) -> tuple[Path, Path, Path]:
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    cap = edit / (state.get("captions") or "remotion/public/captions.json")
    ed = edit / (state.get("editData") or "remotion/public/edit-data.json")
    return cap, cap.with_name("captions.original.json"), ed


def frases_de(palavras: list[dict]) -> list[list[dict]]:
    """Agrupa as palavras onde quem fala respira: pontuação final, pausa, ou frase longa demais para ler."""
    out: list[list[dict]] = []
    cur: list[dict] = []
    for i, w in enumerate(palavras):
        if not str(w.get("text") or "").strip():
            continue
        cur.append(w)
        prox = next((x for x in palavras[i + 1:] if str(x.get("text") or "").strip()), None)
        fim = str(w["text"]).rstrip()[-1:] in ".!?…"
        pausa = prox is not None and prox["startMs"] - w["endMs"] > PAUSA_MS
        if fim or pausa or len(cur) >= MAX_PALAVRAS:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def repartir(frase: list[dict], traducao: str) -> list[dict]:
    """A frase traduzida no tempo da original: cada palavra fica o tempo proporcional às letras dela."""
    ws = traducao.split()
    ini, fim = int(frase[0]["startMs"]), int(frase[-1]["endMs"])
    pesos = [len(w) + 1 for w in ws]
    total = sum(pesos)
    out, t = [], float(ini)
    for w, p in zip(ws, pesos):
        d = (fim - ini) * p / total
        a, b = round(t), round(t + d)
        out.append({"text": w, "startMs": a, "endMs": max(b, a + 1), "timestampMs": round((a + b) / 2), "confidence": None})
        t += d
    return out


def aplicar(palavras: list[dict], traducoes: list[str]) -> list[dict]:
    frases = frases_de(palavras)
    if len(traducoes) != len(frases):
        raise LegendaInvalida(f"são {len(frases)} frases e vieram {len(traducoes)} traduções: tem de ser uma para cada")
    vazias = [i for i, t in enumerate(traducoes) if not (isinstance(t, str) and t.strip())]
    if vazias:
        raise LegendaInvalida(f"tradução vazia nas frases {vazias}")
    return [w for f, t in zip(frases, traducoes) for w in repartir(f, t)]


def _original(cap: Path, orig: Path) -> list[dict]:
    return json.loads((orig if orig.is_file() else cap).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("frases", "voltar"):
        sub.add_parser(nome).add_argument("edit", type=Path)
    a = sub.add_parser("aplicar")
    a.add_argument("edit", type=Path)
    a.add_argument("traducao", type=Path)
    a.add_argument("--idioma", required=True, help="o código do idioma novo, como en, es, fr")
    args = ap.parse_args()
    cap, orig, ed = _caminhos(args.edit)

    if args.cmd == "frases":
        for i, f in enumerate(frases_de(_original(cap, orig))):
            print(json.dumps({"i": i, "start": f[0]["startMs"] / 1000, "end": f[-1]["endMs"] / 1000,
                              "texto": " ".join(w["text"] for w in f)}, ensure_ascii=False))
        return 0

    dados = json.loads(ed.read_text(encoding="utf-8")) if ed.is_file() else {}
    legenda = dados.setdefault("captions", {})
    if args.cmd == "voltar":
        if not orig.is_file():
            print("a legenda já está no idioma original")
            return 0
        cap.write_text(orig.read_text(encoding="utf-8"), encoding="utf-8")
        orig.unlink()
        legenda.pop("idioma", None)
        ed.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        print("legenda de volta ao original")
        return 0

    palavras = _original(cap, orig)
    try:
        novas = aplicar(palavras, json.loads(args.traducao.read_text(encoding="utf-8")))
    except LegendaInvalida as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    if not orig.is_file():
        orig.write_text(json.dumps(palavras, ensure_ascii=False), encoding="utf-8")
    cap.write_text(json.dumps(novas, ensure_ascii=False, indent=2), encoding="utf-8")
    legenda["idioma"] = args.idioma
    ed.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"legenda em {args.idioma}: {len(novas)} palavras em {len(frases_de(palavras))} frases")
    if legenda.get("style") == "stacked":
        print(f"o Empilhado lê o caption-cues.json: refaça com caption_style.py --lang {args.idioma}, e renderize")
    return 0


if __name__ == "__main__":
    sys.exit(main())
