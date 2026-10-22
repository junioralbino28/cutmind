"""O guia das edições pelo chat (references/pelo-chat.md) cobre toda ferramenta do editor.

Ele espelha o editor à mão: uma ferramenta nova sem receita ali é uma edição que só o
editor sabe fazer, e o agente de outra pessoa não a acharia. Os testes leem a fonte (o
código do editor) e falham com o nome do que falta.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
JS = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
GUIA = (RAIZ / "references" / "pelo-chat.md").read_text(encoding="utf-8")


def ferramentas() -> list[str]:
    return sorted(set(re.findall(r"tool\((?:tb|ctx), '([a-z0-9-]+)'", JS)))


def curvas() -> list[tuple[str, str]]:
    bloco = re.search(r"const CURVAS = \[(.*?)\n\];", JS, re.S)
    assert bloco, "não achei o CURVAS no celular.js"
    return re.findall(r"\['([a-z]+)', '[^']*', (\[\[.*?\]\])\]", bloco.group(1))


def test_o_detector_acha_as_ferramentas():
    f = ferramentas()
    assert len(f) >= 25 and {"dividir", "velocidade", "filtros", "trilhas", "melhorar"} <= set(f)


def test_toda_ferramenta_do_editor_tem_receita_no_guia():
    faltam = [t for t in ferramentas() if f"`{t}`" not in GUIA]
    assert not faltam, f"ferramenta do editor sem receita em references/pelo-chat.md: {faltam}"


def test_o_detector_acha_as_curvas():
    nomes = [n for n, _ in curvas()]
    assert len(nomes) == 7 and {"heroi", "montagem", "personalizar"} <= set(nomes)


def test_as_curvas_do_guia_sao_as_do_editor():
    for nome, pontos in curvas():
        assert f"`{pontos}`" in GUIA, f"a curva {nome} do editor mudou: atualize a tabela do guia"


def test_os_testes_citados_existem():
    citados = set(re.findall(r"`tests/(test_[a-z_]+\.py)`", GUIA))
    assert len(citados) >= 8
    faltam = [t for t in sorted(citados) if not (RAIZ / "tests" / t).exists()]
    assert not faltam, f"o guia cita testes que não existem: {faltam}"


def test_o_skill_aponta_para_o_guia():
    assert "references/pelo-chat.md" in (RAIZ / "SKILL.md").read_text(encoding="utf-8")
