"""O Salvar não acorda mais o agente: marcações e pedidos esperam o Pronto (pedidos.json), a montagem e a
voz esperam o Baixar (pendente.json), e o Pronto junta tudo num pronto.json. Com o agente trabalhando, o
corte e o Baixar esperam (plano do ajuste sem IA, Etapa 4)."""
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

NOTA = {"start": 1.0, "end": 2.0, "renderedStart": 1.0, "renderedEnd": 2.0, "phase": 1, "text": "tira isso"}
PEDIDO = {"start": 3.0, "end": 3.0, "phase": 1, "text": "aumenta o texto", "geral": True}


@pytest.fixture
def srv(tmp_path, monkeypatch):
    edit = tmp_path / "videos" / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    (edit / "cut.mp4").write_bytes(b"corte")
    (edit / "edl.json").write_text(json.dumps({"ranges": [{"source": "A", "start": 0.0, "end": 4.0}]}), encoding="utf-8")
    monkeypatch.setattr(ps.ac, "conferir_projeto", lambda e, p: [])
    monkeypatch.setattr(ps.gr, "o_que_falta", lambda e: ["final"])

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
    yield SimpleNamespace(port=server.server_address[1], edit=edit)
    server.shutdown()
    server.server_close()


def pedir(port, metodo, caminho, corpo=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(metodo, caminho, body=None if corpo is None else json.dumps(corpo))
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, json.loads(dados or b"{}")


def _agente(edit: Path, ha_s: float) -> None:
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    st["agente"] = {"trabalhando": True, "desde": time.time() - ha_s}
    (edit / "state.json").write_text(json.dumps(st), encoding="utf-8")


def test_marcacoes_e_pedidos_esperam_o_pronto(srv):
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "notes": [NOTA]})
    assert r.status == 200 and d == {"ok": True, "pedidos": 1}
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "notes": [PEDIDO]})
    assert d["pedidos"] == 2
    assert not (srv.edit / "preview_edits.json").exists() and not (srv.edit / "pronto.json").exists()
    assert pedir(srv.port, "GET", "/api/state")[1]["pedidos"] == 2


def test_pronto_junta_os_pedidos_o_que_foi_feito_e_a_fase(srv):
    pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "notes": [NOTA, PEDIDO]})
    (srv.edit / "ajustes_feitos.json").write_text(json.dumps({"feitos": [{"quando": "x", "oque": "corte: 1 tomada(s) aparada(s)"}]}),
                                                  encoding="utf-8")
    r, d = pedir(srv.port, "POST", "/api/pronto", {})
    assert r.status == 200 and d == {"ok": True, "pedidos": 2, "vigia": False}
    pronto = json.loads((srv.edit / "pronto.json").read_text(encoding="utf-8"))
    assert pronto["fase"] == 1 and [p["text"] for p in pronto["pedidos"]] == ["tira isso", "aumenta o texto"]
    assert pronto["feitos"][0]["oque"].startswith("corte:") and "legado" not in pronto
    assert not (srv.edit / "pedidos.json").exists()  # a lista esvazia
    # outro Pronto antes de o agente pegar o primeiro: os pedidos somam
    pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "notes": [{**NOTA, "text": "mais um"}]})
    pedir(srv.port, "POST", "/api/pronto", {})
    pronto = json.loads((srv.edit / "pronto.json").read_text(encoding="utf-8"))
    assert [p["text"] for p in pronto["pedidos"]] == ["tira isso", "aumenta o texto", "mais um"]


def test_pronto_com_ajustes_de_um_editor_anterior(srv):
    (srv.edit / "preview_edits.json").write_text(json.dumps({"notes": [NOTA]}), encoding="utf-8")
    pedir(srv.port, "POST", "/api/pronto", {})
    assert json.loads((srv.edit / "pronto.json").read_text(encoding="utf-8"))["legado"] is True
    assert pedir(srv.port, "GET", "/api/state")[1]["hasPendingEdits"] is True


def test_voz_e_montagem_esperam_o_baixar(srv):
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "melhorar": {"voz": 60, "fundo": 30}})
    assert r.status == 200 and d == {"ok": True}
    assert ps.pend.ler(srv.edit)["melhorar"] == {"voz": 60, "fundo": 30}
    assert not (srv.edit / "preview_edits.json").exists()
    pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "melhorar": {"desligar": True}})
    assert ps.pend.ler(srv.edit)["melhorar"] == {"desligar": True}  # o mais novo vale


def test_com_o_agente_trabalhando_o_corte_e_o_baixar_esperam(srv):
    _agente(srv.edit, 5 * 60)
    corte = {"type": "timeline-edits", "edl": {"ranges": [{"source": "A", "start": 1.0, "end": 4.0, "take": 0}]}}
    r, d = pedir(srv.port, "POST", "/api/save", corte)
    assert r.status == 409 and "agente está trabalhando" in d["error"]
    r, d = pedir(srv.port, "POST", "/api/gerar", {})
    assert r.status == 409 and "agente está trabalhando" in d["error"]
    r, d = pedir(srv.port, "POST", "/api/pronto", {})
    assert r.status == 409 and "já está trabalhando" in d["error"]
    assert pedir(srv.port, "GET", "/api/state")[1]["agenteTrabalhando"] is True
    # marcar e salvar camadas continua valendo: não mexe no corte
    assert pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "notes": [NOTA]})[0].status == 200


def test_agente_parado_ha_muito_tempo_nao_trava(srv, monkeypatch):
    _agente(srv.edit, 40 * 60)
    monkeypatch.setattr(ps, "comando_gerar", lambda e, a: [sys.executable, "-c", "pass"])
    r, d = pedir(srv.port, "POST", "/api/gerar", {})
    assert r.status == 200 and d["trabalho"] == "gerar"
    assert pedir(srv.port, "GET", "/api/state")[1]["agenteTrabalhando"] is False
