"""O som de uma tomada com curva de velocidade (helpers/esticar.py): cada instante cai onde o
relógio do corte manda, e o tom não muda."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import esticar  # noqa: E402
import tempo  # noqa: E402

SR = 48000
MONTAGEM = [[0, 0.9], [0.1, 0.9], [0.5, 6.8], [0.65, 0.3], [0.8, 1], [1, 1]]


def _inicios(y):
    e = np.convolve(y ** 2, np.ones(48) / 48, "same")
    acima = e > 0.02
    ini = np.flatnonzero(acima[1:] & ~acima[:-1]) + 1
    out, ult = [], -10 ** 9
    for i in ini:
        if i - ult > 0.03 * SR:
            out.append(i / SR)
        ult = i
    return np.array(out)


def test_bipes_caem_onde_a_curva_manda():
    bipes = np.arange(0.1, 5.9, 0.25)
    x = np.zeros(6 * SR, np.float32)
    t = np.arange(int(0.012 * SR)) / SR
    for b in bipes:
        i = int(round(b * SR))
        x[i:i + len(t)] += 0.6 * np.sin(2 * np.pi * 1000 * t)
    peds = tempo.pedacos({"start": 0.0, "end": 6.0, "curva": {"pontos": MONTAGEM}})
    y = esticar.esticar(x[:, None], SR, peds)[:, 0]
    assert abs(len(y) / SR - tempo.corte_ate(peds, 6.0)) < 1 / SR + 1e-9
    achados = _inicios(y)
    for b in bipes:
        v = next(v for a, c, v in peds if a <= b <= c)
        if v > 2.5:  # a 6,8× um bipe de 12 ms vira 2 ms: não há o que medir
            continue
        e = tempo.corte_ate(peds, b)
        # até 1 quadro (30 fps): ao desacelerar, o quadro de 40 ms leva um pouco da gravação
        # além do ponto e o ataque aparece antes (−15 ms a 0,45×, medido); sem deriva ao longo
        assert abs(achados[np.argmin(abs(achados - e))] - e) < 1 / 30, f"bipe de {b:.2f} s"


def test_o_tom_nao_muda():
    t = np.arange(6 * SR) / SR
    x = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    peds = tempo.pedacos({"start": 0.0, "end": 6.0, "curva": {"pontos": MONTAGEM}})
    y = esticar.esticar(np.stack([x, x], 1), SR, peds)
    assert y.shape[1] == 2
    for de, ate in ((0.05, 0.4), (1.2, 1.5), (2.5, 3.0), (4.0, 4.4)):  # trechos lento, rápido e a 1×
        seg = y[int(de * SR):int(ate * SR), 0]
        f = np.fft.rfftfreq(len(seg), 1 / SR)[np.argmax(abs(np.fft.rfft(seg * np.hanning(len(seg)))))]
        assert abs(f - 1000) < 10, f"{de}-{ate} s: {f:.0f} Hz"


def test_um_pedaco_so_estica_por_igual():
    x = np.random.default_rng(1).standard_normal((SR * 2, 1)).astype(np.float32) * 0.1
    y = esticar.esticar(x, SR, [(0.0, 2.0, 2.0)])
    assert abs(len(y) - SR) <= 1
