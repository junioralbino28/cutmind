"""O formato das camadas do projeto (helpers/camadas.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import camadas as cam  # noqa: E402


def _audio(**it):
    return {"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": "midia/v.mp3", "duracao": 2, **it}]}


def _texto(**it):
    return {"id": "t1", "tipo": "texto", "itens": [{"id": "t1-1", "texto": "Olá", "duracao": 2, **it}]}


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
    {"faixas": [_audio(trilha="../fora")]},
    {"faixas": [_audio(trilha=7)]},
    {"faixas": [_texto(texto="")]},
    {"faixas": [_texto(texto="   ")]},
    {"faixas": [_texto(texto="x" * 401)]},
    {"faixas": [_texto(texto="a\x07b")]},
    {"faixas": [_texto(texto=5)]},
    {"faixas": [_texto(x=5000)]},
    {"faixas": [_texto(curva=150)]},
    {"faixas": [_texto(estilo={"cor": "red"})]},
    {"faixas": [_texto(estilo={"corContorno": "#12345"})]},
    {"faixas": [_texto(estilo={"fonte": "Anton; color:red"})]},
    {"faixas": [_texto(estilo={"fonte": "x" * 61})]},
    {"faixas": [_texto(estilo={"peso": 950})]},
    {"faixas": [_texto(estilo={"tamanho": 9})]},
    {"faixas": [_texto(estilo={"contorno": -1})]},
    {"faixas": [_texto(estilo="Anton")]},
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


def test_texto_completa_os_padroes_e_guarda_o_estilo():
    c = cam.normalize({"faixas": [_texto(texto="Linha 1\r\nLinha 2", inicio=1.5, x=300, y=-40,
                                         estilo={"fonte": "Bebas Neue", "peso": 700.0, "cor": "#FFE500",
                                                 "tamanho": 1.25, "contorno": 8, "corContorno": "#000000"},
                                         atras=True, curva=-40)]})
    assert c["faixas"] == [{"id": "t1", "tipo": "texto", "travado": False, "oculto": False, "itens": [
        {"id": "t1-1", "texto": "Linha 1\nLinha 2", "inicio": 1.5, "duracao": 2.0, "x": 300.0, "y": -40.0,
         "estilo": {"fonte": "Bebas Neue", "peso": 700, "cor": "#ffe500", "tamanho": 1.25,
                    "contorno": 8.0, "corContorno": "#000000"},
         "atras": True, "acompanhar": False, "curva": -40.0}]}]
    # sem nada escolhido, o texto fica no meio do quadro e com o estilo padrão
    item = cam.normalize({"faixas": [_texto()]})["faixas"][0]["itens"][0]
    assert (item["x"], item["y"], item["estilo"], item["curva"]) == (540.0, 960.0, {}, 0.0)


def test_textos_na_ordem_das_faixas_sem_as_escondidas():
    c = cam.normalize({"faixas": [
        {"id": "t1", "tipo": "texto", "itens": [{"id": "x1", "texto": "embaixo", "duracao": 1}]},
        {"id": "t2", "tipo": "texto", "oculto": True, "itens": [{"id": "x2", "texto": "escondido", "duracao": 1}]},
        {"id": "i1", "tipo": "imagem", "itens": [{"id": "x3", "arquivo": "midia/a.png", "duracao": 1}]},
        {"id": "t3", "tipo": "texto", "itens": [{"id": "x4", "texto": "em cima", "duracao": 1}]}]})
    assert [(i["id"], i["faixa"]) for i in cam.textos(c)] == [("x1", "t1"), ("x4", "t3")]
    assert [i["id"] for i in cam.aparecem(c)] == ["x3"]  # texto não vira imagem
    assert cam.tocam(c) == []


def test_sem_arquivo_sao_camadas_vazias(tmp_path):
    assert cam.load(tmp_path / "camadas.json") == cam.vazio()
    cam.save(tmp_path / "camadas.json", {"faixas": [_audio()]})
    assert cam.load(tmp_path / "camadas.json")["faixas"][0]["itens"][0]["arquivo"] == "midia/v.mp3"


def test_trilha_do_catalogo_fica_marcada_no_item():
    comum = {"id": "a2", "tipo": "audio", "itens": [{"id": "a2-1", "arquivo": "midia/v.mp3", "duracao": 2, "trilha": None}]}
    c = cam.normalize({"faixas": [_audio(trilha="calma-01"), comum]})
    assert c["faixas"][0]["itens"][0]["trilha"] == "calma-01"
    assert "trilha" not in c["faixas"][1]["itens"][0]  # áudio comum não ganha o campo
