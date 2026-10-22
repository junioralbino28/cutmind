"""A leitura da imagem do detect_color funciona em qualquer sistema.

No Windows o arquivo temporário onde o ffmpeg grava as medidas tem um caminho com
"C:" e barras invertidas; dentro do filtro (`metadata=print:file=...`) os dois-pontos
separam opções e a barra é escape, o ffmpeg recusa ("Invalid argument") e o detector
dizia "análise de imagem falhou" para todo vídeo, voltando a perguntar "normal ou LOG?".
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import detect_color as dc  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")


def _video(tmp_path: Path) -> Path:
    v = tmp_path / "pasta com espaço" / "clipe.mp4"
    v.parent.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
                    "-t", "2", "-pix_fmt", "yuv420p", str(v)], check=True)
    return v


def test_mede_a_imagem(tmp_path):
    s = dc._sample_stats(_video(tmp_path), n=4)
    assert s is not None, "a leitura da imagem falhou (caminho do arquivo de medidas no filtro)"
    assert s["frames"] >= 2 and 0 <= s["black_floor"] < s["white_ceiling"] <= 1


def test_video_normal_sai_com_confianca(tmp_path):
    r = dc.detect(_video(tmp_path), samples=4)
    assert "análise de imagem falhou" not in r["evidence"]
    assert r["tier"] == "estatística" and r["stats"] is not None
