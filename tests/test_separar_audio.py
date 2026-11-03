"""Separar o áudio de uma tomada: o som da gravação inteira, no nível do corte, sem nada vindo do pedido virar caminho."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import remapear as sa_rm  # noqa: E402
import separar_audio as sa  # noqa: E402

com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")


def _gravacao(destino: Path, dur: float = 6.0, som: bool = True, db: int = -6) -> None:
    """O seno do lavfi já nasce em -18 dB: com -6 dB, a gravação fica em ~-28 LUFS, dentro do ganho máximo de +20 dB."""
    entradas = ["-f", "lavfi", "-i", f"color=c=gray:s=320x240:r=30:d={dur}"]
    if som:
        entradas += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={dur},volume={db}dB"]
    subprocess.run(["ffmpeg", "-y", "-v", "error", *entradas, "-c:v", "libx264", "-preset", "ultrafast", *(["-c:a", "aac"] if som else []), str(destino)], check=True)


def _projeto(tmp_path: Path, som: bool = True) -> Path:
    edit = tmp_path / "edit"
    edit.mkdir()
    _gravacao(tmp_path / "take.mp4", som=som)
    (edit / "state.json").write_text(json.dumps({"edl": "edl.json"}), encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps({"sources": {"take": str(tmp_path / "take.mp4")}, "ranges": []}), encoding="utf-8")
    return edit


def _nivel(p: Path) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return float(re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', r.stderr).group(1))


@com_ffmpeg
def test_o_arquivo_tem_a_gravacao_inteira_no_nivel_do_corte(tmp_path):
    edit = _projeto(tmp_path)
    r = sa.separar(edit, "take")
    arq = edit / r["arquivo"]
    assert r["arquivo"].startswith("midia/audio-take-") and arq.is_file()
    assert r["duracao"] == pytest.approx(6.0, abs=0.1) and r["adianta"] == 0
    assert _nivel(tmp_path / "take.mp4") < sa.proxy.ALVO_LUFS - 8, "o teste só prova com uma gravação baixa"
    assert _nivel(arq) == pytest.approx(sa.proxy.ALVO_LUFS, abs=1.5)


@com_ffmpeg
def test_separar_de_novo_reaproveita(tmp_path):
    edit = _projeto(tmp_path)
    a = sa.separar(edit, "take")
    marca = (edit / a["arquivo"]).stat().st_mtime_ns
    assert sa.separar(edit, "take") == a
    assert (edit / a["arquivo"]).stat().st_mtime_ns == marca
    assert not list((edit / "midia").glob(".*")), "não sobra arquivo temporário"


@com_ffmpeg
def test_com_velocidade_o_som_sai_no_ritmo_da_tomada(tmp_path):
    edit = _projeto(tmp_path)
    r = sa.separar(edit, "take", 2)
    assert "2x" in r["arquivo"] and r["duracao"] == pytest.approx(3.0, abs=0.1) and r["adianta"] > 0
    assert sa.separar(edit, "take")["arquivo"] != r["arquivo"], "um arquivo por velocidade"


@com_ffmpeg
def test_gravacao_sem_som_diz_o_motivo(tmp_path):
    with pytest.raises(sa.SepararErro, match="não tem som"):
        sa.separar(_projeto(tmp_path, som=False), "take")


def test_o_pedido_nunca_vira_caminho(tmp_path):
    (tmp_path / "edit").mkdir()
    edit = tmp_path / "edit"
    (tmp_path / "segredo.mp4").write_bytes(b"x")
    (edit / "state.json").write_text("{}", encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps({"sources": {}}), encoding="utf-8")
    for pedido in ("../segredo.mp4", str(tmp_path / "segredo.mp4"), None, 3, {"a": 1}):
        with pytest.raises(sa.SepararErro, match="não achei"):
            sa.separar(edit, pedido)
    assert not (edit / "midia").exists()


@com_ffmpeg
@pytest.mark.parametrize("v", [0, -1, 99, "abc", None])
def test_velocidade_fora_da_faixa(tmp_path, v):
    with pytest.raises(sa.SepararErro, match="velocidade"):
        sa.separar(_projeto(tmp_path), "take", v)


def _cortes(lead_antes: float = 0.167, lead_depois: float = 0.033, **tomada):
    r = {"source": "take", "start": 30.34, "end": 32.64, **tomada}
    def edl(lead, volume):
        return {"sources": {"take": "C:/v/take.mp4"}, "ranges": [{**r, **({"volume": volume} if volume is not None else {})}],
                "jcut_timeline": [{"video_start_in_output": 13.0 + lead, "audio_start_in_output": 13.0, "video_duration": 2.3}]}
    return edl(lead_antes, 0), edl(lead_depois, 0)


def _camada(inicio: float, arquivo: str = "midia/audio-take-abc.m4a", corte: float = 30.34) -> dict:
    return {"faixas": [{"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": arquivo, "inicio": inicio, "corte": corte, "duracao": 2.3}]}]}


def test_refazer_o_corte_leva_a_camada_parada_para_o_som_novo():
    """Medido em 03/11: a sobreposição mudou, e a camada ia com a imagem, 134 ms antes da boca."""
    antes, depois = _cortes()
    depois["jcut_timeline"][0]["audio_start_in_output"] = 13.667
    velho, novo = _camada(13.0), _camada(13.533)
    assert sa_rm.som_separado(velho, novo, antes, depois)["faixas"][0]["itens"][0]["inicio"] == 13.667


@pytest.mark.parametrize("caso", ["movida", "tomada com som", "outro arquivo", "trecho diferente"])
def test_o_resto_fica_onde_o_remapear_pos(caso):
    antes, depois = _cortes()
    depois["jcut_timeline"][0]["audio_start_in_output"] = 13.667
    velho = _camada(13.0)
    if caso == "movida":
        velho = _camada(5.0)
    elif caso == "tomada com som":
        depois["ranges"][0]["volume"] = 1
    elif caso == "outro arquivo":
        velho = _camada(13.0, arquivo="midia/musica.m4a")
    else:
        velho = _camada(13.0, corte=10.0)
    novo = json.loads(json.dumps(velho))
    novo["faixas"][0]["itens"][0]["inicio"] = 7.7
    assert sa_rm.som_separado(velho, novo, antes, depois)["faixas"][0]["itens"][0]["inicio"] == 7.7


def test_o_editor_cala_a_tomada_e_a_camada_comeca_onde_o_som_comecava():
    js = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    corpo = js[js.index("async function separarAudio()"):js.index("// cabeçalho fixo à esquerda da faixa")]
    assert "tool(ctx, 'separar-audio'" in js and "case 'separar-audio': separarAudio(); break;" in js
    assert "r.vol = 0;" in corpo and "remember();" in corpo, "desfazer volta a tomada e tira a camada"
    assert corpo.index("remember();") < corpo.index("r.vol = 0;")
    assert "draftToRendered(d.out) - (d.lead || 0)" in corpo, "o J-cut: o som começa antes da imagem"
    assert "r.start / vel - res.adianta" in corpo and "(r.end - r.start) / vel" in corpo
    assert "if (r.curva)" in corpo
