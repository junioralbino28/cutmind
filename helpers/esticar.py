"""O som de uma tomada com curva de velocidade, esticado pelo relógio do corte (tempo.py).

WSOLA, o mesmo princípio do `atempo` do ffmpeg: quadros de 40 ms com sobreposição de metade,
cada um tirado da gravação no ponto que a curva manda para aquele instante do corte, com até
5 ms de folga para casar a forma de onda com a do quadro anterior. O tom não muda e o som não
se afasta da imagem ao longo da curva, porque cada quadro é posto pelo relógio, não pela soma
dos anteriores.

Por que não o `atempo` trocando de tempo por `asendcmd` a cada pedaço: medido em 21/10, cada
troca perdeu ~1,6 ms e a troca valia ~40–60 ms antes do ponto pedido (a janela do filtro); numa
Montagem de 6 s o som saiu 258 ms mais curto que a imagem.
"""
from __future__ import annotations

import numpy as np

import tempo

JANELA = 0.03  # segundos por quadro
BUSCA = 0.005  # folga, para cada lado, para casar a forma de onda


def esticar(x: np.ndarray, sr: int, peds: list[tuple[float, float, float]]) -> np.ndarray:
    """`x` (amostras, canais) é a gravação de peds[0][0] a peds[-1][1]; devolve o som no
    corte, com (end − start) pela curva de duração, em amostras arredondadas."""
    x = np.asarray(x, np.float32)
    a0 = peds[0][0]
    n_out = int(round(tempo.corte_ate(peds, peds[-1][1]) * sr))
    N = int(round(JANELA * sr)) // 2 * 2
    H = N // 2
    D = int(round(BUSCA * sr))
    w = np.hanning(N + 1)[:N].astype(np.float32)  # periódica: soma 1 com sobreposição de metade
    pad = N + D
    xp = np.pad(x, ((pad, pad + N), (0, 0)))
    mono = xp.mean(1)
    # a saída começa H antes do 0, para o primeiro quadro já cobrir o início inteiro
    y = np.zeros((n_out + 2 * N, x.shape[1]), np.float32)
    soma = np.zeros(n_out + 2 * N, np.float32)
    anterior = None
    for k in range(0, n_out + N, H):
        centro = (k - H + N / 2) / sr  # o instante do corte no meio deste quadro
        alvo = int(round((tempo.gravacao_em(peds, centro) - a0) * sr)) + pad - N // 2
        alvo = min(max(alvo, D), len(mono) - N - D - 1)
        p = alvo
        if anterior is not None:
            ref = mono[anterior + H:anterior + H + N]  # o que viria naturalmente depois
            trecho = mono[alvo - D:alvo + D + N]
            c = np.correlate(trecho, ref, "valid")
            # normalizada pela energia de cada candidato: a crua puxa para onde há mais som e,
            # no ataque de um som num trecho lento, adiantava o ataque (−44 ms a 0,5×, medido)
            e2 = np.cumsum(np.concatenate(([0.0], trecho.astype(np.float64) ** 2)))
            energia = np.sqrt(np.maximum(e2[N:] - e2[:-N], 0.0))[:len(c)]
            if c.max() > 1e-9:
                p = alvo - D + int(np.argmax(c / (energia + 1e-6)))
        y[k:k + N] += xp[p:p + N] * w[:, None]
        soma[k:k + N] += w
        anterior = p
    soma[soma < 1e-3] = 1.0
    return (y / soma[:, None])[H:H + n_out]
