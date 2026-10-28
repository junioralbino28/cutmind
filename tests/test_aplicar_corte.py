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


def test_ponta_alinhada_ao_quadro_e_a_mesma_ponta_arredondada():
    """O editor manda 9,233 para a ponta que o edl.json guarda como 9,233333 (o quadro): não é ponta nova."""
    edl = {**EDL, "ranges": [{**EDL["ranges"][0], "end": 9.233333}, {**EDL["ranges"][1], "start": 20.966667}]}
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 9.233, "take": 0}, {"source": "A", "start": 20.967, "end": 30.0, "take": 1}]}
    assert ac.conferir(edl, pedido, REGIOES, PALAVRAS) == []


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


def _grava(p: Path, dados) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps(dados, ensure_ascii=False).encode("utf-8"))


def test_aplicar_leva_a_fase2_para_o_corte_novo(projeto):
    """Com a Fase 2 pronta, aparar o começo da 2ª tomada leva a legenda, os blocos, a transcrição, o
    segments.json e o rastreio neutro para o corte novo, e o Baixar não para mais (fase2_do_corte)."""
    import gerar as gr
    import tempo
    edit = projeto
    pub = edit / "remotion" / "public"
    _grava(edit / "state.json", {"project": "t", "phase": 2, "video": "cut.mp4", "fps": 30, "style": {"captions": "karaoke"},
                                 "editData": "remotion/public/edit-data.json", "captions": "remotion/public/captions.json"})
    segs, quadros = gr.segmentos_do_corte(edit, 30)
    _grava(pub / "segments.json", {"segments": segs, "videoLag": 0})
    velhas = tempo.tomadas_no_corte(json.loads((edit / "edl.json").read_text(encoding="utf-8")))
    o2 = velhas[1]["out"]  # onde a 2ª tomada (fonte 2,5 s) começa no corte velho
    _grava(pub / "edit-data.json", {
        "fps": 30, "width": 180, "height": 320, "durationSec": round(quadros / 30, 4), "camera": {"zooms": [1.1, 1.3]},
        "inserts": [{"src": "a.png", "start": round(o2 + 0.1, 3), "end": round(o2 + 0.3, 3)},      # some com o aparo
                    {"src": "b.png", "start": round(o2 + 0.7, 3), "end": round(o2 + 0.9, 3)}],
        "behind": [{"kind": "image", "src": "x.jpg", "matte": "fg.mov", "start": round(o2 + 0.1, 3), "dur": 1.0}]})
    _grava(pub / "captions.json", [{"text": "um", "startMs": 500, "endMs": 800, "timestampMs": 600},
                                   {"text": "dois", "startMs": round(o2 * 1000), "endMs": round((o2 + 0.15) * 1000)},
                                   {"text": "três", "startMs": round((o2 + 1.0) * 1000), "endMs": round((o2 + 1.2) * 1000)}])
    _grava(edit / "transcripts" / "cut.json", {"language": "pt", "text": "um dois três", "words": [
        {"text": "um", "start": 0.5, "end": 0.8, "type": "word"},
        {"text": "dois", "start": o2, "end": o2 + 0.15, "type": "word"},
        {"text": "três", "start": o2 + 1.0, "end": o2 + 1.2, "type": "word"}]})
    _grava(pub / "track.json", {"fps": 30, "width": 180, "height": 320, "count": quadros,
                                "points": [[90, 160]] * quadros, "neutral": True})
    assert gr.fase2_do_corte(edit)
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 1.5, "take": 0},
                         {"source": "A", "start": 3.0, "end": 4.0, "take": 1}],
              "changes": [{"source": "A", "take": 1, "from": {"start": 2.5, "end": 4.0}, "to": {"start": 3.0, "end": 4.0}}]}

    with pytest.raises(ac.PrecisaConfirmar) as e:  # pergunta, e diz o que da Fase 2 sairia
        ac.aplicar(edit, pedido)
    sai = [a for a in e.value.avisos if a["tipo"] == "item_sai"]
    assert [(a["item"], a["nome"]) for a in sai] == [("insert", "a.png")]
    assert sai[0]["texto"].startswith("A imagem do vídeo final «a.png» estava num trecho")

    res = ac.aplicar(edit, pedido, confirmado=True)
    assert [(f["item"], f["nome"]) for f in res["fora"]] == [("insert", "a.png")]
    assert gr.fase2_do_corte(edit)                       # o Baixar não para mais
    novas = tempo.tomadas_no_corte(json.loads((edit / "edl.json").read_text(encoding="utf-8")))
    n2 = novas[1]["out"]                                 # a 2ª tomada (agora da fonte 3,0 s) no corte novo
    q = gr._sondar(edit / "cut.mp4")[3]
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    assert ed["durationSec"] == round(q / 30, 4)
    assert [i["src"] for i in ed["inserts"]] == ["b.png"] and abs(ed["inserts"][0]["start"] - (n2 + 0.2)) < 0.05
    behind = ed["behind"][0]
    assert abs(behind["start"] - n2) < 0.05 and behind["_refazerMatte"] is True   # o começo foi aparado
    caps = json.loads((pub / "captions.json").read_text(encoding="utf-8"))
    assert [c["text"] for c in caps] == ["um", "três"] and abs(caps[1]["startMs"] - (n2 + 0.5) * 1000) < 50
    tr = json.loads((edit / "transcripts" / "cut.json").read_text(encoding="utf-8"))
    assert tr["text"] == "um três" and abs(tr["words"][1]["start"] - (n2 + 0.5)) < 0.05
    track = json.loads((pub / "track.json").read_text(encoding="utf-8"))
    assert track["count"] == q and len(track["points"]) == q


