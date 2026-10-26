"""Montagem na batida: o modelo, os lugares no tempo da música, a padronização de fotos e clipes, o
projeto escrito e, quando o modelo pequeno do Beat This! está baixado, uma montagem de ponta a ponta
conferida troca a troca."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import batida  # noqa: E402
import camadas as cam  # noqa: E402
import montagem as m  # noqa: E402


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *map(str, args)], check=True)


def _sondar(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate,nb_frames", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return {s["codec_type"]: s for s in json.loads(r.stdout)["streams"]}


def _grade(batidas, fortes=None, drop=None, confianca="alta"):
    return {"batidas": [round(float(x), 3) for x in batidas],
            "fortes": [round(float(x), 3) for x in (fortes if fortes is not None else batidas[::4])],
            "drop": drop, "confianca": confianca, "bpm": 120.0}


# ---------- o modelo ----------

def test_modelo_confere_os_textos():
    mod = m.carregar_modelo({"vagas": [{"batidas": 2, "repetir": 3}], "textos": [
        {"texto": "OI", "vaga": 2},
        {"nome": "Título", "texto": "A\nB", "vaga": 1, "batidas": 4, "x": 300, "y": 700,
         "estilo": {"fonte": "Anton", "cor": "#FFE500"}}]})
    assert mod["textos"][0] == {"nome": "Texto 1", "texto": "OI", "vaga": 2, "batidas": None, "x": 540.0,
                                "y": 960.0, "estilo": {}}
    assert mod["textos"][1]["nome"] == "Título" and mod["textos"][1]["estilo"] == {"fonte": "Anton", "cor": "#ffe500"}
    assert m.carregar_modelo({"vagas": [{"batidas": 1}]})["textos"] == []
    for ruim in ([{"texto": "OI", "vaga": 4}], [{"vaga": 1}], [{"texto": "OI", "estilo": {"cor": "vermelho"}}],
                 [{"texto": "OI", "batidas": 0}], [{"texto": "OI"}] * 21, "OI"):
        with pytest.raises(m.ErroMontagem):
            m.carregar_modelo({"vagas": [{"batidas": 2, "repetir": 3}], "textos": ruim})


def test_texto_do_modelo_fecha_na_troca_do_lugar():
    b = [0.5 * k for k in range(40)]
    plano = m.planejar(_grade(b, fortes=[0.0]), m.carregar_modelo({"vagas": [{"batidas": 4, "repetir": 2},
                                                                              {"batidas": 1, "repetir": 4}]}))
    assert m.janela_do_texto(plano, _grade(b), 1, None) == (0, 60)  # sem batidas: o lugar
    assert m.janela_do_texto(plano, _grade(b), 1, 8) == (0, 120)    # 4 + 4: fecha na troca do lugar 3
    assert m.janela_do_texto(plano, _grade(b), 3, 2) == (120, 30)
    assert m.janela_do_texto(plano, _grade(b), 1, 6) == (0, 90)     # no meio do lugar 2: a batida da grade
    assert m.janela_do_texto(plano, _grade(b), 3, 50) == (120, plano["quadros"] - 120)  # passa do fim: o fim
    plano["lugares"][3]["quadro"] += 4  # uma troca que foi para o golpe: o texto acompanha a troca
    plano["lugares"][2]["quadros"] += 4
    assert m.janela_do_texto(plano, _grade(b), 1, 9) == (0, 139)
    curto = m.planejar(_grade([0.5 * k for k in range(4)], fortes=[0.0]),
                       m.carregar_modelo({"vagas": [{"batidas": 1, "repetir": 6}]}))
    assert m.janela_do_texto(curto, _grade(b), 5, None) is None  # a música acabou antes do lugar


def test_modelo_abre_repetir_e_numera_os_lugares():
    mod = m.carregar_modelo({"id": "t", "vagas": [{"batidas": 4, "repetir": 2},
                                                  {"batidas": 1, "movimento": "parado"}], "drop_na_vaga": 3})
    assert [(v["n"], v["batidas"]) for v in mod["vagas"]] == [(1, 4), (2, 4), (3, 1)]
    assert mod["vagas"][2]["movimento"] == "parado" and "movimento" not in mod["vagas"][0]
    assert mod["comeca"] == "forte" and mod["drop_na_vaga"] == 3 and mod["nome"] == "t"


@pytest.mark.parametrize("ruim", [
    {"vagas": []},
    {"vagas": [{"batidas": 0}]},
    {"vagas": [{"batidas": 1.5}]},
    {"vagas": [{"batidas": True}]},
    {"vagas": [{"batidas": 2, "repetir": 0}]},
    {"vagas": [{"batidas": 1}], "drop_na_vaga": 2},
    {"vagas": [{"batidas": 1, "movimento": "giro"}]},
    {"vagas": [{"batidas": 1}], "comeca": "meio"},
    {"vagas": [{"batidas": 1}], "versao": 2},
    {"vagas": [{"batidas": 1, "repetir": m.MAX_VAGAS + 1}]},
    {"vagas": [{"batidas": 1}], "golpe": "sim"},
])
def test_modelo_recusa_o_que_nao_entende(ruim):
    with pytest.raises(m.ErroMontagem):
        m.carregar_modelo(ruim)


# ---------- os lugares no tempo da música ----------

def test_cada_borda_vai_para_o_quadro_mais_perto_da_sua_batida():
    """Batidas irregulares (como as de uma música tocada): cada borda é arredondada a partir da
    batida dela, então o erro nunca passa de meio quadro e não se acumula."""
    b = [0.24 + 0.5 * k + 0.013 * np.sin(1.7 * k) for k in range(40)]
    grade = _grade(b, fortes=b[1::4])  # o primeiro tempo forte é a 2ª batida
    plano = m.planejar(grade, m.carregar_modelo({"vagas": [{"batidas": 2, "repetir": 8}]}))
    t0 = plano["inicio_musica"]
    assert t0 == round(b[1], 3)
    lug = plano["lugares"]
    assert lug[0]["quadro"] == 0 and len(lug) == 8
    for k, lg in enumerate(lug):
        batida_k = round(b[1 + 2 * k], 3) - t0
        assert abs(lg["quadro"] / 30 - batida_k) <= 1 / 60 + 1e-9
        assert lg["batida"] == pytest.approx(batida_k, abs=1e-4)
    for a, z in zip(lug, lug[1:]):
        assert a["quadro"] + a["quadros"] == z["quadro"]  # sem buraco nem sobreposição
    assert plano["quadros"] == lug[-1]["quadro"] + lug[-1]["quadros"]


def test_o_lugar_do_drop_cai_no_drop():
    b = [0.5 * k for k in range(60)]
    plano = m.planejar(_grade(b, drop=16.0), m.carregar_modelo(
        {"drop_na_vaga": 5, "vagas": [{"batidas": 4, "repetir": 4}, {"batidas": 1, "repetir": 8}]}))
    assert plano["inicio_musica"] == 8.0  # 16 batidas antes do drop: a música entra 8 s antes dele
    quinto = plano["lugares"][4]
    assert quinto["n"] == 5 and quinto["batida"] == pytest.approx(8.0) and quinto["quadro"] == 240
    assert plano["avisos"] == []


def test_drop_cedo_demais_avisa_e_entra_no_primeiro_tempo_forte():
    b = [0.5 * k for k in range(60)]
    plano = m.planejar(_grade(b, fortes=b[2::4], drop=4.0), m.carregar_modelo(
        {"drop_na_vaga": 5, "vagas": [{"batidas": 4, "repetir": 4}, {"batidas": 1}]}))
    assert plano["inicio_musica"] == 1.0
    assert any("não cai no drop" in a for a in plano["avisos"])


def test_musica_curta_deixa_de_fora_os_lugares_que_sobram():
    b = [0.5 * k for k in range(10)]
    plano = m.planejar(_grade(b), m.carregar_modelo({"vagas": [{"batidas": 4, "repetir": 4}]}))
    assert len(plano["lugares"]) == 2
    assert any("2 de 4 lugares" in a for a in plano["avisos"])


def _sincopada(compassos: int = 6) -> dict:
    """Batidas a cada 0,5 s; em cada compasso o 3º tempo é fraco e o golpe mais forte vem meia batida
    depois dele (o bumbo sincopado). Os outros contratempos são fracos."""
    b = [0.5 * k for k in range(4 * compassos + 1)]
    ac = []
    for i, x in enumerate(b):
        ac.append([x, 0.3 if i % 4 == 2 else 1.0])
        if i + 1 < len(b):
            ac.append([round(x + 0.27, 3), 1.8 if i % 4 == 2 else 0.2])  # o pico 20 ms depois do meio
    g = _grade(b)
    g["acentos"] = ac
    return g


def test_troca_vai_para_o_golpe_forte_do_contratempo():
    g = _sincopada()
    plano = m.planejar(g, m.carregar_modelo({"vagas": [{"batidas": 1, "repetir": 8}]}))
    inicio = [lg["batida"] for lg in plano["lugares"]]
    # a troca do 3º tempo (1,0 s e 3,0 s) vai para o golpe (1,27 s e 3,27 s); as outras ficam na batida
    assert inicio == [0.0, 0.5, 1.27, 1.5, 2.0, 2.5, 3.27, 3.5]
    assert [lg["golpe"] for lg in plano["lugares"]] == [False, False, True, False, False, False, True, False]
    assert plano["no_golpe"] == 2
    assert plano["lugares"][2]["quadro"] == round(1.27 * 30)
    lug = plano["lugares"]
    assert all(a["quadro"] + a["quadros"] == z["quadro"] for a, z in zip(lug, lug[1:]))
    # com "golpe": false, só a grade
    reto = m.planejar(g, m.carregar_modelo({"golpe": False, "vagas": [{"batidas": 1, "repetir": 8}]}))
    assert [lg["batida"] for lg in reto["lugares"]] == [0.5 * k for k in range(8)] and reto["no_golpe"] == 0
    # num lugar de 2 batidas, a troca que cai no 3º tempo também vai para o golpe
    dois = m.planejar(g, m.carregar_modelo({"vagas": [{"batidas": 2, "repetir": 4}]}))
    assert [lg["batida"] for lg in dois["lugares"]] == [0.0, 1.27, 2.0, 3.27]


def test_duas_trocas_nunca_colam_no_mesmo_golpe():
    """Contratempo forte entre duas batidas fracas: a 1ª troca vai para ele e a 2ª, que iria para o mesmo
    lugar, fica na batida."""
    b = [0.5 * k for k in range(9)]
    ac = []
    for i, x in enumerate(b):
        ac.append([x, 0.3 if i in (2, 3) else 1.0])
        if i + 1 < len(b):
            ac.append([x + 0.25, 1.8 if i == 2 else 0.2])
    g = _grade(b)
    g["acentos"] = ac
    plano = m.planejar(g, m.carregar_modelo({"vagas": [{"batidas": 1, "repetir": 6}]}))
    inicio = [lg["batida"] for lg in plano["lugares"]]
    assert inicio == [0.0, 0.5, 1.25, 1.5, 2.0, 2.5] and min(lg["quadros"] for lg in plano["lugares"]) >= 7


def test_referencias_sao_as_batidas_e_os_contratempos_fortes():
    g = _sincopada(2)
    refs = m.referencias(g)
    assert list(refs) == sorted([0.5 * k for k in range(9)] + [1.27, 3.27])
    assert list(m.referencias(_grade([0.0, 0.5, 1.0]))) == [0.0, 0.5, 1.0]  # grade antiga: só as batidas


def test_musica_sem_batida_nao_monta():
    with pytest.raises(m.ErroMontagem):
        m.planejar(_grade([]), m.carregar_modelo({"vagas": [{"batidas": 1}]}))


def test_batida_irregular_avisa():
    b = [0.5 * k for k in range(20)]
    plano = m.planejar(_grade(b, confianca="baixa"), m.carregar_modelo({"vagas": [{"batidas": 2}]}))
    assert any("confiança baixa" in a for a in plano["avisos"])


# ---------- a padronização ----------

def test_foto_e_clipes_viram_1080x1920_a_30_qps_com_som(tmp_path):
    foto = tmp_path / "foto.png"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=400x300", "-frames:v", "1", foto)
    longo = tmp_path / "longo.mp4"  # deitado, 25 qps, sem som
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", longo)
    curto = tmp_path / "curto.mp4"  # em pé, 60 qps, com som, 0,4 s para um lugar de 0,5 s
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=180x320:r=60:d=0.4", "-f", "lavfi", "-i", "sine=f=440:d=0.4", curto)
    curtissimo = tmp_path / "curtissimo.mp4"  # 0,2 s: nem a 0,5× enche o lugar
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=0.2", curtissimo)
    casos = {"foto": (foto, 15, 1.0, 0.5, False), "longo": (longo, 15, 1.0, 0.5, False),
             "curto": (curto, 15, 0.8, 0.4, False), "curtissimo": (curtissimo, 15, 0.5, 0.25, True)}
    for nome, (src, q, vel, fim, congela) in casos.items():
        out = tmp_path / f"p_{nome}.mp4"
        p = m.padronizar(src, out, q)
        s = _sondar(out)
        assert (s["video"]["width"], s["video"]["height"], s["video"]["r_frame_rate"]) == (1080, 1920, "30/1"), nome
        assert "audio" in s, nome  # toda mídia sai com faixa de som, mesmo a que não tinha
        assert (p["velocidade"], p["fim"], p["congela"]) == (vel, fim, congela), nome
        # o trecho tocado na velocidade dá exatamente o lugar
        assert round(p["fim"] / p["velocidade"] * 30, 6) == q, nome
        assert int(s["video"]["nb_frames"]) == p["quadros_no_arquivo"] >= round(p["fim"] * 30), nome


def _primeiro_quadro(video: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(1920, 1080, 3).astype(int)


def test_midia_deitada_entra_inteira_sobre_ela_mesma_desfocada(tmp_path):
    """Faixas vermelha, verde e azul lado a lado: cortada para encher a tela em pé, só o verde do meio
    sobraria. Inteira, as duas pontas aparecem no meio da altura, e em cima fica o fundo desfocado."""
    caixas = ",drawbox=x=0:w=213:h=360:color=red:t=fill,drawbox=x=427:w=213:h=360:color=blue:t=fill"
    foto, clipe = tmp_path / "deitada.png", tmp_path / "deitado.mp4"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=green:s=640x360{caixas}", "-frames:v", "1", foto)
    _ffmpeg("-f", "lavfi", "-i", f"color=c=green:s=640x360:r=30:d=1{caixas}", clipe)
    for src in (foto, clipe):
        out = tmp_path / f"{src.stem}.out.mp4"
        m.padronizar(src, out, 10, "parado")
        q = _primeiro_quadro(out)
        esq, dir_, topo = q[960, 30], q[960, 1050], q[100, 30]
        assert esq[0] > 180 and esq[1] < 80 and esq[2] < 80, (src.name, esq)  # a ponta vermelha
        assert dir_[2] > 180 and dir_[0] < 80 and dir_[1] < 80, (src.name, dir_)  # a ponta azul
        assert topo[1] > 90 and topo[0] < 120, (src.name, topo)  # acima da imagem: o meio dela, desfocado


def test_midia_em_pe_sai_igual_a_antes(tmp_path):
    """Em pé, o enquadramento novo dá o mesmo quadro, bit a bit, que o corte para encher a tela."""
    clipe = tmp_path / "em-pe.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=480x640:r=30:d=0.3", clipe)
    antigo = ("scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2:flags=lanczos"
              ":out_color_matrix=bt709:out_range=tv,format=yuv420p,crop=1080:1920,setsar=1")

    def hashes(grafo):
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(clipe), "-filter_complex", grafo, "-map", "[v]",
                            "-f", "framemd5", "-"], capture_output=True, text=True, check=True)
        return [x.split(",")[-1].strip() for x in r.stdout.splitlines() if x and not x.startswith("#")]

    assert hashes(f"[0:v]{antigo}[v]") == hashes(f"[0:v]null[m];{m._enquadrar('m', 'v', 1080, 1920)}")


def _quadro_de(video: Path, w: int, h: int) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3).astype(int)


def _faixas(caminho: Path, w: int, h: int, deitadas: bool) -> Path:
    """Vermelho, verde e azul em três faixas (lado a lado, ou de cima para baixo)."""
    if deitadas:
        cx = f",drawbox=y=0:h={h // 3}:w={w}:color=red:t=fill,drawbox=y={h - h // 3}:h={h // 3}:w={w}:color=blue:t=fill"
    else:
        cx = f",drawbox=x=0:w={w // 3}:h={h}:color=red:t=fill,drawbox=x={w - w // 3}:w={w // 3}:h={h}:color=blue:t=fill"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=green:s={w}x{h}{cx}", "-frames:v", "1", caminho)
    return caminho


def _cor(px) -> str:
    r, g, b = px
    if r > 180 and g < 80 and b < 80:
        return "vermelho"
    if b > 180 and r < 80 and g < 80:
        return "azul"
    if g > 90 and r < 120 and b < 120:
        return "verde"
    return f"? {tuple(px)}"


@pytest.mark.parametrize("formato,midia,pontos", [
    # deitado: a foto em pé entra inteira (as faixas de cima e de baixo aparecem) e o lado é o fundo desfocado
    ("16:9", (360, 640, True), {(30, 960): "vermelho", (1050, 960): "azul", (540, 100): "verde"}),
    # deitado: a foto deitada enche a tela até as bordas
    ("16:9", (640, 360, False), {(30, 30): "vermelho", (1050, 1890): "azul", (540, 960): "verde"}),
    # quadrado: a 4:3 enche (corta um pouco dos lados); a 16:9 entra inteira, com o fundo em cima
    ("1:1", (640, 480, False), {(30, 30): "vermelho", (1050, 1050): "azul"}),
    ("1:1", (640, 360, False), {(540, 30): "vermelho", (540, 1050): "azul", (30, 540): "verde"}),
])
def test_cada_formato_enquadra_pela_proporcao_da_midia(tmp_path, formato, midia, pontos):
    w, h = m.quadro_do_formato(formato)
    foto = _faixas(tmp_path / "foto.png", *midia)
    out = tmp_path / "out.mp4"
    m.padronizar(foto, out, 3, "parado", tamanho=(w, h))
    s = _sondar(out)["video"]
    assert (s["width"], s["height"]) == (w, h)
    q = _quadro_de(out, w, h)
    assert {p: _cor(q[p]) for p in pontos} == pontos


def test_enquadre_a_mao_poe_a_midia_no_tamanho_e_no_lugar_escolhidos(tmp_path):
    """Faixas vermelha, verde e azul (640×360) na tela deitada: no automático a foto enche, e a ponta
    esquerda é vermelha. A 2× de caber, com o centro a 1/4 da largura, a borda esquerda da tela mostra o
    verde do meio e a direita, o azul."""
    foto = _faixas(tmp_path / "foto.png", 640, 360, False)
    clipe = tmp_path / "clipe.mp4"
    _ffmpeg("-loop", "1", "-i", foto, "-t", "0.5", "-r", "30", "-pix_fmt", "yuv420p", clipe)
    for src in (foto, clipe):
        auto, mao = tmp_path / f"{src.stem}.auto.mp4", tmp_path / f"{src.stem}.mao.mp4"
        m.padronizar(src, auto, 3, "parado", tamanho=(1920, 1080))
        m.padronizar(src, mao, 3, "parado", tamanho=(1920, 1080), enquadre={"escala": 2, "x": 0.25, "y": 0.5})
        assert _cor(_quadro_de(auto, 1920, 1080)[540, 30]) == "vermelho", src.name
        q = _quadro_de(mao, 1920, 1080)
        assert (_cor(q[540, 30]), _cor(q[540, 1890])) == ("verde", "azul"), src.name


def test_tamanho_exibido_e_o_da_tela_girada(tmp_path):
    foto, clipe, girado = tmp_path / "f.png", tmp_path / "c.mp4", tmp_path / "g.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=90x160", "-frames:v", "1", foto)
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=1", "-pix_fmt", "yuv420p", clipe)
    _ffmpeg("-display_rotation:v", "90", "-i", clipe, "-c", "copy", girado)  # o vídeo de celular em pé
    assert m.tamanho_exibido(foto) == (90, 160)
    assert m.tamanho_exibido(clipe, 0.3) == (160, 90)
    assert m.tamanho_exibido(girado, 0.3) == (90, 160)


@pytest.mark.parametrize("ruim", [{"escala": 0.1, "x": 0.5, "y": 0.5}, {"escala": 1, "x": 1.2, "y": 0.5},
                                  {"escala": 1, "x": 0.5}, {"escala": True, "x": 0.5, "y": 0.5}, [1, 0.5, 0.5]])
def test_enquadre_recusa_o_que_nao_entende(ruim):
    with pytest.raises(m.ErroMontagem):
        m.conferir_enquadre(ruim)


def test_levar_ponto_guarda_o_lugar_relativo_e_o_limite_das_camadas():
    assert m.levar_ponto(540, 760, "9:16", "16:9") == (960, 427.5)
    assert m.levar_ponto(960, 427.5, "16:9", "1:1") == (540, 427.5)
    assert m.levar_ponto(540, 960, None, "9:16") == (540, 960)
    assert m.levar_ponto(2160, -1920, "9:16", "16:9") == (2160, -1080)  # x passaria de 2160
    # ir e voltar muitas vezes não faz o texto andar
    x, y = 333, 761
    for _ in range(20):
        x, y = m.levar_ponto(x, y, "9:16", "16:9")
        x, y = m.levar_ponto(x, y, "16:9", "1:1")
        x, y = m.levar_ponto(x, y, "1:1", "9:16")
    assert (x, y) == (333, 761)
    with pytest.raises(m.ErroMontagem):
        m.quadro_do_formato("4:3")


def test_modelo_guarda_o_formato_dos_textos():
    mod = m.carregar_modelo({"formato": "16:9", "vagas": [{"batidas": 2}], "textos": [{"texto": "OI"}]})
    assert mod["formato"] == "16:9" and (mod["textos"][0]["x"], mod["textos"][0]["y"]) == (960, 540)
    assert m.carregar_modelo({"vagas": [{"batidas": 2}]})["formato"] == "9:16"
    with pytest.raises(m.ErroMontagem):
        m.carregar_modelo({"formato": "4:3", "vagas": [{"batidas": 2}]})


def test_listar_midias_pasta_em_ordem_e_ponto_de_entrada(tmp_path):
    pasta = tmp_path / "fotos"
    pasta.mkdir()
    for nome in ("b.png", "A.mp4", "notas.txt"):
        (pasta / nome).write_bytes(b"x")
    clipe = tmp_path / "clipe.mp4"
    clipe.write_bytes(b"x")
    lista = m.listar_midias([str(pasta), f"{clipe}@2,5"])
    assert [(p.name, de) for p, de in lista] == [("A.mp4", 0.0), ("b.png", 0.0), ("clipe.mp4", 2.5)]
    with pytest.raises(m.ErroMontagem):
        m.listar_midias([str(tmp_path / "nao-existe.mp4")])


def _wav(caminho: Path, segundos: float, freq: float, sr: int = 22050) -> Path:
    t = np.arange(int(segundos * sr)) / sr
    pcm = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return caminho


def test_copiar_musica_reaproveita_a_mesma_e_numera_a_diferente(tmp_path):
    edit = tmp_path / "edit"
    um = _wav(tmp_path / "Minha Música.wav", 1.0, 440)
    a = m.copiar_musica(um, edit)
    assert a == edit / "midia" / "minha-musica.wav"
    assert m.copiar_musica(um, edit) == a  # a mesma música: a mesma cópia
    outra = tmp_path / "outra"
    outra.mkdir()
    dois = _wav(outra / "Minha Música.wav", 1.0, 660)
    assert m.copiar_musica(dois, edit) == edit / "midia" / "minha-musica-2.wav"
    clipe = tmp_path / "clipe da música.mp4"  # o clipe da música: vai só o som
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:d=1", "-f", "lavfi", "-i", "sine=f=330:d=1",
            "-c:a", "aac", "-shortest", clipe)
    som = m.copiar_musica(clipe, edit)
    assert som.suffix == ".m4a" and set(_sondar(som)) == {"audio"}
    assert m.copiar_musica(clipe, edit) == som
    assert not list((edit / "midia").glob(".*extraindo*"))


# ---------- o projeto ----------

def test_usar_escreve_edl_camadas_e_estado(tmp_path, monkeypatch):
    """Sem renderizar e sem o Beat This!: a grade vem pronta, 120 BPM."""
    b = [0.5 * k for k in range(40)]

    def grade_falsa(arquivo, edit=None, modelo=None):
        destino = Path(edit) / "batidas" / "falsa.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("{}", encoding="utf-8")
        return _grade(b), destino

    monkeypatch.setattr(m.batida, "analisar", grade_falsa)
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    fotos = []
    for i, cor in enumerate(("red", "blue")):
        fotos.append(tmp_path / f"f{i}.png")
        _ffmpeg("-f", "lavfi", "-i", f"color=c={cor}:s=90x160", "-frames:v", "1", fotos[-1])
    edit = tmp_path / "edit"
    r = m.usar({"id": "teste", "nome": "Teste", "vagas": [{"batidas": 2, "repetir": 3}]}, musica,
               [str(f) for f in fotos], edit, so_dados=True, jobs=1)
    assert r["lugares"] == 3 and r["duracao"] == 3.0
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["jcut"] is False and edl["montagem"]["inicio_musica"] == 0.0
    assert [x["vaga"] for x in edl["ranges"]] == [1, 2, 3]
    assert [x["end"] for x in edl["ranges"]] == [1.0, 1.0, 1.0]
    assert all(Path(p).is_absolute() and Path(p).is_file() for p in edl["sources"].values())
    assert [x["source"][:3] for x in edl["ranges"]] == ["v01", "v02", "v03"]
    assert edl["ranges"][2]["source"].endswith("_f0")  # duas fotos para três lugares: repete em ordem
    c = cam.load(edit / "camadas.json")
    assert c["video"]["mudo"] is True
    item = c["faixas"][0]["itens"][0]
    assert (item["arquivo"], item["corte"], item["duracao"]) == ("midia/musica.wav", 0.0, 3.0)
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    assert (st["video"], st["finalVideo"], st["fps"]) == ("cut.mp4", "final.mp4", 30)
    # de onde cada lugar saiu, para refazer um sem refazer os outros, e as mídias que o Trocar oferece
    lug = edl["montagem"]["lugares"]
    assert [(x["vaga"], Path(x["midia"]).name, x["de"]) for x in lug] == [(1, "f0.png", 0.0), (2, "f1.png", 0.0),
                                                                         (3, "f0.png", 0.0)]
    assert [Path(x).name for x in edl["montagem"]["midias"]] == ["f0.png", "f1.png"]
    # uma pasta com outra edição não é atropelada
    (edit / "edl.json").write_text(json.dumps({"ranges": []}), encoding="utf-8")
    with pytest.raises(m.ErroMontagem):
        m.usar({"vagas": [{"batidas": 2}]}, musica, [str(fotos[0])], edit, so_dados=True, jobs=1)


def _grade_fixa(monkeypatch, b):
    def grade_falsa(arquivo, edit=None, modelo=None):
        destino = Path(edit) / "batidas" / "falsa.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("{}", encoding="utf-8")
        return _grade(b), destino

    monkeypatch.setattr(m.batida, "analisar", grade_falsa)


def test_usar_poe_os_textos_do_modelo_nas_camadas(tmp_path, monkeypatch):
    _grade_fixa(monkeypatch, [0.5 * k for k in range(12)])  # 12 batidas: dos 7 lugares de 2, cabem 5
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    foto = tmp_path / "f.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=90x160", "-frames:v", "1", foto)
    modelo = {"vagas": [{"batidas": 2, "repetir": 7}], "textos": [
        {"nome": "Título", "texto": "OLÁ", "vaga": 1, "batidas": 4, "y": 700, "estilo": {"fonte": "Anton"}},
        {"nome": "Fim", "texto": "TCHAU", "vaga": 4},
        {"nome": "Longe", "texto": "NÃO CABE", "vaga": 6}]}
    edit = tmp_path / "edit"
    r = m.usar(modelo, musica, [str(foto)], edit, so_dados=True, jobs=1)
    assert r["textos"] == ["Título", "Fim"] and any('"Longe" ficou de fora' in a for a in r["avisos"])
    c = cam.load(edit / "camadas.json")
    assert [f["id"] for f in c["faixas"]] == ["musica", "modelo-texto-1", "modelo-texto-2"]
    t1, t2 = (f["itens"][0] for f in c["faixas"][1:])
    assert (t1["nome"], t1["texto"], t1["inicio"], t1["duracao"], t1["y"], t1["estilo"]) == (
        "Título", "OLÁ", 0.0, 2.0, 700.0, {"fonte": "Anton"})
    assert (t2["nome"], t2["inicio"], t2["duracao"]) == ("Fim", 3.0, 1.0)  # o lugar 4: da batida 6 à 8
    # montar de novo refaz os textos do modelo e deixa os da pessoa
    c["faixas"].append({"id": "t-meu", "tipo": "texto", "itens": [{"id": "t-meu-1", "texto": "meu", "duracao": 1}]})
    cam.save(edit / "camadas.json", c)
    m.usar(modelo, musica, [str(foto)], edit, so_dados=True, jobs=1)
    assert [f["id"] for f in cam.load(edit / "camadas.json")["faixas"]] == ["musica", "t-meu", "modelo-texto-1",
                                                                            "modelo-texto-2"]


def test_modelo_confere_as_transicoes():
    mod = m.carregar_modelo({"vagas": [{"batidas": 2, "repetir": 4}], "transicoes": [
        {"vaga": 4, "pacote": "t-zoom-central", "duracao": 0.3}, {"vaga": 2, "pacote": "t-abrir-2"}]})
    assert mod["transicoes"] == [{"vaga": 2, "pacote": "t-abrir-2", "duracao": 0.5},
                                 {"vaga": 4, "pacote": "t-zoom-central", "duracao": 0.3}]
    assert m.carregar_modelo({"vagas": [{"batidas": 1}]})["transicoes"] == []
    for ruim in ([{"vaga": 1, "pacote": "t-x"}],  # a 1ª troca é a que abre o lugar 2
                 [{"vaga": 5, "pacote": "t-x"}],
                 [{"vaga": 2, "pacote": "T X"}],
                 [{"vaga": 2, "pacote": "t-x", "duracao": 9}],
                 [{"vaga": 2, "pacote": "t-x"}, {"vaga": 2, "pacote": "t-y"}]):
        with pytest.raises(m.ErroMontagem):
            m.carregar_modelo({"vagas": [{"batidas": 2, "repetir": 4}], "transicoes": ruim})
    with pytest.raises(m.ErroMontagem):  # um lugar só não tem troca
        m.carregar_modelo({"vagas": [{"batidas": 2}], "transicoes": [{"vaga": 2, "pacote": "t-x"}]})


def test_transicoes_cabem_entre_as_trocas():
    # lugares de 1 s, 0,2 s, 1 s e 1 s: cada transição toma no máximo a distância até a troca vizinha
    plano = {"quadros": 96, "lugares": [{"quadro": 0}, {"quadro": 30}, {"quadro": 36}, {"quadro": 66}]}
    tr = m.transicoes_nos_lugares(plano, [{"vaga": 2, "pacote": "t-a", "duracao": 0.8},
                                         {"vaga": 3, "pacote": "t-b", "duracao": 0.8},
                                         {"vaga": 4, "pacote": "t-c", "duracao": 2.0},
                                         {"vaga": 9, "pacote": "t-d", "duracao": 0.5}])
    assert tr == [{"id": "t2", "tipo": "transicao", "pacote": "t-a", "corte": 1.0, "duracao": 0.2},
                  {"id": "t3", "tipo": "transicao", "pacote": "t-b", "corte": 1.2, "duracao": 0.2},
                  {"id": "t4", "tipo": "transicao", "pacote": "t-c", "corte": 2.2, "duracao": 1.0}]
    m.efeitos.normalize({"versao": 1, "itens": tr})  # e o efeitos.json aceita: encostam, não se sobrepõem


def _foto(caminho: Path, cor: str = "red") -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"color=c={cor}:s=90x160", "-frames:v", "1", caminho)
    return caminho


def test_usar_grava_transicoes_e_batidas_e_mantem_o_nome(tmp_path, monkeypatch):
    _grade_fixa(monkeypatch, [0.5 * k for k in range(20)])
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    foto = _foto(tmp_path / "f.png")
    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "state.json").write_text(json.dumps({"project": "Viagem", "phase": 0, "montagem": True}), encoding="utf-8")
    (edit / "efeitos.json").write_text(json.dumps({"versao": 1, "itens": [
        {"id": "f1", "tipo": "filtro", "pacote": "f-x", "inicio": 0, "duracao": 1}]}), encoding="utf-8")
    modelo = {"comeca": "batida", "vagas": [{"batidas": 2, "repetir": 2}, {"batidas": 1, "repetir": 2}],
              "transicoes": [{"vaga": 3, "pacote": "t-zoom-central", "duracao": 0.4}]}
    m.usar(modelo, musica, [str(foto)], edit, so_dados=True, jobs=1)
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert [x["batidas"] for x in edl["montagem"]["lugares"]] == [2, 2, 1, 1]
    assert edl["montagem"]["comeca"] == "batida"
    # a montagem é nova: o filtro de antes era de outros lugares e sai; a transição do modelo entra
    assert m.efeitos.load(edit / "efeitos.json")["itens"] == [
        {"id": "t3", "tipo": "transicao", "pacote": "t-zoom-central", "corte": 2.0, "duracao": 0.4}]
    assert json.loads((edit / "state.json").read_text(encoding="utf-8"))["project"] == "Viagem"


def test_capturar_devolve_o_modelo_da_montagem(tmp_path, monkeypatch):
    import montagens

    _grade_fixa(monkeypatch, [0.5 * k for k in range(40)])
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    foto = _foto(tmp_path / "f.png")
    edit = tmp_path / "edit"
    modelo = {"nome": "Ida", "drop_na_vaga": 3, "vagas": [{"batidas": 4}, {"batidas": 2, "repetir": 2},
                                                          {"batidas": 1, "movimento": "parado", "repetir": 4}],
              "textos": [{"nome": "Título", "texto": "OI", "vaga": 1, "batidas": 6, "y": 700},
                         {"nome": "Fim", "texto": "TCHAU", "vaga": 7}],
              "transicoes": [{"vaga": 2, "pacote": "t-abrir-2", "duracao": 0.6}]}
    m.usar(modelo, musica, [str(foto)], edit, so_dados=True, jobs=1)
    cap = m.capturar(edit, "Volta")
    assert cap.pop("avisos") == [] and cap["nome"] == "Volta"
    ida, volta = montagens.normalize({**modelo, "nome": "X"}), montagens.normalize({**cap, "nome": "X"})
    for k in ("vagas", "textos", "transicoes", "drop_na_vaga", "comeca", "golpe"):
        assert ida[k] == volta[k], k
    # um texto solto no meio de um lugar passa a começar com ele; o filtro não vai para o modelo
    c = cam.load(edit / "camadas.json")
    c["faixas"].append({"id": "t-meu", "tipo": "texto", "itens": [
        {"id": "t-meu-1", "texto": "meu", "inicio": 2.4, "duracao": 0.5}]})
    cam.save(edit / "camadas.json", c)
    ef = m.efeitos.load(edit / "efeitos.json")
    ef["itens"].append({"id": "f1", "tipo": "filtro", "pacote": "f-x", "inicio": 0, "duracao": 1})
    m.efeitos.save(edit / "efeitos.json", ef)
    cap = m.capturar(edit, "Volta")
    solto = [t for t in cap["textos"] if t["texto"] == "meu"][0]
    assert (solto["nome"], solto["vaga"], solto["batidas"]) == ("Texto 3", 2, 1)
    assert any("filtro" in a for a in cap["avisos"])
    (tmp_path / "corte").mkdir()
    (tmp_path / "corte" / "edl.json").write_text(json.dumps({"ranges": []}), encoding="utf-8")
    with pytest.raises(m.ErroMontagem):  # um corte de fala não vira modelo de montagem
        m.capturar(tmp_path / "corte", "Corte")


def test_montar_pelo_salvar_do_editor(tmp_path, monkeypatch):
    import montagens

    _grade_fixa(monkeypatch, [0.5 * k for k in range(20)])
    edit = tmp_path / "edit"
    (edit / "midia").mkdir(parents=True)
    _wav(edit / "midia" / "musica.wav", 2.0, 440)
    _foto(edit / "midia" / "f0.png")
    _foto(edit / "midia" / "f1.png", "blue")
    montagens.salvar({"nome": "Rápido", "vagas": [{"batidas": 1, "repetir": 4}]})
    pedido = {"modelo": "rapido", "musica": "midia/musica.wav", "midias": ["midia/f1.png", "midia/f0.png"]}
    (edit / "preview_edits.json").write_text(json.dumps({"montagem": {"usar": pedido}}), encoding="utf-8")
    r = m.montar(edit, so_dados=True)
    assert r["lugares"] == 4
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["montagem"]["modelo"] == "rapido"
    assert [Path(x["midia"]).name for x in edl["montagem"]["lugares"]] == ["f1.png", "f0.png", "f1.png", "f0.png"]
    # nada fora do midia/ do projeto, nem um modelo que sumiu
    fora = tmp_path / "fora.png"
    fora.write_bytes((edit / "midia" / "f0.png").read_bytes())
    for ruim in ({**pedido, "midias": [str(fora)]}, {**pedido, "midias": ["midia/../../fora.png"]},
                 {**pedido, "musica": "midia/nao.wav"}, {**pedido, "modelo": "nao-existe"}, {**pedido, "midias": []}):
        (edit / "preview_edits.json").write_text(json.dumps({"montagem": {"usar": ruim}}), encoding="utf-8")
        with pytest.raises(m.ErroMontagem):
            m.montar(edit, so_dados=True)


def test_montar_aceita_as_fotos_da_montagem_aberta(tmp_path, monkeypatch):
    """Outro modelo numa montagem feita pelo chat: as fotos dela ficam fora do midia/ e valem; um
    arquivo qualquer de fora, não. E a música segue tendo de estar no midia/."""
    import montagens

    _grade_fixa(monkeypatch, [0.5 * k for k in range(20)])
    edit = tmp_path / "edit"
    (edit / "midia").mkdir(parents=True)
    _wav(edit / "midia" / "musica.wav", 2.0, 440)
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    a, b = _foto(fotos / "a.png"), _foto(fotos / "b.png", "blue")
    musica_fora = _wav(fotos / "musica.wav", 2.0, 440)
    m.usar({"nome": "Dois", "vagas": [{"batidas": 2, "repetir": 2}]}, edit / "midia" / "musica.wav", [str(a), str(b)],
           edit, so_dados=True, jobs=1)
    montagens.salvar({"nome": "Quatro", "vagas": [{"batidas": 1, "repetir": 4}]})
    pedido = {"modelo": "quatro", "musica": "midia/musica.wav", "midias": [str(b), str(a)]}
    (edit / "preview_edits.json").write_text(json.dumps({"montagem": {"usar": pedido}}), encoding="utf-8")
    assert m.montar(edit, so_dados=True)["lugares"] == 4
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert [Path(x["midia"]).name for x in edl["montagem"]["lugares"]] == ["b.png", "a.png", "b.png", "a.png"]
    fora = _foto(tmp_path / "fora.png")
    for ruim in ({**pedido, "midias": [str(fora)]}, {**pedido, "musica": str(musica_fora)}):
        (edit / "preview_edits.json").write_text(json.dumps({"montagem": {"usar": ruim}}), encoding="utf-8")
        with pytest.raises(m.ErroMontagem):
            m.montar(edit, so_dados=True)


def test_imagem_fora_do_quadro_refaz_so_o_remotion_uma_vez(tmp_path, monkeypatch):
    """Com o computador ocupado, o Remotion pode pegar um quadro vizinho do vídeo: o conferir reprova a
    imagem e o render dele é refeito uma vez, um quadro por vez. A batida errada com a imagem certa, ou
    um vídeo sem Remotion (a imagem é o cut.mp4), não refazem nada."""
    chamadas, respostas = [], []
    monkeypatch.setattr(m, "conferir", lambda edit, modelo_batida=None: respostas.pop(0))
    monkeypatch.setattr(m, "renderizar", lambda edit, **kw: chamadas.append(kw))
    monkeypatch.setattr(m, "tem_visual", lambda edit: True)
    respostas[:] = [{"ok": False, "fora_do_quadro": 4}, {"ok": True, "fora_do_quadro": 0}]
    assert m.conferir_o_render(tmp_path) is True
    assert chamadas == [{"concorrencia": 1, "so_remotion": True}]
    chamadas.clear()
    respostas[:] = [{"ok": False, "fora_do_quadro": 4}, {"ok": False, "fora_do_quadro": 2}]
    assert m.conferir_o_render(tmp_path) is False and len(chamadas) == 1  # uma vez só
    chamadas.clear()
    respostas[:] = [{"ok": False, "fora_do_quadro": 0}]
    assert m.conferir_o_render(tmp_path) is False and chamadas == []
    monkeypatch.setattr(m, "tem_visual", lambda edit: False)
    respostas[:] = [{"ok": False, "fora_do_quadro": 3}]
    assert m.conferir_o_render(tmp_path) is False and chamadas == []
    respostas[:] = [{"ok": True, "fora_do_quadro": 0}]
    assert m.conferir_o_render(tmp_path) is True and chamadas == [] and respostas == []


def test_renderizar_so_o_remotion_um_quadro_por_vez(tmp_path, monkeypatch):
    passos, cmds = [], []
    monkeypatch.setattr(m.aquecer_navegador, "macos_antigo", lambda: None)
    monkeypatch.setattr(m, "_passo", lambda args: passos.append(Path(args[0]).name))
    monkeypatch.setattr(m, "tem_visual", lambda edit: True)
    monkeypatch.setattr(m, "preparar_remotion", lambda edit: tmp_path / "remotion")

    class Feito:
        returncode = 0

    monkeypatch.setattr(m.subprocess, "run", lambda cmd, cwd=None: cmds.append(cmd) or Feito())
    m.renderizar(tmp_path, concorrencia=1, so_remotion=True)
    assert passos == ["mixar_final.py"] and cmds[0][-1] == "--concurrency=1"  # o cut.mp4 fica
    passos.clear()
    cmds.clear()
    m.renderizar(tmp_path)
    assert passos == ["render.py", "mixar_final.py"] and not [c for c in cmds[0] if c.startswith("--concurrency")]


def test_render_do_formato_nao_em_pe_guarda_o_tamanho_dos_clipes(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(m, "_passo", lambda args: chamadas.append(args))
    monkeypatch.setattr(m, "tem_visual", lambda edit: False)
    for formato, espera in ((None, False), ("9:16", False), ("16:9", True), ("1:1", True)):
        (tmp_path / "edl.json").write_text(json.dumps({"montagem": {"formato": formato}}), encoding="utf-8")
        chamadas.clear()
        m.renderizar(tmp_path)
        assert ("--keep-resolution" in chamadas[0]) == espera, formato


def test_so_passa_pelo_remotion_com_algo_por_cima(tmp_path):
    def camadas(*faixas):
        cam.save(tmp_path / "camadas.json", {"faixas": list(faixas)})

    assert not m.tem_visual(tmp_path)
    camadas({"id": "a", "tipo": "audio", "itens": [{"id": "a1", "arquivo": "midia/m.mp3", "duracao": 2}]})
    assert not m.tem_visual(tmp_path)  # só a música
    camadas({"id": "t", "tipo": "texto", "oculto": True, "itens": [{"id": "t1", "texto": "oi", "duracao": 1}]})
    assert not m.tem_visual(tmp_path)  # o texto escondido não entra
    camadas({"id": "t", "tipo": "texto", "itens": [{"id": "t1", "texto": "oi", "duracao": 1}]})
    assert m.tem_visual(tmp_path)
    camadas({"id": "i", "tipo": "imagem", "itens": [{"id": "i1", "arquivo": "midia/a.png", "duracao": 1}]})
    assert m.tem_visual(tmp_path)
    camadas()
    (tmp_path / "efeitos.json").write_text(json.dumps({"versao": 1, "itens": [
        {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 0, "duracao": 1}]}), encoding="utf-8")
    assert m.tem_visual(tmp_path)


def test_preparar_remotion_escreve_o_public_da_montagem(tmp_path, monkeypatch):
    edit = tmp_path / "edit"
    rem = edit / "remotion"
    (rem / "node_modules" / "@remotion" / "cli").mkdir(parents=True)
    (rem / "public").mkdir()
    (rem / "package.json").write_text("{}", encoding="utf-8")
    (edit / "cut.mp4").write_bytes(b"corte")
    (edit / "edl.json").write_text(json.dumps({"jcut": False, "montagem": {"lugares": [{"vaga": 1}]}, "ranges": [
        {"source": "a", "start": 0.0, "end": 1.0, "vaga": 1}, {"source": "b", "start": 2.0, "end": 2.5, "vaga": 2}]}),
        encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"video": "cut.mp4", "fps": 30}), encoding="utf-8")
    (rem / "public" / "edit-data.json").write_text(json.dumps({
        "inserts": [{"src": "agente.png", "start": 0, "end": 1}, {"src": "c.png", "start": 0, "end": 1, "camada": "i1"}],
        "captions": {"enabled": True, "fontSize": 61}}), encoding="utf-8")
    chamados, zerados = [], []
    monkeypatch.setattr(m, "_template_do_kit", lambda e: chamados.append("atualizar_template"))
    monkeypatch.setattr(m, "_passo", lambda args: chamados.append(Path(args[0]).name))
    monkeypatch.setattr(m, "imagem_do_zero", lambda v: zerados.append(Path(v).relative_to(edit).as_posix()))
    monkeypatch.setattr(m, "atraso_da_imagem", lambda v: 0)
    assert m.preparar_remotion(edit) == rem.resolve()
    assert zerados == ["remotion/public/cut.mp4"]
    pub = rem / "public"
    assert json.loads((pub / "segments.json").read_text(encoding="utf-8")) == {
        "segments": [{"start": 0.0, "dur": 1.0}, {"start": 1.0, "dur": 0.5}], "videoLag": 0}
    tr = json.loads((pub / "track.json").read_text(encoding="utf-8"))
    assert (tr["count"], len(tr["points"]), tr["neutral"]) == (45, 45, True)
    assert json.loads((pub / "captions.json").read_text(encoding="utf-8")) == []
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    assert (ed["fps"], ed["durationSec"], ed["videoLag"], ed["width"], ed["height"]) == (30, 1.5, 0, 1080, 1920)
    assert ed["captions"] == {"enabled": False, "fontSize": 61}
    assert not ed["hook"]["enabled"] and not ed["camera"]["enabled"] and not ed["soundtrack"]["enabled"]
    assert ed["inserts"] == [{"src": "c.png", "start": 0, "end": 1, "camada": "i1"}]  # o resto é das camadas
    assert json.loads((edit / "state.json").read_text(encoding="utf-8"))["editData"] == "remotion/public/edit-data.json"
    # o projeto já montado acompanha o código do kit antes de cada render
    assert (pub / "cut.mp4").read_bytes() == b"corte"
    assert chamados == ["atualizar_template", "camadas_edit_data.py"]
    # com filtro, transição ou ajuste, o efeitos_render.py grava o public/cut.mp4 antes das camadas
    (edit / "efeitos.json").write_text(json.dumps({"versao": 1, "itens": [
        {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 0, "duracao": 1}]}), encoding="utf-8")
    chamados.clear()
    m.preparar_remotion(edit)
    assert chamados == ["atualizar_template", "efeitos_render.py", "camadas_edit_data.py"]
    # o Remotion desenha no quadro do formato da montagem
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    edl["montagem"]["formato"] = "16:9"
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    m.preparar_remotion(edit)
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    tr = json.loads((pub / "track.json").read_text(encoding="utf-8"))
    assert (ed["width"], ed["height"], tr["width"], tr["height"]) == (1920, 1080, 1920, 1080)


def test_template_do_kit_troca_o_codigo_velho_da_montagem(tmp_path):
    """Uma montagem feita com um kit anterior recebe o EfeitosBase.tsx novo (o que leva a duração da
    transição ao motor) antes do render, sem npm install quando o package.json é o mesmo."""
    edit = tmp_path / "edit"
    shutil.copytree(m.TEMPLATE, edit / "remotion")
    base = edit / "remotion" / "src" / "EfeitosBase.tsx"
    base.write_text(base.read_text(encoding="utf-8").replace(", duracao_ms: r.tr.duracao_ms", ""), encoding="utf-8")
    assert "duracao_ms: r.tr" not in base.read_text(encoding="utf-8")
    pl = m.atualizar_template.planejar(edit)
    assert pl["trocados"] == ["src/EfeitosBase.tsx"] and not pl["novos"] and not pl["npm"]  # sem npm install
    m._template_do_kit(edit)
    assert base.read_bytes() == (m.TEMPLATE / "src" / "EfeitosBase.tsx").read_bytes()
    assert list((edit / ".template-anterior").glob("*/src/EfeitosBase.tsx"))  # o anterior fica guardado


def _hashes(video: Path) -> list[str]:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:v:0", "-f", "framemd5", "-"],
                       capture_output=True, text=True, check=True)
    return [ln.split(",")[-1].strip() for ln in r.stdout.splitlines() if ln and not ln.startswith("#")]


def test_imagem_do_zero_tira_o_atraso_sem_recodificar(tmp_path):
    """O cut.mp4 da montagem começa 0,021 s depois do zero e o Remotion mostrava em cada quadro o quadro
    anterior do corte. Aqui, com quadros B, som e o vídeo começando em 0,05 s (2 quadros, arredondado
    para cima)."""
    video = tmp_path / "cut.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=1", "-f", "lavfi", "-i", "sine=f=440:d=1",
            "-c:v", "libx264", "-bf", "2", "-c:a", "aac", "-output_ts_offset", "0.05", video)
    antes = _hashes(video)
    assert m.atraso_da_imagem(video) == 2 and len(antes) == 30
    m.imagem_do_zero(video)
    assert m.atraso_da_imagem(video) == 0
    assert set(_sondar(video)) == {"video"}  # só a imagem: o som do vídeo final vem do mixar_final
    assert _hashes(video) == antes  # os mesmos quadros, na mesma ordem
    assert not list(tmp_path.glob("*.zero.mp4"))


def test_preparar_remotion_sem_node_diz_o_que_falta(tmp_path, monkeypatch):
    edit = tmp_path / "edit"
    edit.mkdir()
    monkeypatch.setattr(m.shutil, "which", lambda nome: None)
    with pytest.raises(m.ErroMontagem, match="Node"):
        m.preparar_remotion(edit)
    assert (edit / "remotion" / "package.json").is_file()  # o modelo de Reels já foi copiado


def test_aplicar_refaz_so_o_lugar_mudado(tmp_path, monkeypatch):
    _grade_fixa(monkeypatch, [0.5 * k for k in range(40)])
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    fotos = []
    for i, cor in enumerate(("red", "blue", "green")):
        fotos.append(tmp_path / f"f{i}.png")
        _ffmpeg("-f", "lavfi", "-i", f"color=c={cor}:s=90x160", "-frames:v", "1", fotos[-1])
    clipe = tmp_path / "clipe.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=3", clipe)
    edit = tmp_path / "edit"
    m.usar({"vagas": [{"batidas": 2, "repetir": 3}]}, musica, [str(fotos[0]), str(fotos[1])], edit, so_dados=True, jobs=1)
    pasta = edit / "montagem"
    antes = {p.name: p.stat().st_mtime_ns for p in pasta.glob("v*.mp4")}
    assert sorted(antes) == ["v01_f0.mp4", "v02_f1.mp4", "v03_f0.mp4"]

    r = m.aplicar(edit, [{"vaga": 2, "midia": str(fotos[2])}], so_dados=True)
    assert [x["vaga"] for x in r["lugares"]] == [2] and "total_s" in r
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert [x["source"] for x in edl["ranges"]] == ["v01_f0", "v02_f2", "v03_f0"]
    assert [x["end"] for x in edl["ranges"]] == [1.0, 1.0, 1.0] and edl["ranges"][1]["vaga"] == 2
    assert "v02_f1" not in edl["sources"] and Path(edl["sources"]["v02_f2"]).is_file()
    assert not (pasta / "v02_f1.mp4").exists()
    depois = {p.name: p.stat().st_mtime_ns for p in pasta.glob("v*.mp4")}
    assert depois["v01_f0.mp4"] == antes["v01_f0.mp4"] and depois["v03_f0.mp4"] == antes["v03_f0.mp4"]
    lug = {x["vaga"]: x for x in edl["montagem"]["lugares"]}
    assert Path(lug[2]["midia"]).name == "f2.png" and lug[2]["de"] == 0.0
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    assert "v02_f2" in st["sourceDurations"] and "v02_f1" not in st["sourceDurations"]

    # um clipe entrando dos 1,5 s, e depois só o trecho muda (a mesma mídia fica)
    m.aplicar(edit, [{"vaga": 3, "midia": str(clipe), "de": 1.5}], so_dados=True)
    m.aplicar(edit, [{"vaga": 3, "de": 0.5}], so_dados=True)
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    lug = {x["vaga"]: x for x in edl["montagem"]["lugares"]}
    assert Path(lug[3]["midia"]).name == "clipe.mp4" and lug[3]["de"] == 0.5
    assert edl["ranges"][2]["source"] == "v03_clipe" and not (pasta / "v03_clipe.novo.mp4").exists()

    # pelo Salvar do editor: o preview_edits.json, com mídia de midia/
    (edit / "midia" / "nova.png").write_bytes(fotos[0].read_bytes())
    (edit / "preview_edits.json").write_text(json.dumps({"montagem": {"lugares": [{"vaga": 1, "midia": "midia/nova.png"}]}}),
                                             encoding="utf-8")
    m.aplicar(edit, so_dados=True)
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["ranges"][0]["source"] == "v01_nova"
    assert edl["montagem"]["lugares"][0]["midia"] == "midia/nova.png"  # a do projeto, como o Trocar a lista
    with pytest.raises(m.ErroMontagem):
        m.aplicar(edit, [{"vaga": 9, "de": 1}], so_dados=True)
    with pytest.raises(m.ErroMontagem):
        m.aplicar(edit, [{"vaga": 1, "de": 0}, {"vaga": 1, "de": 0}], so_dados=True)

    # um pedido que falha no meio não deixa nada pela metade
    ruim = tmp_path / "ruim.png"
    ruim.write_bytes(b"isto nao e uma foto")
    edl_antes = (edit / "edl.json").read_bytes()
    with pytest.raises(m.ErroMontagem):
        m.aplicar(edit, [{"vaga": 2, "midia": str(fotos[0])}, {"vaga": 3, "midia": str(ruim)}], so_dados=True)
    assert (edit / "edl.json").read_bytes() == edl_antes
    assert not list(pasta.glob("*.novo*")) and (pasta / "v02_f2.mp4").is_file()


def _tamanhos(edit: Path) -> set[tuple[int, int]]:
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    return {(s["width"], s["height"]) for s in (_sondar(Path(p))["video"] for p in edl["sources"].values())}


def test_trocar_o_formato_refaz_todos_os_lugares_e_leva_os_textos(tmp_path, monkeypatch):
    _grade_fixa(monkeypatch, [0.5 * k for k in range(40)])
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    fotos = [_foto(tmp_path / "f0.png", "red"), _foto(tmp_path / "f1.png", "blue")]
    clipe = tmp_path / "clipe.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=3", clipe)
    modelo = {"vagas": [{"batidas": 2, "repetir": 3}],
              "textos": [{"nome": "Título", "texto": "OI", "vaga": 1, "x": 540, "y": 760}]}
    edit = tmp_path / "edit"
    r = m.usar(modelo, musica, [str(fotos[0]), str(clipe)], edit, so_dados=True, jobs=1, formato="16:9")
    assert r["formato"] == "16:9" and _tamanhos(edit) == {(1920, 1080)}
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["montagem"]["formato"] == "16:9"
    t = [f for f in cam.load(edit / "camadas.json")["faixas"] if f["tipo"] == "texto"][0]["itens"][0]
    assert (t["x"], t["y"]) == (960, 427.5)  # o modelo é em pé: o texto vai para o mesmo lugar relativo

    # pelo Salvar do editor: só o formato; o lugar 2 também troca de mídia no mesmo Salvar
    (edit / "preview_edits.json").write_text(json.dumps({"montagem": {
        "formato": "1:1", "lugares": [{"vaga": 2, "midia": str(fotos[1])}]}}), encoding="utf-8")
    ranges_antes = [(x["end"], x.get("velocidade")) for x in edl["ranges"]]
    r = m.aplicar(edit, so_dados=True)
    assert r["formato_mudou"] and sorted(x["vaga"] for x in r["lugares"]) == [1, 2, 3]
    assert _tamanhos(edit) == {(1080, 1080)}
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["montagem"]["formato"] == "1:1"
    assert [x["source"] for x in edl["ranges"]] == ["v01_f0", "v02_f1", "v03_f0"]
    assert [(x["end"], x.get("velocidade")) for x in edl["ranges"]] == ranges_antes  # o tempo de cada lugar fica
    t = [f for f in cam.load(edit / "camadas.json")["faixas"] if f["tipo"] == "texto"][0]["itens"][0]
    assert (t["x"], t["y"]) == (540, 427.5)
    assert m.capturar(edit, "Quadrado")["formato"] == "1:1"

    # de volta ao em pé, pela linha de comando; o mesmo formato sem lugar nenhum não tem o que refazer
    m.aplicar(edit, [], so_dados=True, formato="9:16")
    assert _tamanhos(edit) == {(1080, 1920)}
    with pytest.raises(m.ErroMontagem):
        m.aplicar(edit, [], so_dados=True, formato="9:16")


def test_enquadre_do_lugar_fica_ate_a_midia_ou_o_formato_mudar(tmp_path, monkeypatch):
    _grade_fixa(monkeypatch, [0.5 * k for k in range(40)])
    musica = _wav(tmp_path / "musica.wav", 2.0, 440)
    deitada, outra = _faixas(tmp_path / "deitada.png", 640, 360, False), _foto(tmp_path / "f1.png", "blue")
    edit = tmp_path / "edit"
    m.usar({"vagas": [{"batidas": 2, "repetir": 2}]}, musica, [str(deitada)], edit, so_dados=True, jobs=1)
    lugares = lambda: {lg["vaga"]: lg for lg in json.loads((edit / "edl.json").read_text(encoding="utf-8"))["montagem"]["lugares"]}  # noqa: E731
    clipe1 = lambda: Path(json.loads((edit / "edl.json").read_text(encoding="utf-8"))["sources"]["v01_deitada"])  # noqa: E731
    assert _cor(_quadro_de(clipe1(), 1080, 1920)[960, 30]) == "vermelho"  # automático: a foto deitada inteira
    perto = {"escala": 3.16, "x": 0.5, "y": 0.5}  # enche a tela em pé: só o meio da foto aparece
    r = m.aplicar(edit, [{"vaga": 1, "enquadre": perto}], so_dados=True)
    assert r["lugares"][0]["enquadre"] == perto and lugares()[1]["enquadre"] == perto and "enquadre" not in lugares()[2]
    assert _cor(_quadro_de(clipe1(), 1080, 1920)[960, 30]) == "verde"
    m.aplicar(edit, [{"vaga": 1, "de": 0}], so_dados=True)  # outro pedido no lugar: o enquadre fica
    assert lugares()[1]["enquadre"] == perto
    m.aplicar(edit, [{"vaga": 1, "enquadre": None}], so_dados=True)  # de volta ao automático
    assert "enquadre" not in lugares()[1] and _cor(_quadro_de(clipe1(), 1080, 1920)[960, 30]) == "vermelho"
    m.aplicar(edit, [{"vaga": 1, "enquadre": perto}], so_dados=True)
    m.aplicar(edit, [{"vaga": 1, "midia": str(outra)}], so_dados=True)  # mídia nova: volta ao automático
    assert "enquadre" not in lugares()[1]
    m.aplicar(edit, [{"vaga": 2, "enquadre": perto}], so_dados=True)
    m.aplicar(edit, [], so_dados=True, formato="16:9")  # formato novo: a escala era daquele quadro
    assert all("enquadre" not in lg for lg in lugares().values())
    # formato novo com um enquadre pedido no mesmo Salvar (o ajuste feito na prévia do formato novo): vale
    m.aplicar(edit, [{"vaga": 2, "enquadre": {"escala": 1, "x": 0.5, "y": 0.5}}], so_dados=True, formato="1:1")
    assert lugares()[2]["enquadre"] == {"escala": 1, "x": 0.5, "y": 0.5} and "enquadre" not in lugares()[1]


def test_conferir_aceita_a_troca_gradual_da_transicao(tmp_path, monkeypatch):
    """Com transição, a imagem muda aos poucos e o maior salto pode cair fora do corte; ali vale o
    corte, o centro da transição. Sem transição, o mesmo salto fora do quadro reprova."""
    edit = tmp_path / "edit"
    edit.mkdir()
    ranges = [{"source": f"v0{i}", "start": 0.0, "end": 0.5, "vaga": i} for i in range(1, 5)]
    (edit / "edl.json").write_text(json.dumps({"ranges": ranges, "montagem": {
        "batidas": "grade.json", "inicio_musica": 0.0}}), encoding="utf-8")
    (edit / "grade.json").write_text(json.dumps(_grade([0.0, 0.5, 1.0, 1.5, 2.0])), encoding="utf-8")
    (edit / "final.mp4").write_bytes(b"")
    d = np.zeros(59)
    d[[14, 27, 44]] = 50.0  # as trocas nos quadros 15, 28 (2 antes do corte do lugar 3) e 45
    monkeypatch.setattr(m, "diferencas", lambda video: d)
    monkeypatch.setattr(m.batida, "ler_audio", lambda video: np.zeros(1))
    monkeypatch.setattr(m.batida, "detectar", lambda *a: (np.array([0.5, 1.0, 1.5]), None))
    rel = m.conferir(edit, mostrar=False)
    assert not rel["ok"] and rel["fora_do_quadro"] == 1 and rel["com_transicao"] == 0

    m.efeitos.save(edit / "efeitos.json", {"versao": 1, "itens": [
        {"id": "t1", "tipo": "transicao", "pacote": "t-zoom-central", "corte": 1.0, "duracao": 0.4}]})
    rel = m.conferir(edit, mostrar=False)
    assert rel["ok"] and rel["fora_do_quadro"] == 0 and rel["com_transicao"] == 1, m.relatorio(rel)
    assert [x["transicao"] for x in rel["trocas"]] == [None, "t-zoom-central", None]
    assert "2 de 2 trocas no quadro planejado; 1 com transição" in m.relatorio(rel)


# ---------- de ponta a ponta ----------

PEQUENO = batida.pasta() / batida.MODELOS["pequeno"]["arquivo"]


@pytest.mark.skipif(not PEQUENO.is_file(), reason="o modelo pequeno do Beat This! não está baixado")
def test_montagem_de_ponta_a_ponta_corta_na_batida(tmp_path):
    from test_batida import _bateria  # a mesma bateria de rock que o Beat This! acerta 100%

    sr = 22050
    pcm = (np.clip(_bateria(sr, 120.0, 12.0), -1, 1) * 32767 * 0.8).astype("<i2")
    musica = tmp_path / "bateria.wav"
    with wave.open(str(musica), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    midias = []
    for i, cor in enumerate(("red", "green", "blue")):
        midias.append(tmp_path / f"m{i}.png")
        _ffmpeg("-f", "lavfi", "-i", f"color=c={cor}:s=90x160", "-frames:v", "1", midias[-1])
    clipe = tmp_path / "clipe.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=3", clipe)
    midias.append(clipe)
    edit = tmp_path / "edit"
    m.usar({"id": "e2e", "vagas": [{"batidas": 2, "repetir": 4}, {"batidas": 1, "repetir": 4}]}, musica,
           [str(x) for x in midias], edit, modelo_batida="pequeno", jobs=2)
    rel = m.conferir(edit, modelo_batida="pequeno", mostrar=False)
    assert rel["fora_do_quadro"] == 0, rel["trocas"]
    assert rel["ok"], m.relatorio(rel)
    assert abs(rel["som_vs_plano_ms"]) <= 20  # a música não atrasa da imagem

    # trocar a mídia de um lugar (o Salvar do editor) refaz só ele, e a batida continua certa
    m.aplicar(edit, [{"vaga": 3, "midia": str(midias[0])}])
    rel = m.conferir(edit, modelo_batida="pequeno", mostrar=False)
    assert rel["ok"] and rel["fora_do_quadro"] == 0, m.relatorio(rel)

    # o detector do deslocamento funciona: a música entrando 100 ms depois reprova
    c = cam.load(edit / "camadas.json")
    c["faixas"][0]["itens"][0]["corte"] += 0.1
    cam.save(edit / "camadas.json", c)
    deslocado = edit / "deslocado.mp4"
    subprocess.run([sys.executable, "-X", "utf8", str(Path(m.__file__).with_name("mixar_final.py")), str(edit),
                    "--render", str(edit / "cut.mp4"), "--imagem", "corte", "-o", str(deslocado)],
                   check=True, capture_output=True)
    rel = m.conferir(edit, video=deslocado, modelo_batida="pequeno", mostrar=False)
    assert not rel["ok"] and rel["som_vs_plano_ms"] == pytest.approx(-100, abs=20), m.relatorio(rel)


def test_montagem_com_texto_num_macos_antigo_para_antes_do_remotion(tmp_path, monkeypatch):
    """No macOS 12 o compositor do Remotion cai com "Symbol not found": a montagem diz o que fazer em vez
    de esperar o render morrer (medido num MacBook Air 2015)."""
    monkeypatch.setattr(m, "_passo", lambda args: None)
    monkeypatch.setattr(m, "tem_visual", lambda edit: True)
    monkeypatch.setattr(m, "preparar_remotion", lambda edit: (_ for _ in ()).throw(AssertionError("não devia preparar")))
    monkeypatch.setattr(m.aquecer_navegador, "macos_antigo", lambda: "12.7.6")
    with pytest.raises(m.ErroMontagem, match=r"macOS 13 ou mais novo, e este Mac está no 12\.7\.6"):
        m.renderizar(tmp_path, so_remotion=True)
