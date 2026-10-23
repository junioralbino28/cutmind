"""Velocidade do vídeo final (seleção em massa do editor): velocidade.json → final-entrega.mp4.

O final de teste tem um FLASH branco e um BIPE de 1 kHz nos mesmos instantes. Depois de
acelerar um trecho a 2× e desacelerar outro a 0,5×, cada flash tem de cair onde a conta
dos trechos diz, junto do seu bipe (≤ 1 quadro), o bipe continua em 1 kHz e o vídeo dura
a soma de cada pedaço ÷ o seu fator.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import velocidade as vel  # noqa: E402
from test_velocidade_render import FLASHES, FPS, _goertzel, _inicios, _luz_por_quadro, _som  # noqa: E402

TOTAL = 6.5
TRECHOS = [{"inicio": 2.0, "fim": 4.5, "fator": 2}, {"inicio": 5.0, "fim": 6.0, "fator": 0.5}]


def test_normaliza_ordena_e_tira_o_fator_um():
    v = vel.normalize({"duracao": 6.5, "trechos": [
        {"inicio": 5, "fim": 6, "fator": 0.5}, {"inicio": 0.5, "fim": 1, "fator": 1},
        {"inicio": 2.0001, "fim": 4.49999, "fator": 2}]})
    assert v == {"versao": 1, "duracao": 6.5, "trechos": [
        {"inicio": 2.0, "fim": 4.5, "fator": 2.0}, {"inicio": 5.0, "fim": 6.0, "fator": 0.5}]}
    assert vel.normalize({}) == vel.vazio()


@pytest.mark.parametrize("trechos, motivo", [
    ([{"inicio": 1, "fim": 3, "fator": 2}, {"inicio": 2.5, "fim": 4, "fator": 1.5}], "cruzam"),
    ([{"inicio": 1, "fim": 1.05, "fator": 2}], "curto"),
    ([{"inicio": 1, "fim": 2, "fator": 8}], "fator"),
    ([{"inicio": 1, "fim": 2, "fator": True}], "fator"),
    ([{"inicio": -1, "fim": 2, "fator": 2}], "inicio"),
    ("tudo", "trechos"),
])
def test_recusa_o_que_nao_da_para_aplicar(trechos, motivo):
    with pytest.raises(vel.VelocidadeInvalida, match=motivo):
        vel.normalize({"trechos": trechos})


def test_adiantamento_do_atempo_entre_os_medidos():
    import velocidade_final as vf
    assert vf.adiantamento(0.5) == pytest.approx(26.0)
    assert vf.adiantamento(0.1) == vf.ADIANTA_MS[0.25] and vf.adiantamento(9) == vf.ADIANTA_MS[4.0]
    a, b = sorted((vf.ADIANTA_MS[1.25], vf.ADIANTA_MS[1.5]))
    assert a <= vf.adiantamento(1.4) <= b


def test_pedacos_cobrem_o_video_inteiro():
    v = {"trechos": TRECHOS}
    assert vel.pedacos(v, TOTAL) == [(0.0, 2.0, 1.0), (2.0, 4.5, 2), (4.5, 5.0, 1.0), (5.0, 6.0, 0.5), (6.0, 6.5, 1.0)]
    # o trecho que passa do fim é cortado nele; o que começa depois do fim some
    assert vel.pedacos({"trechos": [{"inicio": 6.0, "fim": 9.0, "fator": 2}, {"inicio": 9.5, "fim": 10, "fator": 2}]},
                       TOTAL) == [(0.0, 6.0, 1.0), (6.0, 6.5, 2)]
    assert vel.duracao_entregue(v, TOTAL) == pytest.approx(2.0 + 1.25 + 0.5 + 2.0 + 0.5)


@pytest.fixture(scope="module")
def projeto(tmp_path_factory):
    """Um <edit> com final.mp4 (H.264 + AAC, como o mixar_final.py entrega) e o state.json."""
    edit = tmp_path_factory.mktemp("velf") / "edit"
    edit.mkdir()
    janelas = "+".join(f"between(t,{t:.2f},{t + 0.1:.2f})" for t in FLASHES)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s=160x284:r={FPS}:d={TOTAL}",
                    "-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*1000*t)*({janelas})':s=48000:d={TOTAL}",
                    "-filter_complex", f"[0:v]geq=lum='255*({janelas.replace('(t,', '(T,')})':cb=128:cr=128[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "1",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(edit / "final.mp4")], check=True)
    return edit


def _rodar(edit: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HELPERS / "velocidade_final.py"), str(edit), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONUTF8": "1"})


def _preparar(edit: Path, velocidade: dict, extra: dict | None = None) -> None:
    (edit / "state.json").write_text(json.dumps({"project": "Teste", "phase": 2, "video": "cut.mp4",
                                                 "finalVideo": "final.mp4", **(extra or {})}), encoding="utf-8")
    (edit / "velocidade.json").write_text(json.dumps(velocidade), encoding="utf-8")


def _no_entregue(t: float) -> float:
    """Onde o instante t do final cai no vídeo entregue."""
    out = 0.0
    for a, b, f in vel.pedacos({"trechos": TRECHOS}, TOTAL):
        if t < b:
            return out + (t - a) / f
        out += (b - a) / f
    return out


def test_acelera_tudo_junto_imagem_som_e_tom(projeto):
    _preparar(projeto, {"versao": 1, "duracao": TOTAL, "trechos": TRECHOS})
    r = _rodar(projeto)
    assert r.returncode == 0, r.stderr[-1500:]
    saida = projeto / "final-entrega.mp4"
    assert json.loads((projeto / "state.json").read_text(encoding="utf-8"))["entregaVideo"] == "final-entrega.mp4"

    luz = _luz_por_quadro(saida)
    esperado = vel.duracao_entregue({"trechos": TRECHOS}, TOTAL) * FPS
    assert abs(len(luz) - esperado) <= 1, (len(luz), esperado)

    flashes = _inicios(luz, 128, 1 / FPS)
    previstos = [_no_entregue(t) for t in FLASHES]
    assert len(flashes) == len(previstos), (flashes, previstos)
    som = [abs(x) for x in _som(saida)]
    env = [max(som[i:i + 48]) for i in range(0, len(som), 48)]  # envelope em blocos de 1 ms
    bipes = _inicios(env, 4000, 0.001)
    sinal = _som(saida)
    for f, p in zip(flashes, previstos):
        assert abs(f - p) <= 1 / FPS + 1e-6, (f, p)  # a imagem no lugar certo (no quadro mais perto)
        b = min(bipes, key=lambda x: abs(x - p))
        # o som no instante certo: sem compensar o atempo, a 0,5× ele vinha 34 ms antes (medido)
        assert abs(b - p) <= 0.015, (p, b)
        assert abs(b - f) <= 1 / FPS, (f, b)  # e junto da imagem
        janela = sinal[int((f + 0.01) * 48000):int((f + 0.03) * 48000)]
        assert _goertzel(janela, 48000, 1000) > 8 * _goertzel(janela, 48000, 2000), f  # o tom fica


def test_final_de_outra_duracao_nao_e_acelerado(projeto):
    """O corte foi refeito depois de marcar: os trechos podem estar no lugar errado."""
    _preparar(projeto, {"versao": 1, "duracao": 9.0, "trechos": TRECHOS})
    (projeto / "final-entrega.mp4").unlink(missing_ok=True)
    r = _rodar(projeto)
    assert r.returncode == 2 and "não apliquei" in r.stderr
    assert not (projeto / "final-entrega.mp4").exists()
    assert "entregaVideo" not in json.loads((projeto / "state.json").read_text(encoding="utf-8"))


def test_sem_trechos_o_final_volta_a_ser_a_entrega(projeto):
    _preparar(projeto, {"versao": 1, "trechos": []}, {"entregaVideo": "final-entrega.mp4"})
    (projeto / "final-entrega.mp4").write_bytes(b"velho")
    r = _rodar(projeto)
    assert r.returncode == 0, r.stderr
    assert not (projeto / "final-entrega.mp4").exists()
    state = json.loads((projeto / "state.json").read_text(encoding="utf-8"))
    assert "entregaVideo" not in state and state["finalVideo"] == "final.mp4"
