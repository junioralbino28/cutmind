"""O painel de Texto põe tamanho, cor e contorno antes da grade de fontes.

No teste real de 23/10 a grade de fontes vinha primeiro: na coluna do computador ela ocupava
a altura toda, e o resto ficou fora da vista ("não tem como mudar o tamanho"; "a cor e o
contorno não aparecem, só o tipo de letra"). Os três painéis de texto (camada, efeito e
legenda) seguem a mesma ordem. O teste lê a fonte do editor.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

JS = (Path(__file__).resolve().parents[1] / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
PAINEIS = ("openTextoCamada", "openCenaTexto", "openLegendaTexto")


def corpo(nome: str, js: str = JS) -> str:
    m = re.search(rf"\nfunction {nome}\(.*?\n}}\n", js, re.S)
    assert m, f"não achei a função {nome} no celular.js"
    return m.group(0)


def ordem(trecho: str) -> list[str]:
    """Os campos do painel na ordem em que são montados."""
    achados = [(m.start(), m.group(1)) for m in re.finditer(r"campoTexto\(box, (?:t\()?'([A-Za-zçã]+)'\)?\)", trecho)]
    achados += [(m.start(), "Contorno") for m in re.finditer(r"campoContorno\(box", trecho)]
    achados += [(m.start(), "Fonte") for m in re.finditer(r"fonteGrade\(box", trecho)]
    return [n for _, n in sorted(achados)]


@pytest.mark.parametrize("painel", PAINEIS)
def test_tamanho_cor_e_contorno_vem_antes_das_fontes(painel):
    campos = ordem(corpo(painel))
    assert "Fonte" in campos and "Tamanho" in campos, campos
    fonte = campos.index("Fonte")
    for campo in ("Tamanho", "Cor", "Contorno"):
        if campo in campos:
            assert campos.index(campo) < fonte, f"{painel}: {campo} depois das fontes ({campos})"


def test_o_detector_acha_a_ordem_errada():
    # o painel antigo, com as fontes primeiro, tem de reprovar: sem isto o teste de cima
    # passaria com um detector quebrado
    antigo = ("\nfunction openTextoCamada() {\n  fonteGrade(box, e.fonte, f);\n"
              "  paletaCores(campoTexto(box, 'Cor'), e.cor);\n  regua(campoTexto(box, 'Tamanho'), 20);\n}\n")
    campos = ordem(corpo("openTextoCamada", antigo))
    assert campos == ["Fonte", "Cor", "Tamanho"]
    assert campos.index("Tamanho") > campos.index("Fonte")


def test_cor_do_contorno_liga_um_contorno_que_se_ve():
    c = corpo("campoContorno")
    assert re.search(r"CONTORNO_VISIVEL", c) and re.search(r"reguaPoe\(r, CONTORNO_VISIVEL\)", c)
    assert int(re.search(r"const CONTORNO_VISIVEL = (\d+);", JS).group(1)) >= 4
