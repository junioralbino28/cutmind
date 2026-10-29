"""A zona segura do Reels: nada do template nasce na faixa que some.

Medido no Reels 1 (29/10/2026) com os gabaritos do Instagram: a grade do perfil mostra só 1080×1440 do
1080×1920 (somem 240 px em cima e 240 embaixo), o cabeçalho do Reels fica em cima, a coluna de botões à
direita e o nome e a descrição do post embaixo. O template punha o cartão de imagem a 90 px do topo, o
título "cartão" a 120 e as palavras atrás da pessoa a 180: tudo cortado na grade.

As posições do template têm cópias no editor (a prévia desenha igual): este teste também cobra que as
cópias batam, porque nenhum outro teste olhava para elas.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "assets" / "shortform" / "src"
PREVIEW = RAIZ / "assets" / "preview"


def _zona() -> dict[str, int]:
    texto = (SRC / "zonaSegura.ts").read_text(encoding="utf-8")
    return {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", texto.split("ZONA_SEGURA", 1)[1].split("}", 1)[0])}


def test_a_zona_tem_os_numeros_medidos():
    z = _zona()
    assert z["topo"] == 240 and z["base"] == 1680  # a grade do perfil: 1080×1440 no meio
    assert z["legendaPost"] <= 1580  # o nome e a descrição do post
    assert z["colunaX"] <= 940 and z["colunaY0"] <= 900 and z["colunaY1"] >= 1660  # os botões à direita


def test_o_cartao_de_imagem_nasce_abaixo_da_faixa_de_cima():
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    assert "ZONA_SEGURA" in main
    topo = int(re.search(r"const CARD_TOP = (?:ZONA_SEGURA\.topo \+ )?(\d+)", main).group(1))
    if "CARD_TOP = ZONA_SEGURA.topo +" in main:
        topo += _zona()["topo"]
    assert topo >= _zona()["topo"]


def test_os_titulos_nascem_abaixo_da_faixa_de_cima_e_o_editor_desenha_igual():
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    tops = {m.group(1): int(m.group(2)) for m in re.finditer(r"(\w+): \{weights: \[[^\]]*\][^}]*?top: (\d+)\}", main)}
    assert set(tops) == {"outline", "card", "realce", "misto"}
    assert min(tops.values()) >= _zona()["topo"], tops
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    hl = dict((k, int(v)) for k, v in re.findall(r"(\w+): (\d+)", re.search(r"const HL_TOP = \{([^}]*)\}", js).group(1)))
    assert hl == tops
    gancho = {m.group(1): int(m.group(2)) for m in re.finditer(r"(\w+): \{ cap: \d+, w: \d+, lh: [\d.]+, top: (\d+) \}", js)}
    assert gancho == tops


def test_a_previa_do_cartao_de_imagem_e_o_cartao_do_render():
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    w = int(re.search(r"const CARD_W = (\d+)", main).group(1))
    h = int(re.search(r"const CARD_H = (\d+)", main).group(1))
    m = re.search(r"const CARD_TOP = (?:ZONA_SEGURA\.topo \+ )?(\d+)", main)
    topo = int(m.group(1)) + (_zona()["topo"] if "ZONA_SEGURA.topo +" in m.group(0) else 0)
    css = (PREVIEW / "celular.css").read_text(encoding="utf-8")
    regra = re.search(r"\.ov-img \{([^}]*)\}", css).group(1)
    pct = lambda nome: float(re.search(rf"{nome}: ([\d.]+)%", regra).group(1))  # noqa: E731
    assert abs(pct("top") - topo / 1920 * 100) < 0.01
    assert abs(pct("width") - w / 1080 * 100) < 0.01
    assert abs(pct("height") - h / 1920 * 100) < 0.01


def test_as_palavras_atras_da_pessoa_e_os_exemplos_nao_nascem_na_faixa():
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    atras = re.search(r"const BehindWordsEl[\s\S]*?paddingTop: (?:ZONA_SEGURA\.topo \+ )?(\d+)", main)
    assert atras and int(atras.group(1)) + (_zona()["topo"] if "ZONA_SEGURA.topo +" in atras.group(0) else 0) >= 240
    cg = (SRC / "CustomGraphics.tsx").read_text(encoding="utf-8")
    margens = [int(x) for x in re.findall(r"marginTop: (\d+),", cg) if int(x) > 40]
    assert margens and min(margens) >= _zona()["topo"], margens


def test_a_regua_do_editor_usa_os_mesmos_numeros():
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    bloco = re.search(r"const ZONA_SEGURA = \{([^}]*)\}", js)
    assert bloco, "o editor não tem a régua da zona segura"
    z = {k: int(v) for k, v in re.findall(r"(\w+): (\d+)", bloco.group(1))}
    assert z == _zona()
    html = (PREVIEW / "celular.html").read_text(encoding="utf-8")
    assert 'id="btnZona"' in html
    en = (PREVIEW / "i18n-en.js").read_text(encoding="utf-8")
    assert '"Zona segura"' in en


def _cenas():
    sys.path.insert(0, str(RAIZ / "helpers"))
    import cenas
    return cenas


def _pessoa(**k):
    return {"x0": 300, "x1": 780, "topo": 600, "base": 1920, "cabecaX": 540, "presenca": 1.0, **k}


def test_os_efeitos_de_cena_usam_a_mesma_regua():
    z = _zona()
    assert _cenas().ZONA_TOPO == z["topo"]
    assert _cenas().ZONA_BOTOES == (z["colunaX"], z["colunaY0"], z["colunaY1"])


def _nos_botoes(x, y, w, h) -> bool:
    bx, by0, by1 = _cenas().ZONA_BOTOES
    return x + w > bx and y + h > by0 and y < by1


@pytest.mark.parametrize("pessoa", [dict(topo=420), dict(topo=600, x0=120, x1=640, cabecaX=380),
                                    dict(topo=500, x0=440, x1=960, cabecaX=700)])
def test_nada_com_texto_entra_na_coluna_de_botoes_nem_cobre_o_nome_da_capa(pessoa):
    cenas = _cenas()
    p = _pessoa(**pessoa)
    ms = [{"t": f"Manchete {i}", "at": 1 + i * 0.2} for i in range(4)]
    for s in filter(None, cenas.layout("mural", p, {"manchetes": ms})["slots"]):
        assert not _nos_botoes(s["x"], s["y"], s["w"], s["h"]), s
    for pedido in ({"esquerda": [["a", "b"]]}, {"direita": [["c", "d"]]}, {"esquerda": [["a", "b"]], "direita": [["c", "d"]]}):
        lay = cenas.layout("capa", p, {"nome": "EDITOR", "selo": "ESPECIAL", **pedido})
        selo = lay["selo"]
        caixa = (selo["x"] - selo["d"] / 2, selo["y"] - selo["d"] / 2, selo["d"], selo["d"])
        assert caixa[1] >= lay["baseline"] + 10 and caixa[1] >= _zona()["topo"]  # abaixo do nome da revista
        assert not _nos_botoes(*caixa) and 0 <= caixa[0] and caixa[0] + caixa[2] <= cenas.W
        for col in lay["colunas"].values():
            if col:
                assert not _nos_botoes(col["x"], col["y"], col["w"], 400), col
                assert cenas._inter(caixa, (col["x"], col["y"], col["w"], 400)) == 0, (col, selo)


@pytest.mark.parametrize("topo", [300, 400, 600, 900])
def test_o_texto_dos_efeitos_de_cena_nasce_abaixo_da_faixa(topo):
    cenas, z = _cenas(), _zona()["topo"]
    p = _pessoa(topo=topo)
    vidro = cenas.layout("vidro", p, {"palavra": "GARGALO"})
    assert vidro["y"] - 0.36 * vidro["tamanho"] >= z  # o topo das letras, como o vidro.tsx desenha
    ms = [{"t": f"Manchete {i}", "at": 1 + i * 0.2} for i in range(4)]
    for s in filter(None, cenas.layout("mural", p, {"manchetes": ms})["slots"]):
        r = math.radians(abs(s["r"]))  # o recorte girado sobe um canto
        assert s["y"] + s["h"] / 2 - (s["w"] / 2 * math.sin(r) + s["h"] / 2 * math.cos(r)) >= z, s
    parede = cenas.layout("parede", p, {"gigante": "POSTS"})
    assert parede["bloco"]["y"] - 158 >= z and 0 <= parede["desce"] <= 260
    if topo >= 320:  # a pessoa desce até 260 px: a cabeça fica abaixo da fita e da palavra
        assert parede["bloco"]["y"] + 158 < topo + parede["desce"]
    larga = _pessoa(topo=topo, x0=150, x1=1000, cabecaX=540)  # a cabeça bate na etiqueta
    assert cenas.layout("grafico", larga, {"valores": [0.2, 1], "etiqueta": "ESCALA"})["bloco"]["y"] - 65 >= z
    capa = cenas.layout("capa", p, {"nome": "EQUIPE"})
    assert capa["baseline"] - 0.72 * capa["tamanho"] >= z


def test_o_mural_sem_lugar_deixa_a_manchete_fora_em_vez_de_empilhar():
    cenas = _cenas()
    perto = _pessoa(topo=380, x0=90, x1=990, cabecaX=540)  # close no meio: quase não sobra parede
    ms = [{"t": f"Manchete {i}", "at": 1 + i * 0.2} for i in range(4)]
    slots = cenas.layout("mural", perto, {"manchetes": ms})["slots"]
    assert len(slots) == 4 and None in slots
    postos = [s for s in slots if s]
    for i, s in enumerate(postos):
        r = (s["x"], s["y"], s["w"], s["h"])
        assert cenas.cobre(perto, r) <= 0.25 and 0 <= s["x"] and s["x"] + s["w"] <= cenas.W  # a borda não corta letra
        for o in postos[i + 1:]:
            assert cenas._inter(r, (o["x"], o["y"], o["w"], o["h"])) <= 0.3 * s["w"] * s["h"]


def test_o_site_nao_sobe_o_titulo_para_a_faixa_e_encolhe_a_pessoa():
    cenas, z = _cenas(), _zona()["topo"]
    menu_top, menu_h = cenas._MENU
    assert menu_top >= z
    titulo = cenas._SITE[0][1]
    for topo in (200, 400, 700):
        lay = cenas.layout("chroma", _pessoa(topo=topo, x0=100, x1=980), {"titulo": "Site"})
        assert titulo + (lay["bloco"]["y"] - cenas._SITE_CENTRO[1]) >= menu_top + menu_h  # nunca por cima do menu
    # pedida grande, a pessoa bate na frase: ela diminui em vez de o texto subir
    grande = cenas.layout("chroma", _pessoa(topo=150, x0=40, x1=1040), {"titulo": "Site", "escala": 0.85})
    assert grande["escala"] < 0.85


def test_o_template_e_o_editor_desenham_os_efeitos_de_cena_no_mesmo_lugar():
    cenas = _cenas()
    tsx = (SRC / "cenas" / "fundoNovo.tsx").read_text(encoding="utf-8")
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    cx, cy = cenas._SITE_CENTRO
    assert f"L.bloco ?? {{x: {cx}, y: {cy}}}" in tsx and f"translate(${{bx - {cx}}}px, ${{by - {cy}}}px)" in tsx
    assert f"lay(c).bloco || {{ x: {cx}, y: {cy} }}" in js
    menu = re.search(r"left: 56, right: 56, top: (\d+), height: (\d+)", tsx)
    assert (int(menu.group(1)), int(menu.group(2))) == cenas._MENU
    assert f"top: {cenas._SITE[0][1]}, width: 900" in tsx  # o título
    y = cenas.layout("parede", _pessoa(), {"gigante": "X"})["bloco"]["y"]
    assert f"c.layout?.bloco ?? {{x: W / 2, y: {y}}}" in tsx and f"lay(c).bloco || {{ x: 540, y: {y} }}" in js
    assert "layout?.desce" in tsx
    assert "c.layout?.selo" in tsx  # o selo vai onde o helper mediu, não num lugar fixo


def test_o_manifesto_continua_lendo():  # a régua não pode quebrar o versao.json
    assert json.loads((RAIZ / "versao.json").read_text(encoding="utf-8"))["versao"]
