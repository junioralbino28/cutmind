"""Camadas, efeitos e trechos de velocidade levados do corte antigo para o novo, pela gravação."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import remapear as rm  # noqa: E402

VELHO = {"ranges": [{"source": "A", "start": 0.0, "end": 10.0}, {"source": "A", "start": 20.0, "end": 30.0}]}
# a pessoa aparou o começo da 1ª tomada (0 → 2)
NOVO = {"ranges": [{"source": "A", "start": 2.0, "end": 10.0}, {"source": "A", "start": 20.0, "end": 30.0}]}


def test_instante_vai_pela_gravacao():
    levar = rm.mapa(VELHO, NOVO, [0, 1])
    assert abs(levar(5.0) - 3.0) < 1e-6      # gravação 5 s → corte novo 3 s
    assert abs(levar(15.0) - 13.0) < 1e-6    # gravação 25 s → 8 + 5


def test_instante_que_saiu_do_corte_nao_tem_lugar():
    assert rm.mapa(VELHO, NOVO, [0, 1])(1.0) is None


def test_tomada_duplicada_usa_a_primeira_que_contem():
    dup = {"ranges": VELHO["ranges"] + [{"source": "A", "start": 0.0, "end": 10.0}]}
    assert abs(rm.mapa(VELHO, dup, [0, 1, 0])(4.0) - 4.0) < 1e-6


def test_tomada_com_velocidade_conta_o_tempo_do_corte():
    rapido = {"ranges": [{"source": "A", "start": 0.0, "end": 10.0, "velocidade": 2.0}, VELHO["ranges"][1]]}
    levar = rm.mapa(VELHO, rapido, [0, 1])
    assert abs(levar(4.0) - 2.0) < 1e-6      # gravação 4 s, a 2× → 2 s de corte
    assert abs(levar(15.0) - 10.0) < 1e-6    # a 1ª tomada agora dura 5 s; 5 + 5


def test_tomada_movida_de_lugar():
    trocada = {"ranges": [VELHO["ranges"][1], VELHO["ranges"][0]]}
    levar = rm.mapa(VELHO, trocada, [1, 0])
    assert abs(levar(2.0) - 12.0) < 1e-6
    assert abs(levar(12.0) - 2.0) < 1e-6


def test_camadas_levadas_e_a_que_sumiu_avisada():
    cam = {"versao": 1, "video": {"mudo": False}, "faixas": [{"tipo": "imagem", "itens": [
        {"id": "a", "arquivo": "midia/x.png", "inicio": 4.0, "duracao": 2.0},
        {"id": "b", "arquivo": "midia/y.png", "inicio": 0.5, "duracao": 1.0}]}]}
    novo, fora = rm.camadas(cam, rm.mapa(VELHO, NOVO, [0, 1]), total=18.0)
    itens = novo["faixas"][0]["itens"]
    assert [i["id"] for i in itens] == ["a"] and abs(itens[0]["inicio"] - 2.0) < 1e-6
    assert abs(itens[0]["duracao"] - 2.0) < 1e-3
    assert fora == [{"item": "imagem", "nome": "y.png", "inicio": 0.5}]
    assert cam["faixas"][0]["itens"][0]["inicio"] == 4.0   # o original não muda


def test_camada_que_passa_do_fim_e_encurtada():
    cam = {"versao": 1, "faixas": [{"tipo": "texto", "itens": [{"id": "t", "texto": "oi", "inicio": 17.0, "duracao": 5.0}]}]}
    novo, fora = rm.camadas(cam, rm.mapa(VELHO, NOVO, [0, 1]), total=18.0)
    it = novo["faixas"][0]["itens"][0]
    assert not fora and abs(it["inicio"] - 15.0) < 1e-6 and it["duracao"] <= 3.0 + 1e-6


def test_item_que_sobra_com_quase_nada_no_fim_saiu():
    cam = {"versao": 1, "faixas": [{"tipo": "imagem", "itens": [{"id": "z", "arquivo": "midia/z.png", "inicio": 19.99, "duracao": 2.0}]}]}
    novo, fora = rm.camadas(cam, rm.mapa(VELHO, NOVO, [0, 1]), total=18.0)
    assert novo["faixas"][0]["itens"] == [] and fora[0]["nome"] == "z.png"


def test_transicao_vai_para_a_emenda_nova_ou_sai():
    ef = {"versao": 1, "itens": [{"tipo": "transicao", "pacote": "t-x", "corte": 10.0, "duracao": 0.4}]}
    novo, fora = rm.efeitos(ef, rm.mapa(VELHO, NOVO, [0, 1]), emendas=[8.0], total=18.0)
    assert abs(novo["itens"][0]["corte"] - 8.0) < 1e-6 and not fora
    _, fora = rm.efeitos(ef, rm.mapa(VELHO, NOVO, [0, 1]), emendas=[], total=18.0)
    assert fora == [{"item": "transicao", "nome": "t-x", "inicio": 10.0}]


def test_filtro_levado_e_o_que_sumiu_avisado():
    ef = {"versao": 1, "itens": [{"tipo": "filtro", "pacote": "f-a", "inicio": 3.0, "duracao": 4.0},
                                 {"tipo": "ajuste", "ajustes": {"brilho": 10}, "inicio": 0.0, "duracao": 1.5}]}
    novo, fora = rm.efeitos(ef, rm.mapa(VELHO, NOVO, [0, 1]), emendas=[8.0], total=18.0)
    assert [it["tipo"] for it in novo["itens"]] == ["filtro"] and abs(novo["itens"][0]["inicio"] - 1.0) < 1e-6
    assert fora == [{"item": "ajuste", "nome": "", "inicio": 0.0}]


def test_velocidade_ganha_a_duracao_nova():
    vel = {"versao": 1, "duracao": 20.0, "trechos": [{"inicio": 12.0, "fim": 14.0, "fator": 2.0},
                                                    {"inicio": 0.2, "fim": 1.0, "fator": 1.5}]}
    novo, fora = rm.velocidade(vel, rm.mapa(VELHO, NOVO, [0, 1]), total=18.0)
    assert novo["duracao"] == 18.0 and len(novo["trechos"]) == 1
    assert fora == [{"item": "velocidade", "nome": "1.5×", "inicio": 0.2}]
    assert abs(novo["trechos"][0]["inicio"] - 10.0) < 1e-6 and abs(novo["trechos"][0]["fim"] - 12.0) < 1e-3
