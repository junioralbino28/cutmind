"""O som do corte sem J-cut fica no lugar da imagem em todas as emendas (edição real de 01/11).

Emendar trechos AAC por cópia leva junto o preparo do codificador de cada um: 26 emendas deram
186,4 s de som num cut.mp4 de 185,6 s. Quem toca pelos tempos (navegador, `-ss`) não vê; quem lê o som
corrido (efeito de voz, mixagem, a transcrição que vira a legenda) escorrega até 0,8 s no fim.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sem ffmpeg")
FPS = 30
TAXA = 48000
BIPE = 0.1  # o bipe de cada trecho, a 0,1 s do começo dele


def _trecho(p: Path, seg: float) -> None:
    # o mesmo formato do extract_segment: H.264 + AAC 192k a 48 kHz, com um bipe de 20 ms
    som = f"aevalsrc=sin(2*PI*1000*t)*between(t\\,{BIPE}\\,{BIPE + 0.02}):s={TAXA}:d={seg}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r={FPS}:d={seg}",
                    "-f", "lavfi", "-i", som, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", str(TAXA), "-shortest", str(p)], check=True)


def _som(p: Path) -> np.ndarray:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a", "-f", "s16le", "-ac", "1", "-ar", str(TAXA), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32)


def _quadros(p: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True, check=True)
    return int(r.stdout.strip().strip(","))


def _bipes(x: np.ndarray) -> list[float]:
    """O começo de cada bipe no som corrido (s)."""
    alto = np.abs(x) > 0.3 * np.abs(x).max()
    inicios, ultimo = [], -1.0
    for i in np.flatnonzero(alto):
        t = i / TAXA
        if t - ultimo > 0.2:
            inicios.append(t)
        ultimo = t
    return inicios


def test_o_som_emendado_fica_no_lugar_da_imagem(tmp_path):
    trechos, comecos, t = [], [], 0.0
    for i in range(12):
        p = tmp_path / f"seg_{i:02d}.mp4"
        _trecho(p, 1.0 + (i % 3) / FPS)
        trechos.append(p)
        comecos.append(t)
        t += _quadros(p) / FPS  # o trecho começa onde a imagem do anterior acabou
    saida = tmp_path / "base.mp4"
    render.concat_segments(trechos, saida, tmp_path)
    x = _som(saida)
    bipes = _bipes(x)
    assert len(bipes) == len(trechos)
    # a imagem do mp4 começa depois do 0 (o preparo do AAC do 1º trecho): é dali que a tela conta
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=start_time",
                        "-of", "default=nw=1:nk=1", str(saida)], capture_output=True, text=True, check=True)
    imagem0 = float(r.stdout.strip().strip(",") or 0)
    desvios = [b - (imagem0 + c + BIPE) for b, c in zip(bipes, comecos)]
    # sem o conserto o desvio cresce ~25 ms por emenda (0,28 s no 12º); com ele fica parado
    assert max(abs(d) for d in desvios) < 0.005, [round(d * 1000, 1) for d in desvios]
    # e o som acaba com a imagem, a menos do resto do último bloco do AAC
    assert abs(len(x) / TAXA - _quadros(saida) / FPS) < 0.05
