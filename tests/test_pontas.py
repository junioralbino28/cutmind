"""Pontas seguras (edição real de 01/11: palavra cortada três vezes seguidas num take com ruído de sala alto).

O nível de mentira tem um piso de ruído de -40 dB (o take da reclamação mediu -39,6), palavras a -15 dB e
respiração a -30 dB: o "quieto" desta gravação fica em -33 dB, e a ponta só para depois da respiração.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import pontas  # noqa: E402

PISO = -40.0


def _gravacao(trechos: list[tuple[float, float, float]], dur: float = 12.0) -> np.ndarray:
    """O nível em 10 ms: o piso, e cada (começo, fim, dB) por cima."""
    niv = np.full(int(dur * 100), PISO) + np.random.default_rng(3).normal(0, 0.8, int(dur * 100))
    for a, b, db in trechos:
        niv[int(a * 100):int(b * 100)] = db
    return niv


FALA = [(1.0, 1.6, -15), (1.6, 1.75, -30),  # palavra e a respiração colada nela (acima do quieto, -33)
        (2.2, 2.9, -15), (3.4, 4.0, -15),
        (5.0, 6.5, -15)]  # fala corrida, sem pausa


def _edl(ranges):
    return {"sources": {"A": "a.mp4"}, "ranges": [{"source": "A", **r} for r in ranges]}


def test_o_quieto_e_medido_na_propria_gravacao():
    niv = _gravacao(FALA)
    assert abs(pontas.limiar(niv) - (PISO + pontas.MARGEM_DB)) < 1.5


def test_fim_no_meio_da_palavra_anda_ate_o_silencio_e_comeco_recua():
    niv = _gravacao(FALA)
    edl = _edl([{"start": 1.1, "end": 1.5}, {"start": 3.45, "end": 3.9}])
    mud = {(m["tomada"], m["ponta"]): m for m in pontas.ajustar(edl, Path("."), medir=lambda p: niv)}
    fim = mud[(0, "fim")]
    assert fim["como"] == "até o fim da palavra" and 1.75 < fim["para"] <= 1.75 + 0.05  # passou da respiração
    ini = mud[(0, "inicio")]
    assert ini["como"] == "antes do começo da palavra" and 0.95 <= ini["para"] < 1.0


def test_fim_que_pegou_o_comeco_da_palavra_seguinte_volta():
    niv = _gravacao(FALA)
    edl = _edl([{"start": 2.1, "end": 3.45}])  # 50 ms dentro da palavra seguinte
    m = {x["ponta"]: x for x in pontas.ajustar(edl, Path("."), medir=lambda p: niv)}["fim"]
    assert m["como"] == "antes da palavra seguinte" and 3.35 <= m["para"] < 3.4


def test_rodar_de_novo_nao_muda_nada():
    """O pontas_seguras do projeto mudava a mesma ponta a cada vez (4,525 e depois 4,565)."""
    niv = _gravacao(FALA)
    edl = _edl([{"start": 1.1, "end": 1.5}, {"start": 2.1, "end": 3.45}, {"start": 5.6, "end": 6.0}])
    pontas.aplicar(edl, pontas.ajustar(edl, Path("."), medir=lambda p: niv))
    depois = [m for m in pontas.ajustar(edl, Path("."), medir=lambda p: niv) if m["como"] != "ouvir"]
    assert depois == []


def test_fala_corrida_nao_anda_e_vai_para_ouvir_e_a_ouvida_fica():
    niv = _gravacao(FALA)
    edl = _edl([{"start": 5.6, "end": 6.0}])
    mud = pontas.ajustar(edl, Path("."), medir=lambda p: niv)
    assert {m["ponta"]: m["como"] for m in mud} == {"inicio": "ouvir", "fim": "ouvir"}
    assert pontas.aplicar(edl, mud) == 0 and edl["ranges"][0]["start"] == 5.6
    edl["ranges"][0]["pontas_ouvidas"] = ["inicio", "fim"]
    assert pontas.ajustar(edl, Path("."), medir=lambda p: niv) == []


def test_aplicar_tira_a_linha_do_tempo_do_jcut_velha():
    niv = _gravacao(FALA)
    edl = _edl([{"start": 1.1, "end": 1.5}])
    edl["jcut_timeline"] = [{"out": 0}]
    assert pontas.aplicar(edl, pontas.ajustar(edl, Path("."), medir=lambda p: niv)) == 2
    assert "jcut_timeline" not in edl
    json.dumps(edl)


def test_ponta_depois_do_fim_da_gravacao_e_silencio():
    """No EDL real, uma ponta ficou depois do fim do arquivo (11,583 s num de 11,51): sem som ali, ela andava a
    cada passada."""
    niv = _gravacao(FALA, dur=6.5)  # a gravação acaba no meio da fala corrida
    edl = _edl([{"start": 5.6, "end": 6.58}])
    fim = {m["ponta"]: m for m in pontas.ajustar(edl, Path("."), medir=lambda p: niv)}.get("fim")
    assert fim is None  # quieto: fica
