"""O som do vídeo final com as camadas: a receita da Fase 3 mais os áudios do editor."""
from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
from melhorar_audio import MELHORAR  # noqa: E402
from mixar_final import CamadasNoMix, montar  # noqa: E402


def _projeto(tmp_path, camadas, soundtrack=None):
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    (edit / "midia").mkdir()
    (edit / "state.json").write_text(json.dumps({"fps": 30, "video": "cut.mp4",
                                                 "editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (public / "edit-data.json").write_text(json.dumps({"soundtrack": soundtrack or {"enabled": False, "file": "trilha.mp3", "volume": 0.0445}}),
                                           encoding="utf-8")
    (edit / "camadas.json").write_text(json.dumps(camadas, ensure_ascii=False), encoding="utf-8")
    return edit, public


def _aud(fid, arquivo, inicio, duracao, corte=0.0, volume=1.0, melhorar=False, mudo=False):
    return {"id": fid, "tipo": "audio", "mudo": mudo, "travado": False,
            "itens": [{"id": f"{fid}-1", "arquivo": arquivo, "inicio": inicio, "duracao": duracao,
                       "corte": corte, "volume": volume, "melhorar": melhorar}]}


def _filtro(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


def _entradas(cmd):
    return [cmd[i + 1] for i, x in enumerate(cmd) if x == "-i"]


# ---- o comando ----
def test_sem_camadas_e_a_receita_da_fase_3(tmp_path):
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": []})
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    f = _filtro(cmd)
    assert _entradas(cmd) == [str(edit / "render.mp4"), str(edit / "cut.mp4")]
    assert "[1:a]adelay=33:all=1" in f  # a imagem do Remotion vem 1 quadro atrás do corte
    assert "scale=in_range=full:out_range=limited" in f and "setparams=color_primaries=bt709" in f
    assert "loudnorm=I=-14:TP=-1:LRA=11" in f
    assert cmd[cmd.index("-t") + 1] == "10.000" and "-color_range" in cmd
    assert resumo["voz"] == "corte" and resumo["camadas"] == 0


def test_imagem_do_corte_copia_a_imagem_e_tira_o_atraso(tmp_path):
    """A montagem na batida (montagem.py) não passa pelo Remotion: a imagem é o próprio cut.mp4,
    copiada (sem converter a cor de novo), e a música entra sem o quadro de atraso."""
    edit, _ = _projeto(tmp_path, {"video": {"mudo": True},
                                  "faixas": [_aud("m", "midia/musica.mp3", 0.0, 8.0, corte=12.4)]})
    cmd, resumo = montar(edit, edit / "cut.mp4", edit / "final.mp4", vd=8.0, imagem="corte")
    f = _filtro(cmd)
    assert "scale=in_range" not in f and "[vid]" not in f
    i = cmd.index("-map")
    assert cmd[i:i + 4] == ["-map", "0:v", "-map", "[out]"] and cmd[cmd.index("-c:v") + 1] == "copy"
    assert "atrim=start=12.400:duration=8.000" in f and "adelay=0:all=1" in f
    assert _entradas(cmd) == [str(edit / "cut.mp4"), str(edit / "midia" / "musica.mp3")]
    assert resumo["voz"] == "fora" and resumo["camadas"] == 1
    medir, _ = montar(edit, edit / "cut.mp4", edit / "final.mp4", vd=8.0, imagem="corte", medir=True)
    assert _filtro(medir).startswith("anullsrc")


def test_atraso_da_voz_segue_o_inicio_do_video_do_corte(tmp_path):
    # segments.json mede o atraso (vídeo do cut.mp4 começando em zero = 0); o edit-data manda
    edit, public = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": [_aud("a1", "midia/a.wav", 3.0, 2.0)]})
    (public / "segments.json").write_text(json.dumps({"segments": [], "videoLag": 0}), encoding="utf-8")
    f = _filtro(montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)[0])
    assert "[1:a]adelay=0:all=1" in f and "adelay=3000:all=1" in f
    (public / "edit-data.json").write_text(json.dumps({"videoLag": 2}), encoding="utf-8")
    assert "[1:a]adelay=67:all=1" in _filtro(montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)[0])


def test_camada_de_audio_entra_no_tempo_com_corte_volume_e_melhorar(tmp_path):
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": [
        _aud("a1", "midia/Gravação.m4a", 3.0, 2.0, corte=1.5, volume=1.5, melhorar=True),
        _aud("a2", "midia/fora.m4a", 0.0, 1.0, mudo=True)]})
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    f = _filtro(cmd)
    assert str(edit / "midia" / "Gravação.m4a") in _entradas(cmd)
    assert str(edit / "midia" / "fora.m4a") not in _entradas(cmd)  # silenciada não entra
    assert "atrim=start=1.500:duration=2.000" in f
    assert "volume=1.500" in f and MELHORAR in f
    assert "adelay=3033:all=1" in f  # 3 s no corte + o mesmo quadro de atraso da voz
    assert resumo["camadas"] == 1