def test_transcricao_de_um_corte_mais_velho_sai(projeto):
    """A transcrição feita antes do cut.mp4 de agora é de outro corte: o re-corte apaga, para o
    transcribe.py não devolver do cache as palavras erradas."""
    import os
    edit = projeto
    tr = edit / "transcripts" / "cut.json"
    _grava(tr, {"language": "pt", "text": "velho", "words": [{"text": "velho", "start": 0.5, "end": 0.8}]})
    velho = (edit / "cut.mp4").stat().st_mtime - 60
    os.utime(tr, (velho, velho))
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 1.4, "take": 0},
                         {"source": "A", "start": 2.5, "end": 4.0, "take": 1}],
              "changes": [{"source": "A", "take": 0, "from": {"start": 0.0, "end": 1.5}, "to": {"start": 0.0, "end": 1.4}}]}
    ac.aplicar(edit, pedido, confirmado=True)
    assert not tr.exists()



# ---- o enquadre da gravação (etapa 3): é da pessoa, e sozinho não refaz o corte

def test_enquadre_e_da_pessoa_e_conferido():
    pedido = {"ranges": [{"source": "A", "start": 0.0, "end": 10.0, "take": 0, "enquadre": {"x": 540, "y": 1440, "largura": 1300}},
                         {"source": "A", "start": 20.0, "end": 30.0, "take": 1, "volume": 0.5}]}
    novo, _ = ac.novo_edl(EDL, pedido)
    assert novo["ranges"][0]["enquadre"] == {"x": 540, "y": 1440, "largura": 1300}
    assert "enquadre" not in novo["ranges"][1]
    assert ac.so_enquadre(EDL, novo)
    pedido["ranges"][1]["volume"] = 0.7
    assert not ac.so_enquadre(EDL, ac.novo_edl(EDL, pedido)[0])  # o volume mudou: refaz o corte
    import camadas as cam
    pedido["ranges"][0]["enquadre"] = {"x": 540, "y": 960, "largura": 99999}
    with pytest.raises(cam.CamadasInvalidas):
        ac.novo_edl(EDL, pedido)


def test_so_o_enquadre_grava_sem_refazer_o_corte(projeto):
    edit = projeto
    antes = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    corte = (edit / "cut.mp4").read_bytes()
    enq = {"x": 540, "y": 1440, "largura": 1300, "recorte": {"x": 0.2, "y": 0.1, "w": 0.6, "h": 0.5, "formato": "meia"}}
    # as pontas como o editor manda: arredondadas no milésimo
    pedido = {"ranges": [{"source": "A", "start": round(r["start"], 3), "end": round(r["end"], 3), "take": i}
                         for i, r in enumerate(antes["ranges"])]}
    pedido["ranges"][0]["enquadre"] = enq
    res = ac.aplicar(edit, pedido)
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["ranges"][0]["enquadre"] == enq and "enquadre" not in edl["ranges"][1]
    assert edl["jcut_timeline"] == antes["jcut_timeline"] and edl["total_duration_s"] == antes["total_duration_s"]
    assert (edit / "cut.mp4").read_bytes() == corte and res == {"rede": [], "fora": [], "voz": None}
    del pedido["ranges"][0]["enquadre"]  # Enquadre original: sai do edl.json, ainda sem refazer o corte
    ac.aplicar(edit, pedido)
    assert "enquadre" not in json.loads((edit / "edl.json").read_text(encoding="utf-8"))["ranges"][0]
    assert (edit / "cut.mp4").read_bytes() == corte


def test_enquadre_invalido_no_aplicar_vira_erro_de_corte(projeto):
    edit = projeto
    antes = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    pedido = {"ranges": [{"source": "A", "start": round(r["start"], 3), "end": round(r["end"], 3), "take": i,
                          "enquadre": {"x": 540, "y": 960}} for i, r in enumerate(antes["ranges"])]}
    with pytest.raises(ac.ErroCorte, match="enquadre"):
        ac.aplicar(edit, pedido)
    assert json.loads((edit / "edl.json").read_text(encoding="utf-8")) == antes
