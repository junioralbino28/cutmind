"""O assets/preview/tempo.js dos editores faz a mesma conta do helpers/tempo.py: as mesmas
curvas viram os mesmos pedaços, e os dois relógios batem número a número."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import tempo  # noqa: E402

CURVAS = {
    "montagem": [[0, 0.9], [0.1, 0.9], [0.5, 6.8], [0.65, 0.3], [0.8, 1], [1, 1]],
    "heroi": [[0, 1], [0.05, 1], [0.35, 5.5], [0.45, 0.5], [0.55, 0.5], [0.65, 5.5], [0.95, 1], [1, 1]],
    "degrau": [[0, 1], [0.5, 1], [0.5, 3], [1, 3]],
    "plana": [[0, 1], [0.25, 1], [0.5, 1], [0.75, 1], [1, 1]],
}
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem Node")


def _js(codigo: str):
    script = (f"const Tempo = require({json.dumps(str(RAIZ / 'assets' / 'preview' / 'tempo.js'))});\n"
              f"console.log(JSON.stringify((() => {{ {codigo} }})()));")
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


@pytest.mark.parametrize("nome", sorted(CURVAS))
def test_mesmos_pedacos_e_mesmos_relogios(nome):
    pts = CURVAS[nome]
    py = tempo.pedacos({"start": 2.0, "end": 8.0, "curva": {"pontos": pts}})
    js = _js(f"return Tempo.pedacos(2, 8, 1, {{pontos: {json.dumps(pts)}}});")
    assert len(js) == len(py)
    for a, b in zip(js, py):
        assert a == pytest.approx(list(b), abs=1e-12)
    for s in (2.0, 3.3, 5.0, 6.71, 8.0):
        assert _js(f"const p = Tempo.pedacos(2, 8, 1, {{pontos: {json.dumps(pts)}}}); return Tempo.corteAte(p, {s});") \
            == pytest.approx(tempo.corte_ate(py, s), abs=1e-12)


def test_sem_curva_a_conta_de_sempre():
    assert _js("return Tempo.pedacos(10, 20, 2, null);") == [[10, 20, 2]]
    assert _js("return Tempo.corteAte(Tempo.pedacos(10, 20, 2, null), 14);") == 2


def test_dividir_a_curva_mantem_a_velocidade_de_cada_ponto():
    pts = CURVAS["montagem"]
    esq, dir_ = _js(f"return Tempo.cortarCurva({json.dumps(pts)}, 0.3);")
    assert esq[0][0] == 0 and esq[-1][0] == 1 and dir_[0][0] == 0 and dir_[-1][0] == 1
    inteira = tempo.pedacos({"start": 0.0, "end": 10.0, "curva": {"pontos": pts}})
    a = tempo.pedacos({"start": 0.0, "end": 3.0, "curva": {"pontos": esq}})
    b = tempo.pedacos({"start": 3.0, "end": 10.0, "curva": {"pontos": dir_}})
    # as duas metades somam o mesmo tempo de corte que a tomada inteira
    assert tempo.corte_ate(a, 3.0) + tempo.corte_ate(b, 10.0) == pytest.approx(tempo.corte_ate(inteira, 10.0), rel=1e-4)
