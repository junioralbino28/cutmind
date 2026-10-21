"""O relógio do corte: o tempo da gravação de cada tomada ↔ o tempo do cut.mp4.

Uma tomada do edl.json é o trecho `start`…`end` de um arquivo de origem, tocado a
`velocidade` (régua do editor do celular: 0,25× a 4×; sem ela, 1×). No corte ela dura
(end − start) ÷ velocidade, e um instante `at` da gravação cai em
`out + (at − v_in) ÷ velocidade`. Todo helper que leva tempo de um relógio para o outro
passa por aqui; nenhum faz a conta por conta própria.

Com J-cut, o render.py grava em `jcut_timeline` onde a IMAGEM de cada tomada está no
corte (`video_start_in_output`, `video_duration`) e onde o SOM começa
(`audio_start_in_output`): a imagem entra `lead` segundos de corte depois do som, ou seja,
pula `lead × velocidade` segundos da gravação.
"""
from __future__ import annotations

import math

VEL_MIN, VEL_MAX = 0.25, 4.0


def velocidade(r: dict) -> float:
    """A `velocidade` do range (1 sem ela). Fora de 0,25–4, ou não numérica, é recusada."""
    v = r.get("velocidade")
    if v is None:
        return 1.0
    if isinstance(v, bool):  # True viraria 1× em silêncio
        raise ValueError(f"velocidade inválida: {v!r}")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"velocidade inválida: {v!r}") from None
    if not (VEL_MIN <= v <= VEL_MAX) or math.isnan(v):
        raise ValueError(f"velocidade fora de {VEL_MIN:g}–{VEL_MAX:g}: {v!r}")
    return v


def dur_no_corte(r: dict) -> float:
    """Quanto a tomada dura no corte, sem J-cut."""
    return (float(r["end"]) - float(r["start"])) / velocidade(r)


def tomadas_no_corte(edl: dict) -> list[dict]:
    """Cada tomada como a IMAGEM do cut.mp4 a mostra:
    {source, v_in, v_out (na gravação), out, dur (no corte), vel}."""
    ranges = edl.get("ranges") or []
    jt = edl.get("jcut_timeline")
    out_spans: list[dict] = []
    if jt and len(jt) == len(ranges):
        for r, j in zip(ranges, jt):
            vel = velocidade(r)
            lead = max(0.0, float(j["video_start_in_output"]) - float(j["audio_start_in_output"]))
            v_in = float(r["start"]) + lead * vel
            dur = float(j["video_duration"])
            out_spans.append({"source": r["source"], "v_in": v_in, "v_out": v_in + dur * vel,
                              "out": float(j["video_start_in_output"]), "dur": dur, "vel": vel})
        return out_spans
    t = 0.0
    for r in ranges:
        vel, dur = velocidade(r), dur_no_corte(r)
        out_spans.append({"source": r["source"], "v_in": float(r["start"]), "v_out": float(r["end"]),
                          "out": t, "dur": dur, "vel": vel})
        t += dur
    return out_spans


def no_corte(span: dict, at: float) -> float:
    """O instante `at` da gravação, dentro da tomada `span`, no relógio do corte."""
    return span["out"] + (at - span["v_in"]) / span["vel"]
