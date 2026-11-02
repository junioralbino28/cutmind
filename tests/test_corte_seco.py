"""Imagem e vídeo por cima com corte seco (edição real de 01/11: com o fade de ~6 quadros, duas camadas em tela cheia
seguidas mostravam a pessoa por ~0,3 s na troca)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import aprender  # noqa: E402
import camadas as cam  # noqa: E402
import camadas_edit_data as ced  # noqa: E402

CHEIA = {"largura": 1080, "x": 540, "y": 960}


@pytest.mark.parametrize("it, prop, cobre", [
    (CHEIA, 16 / 9, True),
    (CHEIA, 9 / 16, False),  # deitada: sobra em cima e embaixo
    ({"largura": 700, "x": 540, "y": 960}, 16 / 9, False),
    ({"largura": 1300, "x": 540, "y": 960}, 16 / 9, True),  # maior que o quadro também cobre
    ({"largura": 1080, "x": 700, "y": 960}, 16 / 9, False),  # fora do lugar: um lado fica de fora
    ({"x": 540, "y": 960}, 16 / 9, False),  # o cartão de cima nunca cobre
    ({**CHEIA, "recorte": {"x": 0, "y": 0, "w": 1, "h": 0.5}}, 16 / 9, False),  # só metade da altura aparece
    ({**CHEIA, "recorte": {"x": 0.25, "y": 0, "w": 0.5, "h": 1}}, 8 / 9, True),  # o pedaço estica até a largura
])
def test_cobre_o_quadro(it, prop, cobre):
    assert cam.cobre_o_quadro(it, prop) is cobre


def test_a_escolha_da_pessoa_vence_a_conta():
    assert cam.corte_seco({**CHEIA, "corteSeco": False}, 16 / 9) is False
    assert cam.corte_seco({"corteSeco": True}, None) is True
    assert cam.corte_seco(CHEIA, 16 / 9) is True
    assert cam.corte_seco(CHEIA, None) is False  # sem saber a proporção, fica o fade de sempre


def _projeto(tmp_path, itens, main="// INSERT_LIVRE INSERT_RECORTE INSERT_VIDEO ATRAS_LIVRE LEGENDA_OCULTA ENQUADRE_TOMADA INSERT_SECO"):
    edit = tmp_path / "edit"
    pub = edit / "remotion" / "public"
    pub.mkdir(parents=True)
    (edit / "remotion" / "src").mkdir()
    (edit / "remotion" / "src" / "Main.tsx").write_text(main, encoding="utf-8")
    (edit / "midia").mkdir()
    ff = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
    subprocess.run(ff + ["-i", "color=c=gray:s=108x192", "-frames:v", "1", str(edit / "midia" / "alta.png")], check=True)
    subprocess.run(ff + ["-i", "color=c=gray:s=192x108", "-frames:v", "1", str(edit / "midia" / "deitada.png")], check=True)
    (edit / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps({"fps": 30, "width": 1080, "height": 1920, "inserts": [], "behind": []}), encoding="utf-8")
    (edit / "camadas.json").write_text(json.dumps({"video": {"mudo": False}, "faixas": [
        {"id": "i1", "tipo": "imagem", "itens": [{"id": f"i1-{k}", "inicio": k * 2.0, "duracao": 2.0, **it} for k, it in enumerate(itens)]}]}), encoding="utf-8")
    return edit, pub / "edit-data.json"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
def test_o_edit_data_leva_o_corte_seco_de_quem_cobre_o_quadro(tmp_path):
    edit, ed = _projeto(tmp_path, [
        {"arquivo": "midia/alta.png", **CHEIA},
        {"arquivo": "midia/alta.png", **CHEIA, "corteSeco": False},
        {"arquivo": "midia/deitada.png", **CHEIA},
        {"arquivo": "midia/deitada.png", **CHEIA, "corteSeco": True},
    ])
    ced.aplicar(edit, recortar=False)
    assert [bool(i.get("seco")) for i in json.loads(ed.read_text(encoding="utf-8"))["inserts"]] == [True, False, False, True]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
def test_template_velho_so_para_quando_a_pessoa_pediu(tmp_path):
    velho = "// INSERT_LIVRE INSERT_RECORTE INSERT_VIDEO ATRAS_LIVRE LEGENDA_OCULTA ENQUADRE_TOMADA"
    edit, _ = _projeto(tmp_path / "a", [{"arquivo": "midia/alta.png", **CHEIA}], main=velho)
    ced.aplicar(edit, recortar=False)  # automático: sai com o fade de antes, sem travar o Baixar de projeto antigo
    edit, _ = _projeto(tmp_path / "b", [{"arquivo": "midia/alta.png", **CHEIA, "corteSeco": True}], main=velho)
    with pytest.raises(ced.TemplateVelho, match="corte seco"):
        ced.aplicar(edit, recortar=False)


def test_o_campo_sobrevive_ao_salvar_e_o_agente_aprende():
    limpo = cam.normalize({"video": {"mudo": False}, "faixas": [{"id": "i1", "tipo": "imagem", "itens": [
        {"id": "i1-1", "arquivo": "midia/a.png", "inicio": 0, "duracao": 1, "corteSeco": True},
        {"id": "i1-2", "arquivo": "midia/a.png", "inicio": 1, "duracao": 1}]}]})
    itens = limpo["faixas"][0]["itens"]
    assert itens[0]["corteSeco"] is True and "corteSeco" not in itens[1]
    assert any(m["chave"] == "imagem_corteSeco" for m in aprender._camadas(
        {"faixas": [{"tipo": "imagem", "itens": [{"id": "i", "arquivo": "a", "inicio": 0, "duracao": 1}]}]},
        {"faixas": [{"tipo": "imagem", "itens": [{"id": "i", "arquivo": "a", "inicio": 0, "duracao": 1, "corteSeco": True}]}]}))


def test_o_template_e_o_editor_fazem_a_mesma_conta():
    main = (RAIZ / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "INSERT_SECO" in main and main.count("seco ? 1 : interpolate(") == 4 and main.count("seco={it.seco}") == 2
    js = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    assert "x - it.largura / 2 <= 1 && x + it.largura / 2 >= FRAME_W - 1 && y - alt / 2 <= 1 && y + alt / 2 >= FRAME_H - 1" in js
    assert "tool(ctx, 'corte-seco'" in js and "case 'corte-seco'" in js
