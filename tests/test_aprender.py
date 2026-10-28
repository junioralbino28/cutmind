"""O agente aprende o jeito de editar da pessoa (aprender.py): guardar a entrega, medir o que ela mudou à mão e
gravar a regra na skill dela, atualizando em vez de duplicar (como o Hermes)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import aprender  # noqa: E402

EDL = {"ranges": [{"source": "A", "start": 1.0, "end": 5.0}, {"source": "A", "start": 7.0, "end": 9.5, "volume": 0.8}]}
CAMADAS = {"versao": 1, "video": {"mudo": False}, "faixas": [
    {"id": "t1", "tipo": "texto", "itens": [{"id": "t1-1", "texto": "OFERTA", "inicio": 1, "duracao": 2, "x": 540, "y": 960,
                                            "estilo": {"fonte": "Anton", "cor": "#ffffff"}}]},
    {"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": "midia/t.mp3", "inicio": 0, "duracao": 9, "corte": 0,
                                            "volume": 0.15, "trilha": "lofi-1"}]}]}
EFEITOS = {"versao": 1, "itens": [{"id": "f1", "tipo": "filtro", "pacote": "ambar", "inicio": 0, "duracao": 4, "intensidade": 1}]}


def _grava(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def edit(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_HOME", str(tmp_path / "casa"))
    e = tmp_path / "Video da Ana" / "edit"
    _grava(e / "state.json", {"phase": 2, "video": "cut.mp4", "style": {"captions": "karaoke", "edit": "limpa"}})
    _grava(e / "edl.json", EDL)
    _grava(e / "camadas.json", CAMADAS)
    _grava(e / "efeitos.json", EFEITOS)
    return e


def _mexe(e: Path) -> None:
    """O que a pessoa faz à mão depois da entrega: apara, enquadra, troca filtro, letra e lugar do texto, trilha."""
    edl = json.loads(json.dumps(EDL))
    edl["ranges"][0]["start"] = 1.25
    edl["ranges"][0]["end"] = 4.9
    edl["ranges"][1]["enquadre"] = {"x": 540, "y": 1440, "largura": 1296, "recorte": {"x": 0, "y": 0.25, "w": 1, "h": 0.5, "formato": "meia"}}
    _grava(e / "edl.json", edl)
    c = json.loads(json.dumps(CAMADAS))
    c["faixas"][0]["itens"][0]["estilo"]["fonte"] = "Bebas Neue"
    c["faixas"][0]["itens"][0]["y"] = 1500
    c["faixas"][1]["itens"][0]["volume"] = 0.08
    _grava(e / "camadas.json", c)
    _grava(e / "efeitos.json", {"versao": 1, "itens": [
        {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 0, "duracao": 9.5, "intensidade": 0.6},
        {"id": "x1", "tipo": "transicao", "pacote": "zoom", "corte": 4.0, "duracao": 0.4}]})
    _grava(e / "velocidade.json", {"versao": 1, "trechos": [{"inicio": 2, "fim": 3, "fator": 1.5}]})
    st = json.loads((e / "state.json").read_text(encoding="utf-8"))
    st["style"]["captions"] = "classica"
    _grava(e / "state.json", st)


def test_sem_entrega_guardada_nao_ha_diferenca(edit):
    assert aprender.diferenca(edit) == []
    assert aprender.guardar(edit) == 1
    assert aprender.diferenca(edit) == []  # logo depois de guardar, nada mudou


def test_a_diferenca_vem_em_numeros_por_assunto(edit):
    aprender.guardar(edit)
    _mexe(edit)
    mud = {(m["assunto"], m["chave"]): m for m in aprender.diferenca(edit)}
    assert mud[("corte", "ponta_inicio")]["onde"] == "tomada 1, +0.25 s"
    assert mud[("corte", "ponta_fim")]["onde"] == "tomada 1, -0.1 s"
    assert mud[("enquadre", "enquadre_tomada")]["para"] == {"escala": 1.2, "x": 540, "y": 1440, "formato": "meia"}
    assert (mud[("filtro", "filtro_pacote")]["de"], mud[("filtro", "filtro_pacote")]["para"]) == ("ambar", "filme-pb")
    assert mud[("filtro", "filtro_intensidade")]["para"] == 0.6
    assert mud[("transicao", "transicao_novo")]["para"]["pacote"] == "zoom"
    assert (mud[("texto", "texto_fonte")]["de"], mud[("texto", "texto_fonte")]["para"]) == ("Anton", "Bebas Neue")
    assert mud[("texto", "texto_lugar")]["para"] == [540, 1500]
    assert mud[("trilha", "trilha_volume")]["para"] == 0.08
    assert mud[("velocidade", "trechos_velocidade")]["para"] == [(2, 3, 1.5)]
    assert mud[("estilo", "estilo_captions")]["para"] == "classica"
    texto = aprender.texto_diferenca(aprender.diferenca(edit))
    assert texto.startswith("O QUE A PESSOA MUDOU À MÃO") and "Bebas Neue" in texto


def test_regra_e_atualizada_e_nunca_duplicada(edit):
    r = aprender.regra("texto", "texto.fonte_destaque", "Texto de destaque em Bebas Neue", "Anton → Bebas Neue", "Video da Ana")
    assert r["videos"] == ["Video da Ana"]
    aprender.regra("texto", "texto.fonte_destaque", None, "Anton → Bebas Neue de novo", "Video da Ana")  # mesmo vídeo
    r = aprender.carregar_regras()["regras"]["texto.fonte_destaque"]
    assert r["videos"] == ["Video da Ana"] and len(r["provas"]) == 2
    skill = (aprender.pasta_jeito() / "SKILL.md").read_text(encoding="utf-8")
    assert "**Visto 1 vez** (1 vídeo) `texto.fonte_destaque`" in skill
    aprender.regra("texto", "texto.fonte_destaque", "Texto de destaque em Bebas Neue, 1,3×", "Montserrat → Bebas Neue", "Video do Beto")
    d = aprender.carregar_regras()["regras"]
    assert list(d) == ["texto.fonte_destaque"]  # uma regra só
    assert d["texto.fonte_destaque"]["videos"] == ["Video da Ana", "Video do Beto"]
    assert d["texto.fonte_destaque"]["texto"].endswith("1,3×")  # o agente ajustou o que entendeu
    skill = (aprender.pasta_jeito() / "SKILL.md").read_text(encoding="utf-8")
    assert "**Regra** (2 vídeos) `texto.fonte_destaque`: Texto de destaque em Bebas Neue, 1,3×" in skill
    assert skill.startswith("---\nname: cutmind-meu-jeito")
    for i in range(7):
        aprender.regra("texto", "texto.fonte_destaque", None, f"prova {i}", "Video do Beto")
    assert len(aprender.carregar_regras()["regras"]["texto.fonte_destaque"]["provas"]) == aprender.MAX_PROVAS
    assert aprender.esquecer("texto.fonte_destaque") and not aprender.esquecer("texto.fonte_destaque")
    assert "texto.fonte_destaque" not in (aprender.pasta_jeito() / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("args,motivo", [
    (("cor", "x.y", "t", "p", "v"), "assunto"),
    (("texto", "Fonte Grande", "t", "p", "v"), "chave"),
    (("texto", "texto.a", "t", "  ", "v"), "prova"),
    (("texto", "texto.a", None, "p", "v"), "texto"),
])
def test_regra_sem_prova_ou_mal_escrita_e_recusada(edit, args, motivo):
    with pytest.raises(ValueError, match=motivo):
        aprender.regra(*args)


def test_guarda_so_as_ultimas_entregas(edit):
    for _ in range(aprender.MAX_ENTREGAS + 3):
        n = aprender.guardar(edit)
    pastas = sorted(int(p.name) for p in (edit / ".cutmind" / "entregas").iterdir())
    assert len(pastas) == aprender.MAX_ENTREGAS and pastas[-1] == n


def _agente(e: Path, acao: str, casa: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / "agente.py"), acao, str(e)], capture_output=True, text=True,
                          encoding="utf-8", env={**__import__("os").environ, "CUTMIND_HOME": str(casa)})


def test_o_agente_guarda_ao_terminar_e_ve_o_que_a_pessoa_mudou_ao_comecar(edit, tmp_path):
    casa = tmp_path / "casa"
    r = _agente(edit, "livre", casa)
    assert "entrega 1 guardada" in r.stdout
    _mexe(edit)
    r = _agente(edit, "trabalhando", casa)
    assert "O QUE A PESSOA MUDOU À MÃO" in r.stdout and "filme-pb" in r.stdout
    r = _agente(edit, "trabalhando", casa)  # renovar a marca no meio do trabalho: o que o próprio agente mudou não conta
    assert "O QUE A PESSOA MUDOU" not in r.stdout
    r = _agente(edit, "livre", casa)
    assert "entrega 2 guardada" in r.stdout
    assert aprender.diferenca(edit) == []
