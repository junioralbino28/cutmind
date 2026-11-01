"""A transcrição guardada vale só para o vídeo de que veio (edição real de 01/11).

O cache era pelo NOME: um cut.mp4 renderizado de novo voltava com as palavras do corte antigo, e a legenda
feita delas foi atrasando da voz até +824 ms no fim do vídeo."""
import importlib.util
import os
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("transcribe_cache", RAIZ / "helpers" / "transcribe.py")
t = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t)


class Transcreveu(Exception):
    pass


def _cena(tmp_path, transcricao_antes: bool):
    video = tmp_path / "cut.mp4"
    out = tmp_path / "transcripts" / "cut.json"
    out.parent.mkdir()
    agora = time.time()
    video.write_bytes(b"v")
    out.write_text("{}", encoding="utf-8")
    os.utime(out, (agora - 60, agora - 60) if transcricao_antes else (agora + 60, agora + 60))
    os.utime(video, (agora, agora))
    return video, out


def test_transcricao_mais_nova_que_o_video_vem_do_cache(tmp_path, monkeypatch):
    video, out = _cena(tmp_path, transcricao_antes=False)
    monkeypatch.setattr(t, "_probe_duration", lambda p: (_ for _ in ()).throw(Transcreveu()))
    assert t.transcribe_one(video, tmp_path, verbose=False) == out


def test_video_refeito_depois_da_transcricao_transcreve_de_novo(tmp_path, monkeypatch):
    video, _ = _cena(tmp_path, transcricao_antes=True)
    monkeypatch.setattr(t, "_probe_duration", lambda p: (_ for _ in ()).throw(Transcreveu()))
    with pytest.raises(Transcreveu):
        t.transcribe_one(video, tmp_path, verbose=False)
