"""As imagens das camadas viram inserts no edit-data.json, sem mexer nos inserts do agente."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from camadas_edit_data import aplicar  # noqa: E402


@pytest.fixture
def projeto(tmp_path):
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    (edit / "midia").mkdir()
    (edit / "midia" / "Print do repositório.png").write_bytes(b"png1")
    (edit / "midia" / "outro.jpg").write_bytes(b"jpg2")
    (edit / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    agente = {"src": "inserts/grafico.png", "start": 1.0, "end": 2.0}
    (public / "edit-data.json").write_text(json.dumps({"fps": 30, "inserts": [agente]}), encoding="utf-8")
    return edit, public, agente


def _camadas(edit, faixas):
    (edit / "camadas.json").write_text(json.dumps({"versao": 1, "video": {"mudo": False}, "faixas": faixas},
                                                  ensure_ascii=False), encoding="utf-8")


def _img(fid, arquivo, inicio, duracao, oculto=False):
    return {"id": fid, "tipo": "imagem", "oculto": oculto, "travado": False,
            "itens": [{"id": f"{fid}-1", "arquivo": arquivo, "inicio": inicio, "duracao": duracao}]}


def _inserts(public):
    return json.loads((public / "edit-data.json").read_text(encoding="utf-8"))["inserts"]


def test_imagem_visivel_vira_insert_e_a_escondida_fica_fora(projeto):
    edit, public, agente = projeto
    _camadas(edit, [_img("i1", "midia/Print do repositório.png", 5, 3),
                    _img("i2", "midia/outro.jpg", 9, 2, oculto=True)])
    r = aplicar(edit)
    assert r == {"inserts": 1, "textos": 0, "faltando": [], "pendentes": [], "feitos": []}
    ins = _inserts(public)
    assert ins[0] == agente  # o do agente fica, no mesmo lugar
    assert ins[1] == {"src": "midia/camada-i1-1.png", "start": 5.0, "end": 8.0, "camada": "i1-1"}
    assert (public / "midia" / "camada-i1-1.png").read_bytes() == b"png1"  # nome sem espaço nem acento
    assert not (public / "midia" / "camada-i2-1.jpg").exists()


def test_rodar_de_novo_nao_duplica_e_o_que_saiu_sai_do_video(projeto):
    edit, public, agente = projeto
    _camadas(edit, [_img("i1", "midia/Print do repositório.png", 5, 3), _img("i2", "midia/outro.jpg", 9, 2)])
    aplicar(edit)
    aplicar(edit)
    assert [i.get("camada") for i in _inserts(public)] == [None, "i1-1", "i2-1"]
    _camadas(edit, [_img("i2", "midia/outro.jpg", 9, 2)])  # a pessoa excluiu o print
    aplicar(edit)
    assert [i.get("camada") for i in _inserts(public)] == [None, "i2-1"]
    assert not (public / "midia" / "camada-i1-1.png").exists()  # a cópia antiga também sai


def test_arquivo_que_sumiu_e_avisado(projeto):
    edit, public, _ = projeto
    _camadas(edit, [_img("i1", "midia/nao-existe.png", 5, 3)])
    r = aplicar(edit)
    assert (r["inserts"], r["faltando"]) == (0, ["midia/nao-existe.png"])
    assert [i.get("camada") for i in _inserts(public)] == [None]


def _txt(fid, *itens, oculto=False):
    return {"id": fid, "tipo": "texto", "oculto": oculto, "travado": False,
            "itens": [{"id": f"{fid}-{n}", "duracao": 2, **it} for n, it in enumerate(itens, 1)]}


def _textos(public):
    return json.loads((public / "edit-data.json").read_text(encoding="utf-8")).get("textos")


@pytest.fixture
def ferramentas(monkeypatch):
    """Faz de conta o recorte e o rastreio: grava o arquivo pedido e anota a chamada."""
    import camadas_edit_data as ced
    chamadas = []

    def falso(cmd):
        chamadas.append(cmd)
        saida = Path(cmd[cmd.index("-o") + 1])
        if "face_track.py" in cmd[3]:
            saida.write_text(json.dumps({"fps": 30, "points": [[0.5, 0.4]] * 10}), encoding="utf-8")
        else:
            saida.write_bytes(b"mov")
        return True
    monkeypatch.setattr(ced, "_rodar", falso)
    return chamadas


def test_texto_visivel_vai_para_o_edit_data_e_o_escondido_nao(projeto):
    edit, public, _ = projeto
    _camadas(edit, [_txt("t1", {"texto": "Olá\nmundo", "inicio": 2, "x": 300, "y": 500,
                                "estilo": {"fonte": "Anton", "cor": "#FFE500"}, "curva": 40}),
                    _txt("t2", {"texto": "escondido", "inicio": 4}, oculto=True)])
    r = aplicar(edit)
    assert (r["textos"], r["pendentes"], r["feitos"]) == (1, [], [])
    assert _textos(public) == [{"id": "t1-1", "texto": "Olá\nmundo", "start": 2.0, "end": 4.0, "x": 300.0, "y": 500.0,
                                "estilo": {"fonte": "Anton", "cor": "#ffe500"}, "curva": 40.0}]
    # o template importa o rastreio: sem ninguém pedir, ele existe e fica neutro
    assert json.loads((public / "rastreio.json").read_text(encoding="utf-8")) == {"neutral": True, "points": []}


def test_projeto_sem_texto_nao_ganha_a_lista(projeto):
    edit, public, _ = projeto
    _camadas(edit, [_img("i1", "midia/outro.jpg", 9, 2)])
    aplicar(edit)
    assert _textos(public) is None


def test_atras_da_pessoa_faz_o_recorte_da_janela_em_quadros(projeto, ferramentas):
    edit, public, _ = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    _camadas(edit, [_txt("t1", {"texto": "atrás", "inicio": 1.01, "duracao": 2.0, "atras": True})])
    r = aplicar(edit)
    assert r["feitos"] == ["pessoa-t1-1-30-60.mov"] and r["pendentes"] == []
    cmd = ferramentas[0]
    assert cmd[cmd.index("--start") + 1] == "1.000000" and cmd[cmd.index("--duration") + 1] == "2.000000"
    assert _textos(public)[0]["matte"] == "pessoa-t1-1-30-60.mov"
    aplicar(edit)  # de novo: o recorte já existe, nada roda
    assert len(ferramentas) == 1
    # mudou a janela: o recorte velho sai e outro é feito
    _camadas(edit, [_txt("t1", {"texto": "atrás", "inicio": 3, "duracao": 2.0, "atras": True})])
    aplicar(edit)
    assert sorted(p.name for p in public.glob("pessoa-*")) == ["pessoa-t1-1-90-60.mov"]
    # escondido, guarda o recorte; excluído, o recorte sai
    _camadas(edit, [_txt("t1", {"texto": "atrás", "inicio": 3, "duracao": 2.0, "atras": True}, oculto=True)])
    aplicar(edit)
    assert (public / "pessoa-t1-1-90-60.mov").exists() and _textos(public) == []
    _camadas(edit, [])
    aplicar(edit)
    assert not list(public.glob("pessoa-*"))


def test_sem_recorte_avisa_o_comando_e_o_texto_sai_na_frente(projeto):
    edit, public, _ = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    _camadas(edit, [_txt("t1", {"texto": "atrás", "inicio": 1, "atras": True, "acompanhar": True})])
    r = aplicar(edit, recortar=False)
    assert len(r["pendentes"]) == 2 and "person_matte.py" in r["pendentes"][0] and "face_track.py" in r["pendentes"][1]
    t = _textos(public)[0]
    assert "matte" not in t and t["acompanhar"] is True


def test_acompanhar_rastreia_o_rosto_quando_falta_ou_ficou_velho(projeto, ferramentas):
    import os
    edit, public, _ = projeto
    cut = public / "cut.mp4"
    cut.write_bytes(b"mp4")
    _camadas(edit, [_txt("t1", {"texto": "segue", "inicio": 1, "acompanhar": True})])
    assert aplicar(edit)["feitos"] == ["rastreio.json"]
    assert aplicar(edit)["feitos"] == []  # rastreio novo: não refaz
    os.utime(public / "rastreio.json", (cut.stat().st_mtime - 60,) * 2)  # o corte mudou depois do rastreio
    assert aplicar(edit)["feitos"] == ["rastreio.json"]
    assert [c[3].endswith("face_track.py") for c in ferramentas] == [True, True]


def test_imagem_atras_da_pessoa_vira_behind_no_quadro_do_recorte(projeto, ferramentas):
    edit, public, agente = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    d = json.loads((public / "edit-data.json").read_text(encoding="utf-8"))
    do_agente = {"kind": "words", "matte": "fg.mov", "start": 1.0, "dur": 1.0, "words": []}
    d["behind"] = [do_agente]
    (public / "edit-data.json").write_text(json.dumps(d), encoding="utf-8")
    img = _img("i1", "midia/outro.jpg", 2.01, 1.5)
    img["itens"][0]["atras"] = True
    _camadas(edit, [img])
    r = aplicar(edit)
    assert r["feitos"] == ["pessoa-i1-1-60-45.mov"] and r["inserts"] == 1
    ed = json.loads((public / "edit-data.json").read_text(encoding="utf-8"))
    assert ed["inserts"] == [agente]  # o cartão de cima não ganhou a imagem
    assert ed["behind"] == [do_agente, {"kind": "image", "src": "midia/camada-i1-1.jpg", "matte": "pessoa-i1-1-60-45.mov",
                                        "start": 2.0, "dur": 1.5, "camada": "i1-1"}]


def test_imagem_atras_sem_recorte_fica_no_cartao_de_cima(projeto):
    edit, public, _ = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    img = _img("i1", "midia/outro.jpg", 2, 1.5)
    img["itens"][0]["atras"] = True
    _camadas(edit, [img])
    r = aplicar(edit, recortar=False)
    assert len(r["pendentes"]) == 1 and "person_matte.py" in r["pendentes"][0]
    assert [i.get("camada") for i in _inserts(public)] == [None, "i1-1"]


def test_legenda_que_acompanha_tambem_pede_o_rastreio(projeto, ferramentas):
    edit, public, _ = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    d = json.loads((public / "edit-data.json").read_text(encoding="utf-8"))
    d["captions"] = {"enabled": True, "acompanhar": True}
    (public / "edit-data.json").write_text(json.dumps(d), encoding="utf-8")
    _camadas(edit, [])  # nenhum texto: só a legenda pede
    assert aplicar(edit)["feitos"] == ["rastreio.json"]


# ---- a imagem livre: a pessoa moveu ou redimensionou no editor (teste no celular de 28/10)

def _livre(fid, arquivo, x, y, largura, atras=False):
    f = _img(fid, arquivo, 5, 3)
    f["itens"][0].update({"x": x, "y": y, "largura": largura, **({"atras": True} if atras else {})})
    return f


def test_imagem_livre_leva_lugar_e_tamanho_para_o_insert(projeto):
    edit, public, _ = projeto
    _camadas(edit, [_livre("i1", "midia/outro.jpg", 300, 1500, 420)])
    aplicar(edit)
    assert _inserts(public)[1] == {"src": "midia/camada-i1-1.jpg", "start": 5.0, "end": 8.0, "camada": "i1-1",
                                   "x": 300, "y": 1500, "w": 420}


def test_template_velho_para_em_vez_de_por_no_cartao(projeto):
    edit, public, _ = projeto
    src = public.parent / "src"
    src.mkdir()
    (src / "Main.tsx").write_text("const InsertCard = () => null;", encoding="utf-8")  # sem INSERT_LIVRE
    _camadas(edit, [_livre("i1", "midia/outro.jpg", 300, 1500, 420)])
    import camadas_edit_data as ced
    with pytest.raises(ced.TemplateVelho, match="atualizar_template"):
        aplicar(edit)
    (src / "Main.tsx").write_text("// INSERT_LIVRE\n", encoding="utf-8")
    aplicar(edit)  # com o template de agora, segue
    _camadas(edit, [_img("i1", "midia/outro.jpg", 5, 3)])
    (src / "Main.tsx").write_text("const InsertCard = () => null;", encoding="utf-8")
    aplicar(edit)  # imagem no cartão: o template velho desenha, nada a conferir


def test_o_template_do_kit_desenha_a_imagem_livre():
    main = Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "Main.tsx"
    texto = main.read_text(encoding="utf-8")
    import camadas_edit_data as ced
    assert ced.MARCA_LIVRE in texto and "<InsertLivre" in texto
