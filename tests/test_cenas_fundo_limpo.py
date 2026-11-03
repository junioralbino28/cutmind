"""O fundo sem a pessoa (Vertigem), num vídeo de verdade: o que está atrás dela aparece quando ela anda, e o que nunca
aparece é preenchido sem deixar a pessoa nem um buraco preto."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import cenas_edit_data as ced  # noqa: E402

cv2 = pytest.importorskip("cv2")
W, H, N = 270, 480, 30


def grava(p, quadros, pix, vcodec):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", pix, "-s", f"{W}x{H}", "-r", "30",
                    "-i", "-", *vcodec, str(p)], input=b"".join(quadros), check=True)


def projeto(tmp_path, anda=True):
    """Fundo verde, pessoa vermelha que anda (ou não) de um lado para o outro."""
    video, matte = [], []
    for k in range(N):
        x = 40 + (k * 5 if anda else 0)
        q = np.zeros((H, W, 3), np.uint8)
        q[:] = (40, 200, 40)
        q[150:480, x:x + 60] = (220, 20, 20)
        a = np.zeros((H, W, 4), np.uint8)
        a[150:480, x:x + 60] = (220, 20, 20, 255)
        video.append(q.tobytes())
        matte.append(a.tobytes())
    cut, mov = tmp_path / "cut.mp4", tmp_path / "m.mov"
    grava(cut, video, "rgb24", ["-c:v", "libx264", "-qp", "8", "-pix_fmt", "yuv420p"])
    grava(mov, matte, "rgba", ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"])
    return cut, mov


def le(p):
    return cv2.cvtColor(cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def test_a_pessoa_que_anda_some_do_fundo(tmp_path):
    cut, mov = projeto(tmp_path)
    alvo = tmp_path / "limpo com acento é.jpg"
    assert ced.fundo_limpo(cut, mov, 0, N, 30.0, alvo)
    im = le(alvo)
    assert im.shape[:2] == (1920, 1080)
    # onde ela passou agora é o verde do fundo, nada de vermelho
    assert im[1400, 300, 1] > 150 and im[1400, 300, 0] < 110


def test_quem_nunca_saiu_vira_preenchimento_sem_pessoa(tmp_path):
    cut, mov = projeto(tmp_path, anda=False)
    alvo = tmp_path / "limpo.jpg"
    assert ced.fundo_limpo(cut, mov, 0, N, 30.0, alvo)
    im = le(alvo)
    meio = im[1400, 280]  # o centro da pessoa parada
    assert meio[0] < 110 and meio[1] > 120, meio  # verde, sem o vermelho dela e sem buraco preto