def test_trilha_da_biblioteca_entra_e_sai_suave(tmp_path):
    trilha = _aud("a1", "midia/calma-01.m4a", 0.0, 9.0, volume=0.15)
    trilha["itens"][0]["trilha"] = "calma-01"
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": [trilha, _aud("a2", "midia/voz.m4a", 1.0, 2.0)]})
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    f = _filtro(cmd)
    assert resumo["camadas"] == 2 and resumo["biblioteca"] == 1
    assert "afade=t=in:st=0:d=0.400,afade=t=out:st=7.500:d=1.500" in f  # música: entra e sai devagar
    assert "afade=t=in:st=0:d=0.015,afade=t=out:st=1.985:d=0.015" in f  # gravação: os 15 ms de sempre


def test_som_do_video_desligado_tira_a_voz(tmp_path):
    edit, _ = _projeto(tmp_path, {"video": {"mudo": True}, "faixas": []})
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    assert str(edit / "cut.mp4") not in _entradas(cmd)
    assert resumo["voz"] == "fora"


def test_trilha_ligada_entra_com_volume_e_fades(tmp_path):
    edit, public = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": []},
                            soundtrack={"enabled": True, "file": "trilha.mp3", "volume": 0.0445})
    cmd, _ = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    assert str(public / "trilha.mp3") in _entradas(cmd)
    assert "volume=0.0445,afade=t=in:st=0:d=0.4,afade=t=out:st=8.500:d=1.5" in _filtro(cmd)


def test_base_render_nao_separa_a_voz(tmp_path):
    """O áudio do Remotion mistura voz, trilha e efeitos: dá para somar camadas, não para tirar a voz."""
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": [_aud("a1", "midia/x.m4a", 1.0, 1.0)]})
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0, base="render")
    assert str(edit / "cut.mp4") not in _entradas(cmd) and "[0:a]" in _filtro(cmd)
    assert resumo["voz"] == "render"
    edit2, _ = _projeto(tmp_path / "b", {"video": {"mudo": True}, "faixas": []})
    with pytest.raises(CamadasNoMix):
        montar(edit2, edit2 / "render.mp4", edit2 / "final.mp4", vd=10.0, base="render")


def test_efeito_sonoro_entra_no_tempo_do_video_final(tmp_path):
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": []})
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0,
                         sfx=[(Path("sfx/whoosh.mp3"), 2.5, 0.09)])
    assert "volume=0.090,adelay=2500:all=1" in _filtro(cmd)  # tempo da composição: sem o quadro de atraso
    assert resumo["efeitos"] == 1


def test_volume_de_tomada_troca_o_loudnorm_pela_normalizacao_linear(tmp_path):
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": []})
    _, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    assert resumo["linear"] is False  # sem edl.json: a receita de sempre
    (edit / "edl.json").write_text(json.dumps({"ranges": [{"volume": 1}, {}]}), encoding="utf-8")
    cmd, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0)
    assert resumo["linear"] is False and _filtro(cmd).endswith("loudnorm=I=-14:TP=-1:LRA=11[out]")
    (edit / "edl.json").write_text(json.dumps({"ranges": [{"volume": 0.5}, {}]}), encoding="utf-8")
    medir, resumo = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0, medir=True)
    assert resumo["linear"] is True
    f = _filtro(medir)
    assert "print_format=json" in f and "[vid]" not in f and medir[-3:] == ["-f", "null", "-"]
    cmd, _ = montar(edit, edit / "render.mp4", edit / "final.mp4", vd=10.0, norma="volume=+1.00dB,alimiter=limit=0.891")
    assert _filtro(cmd).endswith("normalize=0,volume=+1.00dB,alimiter=limit=0.891[out]") and "loudnorm" not in _filtro(cmd)


