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


# ---- a janela vai pelo que ficou: o item que cobre a tomada encolhe com ela, não sai ----
def test_janela_da_tomada_aparada_encolhe_com_ela():
    """Um ajuste (ou filtro, ou bloco da Fase 2) que cobre a tomada inteira começa no começo dela;
    aparado o começo, ele continua na tomada, com o que sobrou."""
    levar = rm.mapa(VELHO, NOVO, [0, 1])
    assert levar.janela(0.0, 10.0) == (0.0, 8.0)
    ef = {"versao": 1, "itens": [{"id": "a1", "tipo": "ajuste", "inicio": 0.0, "duracao": 10.0, "ajustes": {"brilho": 20}}]}
    novo, fora = rm.efeitos(ef, levar, [8.0], total=18.0)
    assert not fora and (novo["itens"][0]["inicio"], novo["itens"][0]["duracao"]) == (0.0, 8.0)


def test_janela_toda_no_trecho_tirado_sai():
    assert rm.mapa(VELHO, NOVO, [0, 1]).janela(0.5, 1.5) is None


def test_perto_leva_o_instante_tirado_para_a_borda_da_tomada():
    levar = rm.mapa(VELHO, NOVO, [0, 1])
    assert levar(1.0) is None and levar.perto(1.0) == 0.0
    assert rm.mapa(VELHO, {"ranges": [VELHO["ranges"][1]]}, [1]).perto(4.0) is None  # a tomada inteira saiu


# ---- a Fase 2 no corte novo (Parte B) ----
ED = {"durationSec": 20.0,
      "hook": {"enabled": True, "endSec": 4.0, "text": "oi"},
      "inserts": [{"src": "a.png", "start": 3.0, "end": 5.0}, {"src": "b.png", "start": 0.5, "end": 1.5},
                  {"src": "c.png", "start": 0.5, "end": 1.5, "camada": "i1"}],
      "splitInserts": [{"src": "s.png", "start": 10.0, "end": 20.0}],
      "behind": [{"src": "d.png", "start": 12.0, "dur": 2.0}],
      "numeros": [{"valor": 10, "at": 14.0, "end": 16.0}],
      "cenas": [{"tipo": "vidro", "start": 0.0, "end": 10.0, "at": 1.0, "saiEm": 0.4, "inicio": 0.1,
                 "itens": [{"t": "x", "at": 6.0}]},
                {"tipo": "corteZoom", "at": 1.0},
                {"tipo": "capa", "start": 12.0, "end": 15.0}],
      "captions": {"enabled": True, "windows": [{"start": 10.0, "end": 20.0, "paddingBottom": 900}],
                   "positions": {"all": None, "phrases": [{"at": 1.0, "x": 0.5, "y": 0.3}, {"at": 12.0, "x": 0.5, "y": 0.4}]}},
      "camera": {"zooms": [1.1, 1.3]}}


def test_fase2_leva_blocos_efeitos_e_instantes():
    novo, fora = rm.fase2(ED, rm.mapa(VELHO, NOVO, [0, 1]), total=18.0, origem=[0, 1], n_velhas=2)
    assert [(i["src"], i["start"], i["end"]) for i in novo["inserts"]] == [("a.png", 1.0, 3.0), ("c.png", 0.5, 1.5)]
    assert (novo["splitInserts"][0]["start"], novo["splitInserts"][0]["end"]) == (8.0, 18.0)
    assert (novo["behind"][0]["start"], novo["behind"][0]["dur"]) == (10.0, 2.0)
    assert (novo["numeros"][0]["at"], novo["numeros"][0]["end"]) == (12.0, 14.0)
    vidro = novo["cenas"][0]
    assert (vidro["start"], vidro["end"], vidro["at"]) == (0.0, 8.0, 0.0)  # o instante tirado vai para a borda
    assert vidro["saiEm"] == 0.4 and vidro["inicio"] == 0.1 and vidro["itens"][0]["at"] == 4.0  # relativos ficam
    assert [c["tipo"] for c in novo["cenas"]] == ["vidro", "capa"] and novo["cenas"][1]["start"] == 10.0
    assert novo["hook"]["endSec"] == 2.0
    assert novo["captions"]["windows"] == [{"start": 8.0, "end": 18.0, "paddingBottom": 900}]
    assert [p["at"] for p in novo["captions"]["positions"]["phrases"]] == [0.0, 10.0]
    assert novo["camera"]["zooms"] == [1.1, 1.3]
    assert {(f["item"], f["nome"]) for f in fora} == {("insert", "b.png"), ("cena", "corteZoom")}
    assert ED["inserts"][0]["start"] == 3.0  # o original não muda


def test_fase2_zoom_segue_a_tomada_de_origem():
    trocada = {"ranges": [VELHO["ranges"][1], VELHO["ranges"][0]]}
    novo, _ = rm.fase2(ED, rm.mapa(VELHO, trocada, [1, 0]), total=20.0, origem=[1, 0], n_velhas=2)
    assert novo["camera"]["zooms"] == [1.3, 1.1]
    dup = {"ranges": VELHO["ranges"] + [VELHO["ranges"][0]]}
    novo, _ = rm.fase2(ED, rm.mapa(VELHO, dup, [0, 1, 0]), total=30.0, origem=[0, 1, 0], n_velhas=2)
    assert novo["camera"]["zooms"] == [1.1, 1.3, 1.1]


def test_legenda_leva_as_palavras_e_tira_as_do_trecho_tirado():
    caps = [{"text": "um", "startMs": 500, "endMs": 900, "timestampMs": 700},
            {"text": "dois", "startMs": 3000, "endMs": 3400, "timestampMs": 3200},
            {"text": "três", "startMs": 12000, "endMs": 12500, "timestampMs": 12100}]
    novas, saiu = rm.legenda(caps, rm.mapa(VELHO, NOVO, [0, 1]))
    assert saiu == 1 and [(c["text"], c["startMs"], c["endMs"], c["timestampMs"]) for c in novas] == [
        ("dois", 1000, 1400, 1200), ("três", 10000, 10500, 10100)]


def test_transcricao_do_corte_leva_as_palavras():
    tr = {"language": "pt", "text": "um dois", "words": [{"text": "um", "start": 0.5, "end": 0.9, "type": "word"},
                                                        {"text": "dois", "start": 3.0, "end": 3.4, "type": "word"}]}
    novo = rm.transcricao(tr, rm.mapa(VELHO, NOVO, [0, 1]))
    assert novo["text"] == "dois" and novo["words"] == [{"text": "dois", "start": 1.0, "end": 1.4, "type": "word"}]


def test_fase2_behind_leva_as_palavras_e_marca_o_recorte_que_mudou_de_comeco():
    ed = {"behind": [{"kind": "words", "matte": "fg_w.mov", "start": 12.0, "dur": 2.0, "words": [{"t": "MAS", "at": 12.5}]},
                     {"kind": "image", "src": "x.jpg", "matte": "fg_x.mov", "start": 1.0, "dur": 3.0}]}
    novo, fora = rm.fase2(ed, rm.mapa(VELHO, NOVO, [0, 1]), total=18.0, origem=[0, 1], n_velhas=2)
    so_desloca, aparado = novo["behind"]
    assert (so_desloca["start"], so_desloca["dur"], so_desloca["words"][0]["at"]) == (10.0, 2.0, 10.5)
    assert "_refazerMatte" not in so_desloca      # mesma imagem, só mais cedo: o recorte serve
    assert (aparado["start"], aparado["dur"]) == (0.0, 2.0) and aparado["_refazerMatte"] is True
    assert fora == []
