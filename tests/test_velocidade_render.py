"""Velocidade por tomada (etapa 4c) no render: duração, tom da voz e sincronia imagem × som.

A fonte tem um FLASH branco e um BIPE de 1 kHz nos mesmos instantes. Depois do corte com
uma tomada a 2× e outra a 0,5×, cada flash tem de continuar junto do seu bipe (≤ 1
quadro), o bipe tem de continuar em 1 kHz (o atempo não muda o tom) e cada tomada tem
de durar o trecho ÷ velocidade, em quadros inteiros.
"""
from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render  # noqa: E402
import tempo  # noqa: E402

FPS = 30
FLASHES = [1.0, 2.6, 4.0, 5.4]  # instantes da gravação com flash + bipe (0,1 s cada)


def test_atempo_em_fatores_de_meio_a_dois():
    assert render.atempo_cadeia(1.5) == [1.5]
    assert render.atempo_cadeia(0.25) == [0.5, 0.5]
    assert render.atempo_cadeia(4.0) == [2.0, 2.0]
    assert render.atempo_cadeia(3.0) == [2.0, 1.5]
    assert all(0.5 <= f <= 2.0 for v in (0.3, 0.7, 2.5, 3.9) for f in render.atempo_cadeia(v))
    assert math.prod(render.atempo_cadeia(0.3)) == pytest.approx(0.3)


def test_ajuste_a_quadros_conta_no_tempo_do_corte():
    edl = {"ranges": [{"source": "F", "start": 0.0, "end": 1.01, "velocidade": 2.0},
                      {"source": "F", "start": 2.0, "end": 2.51, "velocidade": 0.5}]}
    render.snap_ranges_to_frames(edl, FPS)
    for r in edl["ranges"]:
        quadros = tempo.dur_no_corte(r) * FPS
        assert abs(quadros - round(quadros)) < 1e-4, (r, quadros)
    assert render.snap_ranges_to_frames(edl, FPS) == 0  # de novo não mexe


@pytest.fixture(scope="module")
def fonte(tmp_path_factory):
    p = tmp_path_factory.mktemp("vel") / "fonte.mkv"  # PCM: sem o atraso do AAC entre flash e bipe
    janelas = "+".join(f"between(t,{t:.2f},{t + 0.1:.2f})" for t in FLASHES)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s=160x284:r={FPS}:d=6.5",
                    # o bipe amostra a amostra: começa no instante exato do flash
                    "-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*1000*t)*({janelas})':s=48000:d=6.5",
                    # no geq o tempo é T (maiúsculo)
                    "-filter_complex", f"[0:v]geq=lum='255*({janelas.replace('(t,', '(T,')})':cb=128:cr=128[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "1",
                    "-c:a", "pcm_s16le", str(p)], check=True)
    return p


def _luz_por_quadro(video: Path) -> list[float]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=16:16,format=gray",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return [sum(raw[i:i + 256]) / 256 for i in range(0, len(raw), 256)]


def _som(video: Path, taxa: int = 48000) -> list[int]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(taxa),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def _inicios(sinal, limiar, passo):
    """Onde o sinal cruza o limiar subindo, em unidades de `passo`."""
    return [i * passo for i in range(1, len(sinal)) if sinal[i] >= limiar > sinal[i - 1]]


def _goertzel(x, taxa, f):
    k = 2 * math.cos(2 * math.pi * f / taxa)
    s1 = s2 = 0.0
    for v in x:
        s1, s2 = v + k * s1 - s2, s1
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - k * s1 * s2))


@pytest.mark.parametrize("jcut", [True, False])
def test_velocidade_mantem_imagem_e_som_juntos_e_o_tom(fonte, tmp_path, jcut):
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"F": str(fonte)}, "grade": "",
           "ranges": [{"source": "F", "start": 0.5, "end": 3.2, "beat": "rapida", "velocidade": 2},
                      {"source": "F", "start": 3.5, "end": 6.0, "beat": "lenta", "velocidade": 0.5}]}
    if not jcut:
        edl["jcut"] = False
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(render.__file__)), str(edit / "edl.json"), "-o", str(edit / "out.mp4"),
                        "--draft", "--no-loudnorm", "--no-subtitles"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr[-1500:]
    salvo = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    spans = tempo.tomadas_no_corte(salvo)

    # duração: cada tomada é o trecho ÷ velocidade (menos o que o J-cut sobrepõe), em quadros inteiros
    luz = _luz_por_quadro(edit / "out.mp4")
    esperado = round(sum(s["dur"] for s in spans) * FPS)
    assert abs(len(luz) - esperado) <= 1, (len(luz), esperado)
    for s in spans:
        assert abs(s["dur"] * FPS - round(s["dur"] * FPS)) < 1e-3

    # cada flash da gravação aparece onde o relógio do corte diz e junto do seu bipe
    flashes = _inicios(luz, 128, 1 / FPS)
    som = [abs(x) for x in _som(edit / "out.mp4")]
    env = [max(som[i:i + 48]) for i in range(0, len(som), 48)]  # envelope em blocos de 1 ms
    bipes = _inicios(env, 4000, 0.001)
    previstos = [tempo.no_corte(s, t) for t in FLASHES for s in spans if s["v_in"] <= t < s["v_out"]]
    assert len(flashes) == len(previstos) >= 3, (flashes, previstos)
    for f, p in zip(flashes, previstos):
        assert abs(f - p) <= 1 / FPS + 1e-6, (f, p)  # a imagem no lugar certo
        b = min(bipes, key=lambda x: abs(x - f))
        assert abs(b - f) <= 1 / FPS, (f, b)  # e o som junto dela

    # o tom: o bipe a 2× e a 0,5× continua em 1 kHz
    sinal = _som(edit / "out.mp4")
    for f in flashes:
        janela = sinal[int((f + 0.01) * 48000):int((f + 0.04) * 48000)]
        e1k = _goertzel(janela, 48000, 1000)
        assert e1k > 8 * max(_goertzel(janela, 48000, 2000), _goertzel(janela, 48000, 500)), f


