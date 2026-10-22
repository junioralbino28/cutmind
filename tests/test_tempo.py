"""O relógio do corte com a velocidade de cada tomada (helpers/tempo.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import tempo  # noqa: E402

EDL = {"ranges": [{"source": "A", "start": 10.0, "end": 20.0, "velocidade": 2},
                  {"source": "B", "start": 5.0, "end": 9.0, "velocidade": 0.5},
                  {"source": "A", "start": 30.0, "end": 33.0}]}


def test_velocidade_e_recusa():
    assert tempo.velocidade({}) == 1.0 and tempo.velocidade({"velocidade": "1.5"}) == 1.5
    for ruim in (0.2, 4.5, "rápido", float("nan"), True):
        with pytest.raises(ValueError):
            tempo.velocidade({"velocidade": ruim})


def test_sem_jcut_cada_tomada_dura_o_trecho_dividido_pela_velocidade():
    t = tempo.tomadas_no_corte(EDL)
    assert [(s["out"], s["dur"]) for s in t] == [(0.0, 5.0), (5.0, 8.0), (13.0, 3.0)]
    assert tempo.no_corte(t[0], 14.0) == 2.0       # 4 s de gravação a 2× = 2 s de corte
    assert tempo.no_corte(t[1], 6.0) == 5.0 + 2.0  # 1 s de gravação a 0,5× = 2 s


def test_com_jcut_a_imagem_pula_lead_vezes_a_velocidade():
    jt = [{"video_start_in_output": 0.0, "video_duration": 4.9, "audio_start_in_output": 0.0},
          {"video_start_in_output": 4.9, "video_duration": 7.6, "audio_start_in_output": 4.7333},
          {"video_start_in_output": 12.5, "video_duration": 2.8333, "audio_start_in_output": 12.3333}]
    t = tempo.tomadas_no_corte({**EDL, "jcut_timeline": jt})
    lead = 4.9 - 4.7333
    assert t[1]["v_in"] == pytest.approx(5.0 + lead * 0.5) and t[1]["out"] == 4.9
    assert t[1]["v_out"] == pytest.approx(t[1]["v_in"] + 7.6 * 0.5)
    assert tempo.no_corte(t[1], t[1]["v_in"] + 1.0) == pytest.approx(4.9 + 2.0)


MONTAGEM = [[0, 0.9], [0.1, 0.9], [0.5, 6.8], [0.65, 0.3], [0.8, 1], [1, 1]]


def _integral(pts, n=400000):
    """∫ dx / v(x) da reta entre os pontos, na força bruta (o que os pedaços têm de bater)."""
    import numpy as np
    xs = np.linspace(0, 1, n + 1)
    v = np.interp(xs, [p[0] for p in pts], [p[1] for p in pts])
    return float(np.trapezoid(1 / v, xs))


def test_curva_e_recusa():
    assert tempo.curva({}) is None
    assert tempo.curva({"curva": {"nome": "montagem", "pontos": MONTAGEM}})[2] == (0.5, 6.8)
    degrau = [[0, 1], [0.5, 1], [0.5, 3], [1, 3]]  # dois pontos no mesmo x: degrau, como no CapCut
    assert len(tempo.curva({"curva": {"pontos": degrau}})) == 4
    ruins = ([[0, 1]], [[0.1, 1], [1, 1]], [[0, 1], [0.9, 1]], [[0, 1], [0.6, 1], [0.4, 1], [1, 1]],
             [[0, 0.05], [1, 1]], [[0, 1], [1, 11]], [[0, True], [1, 1]], [[0, "x"], [1, 1]],
             [[0, float("nan")], [1, 1]], [[i / 20, 1] for i in range(21)], "montagem")
    for pts in ruins:
        with pytest.raises(ValueError):
            tempo.curva({"curva": {"pontos": pts}})
    with pytest.raises(ValueError):  # curva e velocidade juntas: qual valeria?
        tempo.curva({"curva": {"pontos": MONTAGEM}, "velocidade": 2})


def test_pedacos_somam_a_integral_exata_e_vizinhos_diferem_pouco():
    r = {"start": 10.0, "end": 16.0, "curva": {"pontos": MONTAGEM}}
    p = tempo.pedacos(r)
    assert p[0][0] == 10.0 and p[-1][1] == 16.0
    assert all(abs(a[1] - b[0]) < 1e-12 for a, b in zip(p, p[1:]))  # emendados, sem buraco
    assert tempo.dur_no_corte(r) == pytest.approx(6.0 * _integral(MONTAGEM), rel=1e-6)
    saltos = [max(a[2], b[2]) / min(a[2], b[2]) for a, b in zip(p, p[1:])]
    assert max(saltos) <= 1.04 + 1e-9


def test_sem_curva_e_um_pedaco_so_e_a_conta_da_4c():
    r = {"start": 10.0, "end": 20.0, "velocidade": 2}
    assert tempo.pedacos(r) == [(10.0, 20.0, 2.0)]
    assert tempo.dur_no_corte(r) == 5.0 and tempo.segundos_de_corte_por_segundo(r) == 0.5


def test_ida_e_volta_entre_gravacao_e_corte():
    p = tempo.pedacos({"start": 0.0, "end": 6.0, "curva": {"pontos": MONTAGEM}})
    for s in (0.0, 0.3, 2.9, 3.0, 3.95, 5.5, 6.0):
        assert tempo.gravacao_em(p, tempo.corte_ate(p, s)) == pytest.approx(s, abs=1e-9)
    # no começo da Montagem a velocidade é 0,9: 0,3 s de gravação = 0,333 s de corte
    assert tempo.corte_ate(p, 0.3) == pytest.approx(0.3 / 0.9)


def test_curva_no_relogio_do_corte_sem_e_com_jcut():
    edl = {"ranges": [{"source": "A", "start": 0.0, "end": 3.0},
                      {"source": "A", "start": 10.0, "end": 16.0, "curva": {"pontos": MONTAGEM}}]}
    t = tempo.tomadas_no_corte(edl)
    d = 6.0 * _integral(MONTAGEM)
    assert t[1]["out"] == 3.0 and t[1]["dur"] == pytest.approx(d, rel=1e-6) and t[1]["vel"] is None
    assert tempo.no_corte(t[1], 10.3) == pytest.approx(3.0 + 0.3 / 0.9)
    # J-cut: a imagem entra `lead` de corte depois do som; na gravação pula o que a curva anda nesse tempo
    jt = [{"video_start_in_output": 0.0, "video_duration": 3.0, "audio_start_in_output": 0.0},
          {"video_start_in_output": 3.0, "video_duration": d - 0.1, "audio_start_in_output": 2.9}]
    t = tempo.tomadas_no_corte({**edl, "jcut_timeline": jt})
    assert t[1]["v_in"] == pytest.approx(10.0 + 0.1 * 0.9)
    assert t[1]["v_out"] == pytest.approx(16.0, abs=1e-6)
    assert tempo.no_corte(t[1], 10.3) == pytest.approx(3.0 + (0.3 - 0.09) / 0.9)
