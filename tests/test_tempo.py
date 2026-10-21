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
