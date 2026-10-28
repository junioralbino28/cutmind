"""A tela Projetos: a lista em ~/.cutmind, abrir outro projeto e criar um novo pelo editor.

A pasta do kit (CUTMIND_HOME) já vem isolada por teste (conftest.py).
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import preview_server as ps  # noqa: E402
import projetos as pj  # noqa: E402

CODIGO = "codigo-de-teste-0123456789"


def projeto(base: Path, nome: str, fase: int = 1, video: bool = False) -> Path:
    edit = base / nome / "edit"
    edit.mkdir(parents=True)
    estado = {"project": nome, "phase": fase, "video": "cut.mp4", "edl": "edl.json"}
    (edit / "state.json").write_text(json.dumps(estado), encoding="utf-8")
    if video:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=108x192:rate=30:duration=2",
                        "-pix_fmt", "yuv420p", str(edit / "cut.mp4")], check=True)
    return edit


# ---- o módulo ----
def test_registrar_lista_e_por_id(tmp_path):
    a = projeto(tmp_path, "A")
    pid = pj.registrar(a)
    assert pid == pj.id_de(a) and len(pid) == 12
    assert [x["edit"] for x in pj.lista()] == [str(a.resolve())]
    assert pj.por_id(pid) == a.resolve()
    # nada que não seja um id da lista abre: nem caminho, nem id inventado
    assert pj.por_id(str(a)) is None and pj.por_id("0" * 12) is None and pj.por_id(None) is None


def test_pasta_que_sumiu_sai_da_lista(tmp_path):
    a, b = projeto(tmp_path, "A"), projeto(tmp_path, "B")
    pj.registrar(a)
    pj.registrar(b)
    for p in sorted(b.parent.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    b.parent.rmdir()
    assert [x["edit"] for x in pj.lista()] == [str(a.resolve())]
    salvo = json.loads((pj.casa() / "projetos.json").read_text(encoding="utf-8"))
    assert len(salvo["projetos"]) == 1


def test_procurar_acha_edit_e_pula_pastas_pesadas(tmp_path):
    a = projeto(tmp_path / "videos", "A")
    escondido = tmp_path / "videos" / "node_modules" / "X" / "edit"
    escondido.mkdir(parents=True)
    (escondido / "state.json").write_text("{}", encoding="utf-8")
    fundo_demais = tmp_path / "videos" / "1" / "2" / "3" / "4" / "5" / "edit"
    fundo_demais.mkdir(parents=True)
    (fundo_demais / "state.json").write_text("{}", encoding="utf-8")
    assert pj.procurar([tmp_path / "videos"], fundo=3) == [a.resolve()]


def test_nome_seguro():
    assert pj.nome_seguro("  Reels   da Ana  ") == "Reels da Ana"
    assert pj.nome_seguro("Vídeo ação") == "Vídeo ação"
    assert pj.nome_seguro("../../segredo") == "segredo"
    assert pj.nome_seguro("a/b\\c:d*e") == "abcde"
    for ruim in ("", "...", "///", "con", "LPT1"):
        with pytest.raises(ValueError):
            pj.nome_seguro(ruim)


def test_criar_repete_nome_com_numero(tmp_path):
    e1 = pj.criar(tmp_path, "Meu Vídeo")
    e2 = pj.criar(tmp_path, "Meu Vídeo")
    assert e1 == (tmp_path / "Meu Vídeo" / "edit").resolve()
    assert e2 == (tmp_path / "Meu Vídeo 2" / "edit").resolve()
    estado = json.loads((e1 / "state.json").read_text(encoding="utf-8"))
    assert estado["project"] == "Meu Vídeo" and estado["phase"] == 0 and estado["novo"] is True
    assert {x["id"] for x in pj.lista()} == {pj.id_de(e1), pj.id_de(e2)}
    assert pj.resumo(e1)["novo"] is True


def test_resumo_e_capa(tmp_path):
    a = projeto(tmp_path, "A", fase=2, video=True)
    r = pj.resumo(a)
    assert r["nome"] == "A" and r["fase"] == 2 and r["temCapa"] and 1.9 < r["duracao"] < 2.1
    assert r["mudou"] > 0
    capa = pj.capa(a)
    assert capa and capa.suffix == ".jpg" and capa.stat().st_size > 500
    antes = capa.stat().st_mtime_ns
    assert pj.capa(a) == capa and capa.stat().st_mtime_ns == antes  # não refaz à toa
    assert pj.capa(projeto(tmp_path, "B")) is None  # sem vídeo, sem capa


def test_aberto(tmp_path):
    assert pj.aberto() is None
    a = projeto(tmp_path, "A")
    pj.marcar_aberto(a)
    ab = pj.aberto()
    assert ab["id"] == pj.id_de(a) and ab["edit"] == str(a.resolve()) and ab["nome"] == "A"


def test_gravar_espera_quem_esta_lendo(tmp_path):
    """No Windows, trocar o arquivo enquanto outro processo o lê dá PermissionError (o vigia lê o
    aberto.json a cada meio segundo, e a troca de projeto se perdia); a gravação espera a leitura."""
    p = tmp_path / "aberto.json"
    pj._gravar(p, {"v": 1})
    leitura = open(p, "rb")
    threading.Timer(0.2, leitura.close).start()
    try:
        pj._gravar(p, {"v": 2})
    finally:
        leitura.close()
    assert pj._ler(p) == {"v": 2}
    assert not p.with_name(p.name + ".tmp").exists()


# ---- o servidor ----
@pytest.fixture
def srv(tmp_path):
    base = tmp_path / "Downloads"
    a = projeto(base, "Projeto A", video=True)
    b = projeto(base, "Projeto B", fase=2)
    pj.registrar(b)
    pj.registrar(a)

    class H(ps.Handler):
        pass

    H.root = a.resolve()
    H.token = CODIGO
    H.upload_dir = a.parent.resolve()
    H.upload_dir_fixo = False
    H.max_upload = 50_000
    H.bind_host = "0.0.0.0"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    yield SimpleNamespace(port=server.server_address[1], a=a.resolve(), b=b.resolve(), base=base, H=H)
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
    return r, out


def test_lista_de_projetos_marca_o_aberto(srv):
    r, out = pedir(srv.port, "GET", "/api/projetos")
    assert r.status == 200
    d = json.loads(out)
    assert d["aberto"] == pj.id_de(srv.a)
    por_nome = {p["nome"]: p for p in d["projetos"]}
    assert set(por_nome) == {"Projeto A", "Projeto B"}
    assert por_nome["Projeto A"]["aberto"] and not por_nome["Projeto B"]["aberto"]
    assert por_nome["Projeto B"]["fase"] == 2


def test_abrir_troca_o_projeto_do_editor(srv):
    r, out = pedir(srv.port, "POST", "/api/projetos/abrir", {"id": pj.id_de(srv.b)})
    assert r.status == 200 and json.loads(out)["ok"]
    r, out = pedir(srv.port, "GET", "/api/state")
    d = json.loads(out)
    assert d["state"]["project"] == "Projeto B" and d["projeto"]["id"] == pj.id_de(srv.b)
    assert srv.H.root == srv.b and srv.H.upload_dir == srv.b.parent
    assert pj.aberto()["id"] == pj.id_de(srv.b)  # o vigia do agente lê este arquivo


def test_abrir_so_pelo_id_da_lista(srv, tmp_path):
    fora = projeto(tmp_path / "outro", "Fora")
    for corpo in ({"id": pj.id_de(fora)}, {"id": str(fora)}, {"id": "../.."}, {}):
        r, _ = pedir(srv.port, "POST", "/api/projetos/abrir", corpo)
        assert r.status == 404, corpo
    assert srv.H.root == srv.a


def test_novo_projeto_cria_pasta_e_abre(srv):
    r, out = pedir(srv.port, "POST", "/api/projetos/novo", {"nome": "Reels da Ana"})
    assert r.status == 200
    novo = (srv.base / "Reels da Ana" / "edit").resolve()
    assert json.loads(out)["id"] == pj.id_de(novo) and (novo / "state.json").is_file()
    assert srv.H.root == novo and srv.H.upload_dir == novo.parent  # o Enviar manda para a pasta nova
    r, _ = pedir(srv.port, "POST", "/api/projetos/novo", {"nome": "../.."})
    assert r.status == 400


def test_nova_montagem_nasce_marcada(srv):
    r, _ = pedir(srv.port, "POST", "/api/projetos/novo", {"nome": "Viagem", "tipo": "montagem"})
    assert r.status == 200
    st = json.loads(((srv.base / "Viagem" / "edit") / "state.json").read_text(encoding="utf-8"))
    assert st["montagem"] is True and st["novo"] is True and st["project"] == "Viagem"
    assert pj.resumo(srv.base / "Viagem" / "edit")["montagem"] is True
    r, _ = pedir(srv.port, "POST", "/api/projetos/novo", {"nome": "Corte", "tipo": "outro"})
    assert "montagem" not in json.loads(((srv.base / "Corte" / "edit") / "state.json").read_text(encoding="utf-8"))


def test_upload_dir_fixo_nao_acompanha(srv):
    fixo = srv.base / "fixo"
    fixo.mkdir()
    srv.H.upload_dir, srv.H.upload_dir_fixo = fixo.resolve(), True
    pedir(srv.port, "POST", "/api/projetos/abrir", {"id": pj.id_de(srv.b)})
    assert srv.H.upload_dir == fixo.resolve()


def test_capa_do_projeto(srv):
    r, out = pedir(srv.port, "GET", f"/gen/projeto-capa?id={pj.id_de(srv.a)}")
    assert r.status == 200 and r.getheader("Content-Type") == "image/jpeg" and out[:2] == b"\xff\xd8"
    r, _ = pedir(srv.port, "GET", f"/gen/projeto-capa?id={pj.id_de(srv.b)}")  # sem vídeo
    assert r.status == 404
    r, _ = pedir(srv.port, "GET", "/gen/projeto-capa?id=zzz")
    assert r.status == 404


def test_celular_sem_codigo_nao_ve_nem_abre(srv):
    r, _ = pedir(srv.port, "GET", "/api/projetos", remoto=True)
    assert r.status == 403
    r, _ = pedir(srv.port, "POST", "/api/projetos/abrir", {"id": pj.id_de(srv.b)}, remoto=True)
    assert r.status == 403 and srv.H.root == srv.a


def test_main_registra_e_marca_aberto(tmp_path, monkeypatch):
    """O servidor de verdade põe a pasta dele na lista ao subir (sem servir: só o começo do main)."""
    a = projeto(tmp_path, "A")
    chamado = {}

    class Falso:
        def __init__(self, *a, **k):
            chamado["ok"] = True

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(ps, "ThreadingHTTPServer", Falso)
    monkeypatch.setattr(ps, "vigiar_atualizacao", lambda *a, **k: None)   # o Falso não tem socket
    monkeypatch.setattr(sys, "argv", ["preview_server.py", "--root", str(a), "--port", "0"])
    with pytest.raises(KeyboardInterrupt):
        ps.main()
    assert chamado and pj.aberto()["id"] == pj.id_de(a) and pj.por_id(pj.id_de(a)) == a.resolve()
    assert os.environ["CUTMIND_HOME"] in str(pj.casa())


def test_salvar_de_outro_projeto_e_recusado(srv):
    """O PC tinha o projeto A; o celular abriu o B. O Salvar do PC (com o id do A) não grava no B."""
    pedir(srv.port, "POST", "/api/projetos/abrir", {"id": pj.id_de(srv.b)})
    nota = [{"start": 1, "end": 2, "text": "troca isso"}]
    r, out = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "projeto": pj.id_de(srv.a), "notes": nota})
    assert r.status == 409 and "outro projeto" in json.loads(out)["error"]
    assert not (srv.b / "pedidos.json").exists() and not (srv.a / "pedidos.json").exists()
    # com o id certo, grava no projeto aberto, e o id não vai junto
    r, _ = pedir(srv.port, "POST", "/api/save", {"type": "timeline-edits", "projeto": pj.id_de(srv.b), "notes": nota})
    assert r.status == 200
    assert "projeto" not in (srv.b / "pedidos.json").read_text(encoding="utf-8") and not (srv.a / "pedidos.json").exists()
    # editor antigo, sem o id: continua gravando como antes
    r, _ = pedir(srv.port, "POST", "/api/save", {"type": "style-setup"})
    assert r.status == 200 and (srv.b / "preview_style.json").exists()


def test_envio_de_outro_projeto_e_recusado(srv):
    pedir(srv.port, "POST", "/api/projetos/abrir", {"id": pj.id_de(srv.b)})
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=20)
    conn.request("POST", f"/api/upload?name=v.mp4&projeto={pj.id_de(srv.a)}", body=b"x" * 100,
                 headers={"Content-Length": "100"})
    r = conn.getresponse()
    r.read()
    conn.close()
    assert r.status == 409
    assert not (srv.b.parent / "v.mp4").exists()
