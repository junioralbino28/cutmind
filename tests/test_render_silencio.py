"""Um corte sem som nenhum (a montagem na batida tira o som dos clipes) passa pelo loudnorm do
render sem quebrar: o 2º passo recusaria measured_I=-inf."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render  # noqa: E402


def _streams(p: Path) -> list[str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True).stdout
    return sorted(out.split())


def test_corte_mudo_passa_pelo_loudnorm(tmp_path):
    mudo = tmp_path / "mudo.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=160x284:r=30:d=1",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(mudo)], check=True)
    saida = tmp_path / "saida.mp4"
    assert render.apply_loudnorm_two_pass(mudo, saida)
    assert _streams(saida) == _streams(mudo)  # copiado: as duas faixas, os mesmos 30 quadros
