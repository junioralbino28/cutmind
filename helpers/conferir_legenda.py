"""Confere a legenda contra a voz: em cada janela de 20 s, quanto as palavras do captions.json estão
atrasadas (+) ou adiantadas (−) em relação à voz do vídeo.

Num Reels de 3 min editado com o kit (01/11), a legenda feita da transcrição de um som emendado errado foi atrasando de
+91 ms no começo até +824 ms no fim, e todo texto e toda foto postos "na palavra" pela legenda herdaram
o atraso. Nenhuma outra conferência via isso: a legenda batia com a transcrição, só não batia com a voz.

Como mede: a voz vira uma curva de energia (10 ms por ponto) e a legenda vira "tem palavra / não tem";
em cada janela, o deslocamento que mais casa as duas é o atraso dela.

    uv run python -X utf8 helpers/conferir_legenda.py <video> <captions.json> [--janela 20] [--limite 0.08]

Sai 0 com todas as janelas dentro do limite; 1 com as que passam dele (e uma linha por janela).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

PASSO = 0.01  # s por ponto da curva
TAXA = 16000
MAX_ATRASO = 1.5  # s procurados para cada lado
MIN_PALAVRAS = 8  # janela com menos palavras não diz nada


def energia(video: Path) -> np.ndarray:
    """A voz de 0 a 1, um ponto a cada 10 ms (0 = o piso de ruído do próprio vídeo)."""
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:a:0", "-ac", "1", "-ar", str(TAXA),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    n = int(TAXA * PASSO)
    x = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)
    piso, topo = np.percentile(db, 10) + 6, np.percentile(db, 95)
    return np.clip((db - piso) / max(topo - piso, 1e-6), 0, 1)


def palavras(caps: list[dict], n: int) -> np.ndarray:
    """1 onde a legenda tem palavra, 0 no resto (os itens vazios, que só seguram a tela, não contam)."""
    s = np.zeros(n, dtype=np.float32)
    for c in caps:
        if not str(c.get("text", "")).strip():
            continue
        a, b = int(float(c["startMs"]) / 1000 / PASSO), int(float(c["endMs"]) / 1000 / PASSO)
        s[max(a, 0):max(min(b, n), 0)] = 1
    return s


def atrasos(voz: np.ndarray, leg: np.ndarray, caps: list[dict], janela: float = 20.0) -> list[dict]:
    """Uma entrada por janela com palavras suficientes: começo (s), atraso (s, + = legenda depois da voz)
    e quanto as duas casam no melhor deslocamento (0 a 1)."""
    out, m, w = [], int(MAX_ATRASO / PASSO), int(janela / PASSO)
    falas = [float(c["startMs"]) / 1000 for c in caps if str(c.get("text", "")).strip()]
    for a in range(0, len(leg), w):
        b = min(a + w, len(leg))
        if sum(a * PASSO <= t < b * PASSO for t in falas) < MIN_PALAVRAS or b - a < 2 * m:
            continue
        melhor = (-2.0, 0)
        for d in range(-m, m + 1):  # a legenda no ponto i casa com a voz no ponto i - d
            lo, hi = max(a, d), min(b, len(voz) + d)
            if hi - lo < (b - a) // 2:
                continue
            g = leg[lo:hi] - leg[lo:hi].mean()
            v = voz[lo - d: hi - d]
            v = v - v.mean()
            den = float(np.sqrt((g ** 2).sum() * (v ** 2).sum()))
            r = float((g * v).sum() / den) if den > 0 else -1.0
            if r > melhor[0]:
                melhor = (r, d)
        out.append({"inicio": round(a * PASSO, 2), "atraso": round(melhor[1] * PASSO, 3), "casa": round(melhor[0], 2)})
    return out


def conferir(video: Path, captions: Path, janela: float = 20.0) -> list[dict]:
    caps = json.loads(Path(captions).read_text(encoding="utf-8"))
    voz = energia(Path(video))
    return atrasos(voz, palavras(caps, len(voz)), caps, janela)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("captions", type=Path)
    ap.add_argument("--janela", type=float, default=20.0)
    ap.add_argument("--limite", type=float, default=0.08, help="atraso aceito por janela, em s")
    a = ap.parse_args()
    res = conferir(a.video, a.captions, a.janela)
    if not res:
        print("legenda × voz: poucas palavras para medir")
        return 0
    ruins = [r for r in res if abs(r["atraso"]) > a.limite]
    for r in res:
        marca = "  ⚠" if r in ruins else ""
        print(f"  {r['inicio']:7.1f} s: atraso {r['atraso'] * 1000:+5.0f} ms (casa {r['casa']:.2f}){marca}")
    if ruins:
        print(f"legenda × voz: {len(ruins)} de {len(res)} janelas passam de {a.limite * 1000:.0f} ms; "
              "transcreva o cut.mp4 de novo (apague transcripts/cut.json antes: o cache é pelo nome) e refaça a legenda")
        return 1
    print(f"legenda × voz: ok em {len(res)} janelas (maior atraso {max(abs(r['atraso']) for r in res) * 1000:.0f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
