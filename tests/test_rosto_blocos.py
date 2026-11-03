"""A tela dividida e o punch-in pelo rosto medido no trecho (rosto_blocos.py)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import rosto_blocos as rb  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "assets" / "shortform" / "src"


def test_o_foco_poe_os_olhos_na_mesma_altura():
    """Um ponto y da fonte aparece na tela em bandH + (y − focusY) · zoom."""
    for olhos in (600, 800, 1000):
        f = rb.foco(olhos, "top", 750, 1.0)
        assert 750 + (olhos - f) == 750 + rb.OLHOS_ABAIXO_DA_DIVISAO
    f = rb.foco(800, "top", 750, 1.25)
    assert 750 + (800 - f) * 1.25 == 750 + rb.OLHOS_ABAIXO_DA_DIVISAO


def test_o_foco_nunca_abre_vao_na_janela():
    assert rb.foco(100, "top", 750, 1.0) == 0  # olhos muito altos: a janela começa no topo da fonte
    f = rb.foco(1900, "top", 750, 1.0)  # olhos muito baixos: o vídeo ainda cobre a janela até o fim
    assert (1920 - f) * 1.0 >= 1920 - 750
    f = rb.foco(1900, "bottom", 750, 1.0)
    assert (1920 - f) * 1.0 >= 1920 - 750


def test_com_recorte_quem_manda_e_o_topo_da_cabeca():
    """O ponto y da fonte aparece em bandH + (y − focusY) · zoom: o topo fica CABECA_PASSA acima da divisão."""
    for topo, zoom in ((572, 1.0), (300, 1.0), (572, 1.3)):
        f = rb.foco_da_cabeca(topo, 750, zoom)
        assert abs((topo - f) * zoom + rb.CABECA_PASSA) <= 1
    f = rb.foco_da_cabeca(1500, 750, 1.0)  # cabeça muito baixa: o vídeo ainda cobre a janela
    assert (1920 - f) >= 1920 - 750


def test_o_rosto_do_trecho_e_a_mediana():
    rosto = {"fps": 30, "points": [[0.5, 0.4]] * 30 + [[0.25, 0.5]] * 30}
    assert rb.rosto_no_trecho(rosto, 0.0, 1.0) == (540.0, 768.0)
    assert rb.rosto_no_trecho(rosto, 1.0, 2.0) == (270.0, 960.0)
    assert rb.rosto_no_trecho(rosto, 50.0, 51.0) is None


def test_blocos_colados_dividem_um_recorte():
    itens = [{"start": 1.0, "end": 2.0, "cabeca": True}, {"start": 2.0, "end": 3.0, "cabeca": True},
             {"start": 5.0, "end": 6.0, "cabeca": True}, {"start": 7.0, "end": 8.0},
             {"start": 9.0, "end": 10.0, "cabeca": True, "layout": "bottom"}]
    grupos = rb._grupos(itens, 30.0)
    assert [[b["start"] for b in g] for g in grupos] == [[1.0, 2.0], [5.0]]


def projeto(tmp_path, ed):
    edit = tmp_path / "edit"
    pub = edit / "remotion" / "public"
    pub.mkdir(parents=True)
    src = edit / "remotion" / "src"
    src.mkdir()
    (src / "Main.tsx").write_text((SRC / "Main.tsx").read_text(encoding="utf-8"), encoding="utf-8")
    (src / "CustomGraphics.tsx").write_text((SRC / "CustomGraphics.tsx").read_text(encoding="utf-8"), encoding="utf-8")
    (pub / "cut.mp4").write_bytes(b"x")
    (edit / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    # um rastreio de verdade, mais novo que o corte: o helper não chama o face_track
    (pub / "track.json").write_text(json.dumps({"fps": 30, "points": [[0.5, 0.4]] * 300}), encoding="utf-8")
    return edit, pub


def le(pub):
    return json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))


def test_sem_marca_nada_muda(tmp_path):
    ed = {"fps": 30, "splitInserts": [{"src": "a.png", "start": 1, "end": 2, "layout": "top"}]}
    edit, pub = projeto(tmp_path, ed)
    assert rb.aplicar(edit) == {"focos": 0, "punchs": 0, "recortes": [], "pendentes": [], "template": []}
    assert le(pub) == ed


def test_o_bloco_e_o_punch_in_ganham_o_rosto_medido(tmp_path):
    ed = {"fps": 30, "splitInserts": [{"src": "a.png", "start": 1, "end": 2, "focusAuto": True}],
          "punchins": [{"start": 3, "end": 4, "zoom": 1.5}, {"start": 5, "end": 6, "zoom": 1.5, "x": 100, "y": 200, "fixo": True}]}
    edit, pub = projeto(tmp_path, ed)
    r = rb.aplicar(edit)
    assert r["focos"] == 1 and r["punchs"] == 1
    d = le(pub)
    assert d["splitInserts"][0]["focusY"] == rb.foco(768, "top", 750, 1.0) and d["splitInserts"][0]["zoom"] == 1.0
    assert (d["punchins"][0]["x"], d["punchins"][0]["y"]) == (540, 768)
    assert (d["punchins"][1]["x"], d["punchins"][1]["y"]) == (100, 200)  # `fixo` fica como está


def test_rodar_de_novo_nao_regrava(tmp_path):
    ed = {"fps": 30, "punchins": [{"start": 3, "end": 4, "zoom": 1.5}]}
    edit, pub = projeto(tmp_path, ed)
    rb.aplicar(edit)
    antes = (pub / "edit-data.json").stat().st_mtime_ns
    rb.aplicar(edit)
    assert (pub / "edit-data.json").stat().st_mtime_ns == antes


def test_cabeca_pede_o_recorte_e_tira_o_que_sobrou(tmp_path):
    ed = {"fps": 30, "splitInserts": [{"src": "a.png", "start": 1, "end": 2, "cabeca": True}, {"src": "b.png", "start": 2, "end": 3, "cabeca": True}]}
    edit, pub = projeto(tmp_path, ed)
    (pub / "fg_split_1_1.mov").write_bytes(b"velho")
    (pub / "fg_outro.mov").write_bytes(b"de outro")
    (pub / "fg_split_30_60.mov").write_bytes(b"pronto")  # o grupo de agora já existe: não recorta
    # sem `focusAuto` o topo da cabeça não importa: nem mede
    r = rb.aplicar(edit, recortar=False)
    assert r["pendentes"] == [] and not (pub / "fg_split_1_1.mov").exists() and (pub / "fg_outro.mov").exists()
    d = le(pub)
    assert [b["matte"] for b in d["splitInserts"]] == ["fg_split_30_60.mov"] * 2 and d["splitInserts"][1]["matteIni"] == 30


def test_o_topo_medido_fica_no_item_e_nao_mede_de_novo(tmp_path, monkeypatch):
    ed = {"fps": 30, "splitInserts": [{"src": "a.png", "start": 1, "end": 2, "cabeca": True, "focusAuto": True}]}
    edit, pub = projeto(tmp_path, ed)
    (pub / "fg_split_30_30.mov").write_bytes(b"pronto")
    chamadas = []
    monkeypatch.setattr(rb.cenas, "medir_pessoa", lambda m: chamadas.append(m) or {"topo": 600})
    rb.aplicar(edit)
    b = le(pub)["splitInserts"][0]
    assert b["matteTopo"] == 600 and b["focusY"] == rb.foco_da_cabeca(600, 750, 1.0) and len(chamadas) == 1
    rb.aplicar(edit)
    assert len(chamadas) == 1 and le(pub)["splitInserts"][0]["focusY"] == b["focusY"]


def test_template_velho_para_antes_de_medir(tmp_path):
    ed = {"fps": 30, "punchins": [{"start": 3, "end": 4, "zoom": 1.5}]}
    edit, pub = projeto(tmp_path, ed)
    (edit / "remotion" / "src" / "Main.tsx").write_text("antigo", encoding="utf-8")
    assert rb.aplicar(edit)["template"] == ["src/Main.tsx"]
    assert "x" not in le(pub)["punchins"][0]


def test_o_template_do_kit_desenha_os_campos():
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    cg = (SRC / "CustomGraphics.tsx").read_text(encoding="utf-8")
    assert "D.punchins?.find" in main and rb.template_velho(SRC.parent, {"punchins": [{}]}) == []
    assert re.search(r"zoomBloco \?\? LAYOUT\[layout\]\.zoom", cg) and "matteIni" in cg and "key={active.src}" in cg


def test_o_bloco_anda_com_o_corte_e_no_salvar():
    import editdata_aplicar as eda
    import remapear
    assert remapear.BLOCOS["punchins"] == ("start", "end", "punch")
    d = {"punchins": [{"start": 3.0, "end": 4.0, "zoom": 1.5, "x": 540}]}
    eda.aplicar(d, {"punchins": [{"ref": 0, "start": 3.5, "end": 4.5}]})
    assert d["punchins"][0]["start"] == 3.5 and d["punchins"][0]["zoom"] == 1.5 and d["punchins"][0]["x"] == 540


def test_o_zoom_do_punch_in_pede_o_corte_alto(tmp_path):
    import corte_alta
    (tmp_path / "state.json").write_text(json.dumps({"editData": "ed.json"}), encoding="utf-8")
    (tmp_path / "edl.json").write_text(json.dumps({"ranges": []}), encoding="utf-8")
    (tmp_path / "ed.json").write_text(json.dumps({"punchins": [{"start": 1, "end": 2, "zoom": 1.6}, {"start": 3, "end": 4, "zoom": 1.9, "desligado": True}]}), encoding="utf-8")
    assert corte_alta.zoom_maximo(tmp_path) == 1.6  # o desligado não conta
