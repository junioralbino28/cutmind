"""O editor acha cada peça da tela pelo id: um id repetido liga o código à peça errada."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "assets" / "preview" / "celular.html"


def repetidos(html: str) -> dict[str, int]:
    ids = Counter(re.findall(r'\sid="([^"]+)"', html))
    return {k: n for k, n in ids.items() if n > 1}


def test_nenhum_id_repetido_na_tela_do_editor():
    # `$('zoomRange')` devolve o PRIMEIRO elemento com o id: o painel de zoom da tomada, com o
    # mesmo id da régua de zoom da linha do tempo, lia e gravava a régua errada, sem erro nenhum
    assert not repetidos(HTML.read_text(encoding="utf-8"))


def test_o_detector_acha_o_id_repetido():
    # sem este caso, um detector quebrado deixaria o teste de cima sempre verde
    html = HTML.read_text(encoding="utf-8") + '\n<input type="range" id="zoomRange">'
    assert repetidos(html) == {"zoomRange": 2}
