"""A sobreposição do J-cut é MEDIDA: a voz da tomada seguinte só entra antes da imagem pelo tanto de
silêncio que existe dos dois lados da emenda.

Antes eram 5 quadros fixos em toda emenda. Num corte com respiro dos dois lados não fazia diferença
(sobrepunha silêncio com silêncio), mas num corte colado na fala, como quem apara à mão para tirar
um erro, as duas vozes tocavam juntas por ~170 ms ("o áudio parece que está trepado no outro",
31/10).

A gravação de teste tem duas "falas" de tons diferentes (500 Hz e 1500 Hz) separadas por 1 s de
silêncio: no corte final, os dois tons nunca podem soar ao mesmo tempo."""
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

FPS = 30
FALA_A = (1.0, 2.0)  # 500 Hz
FALA_B = (3.0, 4.0)  # 1500 Hz


@pytest.fixture(scope="module")
def fonte(tmp_path_factory):
    p = tmp_path_factory.mktemp("jcut") / "fonte.mkv"  # PCM: o tom começa na amostra exata
    som = (f"0.5*sin(2*PI*500*t)*between(t,{FALA_A[0]},{FALA_A[1]})"
           f"+0.5*sin(2*PI*1500*t)*between(t,{FALA_B[0]},{FALA_B[1]})")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s=160x284:r={FPS}:d=6",
                    "-f", "lavfi", "-i", f"aevalsrc='{som}':s=48000:d=6",
                    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "1",
                    "-c:a", "pcm_s16le", str(p)], check=True)
    return p


def _plano(fonte: Path, tmp_path: Path, a: tuple, b: tuple) -> list[dict]:
    edl = {"sources": {"F": str(fonte)},
           "ranges": [{"source": "F", "start": a[0], "end": a[1]}, {"source": "F", "start": b[0], "end": b[1]}]}
    return render.plan_jcut(edl, tmp_path, render.jcut_settings(edl, FPS))


def test_silencio_nas_pontas(fonte):
    cab, cauda = render.silencio_nas_pontas(fonte, 0.6, 2.3)
    assert cab == pytest.approx(0.4, abs=0.02) and cauda == pytest.approx(0.3, abs=0.02)
    assert render.silencio_nas_pontas(fonte, 1.2, 1.8) == (0.0, 0.0)  # fala de ponta a ponta
    assert render.trailing_silence(fonte, 0.6, 2.3) == pytest.approx(0.3, abs=0.02)  # quem já chamava


def test_com_respiro_dos_dois_lados_a_sobreposicao_continua_inteira(fonte, tmp_path):
    p = _plano(fonte, tmp_path, (0.6, 2.3), (2.7, 4.6))
    assert [x["lead_frames"] for x in p] == [0, render.JCUT_LEAD_FRAMES]


def test_colado_na_fala_dos_dois_lados_nao_sobrepoe(fonte, tmp_path):
    p = _plano(fonte, tmp_path, (0.6, 2.0), (3.0, 4.6))
    assert [x["lead_frames"] for x in p] == [0, 0]
    assert p[1]["v_in"] == p[1]["a_in"] == 3.0  # a imagem entra junto com a voz
    assert p[1]["a_off"] == pytest.approx(p[1]["v_off"])


def test_pouco_silencio_sobrepoe_so_ele(fonte, tmp_path):
    # 0,1 s de silêncio na cabeça da seguinte e nenhum na cauda da anterior: cabem 2 quadros (66 ms)
    p = _plano(fonte, tmp_path, (0.6, 2.0), (2.9, 4.6))
    assert p[1]["lead_frames"] == 2
    assert p[1]["v_in"] == pytest.approx(2.9 + 2 / FPS)


def _som(video: Path, taxa: int = 48000) -> list[int]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(taxa),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def _goertzel(x, taxa, f):
    k = 2 * math.cos(2 * math.pi * f / taxa)
    s1 = s2 = 0.0
    for v in x:
        s1, s2 = v + k * s1 - s2, s1
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - k * s1 * s2))


