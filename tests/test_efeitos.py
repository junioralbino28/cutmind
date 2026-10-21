"""Os efeitos do projeto: o editor grava, o servidor confere aqui, o render final lê."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import efeitos as ef  # noqa: E402

BOM = {"versao": 1, "itens": [
    {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 2.0, "duracao": 3.5, "intensidade": 0.8},
    {"id": "t1", "tipo": "transicao", "pacote": "zoom-central", "corte": 4.2, "duracao": 1.1}]}


def _copia():
    return json.loads(json.dumps(BOM))


def test_efeitos_bons_passam_e_saem_limpos():
    e = _copia()
    e["lixo"] = 1
    e["itens"][0]["extra"] = "não fica"
    e["itens"][1]["inicio"] = 99  # transição não tem início: só o corte
    assert ef.normalize(e) == BOM


def test_intensidade_e_opcional_e_arredonda():
    e = _copia()
    del e["itens"][0]["intensidade"]
    e["itens"][1]["corte"] = 4.20004
    n = ef.normalize(e)
    assert "intensidade" not in n["itens"][0]  # sem ela, vale a do pacote
    assert n["itens"][1]["corte"] == 4.2


@pytest.mark.parametrize("estrago", [
    lambda e: e["itens"][0].update(tipo="programa"),
    lambda e: e["itens"][0].update(pacote="../fora"),
    lambda e: e["itens"][0].update(pacote="Filme"),
    lambda e: e["itens"][0].update(id="a b"),
    lambda e: e["itens"][1].update(id="f1"),
    lambda e: e["itens"][0].update(intensidade=1.5),
    lambda e: e["itens"][0].update(intensidade=True),
    lambda e: e["itens"][0].update(duracao=0),
    lambda e: e["itens"][0].update(inicio=float("nan")),
    lambda e: e["itens"][1].update(duracao=9),
    lambda e: e["itens"][1].update(corte=-1),
    lambda e: e.update(itens="x"),
    lambda e: e.update(itens=[e["itens"][0]] * 0 + [dict(e["itens"][0], id=f"f{i}", inicio=i * 10)
                                                    for i in range(ef.MAX_ITENS + 1)]),
])
def test_efeitos_com_defeito_sao_recusados(estrago):
    e = _copia()
    estrago(e)
    with pytest.raises(ef.EfeitosInvalidos):
        ef.normalize(e)


def test_dois_filtros_ao_mesmo_tempo_ainda_nao():
    e = _copia()
    e["itens"].append(dict(e["itens"][0], id="f2", inicio=5.0))  # 5,0 cai dentro de 2,0–5,5
    with pytest.raises(ef.EfeitosInvalidos, match="ao mesmo tempo"):
        ef.normalize(e)
    e["itens"][-1]["inicio"] = 5.5  # encostado não é sobreposto
    assert len(ef.normalize(e)["itens"]) == 3


def test_duas_transicoes_que_se_cruzam_sao_recusadas():
    e = _copia()
    e["itens"].append(dict(e["itens"][1], id="t2", corte=4.9))
    with pytest.raises(ef.EfeitosInvalidos, match="transições"):
        ef.normalize(e)


def test_janela_da_transicao_fica_centrada_no_corte():
    assert ef.janela(BOM["itens"][1]) == pytest.approx((3.65, 4.75))
    assert ef.janela(BOM["itens"][0]) == pytest.approx((2.0, 5.5))


def test_salvar_e_ler_o_arquivo_do_projeto(tmp_path):
    p = tmp_path / "efeitos.json"
    assert ef.load(p) == {"versao": 1, "itens": []}
    ef.save(p, _copia())
    assert ef.load(p) == BOM
