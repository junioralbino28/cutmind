"""O Salvar do editor que mexe nas tomadas, aplicado sem o agente (aplicar_corte.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import aplicar_corte as ac  # noqa: E402

EDL = {"version": 1, "sources": {"A": "a.mp4"}, "grade": "neutro", "voice_master": True,
       "jcut_timeline": [{}], "total_duration_s": 20.0, "render": {"keep_resolution": True},
       "ranges": [{"source": "A", "start": 0.0, "end": 10.0, "beat": "abre", "quote": "oi", "reason": "r", "gain_db": 2.0},
                  {"source": "A", "start": 20.0, "end": 30.0, "beat": "fecha", "volume": 0.5}]}


def test_copia_o_que_e_do_agente_e_leva_o_que_e_da_pessoa():
    pedido = {"ranges": [{"source": "A", "start": 2.0, "end": 10.0, "beat": "abre", "take": 0, "volume": 1.5},
                         {"source": "A", "start": 20.0, "end": 30.0, "beat": "fecha", "take": 1}]}
    novo, origem = ac.novo_edl(EDL, pedido)
    r0, r1 = novo["ranges"]
    assert (r0["quote"], r0["reason"], r0["gain_db"], r0["volume"], r0["start"]) == ("oi", "r", 2.0, 1.5, 2.0)
    assert "volume" not in r1                     # sem `volume` no Salvar = 100%
    assert "take" not in r0 and origem == [0, 1]
    assert "jcut_timeline" not in novo and "total_duration_s" not in novo
    assert novo["grade"] == "neutro" and novo["voice_master"] is True and novo["render"] == {"keep_resolution": True}
    assert EDL["ranges"][1]["volume"] == 0.5      # o original não muda


def test_divisao_mantida_volta_a_ser_uma():
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 4.0, "take": 0},
                         {"source": "A", "start": 4.0, "end": 10.0, "take": 0}]}
    novo, origem = ac.novo_edl(EDL, pedido)
    assert [(r["start"], r["end"]) for r in novo["ranges"]] == [(0.0, 10.0)] and origem == [0]


def test_divisao_com_volume_diferente_fica_separada():
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 4.0, "take": 0},
                         {"source": "A", "start": 4.0, "end": 10.0, "take": 0, "volume": 2.0}]}
    assert len(ac.novo_edl(EDL, pedido)[0]["ranges"]) == 2


def test_tomadas_encostadas_de_origens_diferentes_nao_juntam():
    """Duas tomadas que o agente separou de propósito (zoom de cada uma) continuam duas."""
    edl = {**EDL, "ranges": [{"source": "A", "start": 0.0, "end": 4.0}, {"source": "A", "start": 4.0, "end": 8.0}]}
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 4.0, "take": 0}, {"source": "A", "start": 4.0, "end": 8.0, "take": 1}]}
    assert len(ac.novo_edl(edl, pedido)[0]["ranges"]) == 2


def test_duplicada_e_velocidade_e_curva():
    curva = {"nome": "Montanha", "pontos": [[0, 1], [0.5, 2], [1, 1]]}
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 10.0, "take": 0, "velocidade": 2.0},
                         {"source": "A", "start": 0.0, "end": 10.0, "take": 0, "curva": curva},
                         {"source": "A", "start": 20.0, "end": 30.0, "take": 1, "vaga": 3}]}
    novo, origem = ac.novo_edl(EDL, pedido)
    r0, r1, r2 = novo["ranges"]
    assert r0["velocidade"] == 2.0 and "curva" not in r0 and r1["curva"] == curva and "velocidade" not in r1
    assert r2["vaga"] == 3 and origem == [0, 0, 1] and r1["quote"] == "oi"


# ---- a conferência antes de aplicar: o que fica desalinhado vira pergunta ----
REGIOES = {"A": [(1.0, 3.0), (5.0, 9.0), (21.0, 29.0)]}
PALAVRAS = {"A": [{"type": "word", "text": " roteiro,", "start": 1.8, "end": 2.4}]}
CAM = {"versao": 1, "video": {"mudo": False}, "faixas": [{"tipo": "imagem", "itens": [
    {"id": "b", "arquivo": "midia/y.png", "inicio": 0.5, "duracao": 1.0}]}]}
APARA = {"ranges": [{"source": "A", "start": 2.0, "end": 10.0, "take": 0},
                    {"source": "A", "start": 20.0, "end": 30.0, "take": 1}]}


def test_conferir_acha_palavra_cortada_e_imagem_que_sai():
    avisos = ac.conferir(EDL, APARA, REGIOES, PALAVRAS, camadas=CAM)
    assert sorted(a["tipo"] for a in avisos) == ["item_sai", "ponta_na_fala"]
    ponta = next(a for a in avisos if a["tipo"] == "ponta_na_fala")
    assert (ponta["palavra"], ponta["tomada"], ponta["ponta"], ponta["em"]) == ("roteiro", 1, "começo", 0.0)
    assert "roteiro" in ponta["texto"]
    sai = next(a for a in avisos if a["tipo"] == "item_sai")
    assert (sai["item"], sai["nome"]) == ("imagem", "y.png") and 0.0 <= sai["em"] <= 0.1


def test_ponta_no_silencio_ou_igual_a_do_agente_nao_pergunta():
    no_silencio = {"ranges": [{**APARA["ranges"][0], "start": 3.05}, APARA["ranges"][1]]}
    assert ac.conferir(EDL, no_silencio, REGIOES, PALAVRAS) == []
    # a ponta que o agente escolheu, mesmo dentro de uma região de fala, não é pergunta nova
    edl = {**EDL, "ranges": [{**EDL["ranges"][0], "start": 2.0}, EDL["ranges"][1]]}
    assert ac.conferir(edl, APARA, REGIOES, PALAVRAS) == []


def test_emenda_com_silencio_longo_pergunta():
    # a 1ª tomada passa a ir até 12 s (a fala acaba em 9) e a 2ª começa em 20 (fala em 21): 4 s mudos
    longa = {"ranges": [{**APARA["ranges"][0], "start": 0.0, "end": 12.0}, APARA["ranges"][1]]}
    avisos = ac.conferir(EDL, longa, REGIOES, PALAVRAS)
    assert [a["tipo"] for a in avisos] == ["silencio_longo"]
    assert avisos[0]["tomadas"] == [1, 2] and abs(avisos[0]["em"] - 12.0) < 1e-6 and avisos[0]["segundos"] > 3.5


def test_emenda_que_ja_existia_nao_pergunta_de_novo():
    so_volume = {"ranges": [{**APARA["ranges"][0], "start": 0.0, "volume": 1.2}, APARA["ranges"][1]]}
    assert ac.conferir(EDL, so_volume, REGIOES, PALAVRAS) == []


def test_montagem_e_gravacao_sem_fala_nao_perguntam_de_fala_nem_de_silencio():
    longa = {"ranges": [{**APARA["ranges"][0], "start": 0.0, "end": 12.0}, APARA["ranges"][1]]}
    assert ac.conferir({**EDL, "montagem": {"formato": "9:16"}}, APARA, REGIOES, PALAVRAS) == []
    assert ac.conferir(EDL, longa, {"A": []}, {}) == []
    # mas o que sai do vídeo continua sendo pergunta
    sai = ac.conferir({**EDL, "montagem": {}}, APARA, REGIOES, PALAVRAS, camadas=CAM)
    assert [a["tipo"] for a in sai] == ["item_sai"]


def test_tomada_sem_origem_conhecida():
    novo, origem = ac.novo_edl(EDL, {"ranges": [{"source": "A", "start": 1.0, "end": 2.0, "take": 9}]})
    assert origem == [None] and novo["ranges"] == [{"source": "A", "start": 1.0, "end": 2.0}]


# ---- de ponta a ponta: vídeo de verdade, render de verdade ----
import json  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

AJUDA = Path(__file__).resolve().parents[1] / "helpers"


def _dur(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


@pytest.fixture
def projeto(tmp_path):
    """4 s de vídeo em pé com "fala" (um tom) de 0 a 1,5 s e de 2,5 a 4 s; o agente cortou a pausa."""
    fonte = tmp_path / "A.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
                    "-af", "volume=enable='between(t,1.5,2.5)':volume=0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(fonte)], check=True)
    edit = tmp_path / "edit"
    edit.mkdir()
    edl = {"version": 1, "sources": {"A": str(fonte)},
           "ranges": [{"source": "A", "start": 0.0, "end": 1.5, "beat": "um", "quote": "primeira"},
                      {"source": "A", "start": 2.5, "end": 4.0, "beat": "dois", "quote": "segunda"}]}
    (edit / "edl.json").write_bytes(json.dumps(edl).encode("utf-8"))
    subprocess.run([sys.executable, "-X", "utf8", str(AJUDA / "render.py"), str(edit / "edl.json"), "-o",
                    str(edit / "cut.mp4"), "--no-subtitles"], check=True, capture_output=True)
    return edit


def test_aplicar_pergunta_antes_e_aplica_depois(projeto):
    import camadas as cam
    edit = projeto
    total = json.loads((edit / "edl.json").read_text(encoding="utf-8"))["total_duration_s"]
    cam.save(edit / "camadas.json", {"versao": 1, "video": {"mudo": False}, "faixas": [
        {"id": "f1", "tipo": "imagem", "itens": [{"id": "i1", "arquivo": "midia/x.png", "inicio": total - 0.6, "duracao": 0.4}]}]})
    antes_edl = (edit / "edl.json").read_bytes()
    dur_antes = _dur(edit / "cut.mp4")
    # a 2ª tomada passa a começar em 3,0 s: no meio da "fala"
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 1.5, "take": 0},
                         {"source": "A", "start": 3.0, "end": 4.0, "take": 1}],
              "changes": [{"source": "A", "take": 1, "from": {"start": 2.5, "end": 4.0}, "to": {"start": 3.0, "end": 4.0}}]}
    with pytest.raises(ac.PrecisaConfirmar) as e:
        ac.aplicar(edit, pedido)
    assert [a["tipo"] for a in e.value.avisos] == ["ponta_na_fala"]
    assert (edit / "edl.json").read_bytes() == antes_edl            # nada mudou

    res = ac.aplicar(edit, pedido, confirmado=True)
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert [r["quote"] for r in edl["ranges"]] == ["primeira", "segunda"] and "render" in edl
    assert all("take" not in r for r in edl["ranges"])
    assert abs((dur_antes - _dur(edit / "cut.mp4")) - 0.5) < 0.08     # meio segundo a menos (±2 quadros)
    item = cam.load(edit / "camadas.json")["faixas"][0]["itens"][0]
    assert abs(item["inicio"] - (total - 0.6 - 0.5)) < 0.08 and res["fora"] == []
    feitos = json.loads((edit / "ajustes_feitos.json").read_text(encoding="utf-8"))["feitos"]
    assert feitos[-1]["oque"].startswith("corte: 1 tomada(s) aparada(s)")


def test_render_que_falha_devolve_o_edl_de_antes(projeto, monkeypatch):
    edit = projeto
    antes = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 1.5, "take": 0},
                         {"source": "A", "start": 2.5, "end": 3.9, "take": 1, "volume": 99}]}  # volume inválido: o render recusa
    with pytest.raises(ac.ErroCorte):
        ac.aplicar(edit, pedido, confirmado=True)
    assert json.loads((edit / "edl.json").read_text(encoding="utf-8")) == antes
