"""O relógio do corte: o tempo da gravação de cada tomada ↔ o tempo do cut.mp4.

Uma tomada do edl.json é o trecho `start`…`end` de um arquivo de origem, tocado a
`velocidade` (régua do editor do celular: 0,25× a 4×; sem ela, 1×). No corte ela dura
(end − start) ÷ velocidade, e um instante `at` da gravação cai em
`out + (at − v_in) ÷ velocidade`. Todo helper que leva tempo de um relógio para o outro
passa por aqui; nenhum faz a conta por conta própria.

Uma tomada com `curva` ({"nome", "pontos": [[x, y], ...]}, as curvas do CapCut: Montagem,
Herói, Bala…) muda de velocidade dentro dela: `x` é a fração da tomada NA GRAVAÇÃO (0 a 1) e
`y` a velocidade ali (0,1× a 10×), em reta entre dois pontos. Aqui ela vira pedaços de
velocidade constante (`pedacos`): vizinhos diferem no máximo 4% e cada um tem a velocidade
média exata do trecho, então a soma é a integral exata da reta. Render, legenda e editor
usam os mesmos pedaços; uma tomada sem curva é um pedaço só, com a conta de sempre.

Com J-cut, o render.py grava em `jcut_timeline` onde a IMAGEM de cada tomada está no
corte (`video_start_in_output`, `video_duration`) e onde o SOM começa
(`audio_start_in_output`): a imagem entra `lead` segundos de corte depois do som, ou seja,
pula `lead × velocidade` segundos da gravação.
"""
from __future__ import annotations

import math

VEL_MIN, VEL_MAX = 0.25, 4.0
CURVA_MIN, CURVA_MAX = 0.1, 10.0  # a faixa das curvas do CapCut
CURVA_PONTOS = 20
PASSO = 1.04  # dois pedaços vizinhos de uma curva diferem no máximo 4% na velocidade


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


def _numero(v) -> float:
    if isinstance(v, bool):
        raise ValueError(f"número inválido: {v!r}")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"número inválido: {v!r}") from None
    if math.isnan(v) or math.isinf(v):
        raise ValueError(f"número inválido: {v!r}")
    return v


def curva(r: dict) -> list[tuple[float, float]] | None:
    """Os pontos (x, velocidade) da `curva` do range, conferidos; None sem curva."""
    c = r.get("curva")
    if c is None:
        return None
    if r.get("velocidade") is not None:
        raise ValueError("curva e velocidade na mesma tomada")
    pts = c.get("pontos") if isinstance(c, dict) else None
    if not isinstance(pts, list) or not 2 <= len(pts) <= CURVA_PONTOS:
        raise ValueError(f"curva precisa de 2 a {CURVA_PONTOS} pontos: {c!r}")
    out: list[tuple[float, float]] = []
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError(f"ponto da curva inválido: {p!r}")
        x, y = _numero(p[0]), _numero(p[1])
        if not (0.0 <= x <= 1.0) or not (CURVA_MIN <= y <= CURVA_MAX):
            raise ValueError(f"ponto da curva fora de x 0–1, velocidade {CURVA_MIN:g}–{CURVA_MAX:g}: {p!r}")
        if out and x < out[-1][0]:
            raise ValueError(f"a curva volta no tempo: {p!r}")
        out.append((x, y))
    if out[0][0] != 0.0 or out[-1][0] != 1.0:
        raise ValueError("a curva começa em x = 0 e termina em x = 1")
    return out


