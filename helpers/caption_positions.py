"""Leva as posições de legenda escolhidas no editor de celular para o relógio do corte.

No modo "Posição das frases" o usuário arrasta cada frase (ou todas de uma vez).
O editor ancora cada frase no MOMENTO DA GRAVAÇÃO da primeira palavra dela
(`source` + `at`, em segundos no arquivo de origem): um recorte feito depois não
desloca a frase, e uma frase cujo momento foi cortado simplesmente some.

O template precisa do relógio do cut.mp4. Este helper faz a conta pelo edl.json
(tempo.py: J-cut e velocidade de cada tomada), e grava em edit-data.json →
`captions.positions`:

    {"all": {"x": 0.5, "y": 0.62} | null,
     "phrases": [{"at": <segundos no cut.mp4>, "x": 0.5, "y": 0.3}, ...]}

x e y são frações do quadro e marcam o CENTRO do bloco da frase.

Uso:
    uv run python helpers/caption_positions.py --style <edit>/preview_style.json \
        --edl <edit>/edl.json --edit-data <edit>/remotion/public/edit-data.json
    (--style aceita também o state.json, que guarda a escolha em "style")
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # roda também com -I
import tempo  # noqa: E402  (mesma pasta: o relógio do corte, com J-cut e velocidade)


def _clamp01(v: object) -> float:
    return min(1.0, max(0.0, float(v)))  # type: ignore[arg-type]


def to_cut(positions: dict, edl: dict) -> tuple[dict, list[dict]]:
    """Âncoras de origem → segundos do cut.mp4. Devolve (positions, frases_sem_lugar).

    Um momento que aparece duas vezes no corte (tomada duplicada) vale nas duas.
    """
    spans = tempo.tomadas_no_corte(edl)
    phrases: list[dict] = []
    dropped: list[dict] = []
    for p in positions.get("phrases") or []:
        try:
            at, x, y = float(p["at"]), _clamp01(p["x"]), _clamp01(p["y"])
        except (KeyError, TypeError, ValueError):
            dropped.append(p)
            continue
        hits = [tempo.no_corte(s, at) for s in spans
                if s["source"] == p.get("source") and s["v_in"] - 1e-3 <= at < s["v_out"]]
        if not hits:
            dropped.append(p)
            continue
        phrases += [{"at": round(max(0.0, t), 3), "x": x, "y": y} for t in hits]
    phrases.sort(key=lambda q: q["at"])
    a = positions.get("all")
    all_ = None
    if isinstance(a, dict) and "x" in a and "y" in a:
        all_ = {"x": _clamp01(a["x"]), "y": _clamp01(a["y"])}
    return {"all": all_, "phrases": phrases}, dropped


def read_positions(style_file: Path) -> dict:
    d = json.loads(style_file.read_text(encoding="utf-8"))
    if "captionPositions" not in d and isinstance(d.get("style"), dict):
        d = d["style"]  # state.json guarda a escolha em "style"
    return d.get("captionPositions") or {}


def main() -> None:
    ap = argparse.ArgumentParser(description="posições das frases → edit-data.json captions.positions")
    ap.add_argument("--style", type=Path, required=True, help="preview_style.json (ou state.json)")
    ap.add_argument("--edl", type=Path, required=True, help="edl.json do corte atual")
    ap.add_argument("--edit-data", type=Path, required=True, help="remotion/public/edit-data.json")
    args = ap.parse_args()

    positions, dropped = to_cut(read_positions(args.style),
                                json.loads(args.edl.read_text(encoding="utf-8")))
    ed = json.loads(args.edit_data.read_text(encoding="utf-8"))
    caps = ed.setdefault("captions", {})
    if positions["all"] is None and not positions["phrases"]:
        caps.pop("positions", None)  # nada arrastado: cada estilo no lugar dele
    else:
        caps["positions"] = positions
    args.edit_data.write_text(json.dumps(ed, ensure_ascii=False, indent=2), encoding="utf-8")

    todas = positions["all"]
    print(f"{args.edit_data} — {len(positions['phrases'])} frase(s) com lugar próprio; "
          f"todas: {'x %.2f y %.2f' % (todas['x'], todas['y']) if todas else 'no lugar do estilo'}")
    for p in dropped:
        print(f"  sem lugar no corte (o momento foi cortado): {p.get('text') or p.get('at')}")


if __name__ == "__main__":
    main()