def test_montagem_na_batida_tambem_vai_pela_normalizacao_linear(tmp_path):
    """O som da montagem é a música inteira: o loudnorm dinâmico subiria a parte calma e desceria o drop."""
    edit, _ = _projeto(tmp_path, {"video": {"mudo": True}, "faixas": []})
    (edit / "edl.json").write_text(json.dumps({"ranges": [{}], "montagem": {"modelo": "x"}}), encoding="utf-8")
    _, resumo = montar(edit, edit / "cut.mp4", edit / "final.mp4", vd=8.0, imagem="corte")
    assert resumo["linear"] is True and "montagem" in resumo["linear_porque"]


# ---- o vídeo de verdade: quem toca, quando ----
def _goertzel(amostras, taxa, freq):
    k = 2 * math.cos(2 * math.pi * freq / taxa)
    s1 = s2 = 0.0
    for x in amostras:
        s1, s2 = x + k * s1 - s2, s1
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - k * s1 * s2)) / max(1, len(amostras))


def _janela(pcm, taxa, a, b):
    return pcm[int(a * taxa):int(b * taxa)]


def _ler_pcm(video, taxa=8000):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(taxa),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
@pytest.mark.parametrize("video_mudo, camada_muda", [(True, False), (False, True)])
def test_no_video_final_a_camada_toca_no_tempo_e_a_silenciada_nao(tmp_path, video_mudo, camada_muda):
    edit, _ = _projeto(tmp_path, {"video": {"mudo": video_mudo},
                                  "faixas": [_aud("a1", "midia/camada.wav", 1.0, 0.8, corte=0.5, mudo=camada_muda)]})
    ff = ["ffmpeg", "-v", "error", "-y"]
    # a imagem do Remotion: cheia (0–255), sem som; a voz do corte: 440 Hz; a camada: 1000 Hz
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=gray:s=108x192:d=3:r=30", "-pix_fmt", "yuvj420p",
                         "-c:v", "libx264", str(edit / "render.mp4")], check=True)
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=black:s=108x192:d=3:r=30", "-f", "lavfi", "-i",
                         "sine=f=440:d=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(edit / "cut.mp4")], check=True)
    subprocess.run(ff + ["-f", "lavfi", "-i", "sine=f=1000:d=3", str(edit / "midia" / "camada.wav")], check=True)
    # -X utf8: como o SKILL.md manda rodar todo helper no Windows
    r = subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / "mixar_final.py"), str(edit), "--render", str(edit / "render.mp4"),
                        "-o", str(edit / "final.mp4")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr + r.stdout
    taxa = 8000
    pcm = _ler_pcm(edit / "final.mp4", taxa)
    dentro = _janela(pcm, taxa, 1.25, 1.65)  # a camada: 1,0 + 1 quadro até 1,8 + 1 quadro
    fora = _janela(pcm, taxa, 0.3, 0.8)
    if video_mudo:
        assert _goertzel(dentro, taxa, 1000) > 20 * max(_goertzel(dentro, taxa, 440), 1e-3)
        assert max(abs(x) for x in fora) < 50  # sem a voz, antes da camada é silêncio
        inicio = next(i for i, x in enumerate(pcm) if abs(x) > 300) / taxa
        assert abs(inicio - 1.033) < 0.03, inicio  # entra em 1 s + 1 quadro
    else:
        assert _goertzel(dentro, taxa, 440) > 20 * max(_goertzel(dentro, taxa, 1000), 1e-3)
    cores = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=color_space,color_primaries,color_transfer,color_range",
                            "-of", "default=nw=1", str(edit / "final.mp4")],
                           capture_output=True, text=True, check=True).stdout.split()
    assert dict(c.split("=") for c in cores) == {"color_range": "tv", "color_space": "bt709",
                                                 "color_transfer": "bt709", "color_primaries": "bt709"}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
