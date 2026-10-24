"""Os efeitos que tiram a pessoa do fundo (`cenas[]`): a medida da pessoa no recorte, o lugar de
cada coisa na tela, a validação e o helper que prepara o edit-data."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import cenas  # noqa: E402
import cenas_edit_data as ce  # noqa: E402

com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")

PESSOA = {"x0": 300, "x1": 780, "topo": 600, "base": 1920, "cabecaX": 540, "presenca": 1.0}


def _pessoa(**k):
    return {**PESSOA, **k}


def _gravar_recorte(caminho: Path, mascaras, w=540, h=960):
    """Um recorte de mentira no formato do person_matte.py: ProRes 4444 com alfa."""
    pr = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                           "-s", f"{w}x{h}", "-r", "30", "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444",
                           "-pix_fmt", "yuva444p10le", "-qscale:v", "6", str(caminho)], stdin=subprocess.PIPE)
    for m in mascaras:
        q = np.zeros((h, w, 4), np.uint8)
        q[m] = (190, 150, 130, 255)
        pr.stdin.write(q.tobytes())
    pr.stdin.close()
    assert pr.wait() == 0


def _elipse(x0=300, x1=780, topo=500, base=1920, w=540, h=960):
    """A pessoa de mentira: uma elipse com essa caixa, em px do quadro 1080x1920."""
    k = w / cenas.W
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = (x0 + x1) / 2 * k, (topo + base) / 2 * k
    return ((xx - cx) / ((x1 - x0) / 2 * k)) ** 2 + ((yy - cy) / ((base - topo) / 2 * k)) ** 2 <= 1


# ---------------------------------------------------------------- a medida da pessoa

@com_ffmpeg
def test_medir_pessoa_acha_a_caixa_e_o_topo(tmp_path):
    arq = tmp_path / "cena-0-6.mov"
    _gravar_recorte(arq, [_elipse()] * 6)
    p = cenas.medir_pessoa(arq)
    assert abs(p["x0"] - 300) <= 8 and abs(p["x1"] - 780) <= 8 and abs(p["topo"] - 500) <= 8
    assert p["base"] >= 1900 and abs(p["cabecaX"] - 540) <= 8
    assert p["presenca"] == 1 and p["quadros"] == 6


@com_ffmpeg
def test_medir_pessoa_ignora_quadros_vazios(tmp_path):
    arq = tmp_path / "cena-0-10.mov"
    _gravar_recorte(arq, [_elipse()] * 7 + [np.zeros((960, 540), bool)] * 3)
    p = cenas.medir_pessoa(arq)
    assert p["presenca"] == pytest.approx(0.7, abs=0.01)
    assert abs(p["x0"] - 300) <= 8 and abs(p["x1"] - 780) <= 8 and abs(p["topo"] - 500) <= 8


@com_ffmpeg
def test_perfil_ve_a_cabeca_mais_estreita_que_os_ombros(tmp_path):
    yy, xx = np.mgrid[0:960, 0:540]
    cabeca = ((xx - 270) / 70) ** 2 + ((yy - 380) / 90) ** 2 <= 1  # no quadro: x 400 a 680, y 580 a 940
    ombros = (yy >= 460) & (xx >= 120) & (xx < 420)  # no quadro: x 240 a 840, de y 920 para baixo
    arq = tmp_path / "cena-0-3.mov"
    _gravar_recorte(arq, [cabeca | ombros] * 3)
    p = cenas.medir_pessoa(arq)
    assert abs(p["x0"] - 240) <= 8 and abs(p["x1"] - 840) <= 8 and abs(p["topo"] - 580) <= 8
    da_cabeca = [r for r in p["perfil"] if r[0] >= 600 and r[1] <= 900]
    assert da_cabeca and all(r[2] >= 380 and r[3] <= 700 for r in da_cabeca)
    # ao lado da cabeça há espaço que a caixa (dos ombros) esconderia
    assert cenas.cobre(p, (60, 620, 300, 200)) == 0 < cenas.cobre({k: v for k, v in p.items() if k != "perfil"},
                                                                     (60, 620, 300, 200))


def test_zoom_aproxima_em_volta_do_topo_da_cabeca():
    p = cenas.com_zoom(_pessoa(base=1500), 1.5)
    assert (p["topo"], p["cabecaX"]) == (600, 540)  # o topo da cabeça fica parado
    assert (p["x0"], p["x1"], p["base"]) == (180, 900, 1920)  # o resto cresce, cortado pelo quadro


# ---------------------------------------------------------------- o lugar de cada coisa

@pytest.mark.parametrize("topo", [400, 600, 900])
def test_layout_vidro_poe_so_a_base_das_letras_atras_da_cabeca(topo):
    lay = cenas.layout("vidro", _pessoa(topo=topo), {"palavra": "GARGALO"})
    t = lay["tamanho"]
    pe, alto = lay["y"] + 0.36 * t, lay["y"] - 0.36 * t  # como o template desenha a palavra
    assert topo <= pe <= topo + 0.3 * t
    assert alto >= 60


def test_layout_vidro_palavra_longa_fica_menor():
    curta = cenas.layout("vidro", PESSOA, {"palavra": "GARGALO"})["tamanho"]
    longa = cenas.layout("vidro", PESSOA, {"palavra": "TRANSFORMAÇÃO"})["tamanho"]
    assert longa < curta and cenas.layout("vidro", PESSOA, {"palavra": "X", "tamanho": 420})["tamanho"] == 420


def test_layout_mural_nao_poe_manchete_em_cima_da_pessoa():
    ms = [{"t": f"Manchete {i}", "at": 1 + i * 0.2} for i in range(4)]
    direita = _pessoa(x0=600, x1=1080, topo=500)
    caixa = (600, 500, 480, 1420)
    slots = cenas.layout("mural", direita, {"manchetes": ms})["slots"]
    assert len(slots) == 4
    for s in slots:
        assert cenas._inter((s["x"], s["y"], s["w"], s["h"]), caixa) <= 0.15 * caixa[2] * caixa[3]
    centros = [s["x"] + s["w"] / 2 for s in cenas.layout("mural", PESSOA, {"manchetes": ms})["slots"]]
    assert any(c < PESSOA["x0"] for c in centros) and any(c > PESSOA["x1"] for c in centros)
    assert len(cenas.layout("mural", PESSOA, {"manchetes": ms[:2]})["slots"]) == 2


def test_layout_chroma_cabe_no_quadro():
    alta = _pessoa(topo=200)
    for lado in ("direita", "esquerda"):
        lay = cenas.layout("chroma", alta, {"titulo": "Site", "lado": lado})
        e = lay["escala"]
        x0, x1, topo = lay["x"] + alta["x0"] * e, lay["x"] + alta["x1"] * e, lay["y"] + alta["topo"] * e
        assert e < 1 and x0 >= 24 and x1 <= cenas.W - 24 and topo >= 24
        assert ((x0 + x1) / 2 > cenas.W / 2) == (lado == "direita")
    # tocando a borda do vídeo (o ombro cortado), a linha do corte fica na borda da tela
    larga = _pessoa(x0=100, x1=1080)
    lay = cenas.layout("chroma", larga, {"titulo": "Site"})
    assert lay["x"] + cenas.W * lay["escala"] >= cenas.W - 1


@pytest.mark.parametrize("topo", [400, 630, 900])
def test_layout_capa(topo):
    p = _pessoa(topo=topo)
    lay = cenas.layout("capa", p, {"nome": "EQUIPE"})
    t, b = lay["tamanho"], lay["baseline"]
    alto = b - 0.72 * t  # o topo do nome
    assert alto < topo < b  # o nome passa atrás da cabeça...
    assert topo - alto >= 0.5 * 0.72 * t  # ...e mais da metade dele fica acima dela
    assert alto >= 298  # abaixo da linha do topo da capa (arredondado)
    for col in lay["colunas"].values():
        assert col and cenas.cobre(p, (col["x"], col["y"], col["w"], 400)) == 0


def test_layout_capa_leva_as_chamadas_para_o_lado_livre():
    p = _pessoa(x0=0, x1=700)  # a pessoa encosta na borda esquerda: só a direita tem espaço
    col = cenas.layout("capa", p, {"nome": "X", "esquerda": [["a", "b"]]})["colunas"]
    assert col["direita"] is None and col["esquerda"]["lado"] == "direita" and col["esquerda"]["x"] >= 700
    # com as duas listas, cada uma fica no seu lado: a que não cabe fica fora (e o helper avisa)
    col = cenas.layout("capa", p, {"nome": "X", "esquerda": [["a", "b"]], "direita": [["c", "d"]]})["colunas"]
    assert col["esquerda"] is None and col["direita"]["lado"] == "direita"


def test_layout_grafico():
    baixa = _pessoa(base=1500)
    lay = cenas.layout("grafico", baixa, {"valores": [0.2, 0.5, 1], "etiqueta": "ESCALA"})
    assert lay["base"] <= 1500 and lay["base"] - lay["altura"] >= 200
    b = lay["bloco"]
    assert not cenas._inter((b["x"] - 200, b["y"] - 65, 400, 130), cenas._cabeca(baixa))
    # a cabeça mais para a direita: a etiqueta vai para a esquerda
    assert cenas.layout("grafico", _pessoa(x0=500, x1=1000, cabecaX=760), {"valores": [0.2, 1]})["bloco"]["x"] < 540


@pytest.mark.parametrize("topo", [400, 600, 900])
def test_layout_parede(topo):
    y = cenas.layout("parede", _pessoa(topo=topo), {"gigante": "POSTS"})["bloco"]["y"]
    assert y - 158 >= 0 and y + 158 < topo  # o bloco (~316 px) dentro do quadro e acima da cabeça


# ---------------------------------------------------------------- validação

def test_validar_diz_o_campo_que_falta():
    assert cenas.validar({"tipo": "vidro", "start": 1, "end": 3}) == ["falta `palavra`"]


def test_validar_lista_os_tipos_que_existem():
    (msg,) = cenas.validar({"tipo": "orbita", "start": 1, "end": 3, "titulo": "x"})
    assert "orbita" in msg and all(t in msg for t in ("fundo", "vidro", "capa", "mural", "parede", "grafico", "chroma"))


def test_validar_confere_faixas_listas_janela_e_caminhos():
    ok = {"tipo": "fundo", "start": 1, "end": 3, "fundo": "fundos/lousa", "escurecer": 0.3}
    assert cenas.validar(ok) == [] and cenas.validar({**ok, "fundo": "midia/Cenário 1.jpg"}) == []
    assert any("fundos/<" in e for e in cenas.validar({**ok, "fundo": "fundos/praia"}))
    assert any("fundos/<" in e for e in cenas.validar({**ok, "fundo": "midia/../../.secrets"}))
    assert cenas.validar({**ok, "escurecer": 0.9}) == ["`escurecer` vai de 0 a 0.6"]
    assert any("0,3 s" in e for e in cenas.validar({**ok, "end": 1.1}))
    vidro = {"tipo": "vidro", "start": 1, "end": 3, "palavra": "A", "at": 5}
    assert cenas.validar(vidro) == ["`at` (5) fica fora da janela (1 a 3)"]
    mural = {"tipo": "mural", "start": 1, "end": 3, "manchetes": [{"t": "a", "at": 1.5}] * 5}
    assert any("1 a 4" in e for e in cenas.validar(mural))
    grafico = {"tipo": "grafico", "start": 1, "end": 3, "valores": [0.1, 1.4]}
    assert any("0 a 1" in e for e in cenas.validar(grafico))
    assert cenas.validar({**grafico, "valores": [0.1, 1], "rotulos": ["a"]}) == ["`rotulos` é uma lista de 2 textos, um por valor"]


# ---------------------------------------------------------------- o helper

@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """Um projeto com o corte de mentira, os fundos prontos de mentira e o recorte trocado por uma
    elipse gravada no formato de verdade (sem o modelo de recorte)."""
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    (edit / "midia").mkdir()
    (edit / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (public / "cut.mp4").write_bytes(b"mp4")
    fundos = tmp_path / "fundos"
    fundos.mkdir()
    for f in cenas.FUNDOS:
        (fundos / f"{f}.jpg").write_bytes(f"jpg {f}".encode())
    monkeypatch.setattr(ce, "FUNDOS_DIR", fundos)
    monkeypatch.setattr(ce, "_tem_recorte", lambda: True)
    chamadas = []

    def recorte_falso(cmd):
        chamadas.append(cmd)
        _gravar_recorte(Path(cmd[cmd.index("-o") + 1]), [_elipse(w=270, h=480)] * 3, w=270, h=480)
        return True
    monkeypatch.setattr(ce, "_rodar", recorte_falso)
    return edit, public, chamadas


def _cenas(public: Path, lista: list) -> None:
    (public / "edit-data.json").write_text(json.dumps({"fps": 30, "cenas": lista}, ensure_ascii=False), encoding="utf-8")


def _lidas(public: Path) -> list:
    return json.loads((public / "edit-data.json").read_text(encoding="utf-8"))["cenas"]


@com_ffmpeg
def test_helper_faz_o_recorte_uma_vez_e_apaga_o_velho(projeto):
    edit, public, chamadas = projeto
    _cenas(public, [{"tipo": "vidro", "start": 1.0, "end": 3.0, "palavra": "GARGALO"}])
    r = ce.aplicar(edit)
    assert (r["feitos"], r["pendentes"], r["erros"], r["prontos"]) == (["cena-30-60.mov"], [], [], 1)
    cmd = chamadas[0]
    assert cmd[cmd.index("--start") + 1] == "1.000000" and cmd[cmd.index("--duration") + 1] == "2.000000"
    assert cmd[-2:] == ["--cor", "misturada"]  # fundo novo: a borda sem a cor do fundo antigo
    c = _lidas(public)[0]
    assert c["matte"] == "cena-30-60.mov" and abs(c["pessoa"]["topo"] - 500) <= 8 and "perfil" not in c["pessoa"]
    assert set(c["layout"]) == {"y", "tamanho"}
    r = ce.aplicar(edit)  # de novo, sobre o que ele mesmo gravou: nada é refeito nem medido
    assert len(chamadas) == 1 and r["medidos"] == [] and _lidas(public)[0] == c
    _cenas(public, [{"tipo": "vidro", "start": 2.0, "end": 3.0, "palavra": "GARGALO"}])  # mudou a janela
    ce.aplicar(edit)
    assert sorted(p.name for p in public.glob("cena-*")) == ["cena-60-30.mov"]
    assert list(json.loads((public / "cenas" / "medidas.json").read_text(encoding="utf-8"))) == ["cena-60-30.mov"]


def test_camadas_nao_apaga_recorte_de_cena_e_vice_versa(projeto):
    from camadas_edit_data import aplicar as aplicar_camadas
    edit, public, _ = projeto
    (edit / "camadas.json").write_text(json.dumps({"versao": 1, "video": {"mudo": False}, "faixas": []}), encoding="utf-8")
    _cenas(public, [])
    (public / "cena-30-60.mov").write_bytes(b"cena")
    (public / "pessoa-t1-1-30-60.mov").write_bytes(b"pessoa")
    aplicar_camadas(edit)
    assert (public / "cena-30-60.mov").exists() and not (public / "pessoa-t1-1-30-60.mov").exists()
    (public / "pessoa-t1-1-30-60.mov").write_bytes(b"pessoa")
    ce.aplicar(edit)
    assert (public / "pessoa-t1-1-30-60.mov").exists() and not (public / "cena-30-60.mov").exists()


@com_ffmpeg
def test_desligada_guarda_o_recorte_mas_nao_ganha_um_novo(projeto):
    edit, public, chamadas = projeto
    _cenas(public, [{"tipo": "vidro", "start": 1.0, "end": 3.0, "palavra": "A"}])
    ce.aplicar(edit)
    _cenas(public, [{"tipo": "vidro", "start": 1.0, "end": 3.0, "palavra": "A", "desligada": True},
                    {"tipo": "vidro", "start": 5.0, "end": 6.0, "palavra": "B", "desligada": True}])
    r = ce.aplicar(edit)
    a, b = _lidas(public)
    assert (len(chamadas), r["pendentes"], r["prontos"]) == (1, [], 0)
    assert a["matte"] == "cena-30-60.mov" and "matte" not in b


@com_ffmpeg
def test_capa_avisa_as_chamadas_que_ficaram_sem_lugar(projeto, monkeypatch):
    edit, public, _ = projeto

    def larga(cmd):  # a pessoa ocupa a largura toda, como num close com as mãos nas bordas
        m = np.zeros((480, 270), bool)
        m[150:, :] = True
        _gravar_recorte(Path(cmd[cmd.index("-o") + 1]), [m] * 3, w=270, h=480)
        return True
    monkeypatch.setattr(ce, "_rodar", larga)
    _cenas(public, [{"tipo": "capa", "start": 1.0, "end": 3.0, "nome": "EQUIPE", "esquerda": [["ANTES", "horas"]]}])
    r = ce.aplicar(edit)
    assert len(r["avisos"]) == 1 and "`esquerda`" in r["avisos"][0]
    assert _lidas(public)[0]["layout"]["colunas"] == {"esquerda": None, "direita": None}


def test_sem_o_extra_de_recorte_avisa_o_comando(projeto, monkeypatch):
    edit, public, chamadas = projeto
    monkeypatch.setattr(ce, "_tem_recorte", lambda: False)
    _cenas(public, [{"tipo": "vidro", "start": 1.0, "end": 3.0, "palavra": "GARGALO"}])
    r = ce.aplicar(edit)
    assert chamadas == [] and r["sem_extra"] and len(r["pendentes"]) == 1 and "person_matte.py" in r["pendentes"][0]
    assert "matte" not in _lidas(public)[0]  # sem recorte, o efeito fica fora do vídeo


def test_erro_de_validacao_nao_grava_nada(projeto):
    edit, public, chamadas = projeto
    _cenas(public, [{"tipo": "vidro", "start": 1.0, "end": 3.0}])
    antes = (public / "edit-data.json").read_bytes()
    r = ce.aplicar(edit)
    assert r["erros"] == ["cenas[0] (vidro): falta `palavra`"] and chamadas == []
    assert (public / "edit-data.json").read_bytes() == antes


@com_ffmpeg
def test_fundo_copia_o_pronto_e_a_imagem_do_projeto(projeto):
    edit, public, _ = projeto
    (edit / "midia" / "Cenário 1.jpg").write_bytes(b"jpg do projeto")
    _cenas(public, [{"tipo": "fundo", "start": 1.0, "end": 3.0, "fundo": "fundos/lousa"},
                    {"tipo": "fundo", "start": 4.0, "end": 6.0, "fundo": "midia/Cenário 1.jpg"},
                    {"tipo": "fundo", "start": 7.0, "end": 9.0, "fundo": "midia/sumiu.jpg"},
                    {"tipo": "mural", "start": 10.0, "end": 12.0, "manchetes": [{"t": "Manchete", "at": 10.5}]}])
    r = ce.aplicar(edit)
    a, b, c, m = _lidas(public)
    assert a["layout"] == {"fundo": "cenas/fundo-lousa.jpg"}
    assert (public / "cenas" / "fundo-lousa.jpg").read_bytes() == b"jpg lousa"
    nome = b["layout"]["fundo"]
    assert nome.isascii() and " " not in nome and (public / nome).read_bytes() == b"jpg do projeto"
    assert r["faltando"] == ["midia/sumiu.jpg"] and "fundo" not in c["layout"]
    assert m["layout"]["fundo"] == "cenas/fundo-parede.jpg"  # o mural usa a parede escura sem pedir
    _cenas(public, [{"tipo": "fundo", "start": 1.0, "end": 3.0, "fundo": "fundos/neon"}])  # trocou o fundo
    ce.aplicar(edit)
    assert sorted(p.name for p in (public / "cenas").iterdir()) == ["fundo-neon.jpg", "medidas.json"]


@com_ffmpeg
def test_parede_sem_fotos_tira_quadros_do_proprio_corte(projeto):
    from PIL import Image
    edit, public, _ = projeto
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=216x384:rate=30:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(public / "cut.mp4")], check=True)
    _cenas(public, [{"tipo": "parede", "start": 1.0, "end": 2.0, "gigante": "POSTS"}])
    r = ce.aplicar(edit)
    assert r["faltando"] == [] and r["pendentes"] == []
    lay = _lidas(public)[0]["layout"]
    assert lay["fundo"] == "cenas/fundo-concreto.jpg" and lay["bloco"]["x"] == 540
    assert len(lay["fotos"]) == cenas.PAREDE_FOTOS
    for f in lay["fotos"]:
        ms = int(f["src"].removeprefix("cenas/quadro-").removesuffix(".jpg"))
        assert not 1000 <= ms <= 2000  # nenhum quadro de dentro da janela do efeito
        with Image.open(public / f["src"]) as im:
            assert im.size == (ce.FOTO_PX, ce.FOTO_PX)
    # com fotos do projeto, são elas (copiadas com nome limpo), com a legenda
    (edit / "midia" / "Meu post.png").write_bytes(b"png")
    _cenas(public, [{"tipo": "parede", "start": 1.0, "end": 2.0, "fotos": [{"src": "midia/Meu post.png", "legenda": "jan"}]}])
    ce.aplicar(edit)
    (foto,) = _lidas(public)[0]["layout"]["fotos"]
    assert foto["legenda"] == "jan" and (public / foto["src"]).read_bytes() == b"png"
    assert not list((public / "cenas").glob("quadro-*"))  # os quadros do corte saíram


@com_ffmpeg
def test_ler_janela_comeca_no_quadro_pedido(tmp_path):
    """O recorte de um efeito tem de começar no mesmo quadro da base: a Letra de vidro mostra os dois."""
    import cv2
    import person_matte as pm
    video = tmp_path / "numerado.mp4"
    pr = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "64x64",
                           "-r", "30", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "30", "-bf", "3", str(video)],
                          stdin=subprocess.PIPE)
    for q in range(60):  # o quadro q é todo cinza q*4
        pr.stdin.write(bytes([q * 4]) * 64 * 64)
    pr.stdin.close()
    assert pr.wait() == 0
    cap = cv2.VideoCapture(str(video))
    lidos = [round(f.mean() / 4) for f in pm.ler_janela(cap, 37, 5)]
    cap.release()
    assert lidos == [37, 38, 39, 40, 41]
