"""A conferência da legenda contra a voz (edição real de 01/11): na legenda certa, nada; na que
foi atrasando, o atraso de cada janela. Medido na legenda real daquele vídeo: +100 ms no começo, +800 ms
no fim (o relato mediu +91 e +824 palavra por palavra)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import conferir_legenda as cl  # noqa: E402


def _fala(seg: float, semente: int = 7) -> tuple[np.ndarray, list[dict]]:
    """Uma voz de mentira (palavras de 120 a 400 ms com pausas) e a legenda certa dela."""
    rng = np.random.default_rng(semente)
    voz = np.zeros(int(seg / cl.PASSO), dtype=np.float32)
    caps, t = [], 0.3
    while t < seg - 1:
        d = float(rng.uniform(0.12, 0.4))
        a, b = int(t / cl.PASSO), int((t + d) / cl.PASSO)
        voz[a:b] = rng.uniform(0.5, 1.0)
        caps.append({"text": "palavra", "startMs": round(t * 1000), "endMs": round((t + d) * 1000)})
        t += d + float(rng.uniform(0.05, 0.6))
    return voz, caps


def _atrasa(caps: list[dict], de: float, ate: float, total: float) -> list[dict]:
    """O atraso crescendo de `de` a `ate` ao longo do vídeo, como no som emendado errado."""
    out = []
    for c in caps:
        k = de + (ate - de) * c["startMs"] / 1000 / total
        out.append({**c, "startMs": c["startMs"] + round(k * 1000), "endMs": c["endMs"] + round(k * 1000)})
    return out


def test_legenda_certa_da_zero_em_todas_as_janelas():
    voz, caps = _fala(120)
    res = cl.atrasos(voz, cl.palavras(caps, len(voz)), caps)
    assert len(res) == 6 and all(abs(r["atraso"]) <= 0.02 for r in res), res


def test_legenda_que_vai_atrasando_aparece_janela_a_janela():
    voz, caps = _fala(120)
    ruim = _atrasa(caps, 0.1, 0.8, 120)
    res = cl.atrasos(voz, cl.palavras(ruim, len(voz)), ruim)
    assert res[0]["atraso"] > 0.08 and res[-1]["atraso"] > 0.6
    assert [r["atraso"] for r in res] == sorted(r["atraso"] for r in res)  # cresce, como no relato


def test_itens_vazios_que_seguram_a_tela_nao_contam():
    voz, caps = _fala(60)
    com_vazio = [{"text": " ", "startMs": 0, "endMs": 60000}] + caps
    assert cl.atrasos(voz, cl.palavras(com_vazio, len(voz)), com_vazio) == cl.atrasos(voz, cl.palavras(caps, len(voz)), caps)