# Curvas de teste (etapa 4d): cada flash cai num trecho até 2×; a 5× um flash de 0,1 s dura
# menos de um quadro e some. A primeira acelera de 0,6× a 2× no meio; a segunda desacelera de
# 1,5× a 0,5× no começo, com o flash de 4,0 s no meio da rampa.
CURVA_A = [[0, 0.6], [0.5, 0.6], [0.7, 2.0], [1, 2.0]]
CURVA_B = [[0, 1.5], [0.4, 0.5], [1, 0.5]]


def test_ajuste_a_quadros_com_curva():
    edl = {"ranges": [{"source": "F", "start": 0.0, "end": 2.71, "curva": {"nome": "a", "pontos": CURVA_A}},
                      {"source": "F", "start": 3.0, "end": 5.53, "curva": {"nome": "b", "pontos": CURVA_B}}]}
    assert render.snap_ranges_to_frames(edl, FPS) == 2
    for r in edl["ranges"]:
        quadros = tempo.dur_no_corte(r) * FPS
        assert abs(quadros - round(quadros)) < 1e-4, (r, quadros)
    assert render.snap_ranges_to_frames(edl, FPS) == 0


def test_setpts_da_curva_leva_cada_ponto_ao_relogio():
    peds = tempo.pedacos({"start": 0.0, "end": 4.0, "curva": {"pontos": CURVA_B}})
    expr = render.setpts_da_curva(peds)
    assert expr.count("if(") == len(peds) - 1 and expr.count("(((") < 3  # árvore, não fila
    # avalia a expressão do ffmpeg em Python (ld(0) = x; if e lt viram funções) contra o tempo.py
    def avaliar(x):
        e = expr.replace("st(0,(PTS-STARTPTS)*TB);", "").replace("/TB", "").replace("ld(0)", repr(x))
        e = e.replace("if(", "_se(").replace("lt(", "_menor(")
        return eval(e, {"_se": lambda c, a, b: a if c else b, "_menor": lambda a, b: a < b})
    for x in (0.0, 0.7, 1.6, 2.9, 4.0):
        assert avaliar(x) == pytest.approx(tempo.corte_ate(peds, x), abs=1e-6)


@pytest.mark.parametrize("jcut", [True, False])
def test_curva_mantem_imagem_e_som_juntos_e_o_tom(fonte, tmp_path, jcut):
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"F": str(fonte)}, "grade": "",
           "ranges": [{"source": "F", "start": 0.5, "end": 3.2, "beat": "acelera", "curva": {"nome": "a", "pontos": CURVA_A}},
                      {"source": "F", "start": 3.5, "end": 6.0, "beat": "freia", "curva": {"nome": "b", "pontos": CURVA_B}}]}
    if not jcut:
        edl["jcut"] = False
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(render.__file__)), str(edit / "edl.json"), "-o", str(edit / "out.mp4"),
                        "--draft", "--no-loudnorm", "--no-subtitles"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr[-1500:]
    salvo = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    spans = tempo.tomadas_no_corte(salvo)
    assert all(s["vel"] is None for s in spans)

    luz = _luz_por_quadro(edit / "out.mp4")
    esperado = round(sum(s["dur"] for s in spans) * FPS)
    assert abs(len(luz) - esperado) <= 1, (len(luz), esperado)

    flashes = _inicios(luz, 128, 1 / FPS)
    som = [abs(x) for x in _som(edit / "out.mp4")]
    env = [max(som[i:i + 48]) for i in range(0, len(som), 48)]
    bipes = _inicios(env, 4000, 0.001)
    previstos = [tempo.no_corte(s, t) for t in FLASHES for s in spans if s["v_in"] <= t < s["v_out"]]
    assert len(flashes) == len(previstos) == 4, (flashes, previstos)
    # Com J-cut (o padrão) imagem e som caem a ±6 ms do previsto (medido). Sem J-cut o som
    # atrasa ~21 ms por tomada, somando: o concat copia o AAC de cada trecho com o atraso de
    # início do codificador (antigo, vale com ou sem curva). Daí 2 quadros nesse caminho.
    folga_som = 1 / FPS if jcut else 2 / FPS
    for f, p in zip(flashes, previstos):
        assert abs(f - p) <= 1 / FPS + 1e-6, (f, p)  # a imagem no lugar da regra
        b = min(bipes, key=lambda x: abs(x - p))
        assert abs(b - p) <= folga_som, (p, b)  # e o som também

    sinal = _som(edit / "out.mp4")
    for p in previstos:  # o tom medido a partir do bipe achado, nos trechos lento e rápido
        f = min(bipes, key=lambda x: abs(x - p))
        janela = sinal[int((f + 0.01) * 48000):int((f + 0.04) * 48000)]
        e1k = _goertzel(janela, 48000, 1000)
        assert e1k > 8 * max(_goertzel(janela, 48000, 2000), _goertzel(janela, 48000, 500)), f
