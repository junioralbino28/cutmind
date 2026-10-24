"""A ferramenta Fundo do editor, lado do servidor: a rota /gen/recorte (a pessoa recortada no
quadro, para os cartões) e o Salvar que aceita o Fundo criado no editor. O recorte de verdade (o
modelo) não roda aqui: recorte_png é de mentira."""
from __future__ import annotations

import http.client
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import preview_server as ps  # noqa: E402


@pytest.fixture
def srv(tmp_path, monkeypatch):
    edit = tmp_path / "videos" / "edit"
    (edit / "midia").mkdir(parents=True)
    (edit / "cut.mp4").write_bytes(b"corte")
    (edit / "midia" / "Cenário 1.jpg").write_bytes(b"jpg")
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 2, "video": "cut.mp4"}), encoding="utf-8")
    feitos = []

    def recorte_falso(video, t, destino):
        feitos.append(t)
        destino.write_bytes(b"\x89PNG recorte " + str(t).encode())
    monkeypatch.setattr(ps, "recorte_png", recorte_falso)
    monkeypatch.setattr(ps, "recorte_disponivel", lambda: True)

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
    yield SimpleNamespace(port=server.server_address[1], edit=edit, feitos=feitos)
    server.shutdown()
    server.server_close()


def pedir(port, metodo, caminho, corpo=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(metodo, caminho, body=None if corpo is None else json.dumps(corpo))
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r.status, r.getheader("Content-Type"), dados


def test_recorte_devolve_a_pessoa_e_guarda_o_quadro(srv):
    st, tipo, dados = pedir(srv.port, "GET", "/gen/recorte?t=1.5")
    assert (st, tipo) == (200, "image/png") and dados.startswith(b"\x89PNG")
    assert pedir(srv.port, "GET", "/gen/recorte?t=1.5")[0] == 200
    assert srv.feitos == [1.5]  # o mesmo quadro não é recortado de novo
    pedir(srv.port, "GET", "/gen/recorte?t=2.0")
    assert srv.feitos == [1.5, 2.0]


def test_recorte_sem_onnxruntime_diz_o_que_falta(srv, monkeypatch):
    monkeypatch.setattr(ps, "recorte_disponivel", lambda: False)
    st, _, dados = pedir(srv.port, "GET", "/gen/recorte?t=1")
    assert st == 409 and "onnxruntime" in json.loads(dados)["error"] and srv.feitos == []


def test_recorte_que_falha_diz_o_motivo(srv, monkeypatch):
    def quebra(video, t, destino):
        raise ValueError("sem quadro nesse tempo")
    monkeypatch.setattr(ps, "recorte_png", quebra)
    st, _, dados = pedir(srv.port, "GET", "/gen/recorte?t=99")
    assert st == 500 and "sem quadro nesse tempo" in json.loads(dados)["error"]
    assert not list((srv.edit / ".preview_cache" / "recorte").glob("*"))  # nada pela metade fica


def _fundo(**k):
    base = {"nova": True, "tipo": "fundo", "start": 4.0, "end": 7.5, "desligada": False, "texto": None, "textos": {},
            "estilo": None, "campos": {"fundo": "fundos/lousa", "escurecer": 0.2, "desfoque": 4}}
    return {**base, **k}


def _salvar(srv, cenas):
    return pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "editData": {"cenas": cenas}})


def test_salvar_aceita_o_fundo_novo_e_a_imagem_do_projeto(srv):
    st, _, dados = _salvar(srv, [_fundo(), _fundo(start=9.0, end=12.0, campos={"fundo": "midia/Cenário 1.jpg"})])
    assert st == 200 and json.loads(dados)["ok"]
    salvo = json.loads((srv.edit / "preview_edits.json").read_text(encoding="utf-8"))
    assert [c["campos"]["fundo"] for c in salvo["editData"]["cenas"]] == ["fundos/lousa", "midia/Cenário 1.jpg"]


@pytest.mark.parametrize("ruim, motivo", [
    (_fundo(tipo="capa"), "só cria o efeito Fundo"),
    (_fundo(campos={"fundo": "fundos/praia"}), "fundos/<"),
    (_fundo(campos={"fundo": "midia/sumiu.jpg"}), "não está no projeto"),
    (_fundo(campos={"fundo": "fundos/lousa", "escurecer": 0.9}), "escurecer"),
    ({"tipo": "vidro", "start": 1, "end": 3, "desligada": True}, "falta o `ref`"),
])
def test_salvar_recusa_o_que_o_editor_nao_cria(srv, ruim, motivo):
    st, _, dados = _salvar(srv, [ruim])
    assert st == 400 and motivo in json.loads(dados)["error"]
    assert not (srv.edit / "preview_edits.json").exists()


def test_dois_salvamentos_somam_o_fundo_novo_aos_efeitos_do_agente():
    velho = {"editData": {"cenas": [{"ref": 2, "tipo": "vidro", "desligada": True}, _fundo(start=9.0, end=12.0)]}}
    novo = {"editData": {"cenas": [{"ref": 0, "tipo": "capa", "desligada": False},
                                    _fundo(campos={"fundo": "fundos/neon"}), _fundo(start=9.0, end=12.0, desligada=True)]}}
    cenas = ps.juntar_salvamentos(velho, novo)["editData"]["cenas"]
    assert [(c.get("ref"), c.get("start")) for c in cenas] == [(0, None), (2, None), (None, 4.0), (None, 9.0)]
    assert cenas[3]["desligada"] is True  # o mesmo Fundo novo, salvo de novo: vale o último
