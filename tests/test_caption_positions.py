"""Posições das frases: do momento da gravação para o relógio do cut.mp4."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from caption_positions import to_cut  # noqa: E402

HELPER = Path(__file__).resolve().parents[1] / "helpers" / "caption_positions.py"

# duas tomadas: a do arquivo A de 10 a 20 s e a do B de 5 a 9 s
EDL = {"sources": {"A": "a.mp4", "B": "b.mp4"},
       "ranges": [{"source": "A", "start": 10.0, "end": 20.0}, {"source": "B", "start": 5.0, "end": 9.0}]}


def test_sem_jcut_soma_as_tomadas():
    pos, perdidas = to_cut({"phrases": [{"source": "B", "at": 6.5, "x": 0.5, "y": 0.3}]}, EDL)
    assert pos["phrases"] == [{"at": 11.5, "x": 0.5, "y": 0.3}]  # 10 s da 1ª + 1,5 s dentro da 2ª
    assert perdidas == [] and pos["all"] is None


def test_com_jcut_a_imagem_entra_depois_do_audio():
    # render.py: a 2ª tomada tem a imagem começando 5 quadros (1/6 s) depois do áudio
    edl = {**EDL, "jcut_timeline": [
        {"video_start_in_output": 0.0, "video_duration": 9.9, "audio_start_in_output": 0.0, "audio_duration": 9.9},
        {"video_start_in_output": 9.9, "video_duration": 3.8333, "audio_start_in_output": 9.7333, "audio_duration": 4.0},
    ]}
    pos, _ = to_cut({"phrases": [{"source": "B", "at": 6.5, "x": 0.4, "y": 0.7}]}, edl)
    # imagem da 2ª começa em 5 + 0,1667 na origem e em 9,9 no corte
    assert pos["phrases"][0]["at"] == round(9.9 + (6.5 - 5.1667), 3)


def test_tomada_acelerada_leva_a_frase_para_o_lugar_certo():
    edl = {**EDL, "ranges": [dict(EDL["ranges"][0], velocidade=2), dict(EDL["ranges"][1], velocidade=0.5)]}
    pos, _ = to_cut({"phrases": [{"source": "A", "at": 14.0, "x": 0.5, "y": 0.3},
                                 {"source": "B", "at": 6.5, "x": 0.5, "y": 0.3}]}, edl)
    # A a 2×: 10 s viram 5; 4 s dentro viram 2. B a 0,5×: 1,5 s dentro viram 3, depois dos 5
    assert [p["at"] for p in pos["phrases"]] == [2.0, 8.0]


def test_momento_cortado_some_e_tomada_duplicada_vale_duas_vezes():
    edl = {**EDL, "ranges": EDL["ranges"] + [{"source": "A", "start": 10.0, "end": 12.0}]}
    pos, perdidas = to_cut({"phrases": [
        {"source": "A", "at": 11.0, "x": 0.5, "y": 0.2, "text": "fica"},
        {"source": "A", "at": 25.0, "x": 0.5, "y": 0.2, "text": "foi cortada"},
    ]}, edl)
    assert [p["at"] for p in pos["phrases"]] == [1.0, 15.0]  # 1ª tomada e a cópia no fim
    assert [p["text"] for p in perdidas] == ["foi cortada"]


def test_todas_e_valores_fora_do_quadro():
    pos, _ = to_cut({"all": {"x": 1.4, "y": -0.2}, "phrases": []}, EDL)
    assert pos["all"] == {"x": 1.0, "y": 0.0}


def test_linha_de_comando_grava_no_edit_data_e_limpa_quando_vazio(tmp_path):
    (tmp_path / "edl.json").write_text(json.dumps(EDL), encoding="utf-8")
    ed = tmp_path / "edit-data.json"
    ed.write_text(json.dumps({"captions": {"style": "karaoke", "positions": {"all": {"x": 0.1, "y": 0.1}}}}), encoding="utf-8")
    estilo = tmp_path / "preview_style.json"
    estilo.write_text(json.dumps({"captionPositions": {"phrases": [
        {"source": "A", "at": 12.0, "x": 0.5, "y": 0.4, "text": "ação é já"}]}}), encoding="utf-8")
    # -X utf8: a saída do helper tem acento e travessão (no Windows, sem isso, sai cp1252)
    args = [sys.executable, "-I", "-X", "utf8", str(HELPER), "--style", str(estilo),
            "--edl", str(tmp_path / "edl.json"), "--edit-data", str(ed)]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    caps = json.loads(ed.read_text(encoding="utf-8"))["captions"]
    assert caps["style"] == "karaoke"  # o resto do edit-data fica
    assert caps["positions"] == {"all": None, "phrases": [{"at": 2.0, "x": 0.5, "y": 0.4}]}
    # o state.json guarda a escolha dentro de "style"; sem posição nenhuma, a chave sai
    st = tmp_path / "state.json"
    st.write_text(json.dumps({"style": {"captions": "karaoke", "captionPositions": {}}}), encoding="utf-8")
    args[args.index(str(estilo))] = str(st)
    assert subprocess.run(args, capture_output=True, text=True, encoding="utf-8").returncode == 0
    assert "positions" not in json.loads(ed.read_text(encoding="utf-8"))["captions"]
