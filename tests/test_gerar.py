"""O Baixar do editor sem o agente (gerar.py): o que falta refazer, o que ele entrega, e a sequência."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import gerar  # noqa: E402

T0 = 1_800_000_000.0  # um instante fixo: cada arquivo ganha a hora que o caso pede
VOZ_VELHA = gerar._voz_velha  # a de verdade (a fixture troca por uma que diz "não")


def _grava(p: Path, dados, hora: float) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(dados if isinstance(dados, bytes) else json.dumps(dados).encode("utf-8"))
    os.utime(p, (hora, hora))
    return p


IMAGEM = {"versao": 1, "faixas": [{"id": "i1", "tipo": "imagem", "itens": [
    {"id": "i1-1", "arquivo": "midia/a.png", "inicio": 1.0, "duracao": 2.0}]}]}
AUDIO = {"versao": 1, "faixas": [{"id": "a1", "tipo": "audio", "itens": [
    {"id": "a1-1", "arquivo": "midia/a.m4a", "inicio": 0.0, "corte": 0.0, "duracao": 2.0, "volume": 1.0}]}]}
FILTRO = {"versao": 1, "itens": [{"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 1.0, "duracao": 2.0}]}
TRECHOS = {"versao": 1, "duracao": 10.0, "trechos": [{"inicio": 1.0, "fim": 4.0, "fator": 1.5}]}


@pytest.fixture
def edit(tmp_path, monkeypatch):
    e = tmp_path / "edit"
    _grava(e / "state.json", {"phase": 1, "video": "cut.mp4"}, T0)
    _grava(e / "edl.json", {"ranges": [{"source": "A", "start": 0.0, "end": 10.0}]}, T0)
    _grava(e / "cut.mp4", b"x", T0)
    monkeypatch.setattr(gerar, "_voz_velha", lambda edit: False)
    return e


def _fase2(e: Path, hora: float = T0) -> None:
    _grava(e / "state.json", {"phase": 2, "video": "cut.mp4", "finalVideo": "final.mp4",
                              "editData": "remotion/public/edit-data.json", "style": {"edit": "split"}}, hora)
    _grava(e / "remotion" / "public" / "edit-data.json", {"fps": 30}, hora)
    _grava(e / "remotion" / "public" / "captions.json", [], hora)


# ---- o que falta ----
def test_sem_nada_por_cima_o_corte_e_a_entrega(edit):
    assert gerar.o_que_falta(edit) == []
    assert gerar.entrega(edit) == "cut.mp4"


def test_filtro_sem_final_pede_remotion_e_final(edit):
    _grava(edit / "efeitos.json", FILTRO, T0 + 1)
    assert gerar.o_que_falta(edit) == ["remotion", "final"]


def test_final_mais_novo_que_tudo_nao_pede_nada(edit):
    _grava(edit / "efeitos.json", FILTRO, T0 + 1)
    _grava(edit / "final.mp4", b"f", T0 + 2)
    assert gerar.o_que_falta(edit) == []
    assert gerar.entrega(edit) == "final.mp4"


def test_camadas_mais_novas_que_o_final(edit):
    _grava(edit / "final.mp4", b"f", T0 + 2)
    _grava(edit / "camadas.json", IMAGEM, T0 + 3)
    assert gerar.o_que_falta(edit) == ["remotion", "final"]


def test_so_som_nas_camadas_nao_passa_pelo_remotion(edit):
    _grava(edit / "camadas.json", AUDIO, T0 + 1)
    assert gerar.o_que_falta(edit) == ["final"]
    _grava(edit / "final.mp4", b"f", T0 + 2)
    assert gerar.o_que_falta(edit) == [] and gerar.entrega(edit) == "final.mp4"


def test_som_do_video_desligado_tambem_e_um_final(edit):
    _grava(edit / "camadas.json", {"versao": 1, "video": {"mudo": True}, "faixas": []}, T0 + 1)
    assert gerar.o_que_falta(edit) == ["final"]


def test_corte_refeito_depois_do_final(edit):
    _grava(edit / "camadas.json", IMAGEM, T0)
    _grava(edit / "final.mp4", b"f", T0 + 2)
    _grava(edit / "cut.mp4", b"y", T0 + 3)
    assert gerar.o_que_falta(edit) == ["remotion", "final"]


def test_velocidade_com_entrega_velha(edit):
    _fase2(edit)
    _grava(edit / "final.mp4", b"f", T0 + 2)
    _grava(edit / "final-entrega.mp4", b"e", T0 + 3)
    _grava(edit / "velocidade.json", TRECHOS, T0 + 4)
    assert gerar.o_que_falta(edit) == ["entrega"]
    _grava(edit / "final-entrega.mp4", b"e", T0 + 5)
    assert gerar.o_que_falta(edit) == []
    assert gerar.entrega(edit) == "final-entrega.mp4"


def test_final_refeito_pede_a_entrega_de_novo(edit):
    _fase2(edit)
    _grava(edit / "velocidade.json", TRECHOS, T0 + 1)
    _grava(edit / "final-entrega.mp4", b"e", T0 + 2)
    _grava(edit / "camadas.json", IMAGEM, T0 + 3)
    assert gerar.o_que_falta(edit) == ["remotion", "final", "entrega"]


def test_com_estilo_o_edit_data_novo_pede_o_final(edit):
    _fase2(edit)
    _grava(edit / "final.mp4", b"f", T0 + 2)
    assert gerar.o_que_falta(edit) == []
    _grava(edit / "remotion" / "public" / "edit-data.json", {"fps": 30}, T0 + 3)
    assert gerar.o_que_falta(edit) == ["remotion", "final"]


def test_voz_para_reaplicar_vem_primeiro(edit, monkeypatch):
    monkeypatch.setattr(gerar, "_voz_velha", lambda e: True)
    assert gerar.o_que_falta(edit) == ["voz"]
    _grava(edit / "camadas.json", IMAGEM, T0)
    _grava(edit / "final.mp4", b"f", T0 + 2)
    assert gerar.o_que_falta(edit) == ["voz", "remotion", "final"]


def test_voz_velha_so_mede_quando_a_voz_ja_foi_aplicada(edit, monkeypatch):
    """Sem nunca ter aplicado o Melhorar voz, nada de medir o som do corte (custaria a cada pergunta)."""
    def nao_mede(e):
        raise AssertionError("mediu o som sem precisar")
    monkeypatch.setattr(gerar.mv, "situacao", nao_mede)
    assert VOZ_VELHA(edit) is False
    _grava(edit / ".melhorar" / "estado.json", {"versao": gerar.mv.VERSAO, "fonte": {"hash": "h"},
                                                 "aplicado": {"hash": "h", "voz": 50, "fundo": 20}}, T0)
    monkeypatch.setattr(gerar.mv, "situacao", lambda e: {"reaplicar": True})
    assert VOZ_VELHA(edit) is True


def test_montagem_com_lugar_salvo(edit):
    _grava(edit / "edl.json", {"montagem": {"lugares": [{"vaga": 1}]}, "ranges": []}, T0)
    _grava(edit / "final.mp4", b"f", T0 + 2)
    assert gerar.o_que_falta(edit) == []
    _grava(edit / ".cutmind" / "pendente.json", {"montagem": {"lugares": [{"vaga": 1, "midia": "midia/b.jpg"}]}}, T0 + 3)
    assert gerar.o_que_falta(edit) == ["montagem"]
    assert gerar.entrega(edit) == "final.mp4"


# ---- a Fase 2 é deste corte? ----
def _segments(e: Path, durs: list[float]) -> None:
    t, segs = 0.0, []
    for d in durs:
        segs.append({"start": round(t, 4), "dur": d})
        t += d
    _grava(e / "remotion" / "public" / "segments.json", {"segments": segs, "videoLag": 0}, T0)


def test_fase2_do_corte(edit):
    _grava(edit / "edl.json", {"ranges": [{"source": "A", "start": 0.0, "end": 4.0},
                                          {"source": "A", "start": 6.0, "end": 9.0}]}, T0)
    _segments(edit, [4.0, 3.0])
    assert gerar.fase2_do_corte(edit)
    _segments(edit, [4.0 + 1 / 30, 3.0])  # um quadro de diferença: o render arredonda
    assert gerar.fase2_do_corte(edit)
    _segments(edit, [3.5, 3.0])  # a tomada 1 foi aparada depois da Fase 2
    assert not gerar.fase2_do_corte(edit)
    _segments(edit, [4.0])  # uma tomada a menos
    assert not gerar.fase2_do_corte(edit)


def test_fase2_do_corte_com_jcut(edit):
    """Com J-cut, a imagem de cada tomada é a do jcut_timeline (o lead entra antes, só som)."""
    _grava(edit / "edl.json", {"ranges": [{"source": "A", "start": 0.0, "end": 4.0},
                                          {"source": "A", "start": 6.0, "end": 9.0}],
                               "jcut_timeline": [
                                   {"audio_start_in_output": 0.0, "video_start_in_output": 0.0, "video_duration": 3.9},
                                   {"audio_start_in_output": 3.7, "video_start_in_output": 3.9, "video_duration": 2.8}]}, T0)
    _segments(edit, [3.9, 2.8])
    assert gerar.fase2_do_corte(edit)


def test_sem_segments_nao_e_deste_corte(edit):
    assert not gerar.fase2_do_corte(edit)


def test_gerar_recusa_final_de_outro_corte(edit):
    _fase2(edit)
    _grava(edit / "camadas.json", IMAGEM, T0 + 3)
    _segments(edit, [3.0])
    with pytest.raises(gerar.ErroGerar, match="o corte mudou depois da legenda"):
        gerar.gerar(edit)


# ---- de verdade: um corte de 3 s renderizado pelo render.py ----
AJUDA = Path(__file__).resolve().parents[1] / "helpers"


def _ff(*args) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def _sonda(p: Path, campos: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                          f"stream={campos}:format=duration", "-of", "json", str(p)], capture_output=True, text=True)
    d = json.loads(out.stdout)
    return {**d["streams"][0], "duration": float(d["format"]["duration"])}


def _hashes(p: Path) -> list[str]:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:v:0", "-f", "framemd5", "-"],
                         capture_output=True, text=True, check=True).stdout
    return [ln.split(",")[-1].strip() for ln in out.splitlines() if ln and not ln.startswith("#")]


@pytest.fixture
def corte(tmp_path):
    fonte = tmp_path / "A.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=180x320:rate=30:duration=4", "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=48000:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", fonte)
    e = tmp_path / "edit"
    e.mkdir()
    (e / "state.json").write_bytes(json.dumps({"phase": 1, "video": "cut.mp4", "fps": 30}).encode("utf-8"))
    edl = {"version": 1, "sources": {"A": str(fonte)},
           "ranges": [{"source": "A", "start": 0.0, "end": 1.5}, {"source": "A", "start": 2.5, "end": 4.0}]}
    (e / "edl.json").write_bytes(json.dumps(edl).encode("utf-8"))
    subprocess.run([sys.executable, "-X", "utf8", str(AJUDA / "render.py"), str(e / "edl.json"), "-o",
                    str(e / "cut.mp4"), "--no-subtitles"], check=True, capture_output=True)
    return e


com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")


@com_ffmpeg
def test_segmentos_pelos_quadros_de_cada_trecho(corte):
    segs, total = gerar.segmentos_do_corte(corte, 30.0)
    assert len(segs) == 2 and total == int(_sonda(corte / "cut.mp4", "nb_read_frames")["nb_read_frames"])
    assert round(sum(s["dur"] for s in segs) * 30) == total and segs[1]["start"] == segs[0]["dur"]
    (corte / "clips_graded" / "seg_02_A_v.mp4").write_bytes(b"sobra de um render com mais tomadas")
    with pytest.raises(gerar.ErroGerar, match="não batem"):
        gerar.segmentos_do_corte(corte, 30.0)


@com_ffmpeg
def test_so_som_mistura_sem_passar_pelo_remotion(corte, monkeypatch):
    musica = corte / "midia" / "m.m4a"
    musica.parent.mkdir()
    _ff("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2", "-c:a", "aac", musica)
    cam = gerar.cam
    cam.save(corte / "camadas.json", {"versao": 1, "video": {"mudo": False}, "faixas": [
        {"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": "midia/m.m4a", "inicio": 0.5, "corte": 0.0,
                                                "duracao": 1.5, "volume": 1.0}]}]})
    monkeypatch.setattr(gerar.mt, "projeto_remotion", lambda e: (_ for _ in ()).throw(AssertionError("Remotion")))
    etapas = []
    r = gerar.gerar(corte, lambda etapa, *a, **k: etapas.append(etapa))
    assert r == {"falta": ["final"], "entrega": "final.mp4"} and etapas[-1] == "pronto" and "som" in etapas
    final, cut = _sonda(corte / "final.mp4", "nb_read_frames"), _sonda(corte / "cut.mp4", "nb_read_frames")
    assert final["nb_read_frames"] == cut["nb_read_frames"]
    assert _hashes(corte / "final.mp4") == _hashes(corte / "cut.mp4")  # a imagem é a do corte, copiada
    assert json.loads((corte / "state.json").read_text(encoding="utf-8"))["finalVideo"] == "final.mp4"
    assert gerar.o_que_falta(corte) == []


NODE_MODULES = os.environ.get("CUTMIND_TESTE_REMOTION")  # um remotion/node_modules pronto: o teste copia


@com_ffmpeg
@pytest.mark.skipif(not NODE_MODULES or not shutil.which("node"),
                    reason="render do Remotion: CUTMIND_TESTE_REMOTION=<pasta node_modules> para rodar")
def test_fase1_com_imagem_e_filtro_pelo_remotion(corte):
    rem = corte / "remotion"
    shutil.copytree(gerar.mt.TEMPLATE, rem)
    shutil.copytree(NODE_MODULES, rem / "node_modules", dirs_exist_ok=True)
    try:
        img = corte / "midia" / "x.png"
        img.parent.mkdir()
        _ff("-f", "lavfi", "-i", "color=c=red:size=320x320", "-frames:v", "1", img)
        gerar.cam.save(corte / "camadas.json", {"versao": 1, "video": {"mudo": False}, "faixas": [
            {"id": "i1", "tipo": "imagem", "itens": [{"id": "i1-1", "arquivo": "midia/x.png", "inicio": 0.5,
                                                     "duracao": 1.0}]}]})
        (corte / "efeitos.json").write_bytes(json.dumps({"versao": 1, "itens": [
            {"id": "f1", "tipo": "filtro", "pacote": "f-ambar", "inicio": 2.0, "duracao": 0.6}]}).encode("utf-8"))
        r = gerar.gerar(corte)
        assert r["falta"] == ["remotion", "final"] and r["entrega"] == "final.mp4"
        final, cut = _sonda(corte / "final.mp4", "nb_read_frames"), _sonda(corte / "cut.mp4", "nb_read_frames")
        assert abs(int(final["nb_read_frames"]) - int(cut["nb_read_frames"])) <= 1
        hf, hc = _hashes(corte / "final.mp4"), _hashes(corte / "cut.mp4")
        assert hf[30] != hc[30] and hf[70] != hc[70]  # no meio da imagem (1,0 s) e do filtro (2,3 s)
        st = json.loads((corte / "state.json").read_text(encoding="utf-8"))
        assert st["finalVideo"] == "final.mp4" and st["phase"] == 1
        ed = json.loads((rem / "public" / "edit-data.json").read_text(encoding="utf-8"))
        assert ed["_gerar"] == "editor" and not ed["captions"]["enabled"] and len(ed["inserts"]) == 1
        assert gerar.o_que_falta(corte) == []
    finally:
        shutil.rmtree(rem / "node_modules", ignore_errors=True)


# ---- o que o re-corte deixou para o Baixar refazer ----

def test_rastreio_do_rosto_mais_velho_que_o_corte_e_refeito(edit, monkeypatch):
    pub = edit / "remotion" / "public"
    feitos = []
    monkeypatch.setattr(gerar, "_passo", lambda args: feitos.append([str(a) for a in args]) or 0)
    _grava(pub / "track.json", {"neutral": True, "points": [[1, 2]]}, T0 - 60)
    gerar._refazer_rastreio(edit, pub)           # o neutro o Salvar já ajustou
    _grava(pub / "track.json", {"points": [[1, 2]]}, T0 + 60)
    gerar._refazer_rastreio(edit, pub)           # feito depois do corte: serve
    assert feitos == []
    _grava(pub / "track.json", {"points": [[1, 2]]}, T0 - 60)
    gerar._refazer_rastreio(edit, pub)
    assert len(feitos) == 1 and feitos[0][0].endswith("face_track.py") and feitos[0][-1] == str(pub / "track.json")
    monkeypatch.setattr(gerar, "_passo", lambda args: 1)
    with pytest.raises(gerar.ErroGerar):
        gerar._refazer_rastreio(edit, pub)


def test_recorte_da_pessoa_marcado_e_refeito_no_mesmo_arquivo(edit, monkeypatch):
    pub = edit / "remotion" / "public"
    _grava(pub / "fg.mov", b"velho", T0)
    _grava(pub / "edit-data.json", {"fps": 30, "behind": [
        {"src": "x.jpg", "matte": "fg.mov", "start": 1.5, "dur": 1.0, "_refazerMatte": True},
        {"src": "y.jpg", "matte": "outro.mov", "start": 4.0, "dur": 1.0}]}, T0)
    pedidos = []

    def falso(cmd, *a, **k):
        pedidos.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"novo")
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(gerar.subprocess, "run", falso)
    gerar._refazer_recortes(edit, pub)
    assert len(pedidos) == 1
    cmd = pedidos[0]
    assert cmd[cmd.index("--start") + 1] == "1.500000" and cmd[cmd.index("--duration") + 1] == "1.000000"
    assert (pub / "fg.mov").read_bytes() == b"novo" and not list(pub.glob("*.refazendo.*"))
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    assert all("_refazerMatte" not in b for b in ed["behind"])
