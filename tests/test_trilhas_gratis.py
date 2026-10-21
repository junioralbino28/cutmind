"""Os sites de trilha grátis do painel do celular e os da referência do agente são os mesmos."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _links_do_celular() -> list[str]:
    js = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    bloco = re.search(r"const TRILHAS_GRATIS = \[(.*?)\n\];", js, re.S)
    assert bloco, "TRILHAS_GRATIS sumiu de celular.js"
    return re.findall(r"'(https?://[^']+)'", bloco.group(1))


def test_o_detector_acha_a_lista_do_celular():
    links = _links_do_celular()
    assert len(links) >= 6  # se a regex quebrar, o teste de baixo passaria sem conferir nada
    assert all(u.startswith("https://") for u in links)


def test_todo_site_do_celular_esta_na_referencia():
    ref = (RAIZ / "references" / "trilhas-gratis.md").read_text(encoding="utf-8")
    faltando = [u for u in _links_do_celular() if f"]({u})" not in ref]
    assert not faltando, f"acrescente em references/trilhas-gratis.md: {faltando}"


def test_a_fase_3_aponta_a_referencia():
    assert "references/trilhas-gratis.md" in (RAIZ / "references" / "shortform.md").read_text(encoding="utf-8")
