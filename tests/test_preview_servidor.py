"""O servidor do editor quando ele abre para a rede (o celular).

Um pedido que vem de 127.0.0.2 faz o papel do celular na rede: o servidor só
confia em 127.0.0.1, então para ele 127.0.0.2 é "de fora" — sem precisar de
um segundo aparelho no teste.
"""
from __future__ import annotations

import argparse
import http.client
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import preview_server as ps  # noqa: E402

CODIGO = "codigo-de-teste-0123456789"


@pytest.fixture
def srv(tmp_path):
    videos = tmp_path / "videos"
    edit = videos / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "edl": "edl.json"}))
    take = videos / "take1.mp4"
    (edit / "edl.json").write_text(json.dumps({"sources": {"take1": str(take)}, "ranges": []}))
    irma = tmp_path / "videos" / "edit-segredo"
    irma.mkdir()
    (irma / "x.txt").write_text("não era para sair daqui")

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = CODIGO
    H.allow_hosts = (".ts.net",)
    H.upload_dir = videos.resolve()
    H.max_upload = 50_000
    H.bind_host = "0.0.0.0"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit, videos=videos, take=take)
    server.shutdown()
    server.server_close()


def pedir(port, metodo, caminho, *, remoto=False, cookie=None, host=None, corpo=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15,
                                      source_address=("127.0.0.2", 0) if remoto else None)
    headers = {}
    if cookie:
        headers["Cookie"] = f"{ps.TOKEN_COOKIE}={cookie}"
    if host:
        headers["Host"] = host
    conn.request(metodo, caminho, body=corpo, headers=headers)
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, dados