def _pedacos_da_curva(pts: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    """A curva em pedaços (x0, x1, velocidade) de 0 a 1. Entre dois pontos a velocidade
    anda em reta; o trecho é cortado onde ela cresce PASSO vezes (passos iguais em
    proporção) e cada pedaço leva a média exata dele: comprimento ÷ ∫ dx/v."""
    out: list[tuple[float, float, float]] = []
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if xb <= xa:  # degrau: nenhum trecho da gravação
            continue
        n = max(1, math.ceil(abs(math.log(yb / ya)) / math.log(PASSO) - 1e-9))
        if yb == ya:
            xs, vs = [xa, xb], [ya, yb]
        else:
            vs = [ya * (yb / ya) ** (k / n) for k in range(n)] + [yb]
            xs = [xa + (v - ya) / (yb - ya) * (xb - xa) for v in vs]
            xs[-1] = xb
        for a, b, va, vb in zip(xs, xs[1:], vs, vs[1:]):
            t = (b - a) / va if abs(vb - va) < 1e-12 else (b - a) * math.log(vb / va) / (vb - va)
            v = (b - a) / t
            if out and out[-1][2] == v:  # trecho reto seguido de outro igual: um pedaço só
                out[-1] = (out[-1][0], b, v)
            else:
                out.append((a, b, v))
    return out


def pedacos(r: dict) -> list[tuple[float, float, float]]:
    """A tomada em pedaços de velocidade constante, na gravação: (de, até, velocidade)."""
    s, e = float(r["start"]), float(r["end"])
    pts = curva(r)
    if pts is None:
        return [(s, e, velocidade(r))]
    L = e - s
    out = [(s + a * L, s + b * L, v) for a, b, v in _pedacos_da_curva(pts)]
    out[-1] = (out[-1][0], e, out[-1][2])
    return out


def segundos_de_corte_por_segundo(r: dict) -> float:
    """Quanto 1 s de gravação vira de corte, em média na tomada (1 ÷ velocidade sem curva)."""
    pts = curva(r)
    if pts is None:
        return 1.0 / velocidade(r)
    return sum((b - a) / v for a, b, v in _pedacos_da_curva(pts))


def corte_ate(peds: list[tuple[float, float, float]], at: float) -> float:
    """Segundos de corte do início dos pedaços até o ponto `at` da gravação."""
    if len(peds) == 1:
        a, _, v = peds[0]
        return (at - a) / v
    t = 0.0
    for a, b, v in peds:
        if at <= b:
            return t + (at - a) / v
        t += (b - a) / v
    return t + (at - peds[-1][1]) / peds[-1][2]


def gravacao_em(peds: list[tuple[float, float, float]], t: float) -> float:
    """O ponto da gravação que cai `t` segundos de corte depois do início dos pedaços."""
    if len(peds) == 1:
        a, _, v = peds[0]
        return a + t * v
    acc = 0.0
    for a, b, v in peds:
        d = (b - a) / v
        if t <= acc + d:
            return a + (t - acc) * v
        acc += d
    return peds[-1][1] + (t - acc) * peds[-1][2]


def recorte(peds: list[tuple[float, float, float]], de: float, ate: float) -> list[tuple[float, float, float]]:
    """Só os pedaços entre `de` e `ate` da gravação (as pontas cortadas no lugar)."""
    out = [(max(a, de), min(b, ate), v) for a, b, v in peds if b > de and a < ate]
    return out or [(de, ate, peds[0][2])]


def dur_trecho(peds: list[tuple[float, float, float]], de: float, ate: float) -> float:
    """Quanto o trecho `de`…`ate` da gravação dura no corte."""
    if len(peds) == 1:
        return (ate - de) / peds[0][2]
    return corte_ate(peds, ate) - corte_ate(peds, de)


def dur_no_corte(r: dict) -> float:
    """Quanto a tomada dura no corte, sem J-cut."""
    if curva(r) is None:
        return (float(r["end"]) - float(r["start"])) / velocidade(r)
    return corte_ate(pedacos(r), float(r["end"]))


def tomadas_no_corte(edl: dict) -> list[dict]:
    """Cada tomada como a IMAGEM do cut.mp4 a mostra:
    {source, v_in, v_out (na gravação), out, dur (no corte), vel, peds}. Com curva,
    `vel` é None e quem leva tempo de um relógio para o outro usa `no_corte`."""
    ranges = edl.get("ranges") or []
    jt = edl.get("jcut_timeline")
    out_spans: list[dict] = []
    if jt and len(jt) == len(ranges):
        for r, j in zip(ranges, jt):
            peds = pedacos(r)
            lead = max(0.0, float(j["video_start_in_output"]) - float(j["audio_start_in_output"]))
            dur = float(j["video_duration"])
            if len(peds) == 1:
                vel = peds[0][2]
                v_in = float(r["start"]) + lead * vel
                v_out = v_in + dur * vel
            else:
                vel = None
                v_in, v_out = gravacao_em(peds, lead), gravacao_em(peds, lead + dur)
            out_spans.append({"source": r["source"], "v_in": v_in, "v_out": v_out,
                              "out": float(j["video_start_in_output"]), "dur": dur, "vel": vel,
                              "peds": peds})
        return out_spans
    t = 0.0
    for r in ranges:
        peds, dur = pedacos(r), dur_no_corte(r)
        out_spans.append({"source": r["source"], "v_in": float(r["start"]), "v_out": float(r["end"]),
                          "out": t, "dur": dur, "vel": peds[0][2] if len(peds) == 1 else None,
                          "peds": peds})
        t += dur
    return out_spans


def no_corte(span: dict, at: float) -> float:
    """O instante `at` da gravação, dentro da tomada `span`, no relógio do corte."""
    if span.get("vel") is not None:
        return span["out"] + (at - span["v_in"]) / span["vel"]
    peds = span["peds"]
    return span["out"] + corte_ate(peds, at) - corte_ate(peds, span["v_in"])
