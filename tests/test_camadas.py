"""O formato das camadas do projeto (helpers/camadas.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import camadas as cam  # noqa: E402


def _audio(**it):
    return {"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": "midia/v.mp3", "duracao": 2, **it}]}


def test_completa_os_padroes_e_arredonda():
    c = cam.normalize({"faixas": [_audio(inicio=1.00049)]})
    assert c == {"versao": 1, "video": {"mudo": False}, "faixas": [
        {"id": "a1", "tipo": "audio", "travado": False, "mudo": False, "itens": [
            {"id": "a1-1", "arquivo": "midia/v.mp3", "inicio": 1.0, "duracao": 2.0,
             "corte": 0.0, "volume": 1.0, "melhorar": False}]}]}


@pytest.mark.parametrize("ruim", [
    {"faixas": [_audio(volume=3)]},
    {"faixas": [_audio(inicio=-1)]},
    {"faixas": [_audio(duracao=0)]},
    {"faixas": [_audio(inicio=float("nan"))]},
    {"faixas": [{"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": "midia/v.png", "duracao": 1}]}]},
    {"faixas": [{"id": "i1", "tipo": "imagem", "itens": [{"id": "i1-1", "arquivo": "midia/v.mp3", "duracao": 1}]}]},
    {"faixas": [{"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": "midia/.oculto.mp3", "duracao": 1}]}]},
    {"faixas": [{"id": "a b", "tipo": "audio", "itens": []}]},
    {"faixas": [{"id": "a1", "tipo": "video", "itens": []}]},
    {"faixas": [_audio(), _audio()]},
    "não é objeto",
])
def test_recusa_o_que_nao_presta(ruim):
    with pytest.raises(cam.CamadasInvalidas):
        cam.normalize(ruim)


def test_o_que_toca_e_o_que_aparece():
    c = cam.normalize({"faixas": [
        {"id": "a1", "tipo": "audio", "mudo": True, "itens": [{"id": "x1", "arquivo": "midia/a.mp3", "duracao": 1}]},
        {"id": "a2", "tipo": "audio", "itens": [{"id": "x2", "arquivo": "midia/b.mp3", "duracao": 1},
                                                 {"id": "x3", "arquivo": "midia/c.mp3", "duracao": 1, "volume": 0}]},
        {"id": "i1", "tipo": "imagem", "oculto": True, "itens": [{"id": "x4", "arquivo": "midia/a.png", "duracao": 1}]},
        {"id": "i2", "tipo": "imagem", "itens": [{"id": "x5", "arquivo": "midia/b.png", "duracao": 1}]}]})
    assert [i["id"] for i in cam.tocam(c)] == ["x2"]
    assert [i["id"] for i in cam.aparecem(c)] == ["x5"]


def test_sem_arquivo_sao_camadas_vazias(tmp_path):
    assert cam.load(tmp_path / "camadas.json") == cam.vazio()
    cam.save(tmp_path / "camadas.json", {"faixas": [_audio()]})
    assert cam.load(tmp_path / "camadas.json")["faixas"][0]["itens"][0]["arquivo"] == "midia/v.mp3"
