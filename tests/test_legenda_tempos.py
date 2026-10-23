"""Pedaço da legenda arrastado no editor: as palavras andam juntas no captions.json."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import legenda_tempos as lt  # noqa: E402


def legenda() -> list[dict]:
    """Seis palavras, 400 ms cada, com 100 ms de folga entre elas."""
    return [{"text": t, "startMs": i * 500, "endMs": i * 500 + 400, "timestampMs": i * 500 + 200, "confidence": None}
            for i, t in enumerate(["um", "dois", "três", "quatro", "cinco", "seis"])]


def test_o_pedaco_anda_inteiro_e_o_resto_fica():
    caps = legenda()
    feitos, fora = lt.aplicar(caps, [{"palavra": 2, "palavras": 2, "deMs": 1000, "paraMs": 1080}])
    assert not fora and len(feitos) == 1
    assert [(c["startMs"], c["endMs"], c["timestampMs"]) for c in caps[2:4]] == [(1080, 1480, 1280), (1580, 1980, 1780)]
    assert caps[1] == legenda()[1] and caps[4] == legenda()[4]


def test_rodar_de_novo_nao_desloca_duas_vezes():
    caps = legenda()
    pedido = [{"palavra": 2, "palavras": 2, "deMs": 1000, "paraMs": 900}]
    lt.aplicar(caps, pedido)
    feitos, fora = lt.aplicar(caps, pedido)
    assert not fora and "já estava" in feitos[0]
    assert caps[2]["startMs"] == 900


def test_nao_passa_por_cima_da_vizinha():
    caps = legenda()
    feitos, fora = lt.aplicar(caps, [{"palavra": 2, "palavras": 1, "deMs": 1000, "paraMs": 1300}])
    assert not feitos and "vizinha" in fora[0]
    assert caps == legenda()


def test_legenda_refeita_depois_do_arraste_fica_de_fora():
    caps = legenda()
    feitos, fora = lt.aplicar(caps, [{"palavra": 2, "palavras": 1, "deMs": 1234, "paraMs": 1100}])
    assert not feitos and "mudou" in fora[0] and caps == legenda()


def test_pelo_preview_edits_do_editor(tmp_path):
    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"captions": "remotion/public/captions.json"}), encoding="utf-8")
    arq = edit / "remotion" / "public" / "captions.json"
    arq.write_text(json.dumps(legenda()), encoding="utf-8")
    (edit / "preview_edits.json").write_text(json.dumps({"editData": {"legenda": {
        "estilo": None, "acompanhar": False,
        "tempos": [{"palavra": 4, "palavras": 2, "deMs": 2000, "paraMs": 2050}]}}}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(HELPERS / "legenda_tempos.py"), str(edit)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr
    caps = json.loads(arq.read_text(encoding="utf-8"))
    assert [c["startMs"] for c in caps] == [0, 500, 1000, 1500, 2050, 2550]
