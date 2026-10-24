"""O render por janela (render_janelas.py): só os quadros das janelas mudam, a contagem e o tempo de
cada quadro ficam iguais, e o som do render sai idêntico. Sem o Remotion: as partes são vídeos de
mentira, com o mesmo formato."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render_janelas as rj  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")
LADO = 64


def _video(caminho: Path, tons: list[int], som: bool = False) -> None:
    """Um vídeo de 30 q/s em que cada quadro é todo de um tom de cinza (o número dele, para conferir)."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{LADO}x{LADO}",
           "-r", "30", "-i", "-"]
    if som:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={len(tons) / 30}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "30"]
    cmd += ["-c:a", "aac", "-b:a", "128k"] if som else []
    pr = subprocess.Popen(cmd + [str(caminho)], stdin=subprocess.PIPE)
    for t in tons:
        pr.stdin.write(bytes([t]) * LADO * LADO)
    pr.stdin.close()
    assert pr.wait() == 0


def _tons(caminho: Path) -> list[float]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(caminho), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return [float(q.mean()) for q in np.frombuffer(raw, np.uint8).reshape(-1, LADO, LADO)]


def _som(caminho: Path) -> str:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(caminho), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _pts(caminho: Path) -> list[float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                          "-of", "csv=p=0", str(caminho)], capture_output=True, text=True, check=True).stdout
    return [float(x.strip(",")) for x in out.split()]


ANTES = [q * 4 for q in range(60)]


def test_janelas_viram_quadros_com_folga_e_juntam_as_que_se_tocam():
    assert rj.em_quadros([(8.0, 8.5), (1.0, 2.0), (2.05, 3.0)], 30, 1, 300) == [(29, 93), (239, 258)]
    assert rj.em_quadros([(0.0, 0.5), (9.9, 20.0)], 30, 0, 300) == [(0, 17), (295, 300)]  # dentro do vídeo
    assert rj.ler_janelas("33.0-36.4, 45.1-48") == [(33.0, 36.4), (45.1, 48.0)]
    with pytest.raises(rj.JanelaErro):
        rj.ler_janelas("36-33")


def test_emenda_troca_so_os_quadros_das_janelas_e_guarda_o_som(tmp_path):
    render, parte, saida = tmp_path / "render.mp4", tmp_path / "parte_20_30.mp4", tmp_path / "saida.mp4"
    _video(render, ANTES, som=True)
    _video(parte, [255 - q * 4 for q in range(20, 30)])
    assert rj.emendar(render, saida, [(20, 30, parte)], 30) == 60
    tons = _tons(saida)
    esperado = [255 - t if 20 <= i < 30 else t for i, t in enumerate(ANTES)]
    assert len(tons) == 60 and max(abs(a - b) for a, b in zip(tons, esperado)) <= 3
    pts = _pts(saida)
    assert len(pts) == 60 and all(abs((b - a) - 1 / 30) < 1e-3 for a, b in zip(pts, pts[1:]))
    assert _som(saida) == _som(render)  # o som copiado, byte a byte


def test_emenda_recusa_parte_com_quadros_a_menos(tmp_path):
    render, parte, saida = tmp_path / "render.mp4", tmp_path / "parte_20_30.mp4", tmp_path / "saida.mp4"
    _video(render, ANTES)
    _video(parte, [0] * 9)
    with pytest.raises(rj.JanelaErro, match="9 quadros, esperado 10"):
        rj.emendar(render, saida, [(20, 30, parte)], 30)
    assert not saida.exists()


def test_o_helper_refaz_a_janela_no_render_e_limpa_as_partes(tmp_path, monkeypatch):
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    (edit / "remotion" / "out").mkdir()
    (edit / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (public / "edit-data.json").write_text(json.dumps({"fps": 30, "videoLag": 0}), encoding="utf-8")
    render = edit / "remotion" / "out" / "render.mp4"
    _video(render, ANTES, som=True)
    som = _som(render)
    pedidas = []

    def remotion_falso(remotion, pasta, faixas):  # o que o partes.mjs faria: um mp4 por faixa
        assert remotion == edit / "remotion"
        pedidas.extend(faixas)
        for a, b in faixas:
            _video(pasta / f"parte_{a}_{b}.mp4", [255 - q * 4 for q in range(a, b)])
    monkeypatch.setattr(rj, "_rodar_partes", remotion_falso)
    r = rj.aplicar(edit, rj.ler_janelas("0.7-0.9"))
    assert pedidas == [(19, 29)] and r["faixas"] == [(19, 29)] and r["total"] == 60
    tons = _tons(render)
    assert abs(tons[18] - ANTES[18]) <= 3 and abs(tons[19] - (255 - ANTES[19])) <= 3 and abs(tons[29] - ANTES[29]) <= 3
    assert _som(render) == som
    assert sorted(p.name for p in render.parent.iterdir()) == ["render.mp4"]  # nem as partes nem o temporário
