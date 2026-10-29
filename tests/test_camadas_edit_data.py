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


def test_imagem_atras_livre_leva_lugar_tamanho_e_recorte_para_o_behind(projeto, ferramentas):
    """Teste no PC de 29/10: atrás da pessoa, a imagem vinha sempre no cartão grande, ignorando o que a pessoa pôs."""
    edit, public, agente = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    f = _livre("i1", "midia/outro.jpg", 300, 700, 600, atras=True)
    f["itens"][0]["recorte"] = {"x": 0.2, "y": 0, "w": 0.6, "h": 1, "formato": "livre"}
    _camadas(edit, [f])
    aplicar(edit)
    ed = json.loads((public / "edit-data.json").read_text(encoding="utf-8"))
    assert ed["inserts"] == [agente]
    b = ed["behind"][0]
    assert (b["kind"], b["x"], b["y"], b["w"]) == ("image", 300, 700, 600) and b["matte"].endswith(".mov")
    assert b["crop"] == {"x": 0.2, "y": 0, "w": 0.6, "h": 1}


def test_imagem_atras_livre_sem_recorte_da_pessoa_sai_no_lugar_dela(projeto):
    edit, public, _ = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    _camadas(edit, [_livre("i1", "midia/outro.jpg", 300, 700, 600, atras=True)])
    r = aplicar(edit, recortar=False)
    assert len(r["pendentes"]) == 1  # o comando do recorte fica avisado; até lá, na frente, mas no lugar certo
    assert {k: _inserts(public)[1][k] for k in ("x", "y", "w")} == {"x": 300, "y": 700, "w": 600}


def test_template_sem_imagem_atras_livre_para(projeto, ferramentas):
    edit, public, _ = projeto
    (public / "cut.mp4").write_bytes(b"mp4")
    src = public.parent / "src"
    src.mkdir()
    (src / "Main.tsx").write_text("// INSERT_LIVRE INSERT_RECORTE", encoding="utf-8")  # o kit de 0.2.0
    _camadas(edit, [_livre("i1", "midia/outro.jpg", 300, 700, 600, atras=True)])
    import camadas_edit_data as ced
    with pytest.raises(ced.TemplateVelho, match="atualizar_template"):
        aplicar(edit)
    (src / "Main.tsx").write_text("// INSERT_LIVRE INSERT_RECORTE ATRAS_LIVRE", encoding="utf-8")
    aplicar(edit)
    img = _img("i1", "midia/outro.jpg", 5, 3)
    img["itens"][0]["atras"] = True
    _camadas(edit, [img])
    (src / "Main.tsx").write_text("// INSERT_LIVRE INSERT_RECORTE", encoding="utf-8")
    aplicar(edit)  # atrás, mas no cartão grande: o template de antes desenha, nada a conferir


def test_o_template_do_kit_desenha_a_imagem_atras_no_lugar_dela():
    main = Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "Main.tsx"
    texto = main.read_text(encoding="utf-8")
    import camadas_edit_data as ced
    assert ced.MARCA_ATRAS_LIVRE in texto and "crop={b.crop}" in texto


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


def test_recorte_vai_para_o_insert_como_crop(projeto):
    edit, public, _ = projeto
    f = _livre("i1", "midia/outro.jpg", 540, 480, 1080)
    f["itens"][0]["recorte"] = {"x": 0.55, "y": 0.1, "w": 0.4, "h": 0.8, "formato": "1:1"}
    _camadas(edit, [f])
    aplicar(edit)
    assert _inserts(public)[1]["crop"] == {"x": 0.55, "y": 0.1, "w": 0.4, "h": 0.8}
    assert _inserts(public)[1]["w"] == 1080


def test_template_sem_recorte_para_em_vez_de_mostrar_a_imagem_inteira(projeto):
    edit, public, _ = projeto
    src = public.parent / "src"
    src.mkdir()
    (src / "Main.tsx").write_text("// INSERT_LIVRE", encoding="utf-8")  # o kit de 28/10 de madrugada
    f = _livre("i1", "midia/outro.jpg", 540, 480, 1080)
    f["itens"][0]["recorte"] = {"x": 0.5, "y": 0, "w": 0.5, "h": 1}
    _camadas(edit, [f])
    import camadas_edit_data as ced
    with pytest.raises(ced.TemplateVelho, match="não recorta"):
        aplicar(edit)
    (src / "Main.tsx").write_text("// INSERT_LIVRE INSERT_RECORTE", encoding="utf-8")
    aplicar(edit)


