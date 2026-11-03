"""O Baixar só refaz o trecho quando tem certeza: qualquer dúvida é o vídeo inteiro."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render_parcial as rp  # noqa: E402


def texto(i, a, b, x=540):
    return {"id": i, "texto": "OI", "start": a, "end": b, "x": x, "y": 600}


def base(**k):
    return {"fps": 30, "durationSec": 100.0, "hook": {"enabled": False}, "captions": {"style": "karaoke"}, "camera": {"zooms": []},
            "textos": [texto("a", 10, 12), texto("b", 40, 42)], "cenas": [], "graficos": [], **k}


def test_mover_um_texto_refaz_so_as_janelas_dele():
    a, b = base(), base(textos=[texto("a", 10, 12, x=300), texto("b", 40, 42)])
    assert rp.janelas(a, b) == [(9.75, 12.25)]


def test_mudar_o_tempo_leva_a_janela_de_antes_e_a_de_agora():
    a, b = base(), base(textos=[texto("a", 20, 22), texto("b", 40, 42)])
    assert rp.janelas(a, b) == [(9.75, 12.25), (19.75, 22.25)]


def test_nada_mudou_e_o_som_nao_conta():
    a = base(soundtrack={"enabled": True, "volume": 0.05})
    assert rp.janelas(a, base(soundtrack={"enabled": True, "volume": 0.2})) == []


def test_o_que_nao_tem_janela_e_o_video_inteiro():
    a = base()
    assert rp.janelas(a, base(hook={"enabled": True})) is None  # o gancho
    assert rp.janelas(a, base(captions={"style": "stacked"})) is None  # a legenda
    assert rp.janelas(a, base(camera={"zooms": [1]})) is None  # a câmera
    assert rp.janelas(a, {**a, "novo": 1}) is None  # um campo que este arquivo não conhece
    assert rp.janelas(a, base(textos=[{"id": "a", "texto": "SEM TEMPO"}, texto("b", 40, 42)])) is None


def test_trocar_a_ordem_das_camadas_e_o_video_inteiro():
    """A de cima passa para baixo em toda a duração delas: nenhum item "mudou" e a imagem muda."""
    a = base()
    assert rp.janelas(a, base(textos=[texto("b", 40, 42), texto("a", 10, 12)])) is None


def test_a_legenda_que_some_muda_so_por_trechos():
    """O texto em destaque esconde a legenda, e dois vizinhos juntam a janela: o vão entre eles também muda."""
    a = base(captions={"style": "karaoke", "ocultarTextos": [{"start": 10, "end": 14}]})
    b = base(captions={"style": "karaoke", "ocultarTextos": [{"start": 10, "end": 12}]})
    assert rp.janelas(a, b) == [(9.75, 14.25)]


def test_o_numero_e_o_punch_in_tem_janela():
    a = base(numeros=[{"at": 5, "end": 7, "valor": 3}], punchins=[{"start": 20, "end": 22, "zoom": 1.4}])
    b = base(numeros=[{"at": 5, "end": 7, "valor": 9}], punchins=[{"start": 20, "end": 22, "zoom": 1.6}])
    assert rp.janelas(a, b) == [(4.75, 7.25), (19.75, 22.25)]


def test_trecho_grande_demais_vai_inteiro():
    a, b = base(), base(textos=[texto("a", 10, 80), texto("b", 40, 42)])
    assert rp.janelas(a, b, 100.0) is None
    assert rp.janelas(a, b) is not None


def projeto(tmp_path):
    rem = tmp_path / "remotion"
    (rem / "public" / "cenas").mkdir(parents=True)
    (rem / "src").mkdir()
    (rem / "out").mkdir()
    (rem / "src" / "Main.tsx").write_text("x", encoding="utf-8")
    (rem / "package.json").write_text("{}", encoding="utf-8")
    (rem / "public" / "cut.mp4").write_bytes(b"corte")
    (rem / "public" / "segments.json").write_text('{"segments": []}', encoding="utf-8")
    (rem / "public" / "edit-data.json").write_text(json.dumps(base()), encoding="utf-8")
    (rem / "out" / "render.mp4").write_bytes(b"render")
    return rem


def grava(rem, ed):
    (rem / "public" / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")


def test_sem_foto_e_o_video_inteiro(tmp_path):
    assert rp.o_que_mudou(projeto(tmp_path)) is None


def test_com_foto_diz_o_que_mudou(tmp_path):
    rem = projeto(tmp_path)
    rp.guardar(rem)
    assert rp.o_que_mudou(rem) == []
    grava(rem, base(textos=[texto("a", 10, 12, x=300), texto("b", 40, 42)]))
    assert rp.o_que_mudou(rem) == [(9.75, 12.25)]


def test_a_medida_dos_recortes_nao_conta_mas_um_arquivo_mudado_sim(tmp_path):
    rem = projeto(tmp_path)
    (rem / "public" / "cenas" / "medidas.json").write_text("{}", encoding="utf-8")
    rp.guardar(rem)
    (rem / "public" / "cenas" / "medidas.json").write_text('{"a": 1}', encoding="utf-8")
    assert rp.o_que_mudou(rem) == []
    (rem / "public" / "segments.json").write_text('{"segments": [1]}', encoding="utf-8")  # o corte mudou
    assert rp.o_que_mudou(rem) is None


def test_arquivo_novo_e_de_um_item_novo(tmp_path):
    rem = projeto(tmp_path)
    rp.guardar(rem)
    (rem / "public" / "foto-nova.jpg").write_bytes(b"foto")
    grava(rem, base(inserts=[{"src": "foto-nova.jpg", "start": 50, "end": 52}]))
    assert rp.o_que_mudou(rem) == [(49.75, 52.25)]


def test_corte_mudado_de_data_e_o_video_inteiro(tmp_path):
    rem = projeto(tmp_path)
    rp.guardar(rem)
    corte = rem / "public" / "cut.mp4"
    st = corte.stat()
    os.utime(corte, (st.st_atime, st.st_mtime + 100))
    assert rp.o_que_mudou(rem) is None


def test_template_novo_e_o_video_inteiro(tmp_path):
    rem = projeto(tmp_path)
    rp.guardar(rem)
    (rem / "src" / "Main.tsx").write_text("y", encoding="utf-8")
    assert rp.o_que_mudou(rem) is None


def test_render_que_caiu_no_meio_nao_vale(tmp_path):
    """Um render cancelado deixa um arquivo pela metade: a foto é do que existia antes dele."""
    rem = projeto(tmp_path)
    rp.guardar(rem)
    (rem / "out" / "render.mp4").write_bytes(b"pela metade")
    assert rp.o_que_mudou(rem) is None