def test_no_video_final_a_tomada_mais_baixa_continua_mais_baixa(tmp_path):
    """O cut.mp4 já sai do render.py com o volume da tomada (aqui: 1ª metade a 50%). O
    loudnorm de uma passada levantava essa metade de volta; a normalização linear não."""
    edit, _ = _projeto(tmp_path, {"video": {"mudo": False}, "faixas": []})
    (edit / "edl.json").write_text(json.dumps({"ranges": [{"volume": 0.5}, {}]}), encoding="utf-8")
    ff = ["ffmpeg", "-v", "error", "-y"]
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=gray:s=108x192:d=6:r=30", "-pix_fmt", "yuvj420p",
                         "-c:v", "libx264", str(edit / "render.mp4")], check=True)
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=black:s=108x192:d=6:r=30", "-f", "lavfi", "-i", "sine=f=440:d=6",
                         "-af", "volume='if(lt(t,3),0.05,0.1)':eval=frame", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                         str(edit / "cut.mp4")], check=True)
    r = subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / "mixar_final.py"), str(edit), "--render", str(edit / "render.mp4"),
                        "-o", str(edit / "final.mp4")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "normalização linear" in r.stdout

    def media(ini, dur):
        p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(ini), "-t", str(dur), "-i", str(edit / "final.mp4"),
                            "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        return float(next(ln.split("mean_volume:")[1].split()[0] for ln in p.stderr.splitlines() if "mean_volume:" in ln))
    dif = media(0.5, 2.0) - media(3.5, 2.0)
    assert abs(dif - (-6.02)) < 0.5, dif


def _vid(fid, arquivo, inicio, duracao, corte=0.0, volume=1.0, oculto=False):
    return {"id": fid, "tipo": "imagem", "oculto": oculto, "travado": False,
            "itens": [{"id": f"{fid}-1", "arquivo": arquivo, "inicio": inicio, "duracao": duracao,
                       "corte": corte, "volume": volume}]}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
def test_no_video_final_toca_o_som_do_video_por_cima_e_o_mudo_fica_de_fora(tmp_path):
    """O vídeo posto por cima com som (660 Hz) entra no tempo, a partir do `corte`; um vídeo sem trilha de som
    na mesma montagem não quebra o ffmpeg (ele não tem [k:a])."""
    edit, _ = _projeto(tmp_path, {"video": {"mudo": True},
                                  "faixas": [_vid("i1", "midia/clipe.mp4", 1.0, 0.8, corte=0.5),
                                             _vid("i2", "midia/mudo.mp4", 0.2, 0.5)]})
    ff = ["ffmpeg", "-v", "error", "-y"]
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=gray:s=108x192:d=3:r=30", "-pix_fmt", "yuvj420p",
                         "-c:v", "libx264", str(edit / "render.mp4")], check=True)
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=black:s=108x192:d=3:r=30", "-f", "lavfi", "-i",
                         "sine=f=440:d=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(edit / "cut.mp4")], check=True)
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=blue:s=160x90:d=3:r=30", "-f", "lavfi", "-i",
                         "sine=f=660:d=3", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                         str(edit / "midia" / "clipe.mp4")], check=True)
    subprocess.run(ff + ["-f", "lavfi", "-i", "color=c=red:s=160x90:d=2:r=30", "-c:v", "libx264",
                         str(edit / "midia" / "mudo.mp4")], check=True)
    r = subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / "mixar_final.py"), str(edit), "--render", str(edit / "render.mp4"),
                        "-o", str(edit / "final.mp4")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr + r.stdout
    taxa = 8000
    pcm = _ler_pcm(edit / "final.mp4", taxa)
    assert _goertzel(_janela(pcm, taxa, 1.25, 1.65), taxa, 660) > 20 * max(_goertzel(_janela(pcm, taxa, 0.3, 0.8), taxa, 660), 1e-3)
    inicio = next(i for i, x in enumerate(pcm) if abs(x) > 300) / taxa
    assert abs(inicio - 1.033) < 0.03, inicio  # entra em 1 s + 1 quadro, como a camada de áudio
