"""Modelos de estilo: o visual de um vídeo guardado com nome em ~/.cutmind/modelos.

A pasta do kit (CUTMIND_HOME) já vem isolada por teste (conftest.py).
"""
from __future__ import annotations

import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import modelos as md  # noqa: E402
import preview_server as ps  # noqa: E402

COMPLETO = {
    "nome": "Canal de Receitas",
    "estilo": {"edit": "limpa", "headline": "realce", "captions": "karaoke", "accent": "#FF5200",
               "elements": {"zoomAuto": True, "zoomCuts": False}},
    "legenda": {"estilo": {"fonte": "Anton", "cor": "#ffffff", "tamanho": 1.2, "contorno": 6,
                           "corContorno": "#000000"}, "acompanhar": True},
    "filtro": {"pacote": "filme-pb", "intensidade": 0.8},
    "transicao": {"pacote": "zoom-central", "duracao": 0.6},
    "ajuste": {"brilho": 10, "vinheta": -20, "contraste": 0},
    "trilha": {"pacote": "lofi-01", "volume": 0.3},
}


def test_modelo_completo_normalizado():
    m = md.normalize(COMPLETO)
    assert m["id"] == "canal-de-receitas" and m["nome"] == "Canal de Receitas" and m["versao"] == 1
    assert m["estilo"]["accent"] == "#ff5200" and m["estilo"]["elements"] == {"zoomAuto": True, "zoomCuts": False}
    assert m["legenda"]["estilo"]["fonte"] == "Anton" and m["legenda"]["acompanhar"] is True
    assert m["ajuste"] == {"brilho": 10, "vinheta": -20}  # 0 é neutro: não é gravado
    assert m["filtro"] == {"pacote": "filme-pb", "intensidade": 0.8}
    assert m["trilha"] == {"pacote": "lofi-01", "volume": 0.3}


def test_so_o_estilo_e_obrigatorio():
    m = md.normalize({"nome": "Só estilo", "estilo": {"captions": "serifada"}})
    assert m["legenda"] is None and m["filtro"] is None and m["transicao"] is None
    assert m["ajuste"] is None and m["trilha"] is None and m["estilo"] == {"captions": "serifada", "elements": {}}


@pytest.mark.parametrize("mexe", [
    {"nome": ""}, {"nome": "x" * 61}, {"nome": "a\x00b"}, {"nome": "!!!"},
    {"estilo": "karaoke"}, {"estilo": {"captions": "../x"}}, {"estilo": {"accent": "laranja"}},
    {"estilo": {"elements": {"zoomAuto": "sim"}}},
    {"legenda": {"estilo": {"cor": "branco"}}}, {"legenda": {"estilo": {"tamanho": 9}}},
    {"filtro": {"pacote": "../../segredo"}}, {"filtro": "filme-pb"}, {"filtro": {"pacote": "a", "intensidade": 3}},
    {"transicao": {"pacote": "zoom", "duracao": 9}},
    {"ajuste": {"nitidez": 10}}, {"ajuste": {"brilho": 500}},
    {"trilha": {"pacote": "lofi", "volume": 5}},
])
def test_recusa_o_que_nao_e_do_formato(mexe):
    with pytest.raises(md.ModeloInvalido):
        md.normalize({**COMPLETO, **mexe})


def test_salvar_listar_trocar_e_apagar():
    m = md.salvar(COMPLETO)
    assert (md.pasta() / "canal-de-receitas.json").is_file() and md.obter("canal-de-receitas")["nome"] == "Canal de Receitas"
    criado = m["criado"]
    # mesmo nome: troca o conteúdo e mantém o lugar
    m2 = md.salvar({**COMPLETO, "filtro": None})
    assert m2["criado"] == criado and md.obter("canal-de-receitas")["filtro"] is None
    md.salvar({"nome": "Outra marca", "estilo": {}})
    assert [x["id"] for x in md.listar()] == ["outra-marca", "canal-de-receitas"]
    assert md.apagar("canal-de-receitas") and not md.apagar("canal-de-receitas")
    assert md.obter("../projetos") is None and md.apagar("../x") is False