def test_o_template_do_kit_recorta_a_imagem():
    main = Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "Main.tsx"
    texto = main.read_text(encoding="utf-8")
    import camadas_edit_data as ced
    assert ced.MARCA_RECORTE in texto and "crop={it.crop}" in texto and "clipPath" in texto


def test_video_por_cima_vai_para_o_insert_com_o_comeco_dele(projeto):
    edit, public, _ = projeto
    (edit / "midia" / "clipe.mp4").write_bytes(b"x")
    f = _img("i1", "midia/clipe.mp4", 5, 3)
    f["itens"][0].update({"corte": 1.25, "volume": 1, "x": 540, "y": 480, "largura": 1080,
                          "recorte": {"x": 0.6, "y": 0, "w": 0.3, "h": 1}})
    _camadas(edit, [f])
    aplicar(edit)
    ins = _inserts(public)[1]
    assert ins["src"] == "midia/camada-i1-1.mp4" and ins["video"] is True and ins["from"] == 1.25
    assert ins["crop"] == {"x": 0.6, "y": 0, "w": 0.3, "h": 1} and ins["w"] == 1080


def test_template_sem_video_para_em_vez_de_sumir_com_ele(projeto):
    edit, public, _ = projeto
    (edit / "midia" / "clipe.mp4").write_bytes(b"x")
    src = public.parent / "src"
    src.mkdir()
    (src / "Main.tsx").write_text("// INSERT_LIVRE INSERT_RECORTE", encoding="utf-8")
    _camadas(edit, [_img("i1", "midia/clipe.mp4", 5, 3)])
    import camadas_edit_data as ced
    with pytest.raises(ced.TemplateVelho, match="vídeo por cima"):
        aplicar(edit)


def test_o_template_do_kit_desenha_o_video_por_cima():
    main = Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "Main.tsx"
    texto = main.read_text(encoding="utf-8")
    import camadas_edit_data as ced
    assert ced.MARCA_VIDEO in texto and "<OffthreadVideo" in texto and "from={it.from}" in texto



# ---- o enquadre da gravação de cada tomada vai para o edit-data, na ordem dos trechos

def _edl_enq(edit, enqs):
    ranges = [{"source": "A", "start": float(i), "end": float(i) + 1, **({"enquadre": e} if e else {})} for i, e in enumerate(enqs)]
    (edit / "edl.json").write_text(json.dumps({"ranges": ranges}), encoding="utf-8")


def test_enquadres_seguem_os_trechos_do_corte(projeto):
    edit, public, _ = projeto
    import camadas_edit_data as ced
    (public / "segments.json").write_text(json.dumps({"segments": [{"start": 0, "dur": 1}, {"start": 1, "dur": 1}]}), encoding="utf-8")
    segs = [0, 1]
    enqs = [{"x": 540, "y": 1440, "largura": 1300, "recorte": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.5}}] + [None] * (len(segs) - 1)
    _edl_enq(edit, enqs)
    _camadas(edit, [])
    aplicar(edit)
    d = json.loads((public / "edit-data.json").read_text(encoding="utf-8"))
    assert d["enquadres"][0] == {"x": 540, "y": 1440, "w": 1300, "crop": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.5}}
    assert d["enquadres"][1:] == [None] * (len(segs) - 1)
    _edl_enq(edit, enqs + [None])  # uma tomada a mais que os trechos: o enquadre cairia na tomada errada
    with pytest.raises(ced.TemplateVelho, match="não batem"):
        aplicar(edit)
    _edl_enq(edit, [None] * len(segs))  # sem enquadre: a lista sai vazia
    aplicar(edit)
    assert json.loads((public / "edit-data.json").read_text(encoding="utf-8"))["enquadres"] == []


def test_template_sem_enquadre_para(projeto):
    edit, public, _ = projeto
    (public / "segments.json").write_text(json.dumps({"segments": [{"start": 0, "dur": 1}]}), encoding="utf-8")
    _edl_enq(edit, [{"x": 540, "y": 1440, "largura": 1300}])
    _camadas(edit, [])
    src = public.parent / "src"
    src.mkdir()
    (src / "Main.tsx").write_text("// INSERT_LIVRE INSERT_RECORTE INSERT_VIDEO", encoding="utf-8")
    import camadas_edit_data as ced
    with pytest.raises(ced.TemplateVelho, match="não enquadra"):
        aplicar(edit)


def test_o_template_do_kit_enquadra_a_gravacao():
    main = Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "Main.tsx"
    texto = main.read_text(encoding="utf-8")
    import camadas_edit_data as ced
    assert ced.MARCA_ENQUADRE in texto and "D.enquadres?.[idx]" in texto and "clipPath" in texto
