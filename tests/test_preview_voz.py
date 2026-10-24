"""Melhorar voz pelo editor: o servidor prepara num processo à parte, conta o andamento,
entrega as faixas da prévia e confere a escolha no Salvar.

O processo do preparo é o `melhorar_voz.preparar` de verdade, com os modelos trocados por
falsos (como em test_melhorar_voz.py): nada de 1 GB aqui.
"""
from __future__ import annotations

import http.client
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import preview_server as ps  # noqa: E402
import test_melhorar_voz as tv  # noqa: E402

pytestmark = tv.pytestmark  # sem ffmpeg, nada daqui roda

FALSO = """
import sys
import numpy as np
sys.path.insert(0, sys.argv[1])
import melhorar_voz as mv


class Estudio:
    quadro = 960

    def caracteristicas(self, x16):
        n = len(x16) // 320
        return x16[:n * 320].reshape(n, 320)

    def gerar(self, f):
        return np.repeat(f.ravel(), 3)


mv.preparar(sys.argv[2], limpar=lambda x: np.convolve(x, np.ones(9) / 9, mode="same"), estudio=Estudio())
"""


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_VOZ_DIR", str(tmp_path / "voz"))
    edit = tmp_path / "videos" / "edit"
    tv._gravar_corte(edit, tv._fala(3.0, 1))
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    falso = tmp_path / "preparo_falso.py"
    falso.write_text(FALSO, encoding="utf-8")
    monkeypatch.setattr(ps, "comando_preparo", lambda e: [sys.executable, "-I", str(falso), str(HELPERS), str(e)])

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.allow_hosts = ()
    H.upload_dir = edit.parent.resolve()
    H.max_upload = 50_000
    H.bind_host = "0.0.0.0"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit)
    server.shutdown()
    server.server_close()


def pedir(port, metodo, caminho, corpo=None, remoto=False):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30,
                                      source_address=("127.0.0.2", 0) if remoto else None)
    conn.request(metodo, caminho, body=None if corpo is None else json.dumps(corpo))
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, dados


def esperar(port, ate=("pronto", "falhou"), prazo=90):
    vistos = []
    fim = time.time() + prazo
    while time.time() < fim:
        a = json.loads(pedir(port, "GET", "/api/melhorar/andamento")[1])
        if not vistos or vistos[-1] != a.get("etapa"):
            vistos.append(a.get("etapa"))
        if a.get("etapa") in ate:
            return a, vistos
        time.sleep(0.2)
    raise AssertionError(f"o preparo não terminou em {prazo} s: {vistos}")


def test_preparar_pelo_editor_ate_a_previa(srv):
    s = json.loads(pedir(srv.port, "GET", "/api/melhorar")[1])
    assert s["preparo"] == "nenhum" and s["escolha"] == {"voz": 50, "fundo": 20}
    r, dados = pedir(srv.port, "POST", "/api/melhorar/preparar", {})
    assert r.status == 200 and json.loads(dados)["novo"] is True
    r, dados = pedir(srv.port, "POST", "/api/melhorar/preparar", {})  # tocou de novo: não dispara outro
    assert r.status == 200 and json.loads(dados)["novo"] is False
    a, vistos = esperar(srv.port)
    assert a["etapa"] == "pronto", (a, vistos)
    s = json.loads(pedir(srv.port, "GET", "/api/melhorar")[1])
    assert s["preparo"] == "pronto" and s["preparado"] and len(s["previa"]) == 7
    r, dados = pedir(srv.port, "GET", "/media/" + s["previa"]["voz-050"])
    assert r.status == 200 and r.getheader("Content-Type") == "audio/flac" and dados[:4] == b"fLaC"
    assert json.loads(pedir(srv.port, "POST", "/api/melhorar/preparar", {})[1]) == {"ok": True, "pronto": True}


def test_salvar_confere_a_escolha_e_o_editor_ve_o_que_falta_aplicar(srv):
    r, _ = pedir(srv.port, "POST", "/api/save", {"melhorar": {"voz": 60.4, "fundo": 10}})
    assert r.status == 200
    assert json.loads((srv.edit / "preview_edits.json").read_text(encoding="utf-8"))["melhorar"] == {"voz": 60, "fundo": 10}
    assert json.loads(pedir(srv.port, "GET", "/api/melhorar")[1])["pendente"] == {"voz": 60, "fundo": 10}
    r, dados = pedir(srv.port, "POST", "/api/save", {"melhorar": {"voz": 150, "fundo": 0}})
    assert r.status == 400 and "0 a 100" in json.loads(dados)["error"]
    r, _ = pedir(srv.port, "POST", "/api/save", {"melhorar": {"desligar": True}})
    assert r.status == 200
    assert json.loads((srv.edit / "preview_edits.json").read_text(encoding="utf-8"))["melhorar"] == {"desligar": True}


def test_preparo_que_morre_aparece_como_falha(srv, monkeypatch):
    monkeypatch.setattr(ps, "comando_preparo", lambda e: [
        sys.executable, "-c", "import sys; print('erro: o DeepFilterNet falhou: teste', file=sys.stderr); sys.exit(1)"])
    assert pedir(srv.port, "POST", "/api/melhorar/preparar", {})[0].status == 200
    a, _ = esperar(srv.port)
    assert a["etapa"] == "falhou" and a["erro"] == "o DeepFilterNet falhou: teste" and not a["vivo"]
    s = json.loads(pedir(srv.port, "GET", "/api/melhorar")[1])
    assert s["preparo"] == "nenhum" and s["andamento"]["erro"] == "o DeepFilterNet falhou: teste"


def test_preparar_sem_o_corte_avisa(srv):
    (srv.edit / "cut.mp4").unlink()
    r, dados = pedir(srv.port, "POST", "/api/melhorar/preparar", {})
    assert r.status == 409 and "ainda não existe" in json.loads(dados)["error"]


def test_editor_toca_as_faixas_que_o_preparo_grava():
    # o editor mistura pelos nomes e pela ordem das faixas: voz-000…voz-100, fundo, original
    import re

    import melhorar_voz as mv

    js = (HELPERS.parent / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    m = re.search(r"const VOZ_FAIXAS = \[([^\]]*)\];", js)
    assert m, "VOZ_FAIXAS sumiu do celular.js"
    faixas = re.findall(r"'([^']+)'", m.group(1))
    assert faixas == [f"voz-{d:03d}" for d in mv.DEGRAUS] + ["fundo", "original"]
    assert len(mv.DEGRAUS) == 5 and "const n = 5," in js  # a mistura de dois vizinhos conta 5 degraus
    # o painel abre no mesmo padrão que o aplicar usa sem números
    assert "|| { voz: %d, fundo: %d };" % (mv.PADRAO["voz"], mv.PADRAO["fundo"]) in js
    pesos = re.search(r"const VOZ_PESO = \{([^}]*)\};", js)
    assert pesos and re.findall(r"(\w+):", pesos.group(1)) == [e for e in mv.ETAPAS if e != "baixar"]


def test_celular_sem_codigo_nao_ve_nem_prepara(srv):
    assert pedir(srv.port, "GET", "/api/melhorar", remoto=True)[0].status == 403
    assert pedir(srv.port, "POST", "/api/melhorar/preparar", {}, remoto=True)[0].status == 403