def test_arquivo_estragado_fica_de_fora():
    md.salvar(COMPLETO)
    (md.pasta() / "quebrado.json").write_text("{nao é json", encoding="utf-8")
    assert [m["id"] for m in md.listar()] == ["canal-de-receitas"]


@pytest.fixture
def srv(tmp_path):
    edit = tmp_path / "videos" / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1}), encoding="utf-8")

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.upload_dir = edit.parent.resolve()
    H.bind_host = "0.0.0.0"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def pedir(port, metodo, caminho, corpo=None, remoto=False):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20,
                                      source_address=("127.0.0.2", 0) if remoto else None)
    dados = json.dumps(corpo).encode() if corpo is not None else None
    conn.request(metodo, caminho, body=dados, headers={"Content-Type": "application/json"} if dados else {})
    r = conn.getresponse()
    out = r.read()
    conn.close()
    return r, (json.loads(out) if out else None)


def test_rotas_dos_modelos(srv):
    r, d = pedir(srv, "GET", "/api/modelos")
    assert r.status == 200 and d == {"modelos": []}
    r, d = pedir(srv, "POST", "/api/modelos", {"modelo": COMPLETO})
    assert r.status == 200 and d["ok"] and d["modelo"]["id"] == "canal-de-receitas"
    r, d = pedir(srv, "GET", "/api/modelos")
    assert [m["nome"] for m in d["modelos"]] == ["Canal de Receitas"]
    r, d = pedir(srv, "POST", "/api/modelos", {"modelo": {**COMPLETO, "filtro": {"pacote": "../x"}}})
    assert r.status == 400 and "filtro.pacote" in d["error"]
    r, d = pedir(srv, "POST", "/api/modelos/apagar", {"id": "canal-de-receitas"})
    assert r.status == 200 and md.listar() == []
    r, d = pedir(srv, "POST", "/api/modelos/apagar", {"id": "canal-de-receitas"})
    assert r.status == 404


def test_celular_sem_codigo_nao_mexe_nos_modelos(srv):
    r, _ = pedir(srv, "POST", "/api/modelos", {"modelo": COMPLETO}, remoto=True)
    assert r.status == 403 and md.listar() == []


def test_salvar_pela_linha_de_comando(tmp_path):
    # o caminho do chat: o agente escreve o JSON e o helper valida, dá o id e grava
    cli = [sys.executable, "-X", "utf8", str(Path(md.__file__)), "salvar"]
    arq = tmp_path / "modelo.json"
    arq.write_bytes(json.dumps(COMPLETO, ensure_ascii=False).encode("utf-8"))
    r = subprocess.run([*cli, str(arq)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and r.stdout.startswith("salvo: canal-de-receitas")
    assert md.obter("canal-de-receitas")["filtro"]["pacote"] == "filme-pb"
    arq.write_bytes(json.dumps({**COMPLETO, "trilha": {"pacote": "../x"}}).encode("utf-8"))
    r = subprocess.run([*cli, str(arq)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1 and "trilha.pacote" in r.stdout
    assert md.obter("canal-de-receitas")["trilha"]["pacote"] == "lofi-01"  # o recusado não gravou


def test_nome_do_pacote_vai_no_modelo():
    m = md.normalize({**COMPLETO, "filtro": {"pacote": "f-ambar", "nome": "Âmbar", "intensidade": 0.7},
                      "transicao": {"pacote": "t-abrir-2", "nome": "Abrir 2", "duracao": 0.6},
                      "trilha": {"pacote": "lofi-01", "nome": "Lo-fi da tarde", "volume": 0.3}})
    assert m["filtro"]["nome"] == "Âmbar" and m["transicao"]["nome"] == "Abrir 2" and m["trilha"]["nome"] == "Lo-fi da tarde"
    for ruim in ("", "a\x07b", "x" * 61, 3):
        with pytest.raises(md.ModeloInvalido):
            md.normalize({**COMPLETO, "filtro": {"pacote": "f-ambar", "nome": ruim}})
