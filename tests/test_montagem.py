"""Montagem na batida: o modelo, os lugares no tempo da música, a padronização de fotos e clipes, o
projeto escrito e, quando o modelo pequeno do Beat This! está baixado, uma montagem de ponta a ponta
conferida troca a troca."""
from __future__ import annotations

import json
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
