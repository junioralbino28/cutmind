"""O corte leve: o Salvar do editor refaz o cut.mp4 das cópias leves (render.py --leve), em rascunho,
e o Baixar (gerar.py) faz o corte cheio das gravações uma vez, no fim.

O que não pode mudar entre os dois é o TEMPO: cada tomada nos mesmos quadros e a mesma linha do tempo
do J-cut (o silêncio das emendas é medido na gravação, nunca na cópia). Senão a legenda, as camadas e
os efeitos postos sobre o corte leve sairiam do lugar no vídeo final."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(AQUI))
import gerar  # noqa: E402
import proxy  # noqa: E402

FPS = 30
FLASHES = [0.7, 1.6, 2.9, 3.8]  # flash e bipe juntos; entre eles, silêncio (as emendas do J-cut)


@pytest.fixture(scope="module")
def gravacao(tmp_path_factory):
    p = tmp_path_factory.mktemp("leve") / "IMG_0002.MOV"
    janelas = "+".join(f"between(t,{t:.2f},{t + 0.15:.2f})" for t in FLASHES)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s=360x640:r={FPS}:d=5",
                    "-f", "lavfi", "-i", f"aevalsrc='0.4*sin(2*PI*700*t)*({janelas})':s=48000:d=5",
                    "-filter_complex", f"[0:v]geq=lum='255*({janelas.replace('(t,', '(T,')})':cb=128:cr=128[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "60",
                    "-c:a", "aac", "-f", "mov", str(p)], check=True)
    return p


@pytest.fixture
def projeto(gravacao, tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"A": str(gravacao)}, "grade": "",
           "ranges": [{"source": "A", "start": 0.4, "end": 2.2}, {"source": "A", "start": 2.6, "end": 4.6}]}
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    assert proxy.gerar_todas(edit) == 0
    return edit


def _render(edit: Path, *extra: str, saida: str = "cut.mp4") -> None:
    r = subprocess.run([sys.executable, "-X", "utf8", str(AQUI / "render.py"), str(edit / "edl.json"), "-o",
                        str(edit / saida), "--no-subtitles", *extra], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr[-1500:]
    return r.stdout


def _edl(edit: Path) -> dict:
    return json.loads((edit / "edl.json").read_text(encoding="utf-8"))


def _quadros_com_flash(video: Path) -> list[int]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=8:8,format=gray",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    luz = [sum(raw[i:i + 64]) / 64 for i in range(0, len(raw), 64)]
    return [i for i in range(1, len(luz)) if luz[i] >= 128 > luz[i - 1]]


def _tamanho(video: Path) -> tuple[int, int, int]:
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                                   "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", str(video)],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    return s["width"], s["height"], int(s["nb_read_frames"])


def test_o_corte_leve_cai_nos_mesmos_quadros_do_cheio(projeto):
    saida = _render(projeto, "--leve")
    assert "corte leve: 1 gravação(ões) pela cópia leve" in saida
    leve = _edl(projeto)
    assert leve["corte_leve"] is True and (projeto / "clips_draft").is_dir()
    q_leve, (w_leve, h_leve, n_leve) = _quadros_com_flash(projeto / "cut.mp4"), _tamanho(projeto / "cut.mp4")
    assert h_leve == 1280  # rascunho

    _render(projeto, "--como-antes")
    cheio = _edl(projeto)
    assert "corte_leve" not in cheio
    assert _tamanho(projeto / "cut.mp4")[1] == 1920  # na qualidade do corte
    # o tempo é o mesmo: a linha do tempo do J-cut, o número de quadros e onde cada flash cai
    assert leve["jcut_timeline"] == cheio["jcut_timeline"]
    assert leve["total_duration_s"] == cheio["total_duration_s"]
    assert n_leve == _tamanho(projeto / "cut.mp4")[2]
    assert q_leve == _quadros_com_flash(projeto / "cut.mp4") and len(q_leve) >= 3


def test_render_de_conferencia_em_outro_arquivo_nao_mexe_na_marca(projeto):
    _render(projeto, "--leve")
    _render(projeto, saida="conferencia.mp4")  # o agente conferindo um corte: não é o do projeto
    assert _edl(projeto)["corte_leve"] is True


def test_o_baixar_faz_o_corte_cheio_antes_de_entregar(projeto):
    _render(projeto, "--leve")
    assert gerar.o_que_falta(projeto) == ["alta"]
    r = gerar.gerar(projeto)
    assert r["falta"][0] == "alta" and r["entrega"] == "cut.mp4"
    assert not gerar.corte_leve(projeto) and _tamanho(projeto / "cut.mp4")[1] == 1920
    assert gerar.o_que_falta(projeto) == []


def test_os_trechos_do_corte_leve_sao_os_da_pasta_dele(projeto):
    _render(projeto, "--leve")
    assert all(c.parent.name == "clips_draft" for c in gerar._clipes(projeto))
    segs, total = gerar.segmentos_do_corte(projeto, FPS)  # o segments.json da Fase 2 depois de um Salvar
    assert len(segs) == 2 and total == _tamanho(projeto / "cut.mp4")[2]


def test_o_salvar_do_editor_refaz_o_corte_leve():
    fonte = (AQUI / "aplicar_corte.py").read_text(encoding="utf-8")
    assert '"--como-antes", "--leve"]' in fonte
