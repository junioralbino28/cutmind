"""O Baixar pelo servidor: diz o que falta, entrega na hora quando nada falta, e gera o vídeo final num
processo à parte sem o agente. O processo é trocado por um falso: o de verdade está em test_gerar.py."""
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

MUDOU = "o corte mudou depois da legenda e dos efeitos do vídeo final: aperte Pronto para o Claude refazer essa parte"
FALSO = """
import sys, time
sys.path.insert(0, sys.argv[1])
import trabalhos as tb
edit, andamento, modo, espera = sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
w = tb.escritor(andamento, 'gerar')
w('desenhando', 'Desenhando o vídeo', 0.5, quadro=10, quadros=20)
time.sleep(espera)
if modo == 'falha':
    msg = '""" + MUDOU + """'
    w('falhou', msg, 1.0, erro=msg)
    sys.exit(1)
open(edit + '/final.mp4', 'wb').write(b'f')
w('pronto', 'Vídeo pronto', 1.0, entrega='final.mp4')
"""


@pytest.fixture
def srv(tmp_path, monkeypatch):
    edit = tmp_path / "videos" / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    (edit / "cut.mp4").write_bytes(b"corte")
    falso = tmp_path / "gerar_falso.py"
    falso.write_text(FALSO, encoding="utf-8")
    estado = SimpleNamespace(falta=["remotion", "final"], entrega="final.mp4", modo="ok", espera=0.0)
    monkeypatch.setattr(ps, "comando_gerar", lambda e, a: [sys.executable, "-I", str(falso), str(HELPERS), str(e), str(a),
                                                          estado.modo, str(estado.espera)])
    monkeypatch.setattr(ps.gr, "o_que_falta", lambda e: list(estado.falta))
    monkeypatch.setattr(ps.gr, "entrega", lambda e: estado.entrega)

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.allow_hosts = ()
    H.upload_dir = edit.parent.resolve()
    H.max_upload = 50_000
    H.bind_host = "127.0.0.1"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit, estado=estado)
    server.shutdown()
    server.server_close()
    fim = time.time() + 10
    while ps.tb.vivo(edit) and time.time() < fim:
        time.sleep(0.05)


def pedir(port, metodo, caminho, corpo=None, cabecalhos=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(metodo, caminho, body=None if corpo is None else json.dumps(corpo), headers=cabecalhos or {})
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, json.loads(dados or b"{}")


def esperar(port, prazo=20, cabecalhos=None):
    fim = time.time() + prazo
    while time.time() < fim:
        a = pedir(port, "GET", "/api/trabalho", cabecalhos=cabecalhos)[1]
        if a.get("etapa") in ("pronto", "falhou"):
            return a
        time.sleep(0.1)
    raise AssertionError("o vídeo final não terminou")


def test_pendente_diz_o_que_falta_e_o_que_entrega(srv):
    r, d = pedir(srv.port, "GET", "/api/pendente")
    assert r.status == 200 and d == {"falta": ["remotion", "final"], "entrega": "final.mp4"}


def test_nada_faltando_entrega_na_hora(srv):
    srv.estado.falta, srv.estado.entrega = [], "cut.mp4"
    r, d = pedir(srv.port, "POST", "/api/gerar", {})
    assert r.status == 200 and d == {"ok": True, "pronto": True, "entrega": "cut.mp4"}
    assert ps.tb.vivo(srv.edit) is None


def test_gerar_roda_a_parte_e_termina_com_a_entrega(srv):
    r, d = pedir(srv.port, "POST", "/api/gerar", {})
    assert r.status == 200 and d == {"ok": True, "trabalho": "gerar", "falta": ["remotion", "final"]}
    a = esperar(srv.port)
    assert (a["tipo"], a["etapa"], a["entrega"]) == ("gerar", "pronto", "final.mp4")
    assert (srv.edit / "final.mp4").read_bytes() == b"f"
    assert not (srv.edit / "preview_edits.json").exists()  # o agente não ficou sabendo


def test_com_o_video_sendo_gerado_nada_muda_no_projeto(srv):
    srv.estado.espera = 1.5
    assert pedir(srv.port, "POST", "/api/gerar", {})[0].status == 200
    r, d = pedir(srv.port, "POST", "/api/gerar", {})
    assert r.status == 409 and "gerado" in d["error"]
    camadas = {"versao": 1, "video": {"mudo": True}, "faixas": []}
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "camadas": camadas})
    assert r.status == 409 and "gerado" in d["error"]
    assert not (srv.edit / "camadas.json").exists() and not (srv.edit / "preview_edits.json").exists()
    esperar(srv.port)


def test_sem_corte_nao_gera(srv):
    (srv.edit / "cut.mp4").unlink()
    r, d = pedir(srv.port, "POST", "/api/gerar", {})
    assert r.status == 409 and "corte" in d["error"]


def test_o_erro_chega_no_idioma_do_editor(srv):
    srv.estado.modo = "falha"
    pedir(srv.port, "POST", "/api/gerar", {})
    a = esperar(srv.port, cabecalhos={"X-CutMind-Idioma": "en"})
    assert a["etapa"] == "falhou" and a["erro"].startswith("the cut changed")
    assert pedir(srv.port, "GET", "/api/trabalho")[1]["erro"] == MUDOU
    estado = pedir(srv.port, "GET", "/api/state", cabecalhos={"X-CutMind-Idioma": "en"})[1]
    assert estado["trabalho"]["erro"].startswith("the cut changed")


def test_salvar_com_dados_da_fase2_grava_o_edit_data_sem_o_agente(srv):
    pub = srv.edit / "remotion" / "public"
    pub.mkdir(parents=True)
    (pub / "edit-data.json").write_text(json.dumps({"hook": {"enabled": True, "endSec": 4.0, "lines": ["oi"]},
                                                     "inserts": [{"src": "a.png", "start": 1.0, "end": 2.0}]}),
                                        encoding="utf-8")
    st = json.loads((srv.edit / "state.json").read_text(encoding="utf-8"))
    (srv.edit / "state.json").write_text(json.dumps({**st, "phase": 2, "editData": "remotion/public/edit-data.json"}),
                                         encoding="utf-8")
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "editData": {
        "inserts": [{"ref": 0, "start": 1.5, "end": 2.5}], "hook": {"endSec": 3.0}}})
    assert r.status == 200 and d == {"ok": True, "avisos": []}
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    assert ed["hook"]["endSec"] == 3.0 and ed["inserts"][0]["start"] == 1.5
    assert not (srv.edit / "preview_edits.json").exists()  # nada para o agente
    feitos = json.loads((srv.edit / "ajustes_feitos.json").read_text(encoding="utf-8"))["feitos"]
    assert feitos[-1]["oque"].startswith("vídeo final:")
    # com uma marcação junto, só a marcação vai para o agente
    nota = {"start": 1.0, "end": 2.0, "text": "troca a imagem", "phase": 2}
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "notes": [nota],
                                                 "editData": {"hook": {"endSec": 2.0}}})
    salvo = json.loads((srv.edit / "preview_edits.json").read_text(encoding="utf-8"))
    assert r.status == 200 and "editData" not in salvo and salvo["notes"][0]["text"] == "troca a imagem"


def test_salvar_fase2_sem_o_projeto_da_fase2_recusa(srv):
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "editData": {"hook": {"endSec": 3.0}}})
    assert r.status == 400 and "editData" in d["error"]
