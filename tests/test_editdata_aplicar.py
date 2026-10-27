"""Os dados da Fase 2 do Salvar (editData) gravados no edit-data.json sem o agente (editdata_aplicar.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import editdata_aplicar as eda  # noqa: E402


def ed():
    return {"inserts": [{"src": "a.png", "start": 1.0, "end": 2.0}],
            "splitInserts": [{"src": "s.png", "label": "Tela", "start": 6.0, "end": 7.0}],
            "behind": [{"src": "b.png", "start": 3.0, "dur": 1.0}],
            "wordAccents": [{"text": "UAU", "start": 8.0, "end": 8.5}],
            "numeros": [{"valor": 10, "at": 4.0, "end": 5.0}],
            "hook": {"enabled": True, "endSec": 4.0, "lines": ["um", "dois"]},
            "cenas": [{"tipo": "fundo", "start": 0.0, "end": 2.0, "fundo": "a.jpg", "escurecer": 0.3},
                      {"tipo": "palavra", "start": 3.0, "end": 4.0, "palavra": "OI",
                       "batidas": [{"palavra": "um", "t": 3.1}, {"palavra": "dois", "t": 3.5}]}],
            "captions": {"enabled": True, "estilo": {"cor": "#fff"}},
            "camera": {"zooms": [1.0, 1.1]}}


def test_blocos_por_ref_com_os_nomes_do_editor():
    d = ed()
    eda.aplicar(d, {"inserts": [{"ref": 0, "start": 1.5, "end": 2.5}], "behind": [{"ref": 0, "start": 3.5, "dur": 0.8}],
                    "splitInserts": [{"ref": 0, "label": "Tela", "start": 6.5, "end": 7.5}],
                    "wordAccents": [{"ref": 0, "text": "UAU", "start": 8.1, "end": 8.6}],
                    "numeros": [{"ref": 0, "at": 4.2, "end": 5.2}], "hook": {"endSec": 3.0}})
    assert (d["inserts"][0]["start"], d["behind"][0]["dur"], d["numeros"][0]["at"], d["hook"]["endSec"]) == (1.5, 0.8, 4.2, 3.0)
    assert d["splitInserts"][0] == {"src": "s.png", "label": "Tela", "start": 6.5, "end": 7.5}
    assert d["wordAccents"][0] == {"text": "UAU", "start": 8.1, "end": 8.6}


def test_ref_que_nao_existe_e_avisado_e_nao_quebra():
    d = ed()
    depois, avisos = eda.aplicar(d, {"inserts": [{"ref": 9, "start": 0, "end": 1}, {"ref": True, "start": 0, "end": 1}]})
    assert len(avisos) == 2 and "inserts" in avisos[0] and d["inserts"] == ed()["inserts"]


def test_texto_do_gancho_tira_as_linhas():
    d = ed()
    eda.aplicar(d, {"destaques": [{"alvo": "hook", "textos": {"text": "novo"}, "texto": {"x": 540, "y": 300}}]})
    assert d["hook"]["text"] == "novo" and "lines" not in d["hook"] and d["hook"]["texto"] == {"x": 540, "y": 300}


def test_gancho_so_com_estilo_mantem_as_duas_linhas():
    """O editor manda o texto do gancho junto (as linhas juntadas com espaço): igual ao de antes, as
    linhas ficam como o agente fez."""
    d = ed()
    eda.aplicar(d, {"destaques": [{"alvo": "hook", "textos": {"text": "um dois"}, "texto": None,
                                   "estilo": {"cor": "#ff0000"}}]})
    assert d["hook"]["lines"] == ["um", "dois"] and "text" not in d["hook"] and d["hook"]["estilo"] == {"cor": "#ff0000"}
    eda.aplicar(d, {"destaques": [{"alvo": "hook", "textos": {"text": "um dois"}, "texto": None, "estilo": None}]})
    assert "estilo" not in d["hook"] and "texto" not in d["hook"]


def test_numero_guarda_valor_como_numero():
    d = ed()
    eda.aplicar(d, {"destaques": [{"alvo": "numero", "ref": 0, "textos": {"valor": "12,5", "sufixo": "%", "rotulo": "a mais"}}]})
    assert d["numeros"][0]["valor"] == 12.5 and d["numeros"][0]["sufixo"] == "%" and d["numeros"][0]["rotulo"] == "a mais"


def test_legenda_sem_estilo_tira_a_chave_e_pede_rastreio_ao_acompanhar():
    d = ed()
    depois, _ = eda.aplicar(d, {"legenda": {"estilo": None, "acompanhar": True}})
    assert "estilo" not in d["captions"] and d["captions"]["acompanhar"] is True and "camadas" in depois


def test_efeito_novo_entra_e_o_desligado_nao():
    d = ed()
    depois, _ = eda.aplicar(d, {"cenas": [{"nova": True, "tipo": "fundo", "start": 5.0, "end": 6.0,
                                           "campos": {"fundo": "b.jpg", "escurecer": 0.5, "desfoque": 8}},
                                          {"nova": True, "tipo": "fundo", "start": 7.0, "end": 8.0, "desligada": True},
                                          {"ref": 0, "desligada": True}]})
    assert len(d["cenas"]) == 3 and d["cenas"][0]["desligada"] is True and "cenas" in depois
    assert d["cenas"][2] == {"tipo": "fundo", "start": 5.0, "end": 6.0, "fundo": "b.jpg", "escurecer": 0.5, "desfoque": 8}


def test_efeito_com_ref_grava_texto_posicao_estilo_e_campos():
    d = ed()
    eda.aplicar(d, {"cenas": [{"ref": 1, "tipo": "palavra", "desligada": False, "texto": {"x": 500, "y": 900},
                               "textos": {"palavra": "OLÁ", "batidas": ["três", "quatro"]}, "estilo": {"peso": 800}},
                              {"ref": 0, "tipo": "fundo", "desligada": False, "texto": None, "textos": {}, "estilo": None,
                               "campos": {"fundo": "c.jpg", "escurecer": 0.1, "desfoque": 4}}]})
    c1, c0 = d["cenas"][1], d["cenas"][0]
    assert c1["palavra"] == "OLÁ" and [b["palavra"] for b in c1["batidas"]] == ["três", "quatro"]
    assert c1["batidas"][0]["t"] == 3.1 and c1["texto"] == {"x": 500, "y": 900} and c1["estilo"] == {"peso": 800}
    assert "desligada" not in c1
    assert (c0["fundo"], c0["escurecer"], c0["desfoque"]) == ("c.jpg", 0.1, 4) and "texto" not in c0


def test_zoom_e_a_lista_inteira():
    d = ed()
    eda.aplicar(d, {"camera": {"zooms": [1.2, 1.0], "mudou": [0]}})
    assert d["camera"]["zooms"] == [1.2, 1.0]


def test_gravar_no_projeto_e_mover_a_legenda(tmp_path):
    pub = tmp_path / "remotion" / "public"
    pub.mkdir(parents=True)
    (tmp_path / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json",
                                                     "captions": "remotion/public/captions.json"}), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps(ed()), encoding="utf-8")
    caps = [{"text": "oi", "startMs": 1000, "endMs": 1300, "timestampMs": 1150},
            {"text": "tudo", "startMs": 2000, "endMs": 2300, "timestampMs": 2150}]
    (pub / "captions.json").write_text(json.dumps(caps), encoding="utf-8")
    r = eda.gravar(tmp_path, {"hook": {"endSec": 2.5},
                              "legenda": {"estilo": {"cor": "#fff"}, "acompanhar": False,
                                          "tempos": [{"palavra": 1, "palavras": 1, "deMs": 2000, "paraMs": 2500}]}})
    salvo = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    assert salvo["hook"]["endSec"] == 2.5
    assert json.loads((pub / "captions.json").read_text(encoding="utf-8"))[1]["startMs"] == 2500
    assert r["avisos"] == [] and r["legenda"] == 1
    feitos = json.loads((tmp_path / "ajustes_feitos.json").read_text(encoding="utf-8"))["feitos"]
    assert feitos[-1]["oque"].startswith("vídeo final:")
