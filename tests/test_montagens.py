"""Os modelos de montagem guardados (montagens.py): o formato, a pasta da pessoa e os do kit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import montagens as mg  # noqa: E402


def test_grava_com_os_iguais_juntos_e_confere():
    m = mg.normalize({"nome": "  Fotos   com zoom ", "drop_na_vaga": 2, "vagas": [
        {"batidas": 2}, {"batidas": 2}, {"batidas": 1, "repetir": 3}, {"batidas": 1, "movimento": "zoom-in"}],
        "textos": [{"nome": "Título", "texto": "OI", "vaga": 1}],
        "transicoes": [{"vaga": 3, "pacote": "t-zoom-central"}], "lixo": "some"})
    assert (m["id"], m["nome"]) == ("fotos-com-zoom", "Fotos com zoom")
    assert m["vagas"] == [{"batidas": 2, "repetir": 2}, {"batidas": 1, "repetir": 3},
                          {"batidas": 1, "movimento": "zoom-in"}]
    assert m["transicoes"] == [{"vaga": 3, "pacote": "t-zoom-central", "duracao": 0.5}]
    assert m["textos"][0]["nome"] == "Título" and "lixo" not in m
    for ruim in ({"vagas": [{"batidas": 1}]},  # sem nome
                 {"nome": "x", "vagas": []},
                 {"nome": "x", "vagas": [{"batidas": 1}], "textos": [{"texto": "a", "vaga": 9}]},
                 {"nome": "x", "vagas": [{"batidas": 1, "repetir": 2}], "transicoes": [{"vaga": 1, "pacote": "t"}]},
                 {"nome": "x", "vagas": [{"batidas": 1}], "textos": [{"texto": "€" * 400, "vaga": 1}] * 20}):  # > 20 KB
        with pytest.raises(mg.MontagemInvalida):
            mg.normalize(ruim)


def test_salvar_listar_obter_apagar():
    a = mg.salvar({"nome": "Rápido", "vagas": [{"batidas": 1, "repetir": 8}]})
    assert (mg.pasta() / "rapido.json").is_file() and mg.obter("rapido")["vagas"] == a["vagas"]
    mg.salvar({"nome": "Rápido", "vagas": [{"batidas": 2, "repetir": 4}]})  # o mesmo nome troca, não duplica
    assert mg.obter("rapido")["vagas"] == [{"batidas": 2, "repetir": 4}]
    assert mg.obter("rapido")["criado"] == a["criado"]
    ids = [m["id"] for m in mg.listar()]
    assert ids[0] == "rapido" and "drop-cedo" in ids  # os da pessoa primeiro, os do kit depois
    assert mg.apagar("rapido") and not mg.obter("rapido") and not mg.apagar("rapido")
    for ruim in ("../x", "", None, "A B"):
        assert mg.obter(ruim) is None and mg.apagar(ruim) is False


def test_os_do_kit_nao_se_apagam_e_o_da_pessoa_vale_no_lugar():
    kit = mg.obter("drop-cedo")
    assert kit["doKit"] and kit["drop_na_vaga"] == 3 and [t["nome"] for t in kit["textos"]] == ["Título", "Chamada"]
    assert mg.apagar("drop-cedo") is False and mg.obter("drop-cedo")
    mg.salvar({"nome": "Drop cedo", "vagas": [{"batidas": 1}]})
    assert not mg.obter("drop-cedo").get("doKit") and mg.obter("drop-cedo")["vagas"] == [{"batidas": 1}]
    assert sum(m["id"] == "drop-cedo" for m in mg.listar()) == 1
    assert mg.apagar("drop-cedo") and mg.obter("drop-cedo")["doKit"]  # apagado o da pessoa, volta o do kit


def test_arquivo_estragado_ou_com_outro_id_fica_de_fora():
    mg.pasta().mkdir(parents=True)
    (mg.pasta() / "quebrado.json").write_text("{", encoding="utf-8")
    (mg.pasta() / "outro-nome.json").write_text(json.dumps({"nome": "Fotos", "vagas": [{"batidas": 1}]}),
                                                encoding="utf-8")
    ids = [m["id"] for m in mg.listar()]
    assert "quebrado" not in ids and "outro-nome" not in ids and "fotos" not in ids


def test_resumo_do_cartao():
    r = mg.resumo(mg.obter("drop-cedo"))
    assert (r["lugares"], r["batidas"], r["ritmo"][:3], r["drop_na_vaga"]) == (34, 40, [4, 4, 1], 3)
    assert r["textos"] == [{"nome": "Título", "vaga": 1, "batidas": 8}, {"nome": "Chamada", "vaga": 3, "batidas": 4}]
    assert r["doKit"] is True and r["transicoes"] == 0
