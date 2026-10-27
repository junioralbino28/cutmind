"""O Salvar que mexe nas tomadas, pelo servidor: confere antes (a pergunta), refaz o corte num
processo à parte e não acorda o agente para isso. O processo do corte é trocado por um falso: o de
verdade está provado em test_aplicar_corte.py."""
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

FALSO = """
import json, sys, time
sys.path.insert(0, sys.argv[1])
import trabalhos as tb
edit, pedido, andamento, espera = sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
tb.escritor(andamento, 'corte')('corte', 'Refazendo o corte', 0.5)
time.sleep(espera)
p = json.load(open(pedido, encoding='utf-8'))
edl = json.load(open(edit + '/edl.json', encoding='utf-8'))
edl['ranges'] = [{k: v for k, v in r.items() if k != 'take'} for r in p['ranges']]
open(edit + '/edl.json', 'w', encoding='utf-8').write(json.dumps(edl))
tb.escritor(andamento, 'corte')('pronto', 'Corte refeito', 1.0, rede=[], fora=[], voz=None)
"""

AVISO = {"tipo": "ponta_na_fala", "em": 0.0, "tomada": 1, "ponta": "começo", "palavra": "roteiro",
         "texto": "A tomada 1 começa no meio da palavra «roteiro»."}
EDL = {"version": 1, "sources": {"A": "A.mp4"}, "ranges": [{"source": "A", "start": 0.0, "end": 10.0},
                                                          {"source": "A", "start": 20.0, "end": 30.0}]}
PEDIDO = {"ranges": [{"source": "A", "start": 2.0, "end": 10.0, "take": 0}, {"source": "A", "start": 20.0, "end": 30.0, "take": 1}],
          "changes": [{"source": "A", "take": 0, "from": {"start": 0.0, "end": 10.0}, "to": {"start": 2.0, "end": 10.0}}],
          "removed": [], "ops": {}}


@pytest.fixture
def srv(tmp_path, monkeypatch):
    edit = tmp_path / "videos" / "edit"
    edit.mkdir(parents=True)
    (edit / "edl.json").write_text(json.dumps(EDL), encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    falso = tmp_path / "corte_falso.py"
    falso.write_text(FALSO, encoding="utf-8")
    estado = SimpleNamespace(avisos=[], espera=0.0)
    monkeypatch.setattr(ps, "comando_corte", lambda e, p, a: [sys.executable, "-I", str(falso), str(HELPERS), str(e), str(p),
                                                               str(a), str(estado.espera)])
    monkeypatch.setattr(ps.ac, "conferir_projeto", lambda e, p: list(estado.avisos))

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


def pedir(port, metodo, caminho, corpo=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(metodo, caminho, body=None if corpo is None else json.dumps(corpo))
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, json.loads(dados or b"{}")


def esperar_trabalho(port, prazo=20):
    fim = time.time() + prazo
    while time.time() < fim:
        a = pedir(port, "GET", "/api/trabalho")[1]
        if a.get("etapa") in ("pronto", "falhou"):
            return a
        time.sleep(0.1)
    raise AssertionError("o trabalho do corte não terminou")


def test_conferir_responde_sem_gravar_nada(srv):
    srv.estado.avisos = [AVISO]
    r, d = pedir(srv.port, "POST", "/api/conferir", {"edl": PEDIDO})
    assert r.status == 200 and d["avisos"] == [AVISO]
    assert json.loads((srv.edit / "edl.json").read_text(encoding="utf-8")) == EDL
    assert not (srv.edit / "preview_edits.json").exists()


def test_salvar_com_aviso_pergunta_e_nao_aplica(srv):
    srv.estado.avisos = [AVISO]
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO})
    assert r.status == 409 and d["avisos"] == [AVISO]
    assert ps.tb.vivo(srv.edit) is None and not (srv.edit / "preview_edits.json").exists()


def test_salvar_confirmado_refaz_o_corte_sem_acordar_o_agente(srv):
    srv.estado.avisos = [AVISO]
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO, "confirmado": True})
    assert r.status == 200 and d == {"ok": True, "trabalho": "corte"}
    assert not (srv.edit / "preview_edits.json").exists()          # nada para o agente
    a = esperar_trabalho(srv.port)
    assert a["etapa"] == "pronto" and a["tipo"] == "corte"
    assert json.loads((srv.edit / "edl.json").read_text(encoding="utf-8"))["ranges"][0]["start"] == 2.0


def test_o_estado_do_editor_traz_o_trabalho(srv):
    srv.estado.espera = 1.0
    assert pedir(srv.port, "GET", "/api/state")[1]["trabalho"] is None
    pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO})
    vivo = pedir(srv.port, "GET", "/api/state")[1]["trabalho"]
    assert vivo["tipo"] == "corte" and vivo["vivo"] is True
    esperar_trabalho(srv.port)
    fim = pedir(srv.port, "GET", "/api/state")[1]["trabalho"]
    assert fim["etapa"] == "pronto" and fim["vivo"] is False      # o fim aparece por um minuto


def test_salvar_sem_aviso_nao_precisa_confirmar(srv):
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO})
    assert r.status == 200 and d["trabalho"] == "corte"
    esperar_trabalho(srv.port)


def test_outro_salvar_enquanto_o_corte_e_refeito_espera(srv):
    srv.estado.espera = 1.5
    assert pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO})[0].status == 200
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO})
    assert r.status == 409 and "refeito" in d["error"]
    esperar_trabalho(srv.port)


def test_a_marcacao_junto_do_corte_espera_o_pronto(srv):
    nota = {"start": 1.0, "end": 2.0, "text": "tira isso", "phase": 1}
    r, d = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "edl": PEDIDO, "notes": [nota]})
    assert r.status == 200 and d["trabalho"] == "corte" and d["pedidos"] == 1
    assert ps.pend.pedidos(srv.edit)[0]["text"] == "tira isso"
    assert not (srv.edit / "preview_edits.json").exists()  # nada para o agente até o Pronto
    esperar_trabalho(srv.port)