def pedir_so_cabecalho(port, caminho, tamanho, *, remoto=True):
    """POST que anuncia um tamanho e não manda o corpo — o servidor tem de
    recusar pelo cabeçalho, sem ler nada."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15,
                                      source_address=("127.0.0.2", 0) if remoto else None)
    conn.putrequest("POST", caminho)
    conn.putheader("Cookie", f"{ps.TOKEN_COOKIE}={CODIGO}")
    if tamanho is not None:
        conn.putheader("Content-Length", str(tamanho))
    conn.endheaders()
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, dados


# ---- quem entra ----
def test_padrao_continua_so_este_computador():
    ap = argparse.ArgumentParser()
    ps.add_network_args(ap)
    assert ap.parse_args([]).host == "127.0.0.1"
    assert ps.is_local_bind("127.0.0.1")
    assert ps.pc_host("0.0.0.0") == "127.0.0.1" and ps.pc_host("192.168.0.5") == "192.168.0.5"


def test_manifesto_aponta_icones_que_existem():
    """Sem ícone de 192 e de 512 que exista de verdade, o Chrome não instala o app."""
    m = json.loads((ps.APP_DIR / "celular.webmanifest").read_text(encoding="utf-8"))
    assert m["display"] == "standalone" and m["start_url"] == "/celular"
    assert {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
    for icone in m["icons"]:
        assert (ps.APP_DIR / icone["src"].removeprefix("/assets/")).is_file(), icone["src"]


def test_computador_entra_sem_codigo(srv):
    r, _ = pedir(srv.port, "GET", "/api/state")
    assert r.status == 200


def test_rede_sem_codigo_ve_a_tela_mas_nao_os_dados(srv):
    """A interface é o código aberto do kit; o que o código protege são os dados."""
    r, corpo = pedir(srv.port, "GET", "/api/state", remoto=True)
    assert r.status == 403 and "QR code" in json.loads(corpo)["error"]
    for dado in ("/media/state.json", "/gen/waveform.json", "/gen/frame?src=take1&t=0"):
        assert pedir(srv.port, "GET", dado, remoto=True)[0].status == 403, dado
    assert pedir(srv.port, "GET", "/celular", remoto=True)[0].status == 200


def test_codigo_errado_e_barrado(srv):
    r, _ = pedir(srv.port, "GET", "/api/state", remoto=True, cookie="chute-" + "x" * 20)
    assert r.status == 403


def test_entrada_pelo_link_grava_o_cookie(srv):
    r, _ = pedir(srv.port, "GET", "/c?t=errado", remoto=True)
    assert r.status == 403
    r, _ = pedir(srv.port, "GET", f"/c?t={CODIGO}", remoto=True)
    assert r.status == 303 and r.getheader("Location") == "/celular"
    cookie = r.getheader("Set-Cookie")
    assert f"{ps.TOKEN_COOKIE}={CODIGO}" in cookie
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    r, _ = pedir(srv.port, "GET", "/api/state", remoto=True, cookie=CODIGO)
    assert r.status == 200


def test_host_de_fora_e_barrado(srv):
    """DNS rebinding: o navegador manda o nome do site de fora no Host."""
    assert pedir(srv.port, "GET", "/api/state", host="site-de-fora.example:4820")[0].status == 403
    assert pedir(srv.port, "GET", "/api/state", host="localhost:4820")[0].status == 200
    assert pedir(srv.port, "GET", "/api/state", host="192.168.0.10:4820")[0].status == 200
    assert pedir(srv.port, "GET", "/api/state", host="meu-pc.tail1234.ts.net")[0].status == 200


def test_caminho_irmao_com_mesmo_prefixo_nao_passa(srv):
    """"edit-segredo" começa com "edit": comparado como texto, passava."""
    r, corpo = pedir(srv.port, "GET", "/media/../edit-segredo/x.txt")
    assert r.status == 400 and "daqui".encode() not in corpo


def test_links_do_celular_so_no_computador(srv):
    r, _ = pedir(srv.port, "GET", "/api/celular", remoto=True, cookie=CODIGO)
    assert r.status == 403
    r, corpo = pedir(srv.port, "GET", "/api/celular")
    dados = json.loads(corpo)
    assert r.status == 200 and dados["enabled"] is True
    assert all(CODIGO in u["url"] for u in dados["urls"])


# ---- envio de vídeo ----
def test_envio_vai_para_a_pasta_dos_videos_sem_sobrescrever(srv):
    r, corpo = pedir(srv.port, "POST", "/api/upload?name=..%2F..%2Ffora.mp4",
                     remoto=True, cookie=CODIGO, corpo=b"a" * 1000)
    assert r.status == 200, corpo
    assert (srv.videos / "fora.mp4").read_bytes() == b"a" * 1000
    assert not (srv.videos.parent / "fora.mp4").exists()
    r, corpo = pedir(srv.port, "POST", "/api/upload?name=fora.mp4",
                     remoto=True, cookie=CODIGO, corpo=b"b" * 10)
    assert json.loads(corpo)["file"] == "fora (2).mp4"
    assert (srv.videos / "fora.mp4").read_bytes() == b"a" * 1000
    aviso = json.loads((srv.edit / "preview_upload.json").read_text(encoding="utf-8"))
    assert [f["file"] for f in aviso["files"]] == ["fora.mp4", "fora (2).mp4"]
    assert not list(srv.videos.glob(".*.parte"))


def test_envio_recusa_o_que_nao_e_video(srv):
    r, _ = pedir(srv.port, "POST", "/api/upload?name=programa.exe",
                 remoto=True, cookie=CODIGO, corpo=b"MZ")
    assert r.status == 415
    assert not (srv.videos / "programa.exe").exists()


def test_envio_recusa_maior_que_o_limite(srv):
    r, _ = pedir_so_cabecalho(srv.port, "/api/upload?name=grande.mp4", 60_000)
    assert r.status == 413
    assert not list(srv.videos.glob("*grande*"))


def test_envio_sem_tamanho_e_recusado(srv):
    r, _ = pedir_so_cabecalho(srv.port, "/api/upload?name=x.mp4", None)
    assert r.status == 411


def test_envio_sem_codigo_e_barrado(srv):
    r, _ = pedir(srv.port, "POST", "/api/upload?name=x.mp4", remoto=True, corpo=b"x")
    assert r.status == 403
    assert not (srv.videos / "x.mp4").exists()


def test_ajuste_grande_demais_e_recusado(srv):
    r, _ = pedir_so_cabecalho(srv.port, "/api/save", ps.MAX_JSON_BYTES + 1)
    assert r.status == 413


def test_nome_do_envio_fica_limpo():
    assert ps.clean_upload_name("../../a.MP4") == "a.mp4"
    assert ps.clean_upload_name("C:\\x\\b?.mov") == "b_.mov"
    assert ps.clean_upload_name("CON.mp4") == "_CON.mp4"
    assert ps.clean_upload_name("") == "video"


def test_codigo_fica_salvo_no_projeto(tmp_path):
    a = ps.ensure_token(tmp_path)
    assert len(a) >= 20 and ps.ensure_token(tmp_path) == a


# ---- quadro avulso do vídeo de origem (alça ao aparar) ----
def test_quadro_de_fonte_que_o_edl_nao_lista(srv):
    r, _ = pedir(srv.port, "GET", "/gen/frame?src=nao-existe&t=0")
    assert r.status == 404


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
def test_quadro_da_fonte_do_edl(srv):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
                    "-t", "1", "-pix_fmt", "yuv420p", str(srv.take)], check=True)
    r, corpo = pedir(srv.port, "GET", "/gen/frame?src=take1&t=0.5&h=120", remoto=True, cookie=CODIGO)
    assert r.status == 200 and r.getheader("Content-Type") == "image/jpeg"
    assert corpo[:2] == b"\xff\xd8"
