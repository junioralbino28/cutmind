"""Volume por tomada (etapa 4a): o `volume` do edl.json entra no fim do render, sobre o normalizado."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render  # noqa: E402


def test_volume_da_tomada():
    assert render.volume_da_tomada({}) == 1.0
    assert render.volume_da_tomada({"volume": None}) == 1.0
    assert render.volume_da_tomada({"volume": 0}) == 0.0
    assert render.volume_da_tomada({"volume": "2.5"}) == 2.5


@pytest.mark.parametrize("ruim", [-0.1, 4.01, "alto", float("nan")])
def test_volume_fora_da_faixa_e_recusado(ruim):
    with pytest.raises(ValueError):
        render.volume_da_tomada({"volume": ruim})


def test_pontos_de_volume():
    assert render.pontos_de_volume([(0, 2, 1.0), (2, 4, 1.0)]) == []  # tudo a 100%: nada a fazer
    # emenda seca: rampa de 20 ms centrada na emenda
    assert render.pontos_de_volume([(0, 2, 0.5), (2, 4, 1.0)]) == [(0, 0.5), (1.99, 0.5), (2.01, 1.0), (4, 1.0)]
    # J-cut: o som da 2ª entra em 1,8 s, a 1ª acaba em 2,0 s; a rampa cobre a sobreposição
    assert render.pontos_de_volume([(0, 2, 2.0), (1.8, 4, 0.0)]) == [(0, 2.0), (1.8, 2.0), (2, 0.0), (4, 0.0)]
    # vizinhas com o mesmo volume não ganham rampa entre elas
    assert render.pontos_de_volume([(0, 1, 0.5), (1, 2, 0.5), (2, 3, 1.0)]) == [(0, 0.5), (1.99, 0.5), (2.01, 1.0), (3, 1.0)]
    # tomada mais curta que as rampas: os pontos nunca voltam no tempo
    pts = render.pontos_de_volume([(0, 1.1, 1.0), (1.0, 1.15, 0.5), (1.05, 2, 1.0)])
    assert all(b[0] >= a[0] for a, b in zip(pts, pts[1:])), pts


def _media_db(arquivo: Path, ini: float, dur: float) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{ini:.3f}", "-t", f"{dur:.3f}",
                        "-i", str(arquivo), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r.stderr).group(1))


def _tom(p: Path, dur: float) -> Path:
    """Imagem preta com um tom de 440 Hz baixo (cabe o dobro sem bater no limitador)."""
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=30:d={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur}",
                    "-af", "volume=0.1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(p)], check=True)
    return p


@pytest.mark.parametrize("vol, esperado", [(0.5, -6.02), (2.0, 6.02)])
def test_aplicar_volume_mede_o_pedido(tmp_path, vol, esperado):
    f = _tom(tmp_path / "corte.mp4", 4)
    antes = _media_db(f, 2.3, 1.4)  # a 2ª metade fica a 100%: a referência
    assert render.aplicar_volume_das_tomadas(f, [(0, 2, vol), (2, 4, 1.0)]) is True
    dif = _media_db(f, 0.3, 1.4) - _media_db(f, 2.3, 1.4)
    assert abs(dif - esperado) < 0.5, dif
    assert abs(_media_db(f, 2.3, 1.4) - antes) < 0.3  # a tomada a 100% não mudou


def test_volume_zero_e_silencio_e_sem_volume_nao_mexe(tmp_path):
    f = _tom(tmp_path / "corte.mp4", 4)
    assert render.aplicar_volume_das_tomadas(f, [(0, 2, 0.0), (2, 4, 1.0)]) is True
    assert _media_db(f, 0.2, 1.6) < -80
    g = _tom(tmp_path / "outro.mp4", 2)
    marca = g.stat().st_mtime_ns
    assert render.aplicar_volume_das_tomadas(g, [(0, 1, 1.0), (1, 2, 1.0)]) is False
    assert g.stat().st_mtime_ns == marca  # sem volume: o arquivo nem é reescrito


@pytest.mark.parametrize("jcut", [True, False])
def test_render_com_loudnorm_preserva_o_volume(tmp_path, jcut):
    """Pela porta da frente (render.py --draft, com o loudnorm ligado, pasta sem render
    anterior): a tomada a 50% sai 6 dB abaixo da outra, do mesmo tom. Com o volume posto
    na extração, o loudnorm dinâmico desfazia a diferença; e o rascunho com J-cut nem
    saía numa pasta nova (procurava clips_graded)."""
    src = _tom(tmp_path / "fonte.mp4", 4)
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"F": str(src)}, "grade": "",
           "ranges": [{"source": "F", "start": 0.2, "end": 1.8, "beat": "A", "volume": 0.5},
                      {"source": "F", "start": 2.0, "end": 3.6, "beat": "B"}]}
    if not jcut:
        edl["jcut"] = False
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(render.__file__)), str(edit / "edl.json"),
                        "-o", str(edit / "out.mp4"), "--draft", "--no-subtitles"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr[-1500:]
    salvo = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    if jcut:
        janelas = [(x["audio_start_in_output"], x["audio_duration"]) for x in salvo["jcut_timeline"]]
    else:
        janelas = [(0.0, salvo["ranges"][0]["end"] - salvo["ranges"][0]["start"])]
        janelas.append((janelas[0][1], salvo["ranges"][1]["end"] - salvo["ranges"][1]["start"]))
    n = [_media_db(edit / "out.mp4", ini + 0.3, dur - 0.6) for ini, dur in janelas]
    assert abs((n[0] - n[1]) - (-6.02)) < 0.5, n


def test_volume_errado_para_antes_de_renderizar(tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"F": str(tmp_path / "nao-existe.mp4")},
           "ranges": [{"source": "F", "start": 0, "end": 1, "volume": 9}]}
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(render.__file__)), str(edit / "edl.json"), "-o", str(edit / "o.mp4")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode != 0 and "volume fora de 0–4" in r.stderr
