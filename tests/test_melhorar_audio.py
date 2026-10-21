"""O Melhorar do editor: a cadeia roda no ffmpeg e tira o chiado de fundo."""
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"


def _rms(p: Path, a: float, b: float) -> float:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(a), "-t", str(b - a), "-i", str(p), "-ac", "1",
                          "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = struct.unpack(f"<{len(raw) // 2}h", raw)
    return math.sqrt(sum(v * v for v in x) / max(1, len(x)))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
def test_melhorar_roda_e_baixa_o_chiado_onde_nao_tem_voz(tmp_path):
    # 2 s de ruído rosa (o espectro de ventilador e ar-condicionado; semente fixa para o
    # teste não sortear um ruído novo a cada rodada), com um "trecho falado" (tom 300 Hz) de 0,8 a 1,4 s
    entrada = tmp_path / "Gravação.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=2:c=pink:a=0.03:seed=1",
                    "-f", "lavfi", "-i", "sine=f=300:d=0.6", "-filter_complex",
                    "[1:a]adelay=800,volume=0.5[v];[0:a][v]amix=inputs=2:normalize=0", str(entrada)], check=True)
    r = subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / "melhorar_audio.py"), str(entrada)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    saida = tmp_path / "Gravação-melhorado.wav"
    assert saida.is_file()
    # a razão "fala ÷ silêncio" sobe: o chiado cai mais que a fala. Medido em 21/10 com esta
    # semente: 7,6 → 16,9 (×2,2); só a cadeia de voz, sem a redução de ruído, dá ×1,24 e não passaria
    antes = _rms(entrada, 1.0, 1.3) / _rms(entrada, 0.2, 0.6)
    depois = _rms(saida, 1.0, 1.3) / _rms(saida, 0.2, 0.6)
    assert depois > 1.5 * antes, (antes, depois)
