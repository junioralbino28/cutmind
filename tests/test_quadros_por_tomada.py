"""Cada tomada extraída tem exatamente os quadros planejados, mesmo de vídeo de celular.

Celular grava com quadro VARIÁVEL (declara 59 fps, entrega ~41 quando falta luz). Com
`-ss` + `-t` + `-r 30` o ffmpeg às vezes põe um quadro a mais no FIM do trecho. No J-cut
a imagem é emendada pelos quadros reais e o som pela conta: cada quadro a mais empurra
todas as imagens seguintes para trás da voz. Medido num corte real de 21 tomadas: 5
tomadas com +1 quadro, imagem 167 ms atrasada no fim, a fala entrando antes do corte.
"""
from __future__ import annotations

import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import render  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")


@pytest.fixture(scope="module")
def vfr(tmp_path_factory) -> Path:
    # quadros jogados fora num padrão irregular, carimbos originais mantidos: quadro variável
    v = tmp_path_factory.mktemp("vfr") / "celular.mp4"
    sel = r"not(eq(mod(n*7\,10)\,3))*not(eq(mod(n*13\,17)\,5))*not(eq(mod(n\,5)\,2))"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x568:rate=59",
                    "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000", "-t", "16",
                    "-vf", f"select='{sel}'", "-fps_mode", "vfr", "-video_track_timescale", "90000",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(v)], check=True)
    return v


def _quadros(v: Path) -> int:
    return int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                               "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(v)],
                              capture_output=True, text=True).stdout)


def _todos(args: list[str]) -> np.ndarray:
    p = subprocess.run(["ffmpeg", "-v", "error", *args, "-vf", "scale=54:96,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, 96 * 54).astype(np.float32)


def test_contagem_exata_em_quadro_variavel(vfr, tmp_path):
    random.seed(7)
    errados = []
    for _ in range(30):
        k = random.randint(40, 120)
        ini = round(random.uniform(0.3, 15.5 - k / 30), 6)  # o trecho cabe no vídeo de 16 s
        out = tmp_path / "seg.mp4"
        render.extract_segment(vfr, ini, k / 30, "", out, streams="v")
        n = _quadros(out)
        if n != k:
            errados.append((ini, k, n))
    assert not errados, f"tomadas com contagem errada (início, planejado, saiu): {errados}"


def test_o_quadro_a_mais_era_o_ultimo(vfr, tmp_path):
    # a correção só pode tirar o quadro do FIM: o começo de cada tomada não anda
    ini, k = 3.688, 74  # saía com 75 quadros
    out = tmp_path / "seg.mp4"
    render.extract_segment(vfr, ini, k / 30, "", out, streams="v")
    novo = _todos(["-i", str(out)])
    antes = _todos(["-ss", f"{ini:.6f}", "-i", str(vfr), "-t", f"{k / 30:.6f}", "-r", "30"])  # o comando antigo
    assert (len(novo), len(antes)) == (k, k + 1)
    # o render recomprime, então nenhum quadro bate exato; o que prova o alinhamento é
    # casar melhor na mesma posição do que deslocado de um (medido: 5,6 contra 7,2–7,7)
    def d(a, b):
        return float(np.abs(a - b).mean())
    assert d(novo, antes[:k]) < d(novo, antes[1:k + 1]) - 1.0
    assert d(novo[-1], antes[k - 1]) < d(novo[-1], antes[k]) - 1.0