def test_no_corte_colado_as_duas_vozes_nunca_tocam_juntas(fonte, tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"F": str(fonte)}, "grade": "",
           "ranges": [{"source": "F", "start": 0.6, "end": 2.0}, {"source": "F", "start": 3.0, "end": 4.6}]}
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(render.__file__)), str(edit / "edl.json"), "-o", str(edit / "out.mp4"),
                        "--draft", "--no-loudnorm", "--no-subtitles"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr[-1500:]
    jt = json.loads((edit / "edl.json").read_text(encoding="utf-8"))["jcut_timeline"]
    assert jt[1]["audio_start_in_output"] == pytest.approx(jt[1]["video_start_in_output"])
    assert jt[1]["lead_frames"] == 0

    som = _som(edit / "out.mp4")
    passo = 480  # 10 ms
    juntas = []
    for i in range(0, len(som) - passo, passo):
        jan = som[i:i + passo]
        e500, e1500 = _goertzel(jan, 48000, 500), _goertzel(jan, 48000, 1500)
        if e500 > 2e5 and e1500 > 2e5:
            juntas.append(round(i / 48000, 3))
    assert not juntas, f"as duas vozes tocaram juntas em {juntas}"
    # e as duas falas estão lá
    meio_a, meio_b = int(0.9 * 48000), int((1.4 + 0.5) * 48000)
    assert _goertzel(som[meio_a:meio_a + passo], 48000, 500) > 2e5
    assert _goertzel(som[meio_b:meio_b + passo], 48000, 1500) > 2e5


# ---------- a prévia do editor: a sobra do J-cut que já veio misturada no cut.mp4 ----------
CELULAR = Path(__file__).resolve().parents[1] / "assets" / "preview" / "celular.js"


def _funcao(fonte: str, nome: str) -> str:
    """O texto de uma função de topo do celular.js (de `function nome(` até a chave de fechamento)."""
    i = fonte.index(f"function {nome}(")
    return fonte[i:fonte.index("\n}\n", i) + 2]


def _sobra(dl: list, k: int, rt: float, lead_quadros: int = 5):
    js = CELULAR.read_text(encoding="utf-8")
    emenda = 2.3
    S = {"fps": FPS, "rendered": [{"start": 0.0, "end": 2.3}, {"start": 2.7, "end": 4.6}],
         "jcut": [{"video_start_in_output": 0.0, "audio_start_in_output": 0.0, "video_duration": emenda},
                  {"video_start_in_output": emenda, "audio_start_in_output": emenda - lead_quadros / FPS,
                   "video_duration": 1.7}]}
    script = (f"const S = {json.dumps(S)};\n"
              + "".join(_funcao(js, n) + "\n" for n in ("jcutGeom", "renderedLayout", "sobraVelha"))
              + f"console.log(JSON.stringify(sobraVelha({json.dumps(dl)}, {k}, {rt})));")
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


A = {"from": 0, "start": 0.0, "end": 2.3}
B = {"from": 1, "start": 2.7, "end": 4.6}
sem_node = pytest.mark.skipif(not __import__("shutil").which("node"), reason="sem Node")


@sem_node
def test_previa_emenda_intacta_toca_como_esta():
    assert _sobra([A, B], 0, 2.2) is False


@sem_node
@pytest.mark.parametrize("dl", [
    [A, {**B, "start": 2.9}],            # o começo da seguinte aparado (o erro tirado)
    [A],                                  # a seguinte tirada
    [{**A, "end": 2.25}, B],              # o fim desta aparado
    [A, {"from": 0, "start": 0.5, "end": 1.0}],  # outra tomada depois (um pedaço copiado)
])
def test_previa_emenda_mexida_cala_so_a_sobra(dl):
    assert _sobra(dl, 0, 2.2) is True     # dentro dos 5 quadros antes da emenda
    assert _sobra(dl, 0, 2.0) is False    # antes deles, a tomada toca normal


@sem_node
def test_previa_sem_sobreposicao_nada_cala():
    assert _sobra([A, {**B, "start": 2.9}], 0, 2.25, lead_quadros=0) is False
    assert _sobra([A, B], 1, 2.5) is False  # a última tomada não tem emenda depois


def test_o_volume_da_previa_passa_pela_sobra():
    js = CELULAR.read_text(encoding="utf-8")
    assert "sobraVelha(dl, k, video.currentTime) ? 0 : volPrevia(dl[k])" in _funcao(js, "syncVolTomada")
