"""Os lugares da montagem no editor: o que o Trocar oferece, os quadros e o clipe do Trecho, e o envio de
uma mídia para um lugar. Só o que é da montagem sai: um caminho qualquer no pedido não abre arquivo."""
from __future__ import annotations

import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import preview_server as ps  # noqa: E402


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *map(str, args)], check=True)


@pytest.fixture
def srv(tmp_path):
    videos = tmp_path / "videos"
    edit = videos / "edit"
    (edit / "midia").mkdir(parents=True)
    originais = tmp_path / "originais"
    originais.mkdir()
    foto, clipe = originais / "foto um.png", originais / "clipe.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=90x160", "-frames:v", "1", foto)
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=2", clipe)
    _ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=90x160", "-frames:v", "1", edit / "midia" / "nova.png")
    _ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1", edit / "midia" / "musica.m4a")
    fora = tmp_path / "segredo.png"
    fora.write_bytes((edit / "midia" / "nova.png").read_bytes())
    lugares = [{"vaga": 1, "midia": str(foto), "de": 0.0}, {"vaga": 2, "midia": str(clipe), "de": 0.5}]
    (edit / "edl.json").write_text(json.dumps({
        "sources": {}, "ranges": [], "montagem": {"lugares": lugares, "midias": [str(foto), str(clipe)]}}),
        encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "edl": "edl.json"}), encoding="utf-8")

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.allow_hosts = ()
    H.upload_dir = videos.resolve()
    H.max_upload = 500_000
    H.bind_host = "127.0.0.1"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit, foto=foto, clipe=clipe, fora=fora)
    server.shutdown()
    server.server_close()


def pedir(port, caminho, metodo="GET", corpo=None, cabecalhos=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(metodo, caminho, body=corpo, headers=cabecalhos or {})
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r, dados


def q(valor) -> str:
    return quote(str(valor), safe="")


def test_trocar_oferece_as_midias_da_montagem_e_as_de_midia(srv):
    r, dados = pedir(srv.port, "/api/montagem/midias")
    assert r.status == 200
    op = json.loads(dados)["opcoes"]
    # primeiro as da montagem, na ordem; depois midia/ (a música fica de fora: não é foto nem vídeo)
    assert [(o["nome"], o["tipo"]) for o in op] == [("foto um.png", "foto"), ("clipe.mp4", "video"),
                                                    ("nova.png", "foto")]
    assert op[0]["midia"] == str(srv.foto) and op[2]["midia"] == "midia/nova.png"
    assert op[1]["duracao"] == pytest.approx(2.0, abs=0.1) and op[0]["duracao"] == 0


def test_estado_leva_os_lugares_salvos_ate_o_agente_refazer(srv):
    """O editor recarrega depois do Salvar; com isto, o lugar segue marcado com a mídia nova."""
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemPendente"] is None
    (srv.edit / "preview_edits.json").write_text(json.dumps(
        {"type": "timeline-edits", "montagem": {"lugares": [{"vaga": 2, "de": 1.0}]}}), encoding="utf-8")
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemPendente"] == [{"vaga": 2, "de": 1.0}]
    (srv.edit / "preview_edits.json").write_text(json.dumps({"notes": []}), encoding="utf-8")  # Salvar sem lugares
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemPendente"] is None


def test_projeto_sem_montagem_nao_tem_lugares(srv):
    (srv.edit / "edl.json").write_text(json.dumps({"sources": {}, "ranges": []}), encoding="utf-8")
    assert pedir(srv.port, "/api/montagem/midias")[0].status == 404
    assert pedir(srv.port, f"/gen/montagem-quadro?midia={q(srv.foto)}")[0].status == 404


def test_quadro_de_uma_midia_da_montagem(srv):
    for midia in (srv.clipe, srv.foto, "midia/nova.png"):
        r, jpg = pedir(srv.port, f"/gen/montagem-quadro?midia={q(midia)}&t=1&h=120")
        assert r.status == 200 and r.getheader("Content-Type") == "image/jpeg" and jpg[:2] == b"\xff\xd8", midia
    antes = len(ps._quadros_guardados)
    assert pedir(srv.port, f"/gen/montagem-quadro?midia={q(srv.clipe)}&t=1&h=120")[1][:2] == b"\xff\xd8"
    assert len(ps._quadros_guardados) == antes  # o mesmo quadro: do guardado, sem outro ffmpeg


@pytest.mark.parametrize("midia", ["FORA", "edl.json", "midia/../edl.json", "midia/musica.m4a", "midia/nao-existe.png",
                                   "../segredo.png", ""])
def test_quadro_so_do_que_e_da_montagem(srv, midia):
    valor = srv.fora if midia == "FORA" else midia
    assert pedir(srv.port, f"/gen/montagem-quadro?midia={q(valor)}&t=0")[0].status == 404


def test_o_trecho_toca_o_clipe_original(srv):
    r, dados = pedir(srv.port, f"/gen/montagem-video?midia={q(srv.clipe)}", cabecalhos={"Range": "bytes=0-99"})
    assert r.status == 206 and len(dados) == 100
    assert pedir(srv.port, f"/gen/montagem-video?midia={q(srv.foto)}")[0].status == 400
    assert pedir(srv.port, f"/gen/montagem-video?midia={q(srv.fora)}")[0].status == 404


def test_envio_para_um_lugar_fica_no_projeto_e_nao_avisa_o_agente(srv):
    corpo = srv.clipe.read_bytes()
    r, dados = pedir(srv.port, "/api/upload?name=do%20celular.mp4&para=montagem", "POST", corpo,
                     {"Content-Length": str(len(corpo))})
    res = json.loads(dados)
    assert r.status == 200 and res["arquivo"] == "midia/do celular.mp4" and res["tipo"] == "video"
    assert (srv.edit / "midia" / "do celular.mp4").read_bytes() == corpo
    assert not (srv.edit / "preview_upload.json").exists()  # não é material novo para cortar
    nomes = [o["nome"] for o in json.loads(pedir(srv.port, "/api/montagem/midias")[1])["opcoes"]]
    assert nomes[-1] == "do celular.mp4"
    # e o Salvar aceita ela no lugar
    assert ps.conferir_montagem(srv.edit, srv.edit.parent, {"lugares": [{"vaga": 2, "midia": res["arquivo"]}]}) == {
        "lugares": [{"vaga": 2, "midia": "midia/do celular.mp4"}]}
    r, _ = pedir(srv.port, "/api/upload?name=som.m4a&para=montagem", "POST", b"x" * 10, {"Content-Length": "10"})
    assert r.status == 415
