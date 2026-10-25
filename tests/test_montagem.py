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
