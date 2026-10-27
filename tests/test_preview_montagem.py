"""Os lugares da montagem no editor: o que o Trocar oferece, os quadros e o clipe do Trecho, e o envio de
uma mídia para um lugar. Só o que é da montagem sai: um caminho qualquer no pedido não abre arquivo."""
from __future__ import annotations

import http.client
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import preview_server as ps  # noqa: E402


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *map(str, args)], check=True)


@pytest.fixture
def srv(tmp_path, monkeypatch):
    # a montagem nova (Usar) vira um trabalho do servidor na hora: aqui, um que termina sem fazer nada
    monkeypatch.setattr(ps, "comando_montar", lambda e: [sys.executable, "-c", "pass"])
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
    fim = time.time() + 10
    while ps.tb.vivo(edit) and time.time() < fim:  # a montagem falsa termina antes de a pasta sumir
        time.sleep(0.05)


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


def _espera_trabalho(srv, prazo: float = 10.0) -> None:
    fim = time.time() + prazo
    while ps.tb.vivo(srv.edit) and time.time() < fim:
        time.sleep(0.05)


def test_estado_leva_os_lugares_salvos_ate_o_agente_refazer(srv):
    """O editor recarrega depois do Salvar; com isto, o lugar segue marcado com a mídia nova."""
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemPendente"] is None
    pendente = srv.edit / ".cutmind" / "pendente.json"
    pendente.parent.mkdir(exist_ok=True)
    pendente.write_text(json.dumps({"montagem": {"lugares": [{"vaga": 2, "de": 1.0}]}}), encoding="utf-8")
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemPendente"] == [{"vaga": 2, "de": 1.0}]
    pendente.write_text(json.dumps({"melhorar": {"voz": 50, "fundo": 20}}), encoding="utf-8")  # sem lugares
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


# ---- modelos de montagem (etapa 5) ----
def _post(port, caminho, corpo):
    dados = json.dumps(corpo).encode("utf-8")
    return pedir(port, caminho, "POST", dados, {"Content-Type": "application/json", "Content-Length": str(len(dados))})


def test_modelos_de_montagem_listar_guardar_e_apagar(srv):
    r, dados = pedir(srv.port, "/api/montagens")
    assert r.status == 200
    kit = [m for m in json.loads(dados)["modelos"] if m["id"] == "drop-cedo"][0]
    assert kit["doKit"] and kit["lugares"] == 34 and kit["ritmo"][:3] == [4, 4, 1]
    # a montagem aberta vira modelo: o que vai nele sai do projeto gravado, nunca do pedido
    edl = json.loads((srv.edit / "edl.json").read_text(encoding="utf-8"))
    edl["ranges"] = [{"source": "a", "start": 0.0, "end": 1.0, "vaga": 1}, {"source": "b", "start": 0.0, "end": 0.5, "vaga": 2}]
    for lg, nb in zip(edl["montagem"]["lugares"], (2, 1)):
        lg["batidas"] = nb
    (srv.edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r, dados = _post(srv.port, "/api/montagens", {"nome": "Meu ritmo", "vagas": [{"batidas": 64}]})
    assert r.status == 200, dados
    out = json.loads(dados)
    assert out["modelo"]["id"] == "meu-ritmo" and out["modelo"]["ritmo"] == [2, 1] and out["avisos"] == []
    assert "meu-ritmo" in [m["id"] for m in json.loads(pedir(srv.port, "/api/montagens")[1])["modelos"]]
    assert _post(srv.port, "/api/montagens/apagar", {"id": "meu-ritmo"})[0].status == 200
    assert _post(srv.port, "/api/montagens/apagar", {"id": "drop-cedo"})[0].status == 404  # o do kit fica
    assert _post(srv.port, "/api/montagens", {"nome": ""})[0].status == 400


def test_salvar_o_usar_de_um_modelo(srv):
    pedido = {"modelo": "drop-cedo", "musica": "midia/musica.m4a", "midias": ["midia/nova.png"]}
    r, dados = _post(srv.port, "/api/save", {"montagem": {"usar": pedido}})
    assert r.status == 200, dados
    assert json.loads((srv.edit / ".cutmind" / "pendente.json").read_text(encoding="utf-8"))["montagem"] == {"usar": pedido}
    _espera_trabalho(srv)
    # um Salvar de lugares antes de a montagem terminar não desfaz o pedido da montagem nova
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 1, "midia": "midia/nova.png"}]}})[0].status == 200
    assert json.loads((srv.edit / ".cutmind" / "pendente.json").read_text(encoding="utf-8"))["montagem"] == {"usar": pedido}
    for ruim in ({**pedido, "modelo": "nao-existe"}, {**pedido, "musica": "midia/nova.png"},
                 {**pedido, "musica": str(srv.fora)}, {**pedido, "midias": []}, {**pedido, "midias": [str(srv.fora)]},
                 {**pedido, "midias": ["midia/../../segredo.png"]}, {**pedido, "midias": ["midia/musica.m4a"]}):
        assert _post(srv.port, "/api/save", {"montagem": {"usar": ruim}})[0].status == 400, ruim


def test_usar_aceita_as_fotos_e_clipes_da_montagem_aberta(srv):
    """Outro modelo numa montagem feita pelo chat: o painel oferece as mídias dela (as do Trocar)."""
    pedido = {"modelo": "drop-cedo", "musica": "midia/musica.m4a", "midias": [str(srv.clipe), "midia/nova.png", str(srv.foto)]}
    r, dados = _post(srv.port, "/api/save", {"montagem": {"usar": pedido}})
    assert r.status == 200, dados
    assert json.loads((srv.edit / ".cutmind" / "pendente.json").read_text(encoding="utf-8"))["montagem"]["usar"]["midias"] == [
        str(srv.clipe), "midia/nova.png", str(srv.foto)]
    assert _post(srv.port, "/api/save", {"montagem": {"usar": {**pedido, "midias": [str(srv.fora)]}}})[0].status == 400


def test_montagem_nova_no_estado_e_no_trocar(srv):
    """A Nova montagem ainda sem edl: o painel envia fotos para midia/ e as vê na lista; depois do
    Salvar, o estado diz que o agente está montando."""
    (srv.edit / "edl.json").unlink()
    assert pedir(srv.port, "/api/montagem/midias")[0].status == 404  # um projeto vazio qualquer
    (srv.edit / "state.json").write_text(json.dumps({"project": "Nova", "phase": 0, "novo": True, "montagem": True}),
                                         encoding="utf-8")
    op = json.loads(pedir(srv.port, "/api/montagem/midias")[1])["opcoes"]
    assert [o["midia"] for o in op] == ["midia/nova.png"]  # só o que chegou: ainda não há montagem
    assert pedir(srv.port, f"/gen/montagem-quadro?midia={q('midia/nova.png')}&t=0&h=120")[0].status == 200
    assert pedir(srv.port, f"/gen/montagem-quadro?midia={q(srv.foto)}&t=0")[0].status == 404
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemNova"] is None
    pedido = {"modelo": "drop-cedo", "musica": "midia/musica.m4a", "midias": ["midia/nova.png"]}
    assert _post(srv.port, "/api/save", {"montagem": {"usar": pedido}})[0].status == 200
    assert json.loads(pedir(srv.port, "/api/state")[1])["montagemNova"] == pedido


def test_usar_vale_num_projeto_novo_e_nao_num_corte_de_fala(srv):
    pedido = {"modelo": "drop-cedo", "musica": "midia/musica.m4a", "midias": ["midia/nova.png"]}
    (srv.edit / "edl.json").unlink()  # a Nova montagem ainda não tem edl
    assert _post(srv.port, "/api/save", {"montagem": {"usar": pedido}})[0].status == 200
    (srv.edit / "edl.json").write_text(json.dumps({"sources": {}, "ranges": [{"source": "a", "start": 0, "end": 1}]}),
                                       encoding="utf-8")
    r, dados = _post(srv.port, "/api/save", {"montagem": {"usar": pedido}})
    assert r.status == 400 and "Nova montagem" in json.loads(dados)["error"]


def test_salvar_o_formato_da_montagem(srv):
    """O formato vai no Salvar; voltar ao de agora antes de o agente refazer desfaz o pedido."""
    ler = lambda: json.loads((srv.edit / ".cutmind" / "pendente.json").read_text(encoding="utf-8"))  # noqa: E731
    r, dados = _post(srv.port, "/api/save", {"montagem": {"lugares": [], "formato": "16:9"}})
    assert r.status == 200, dados
    assert ler()["montagem"] == {"lugares": [], "formato": "16:9"}
    assert json.loads(pedir(srv.port, "/api/state")[1])["formatoPendente"] == "16:9"
    # um lugar salvo depois soma, e o formato pedido fica
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 2, "de": 1.0}]}})[0].status == 200
    assert ler()["montagem"] == {"lugares": [{"vaga": 2, "de": 1.0}], "formato": "16:9"}
    # de volta ao em pé (o de agora): o formato sai, o lugar fica
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [], "formato": "9:16"}})[0].status == 200
    assert ler()["montagem"] == {"lugares": [{"vaga": 2, "de": 1.0}]}
    assert json.loads(pedir(srv.port, "/api/state")[1])["formatoPendente"] is None
    for ruim in ("4:3", 16, ""):
        assert _post(srv.port, "/api/save", {"montagem": {"lugares": [], "formato": ruim}})[0].status == 400, ruim


def test_usar_leva_o_formato_escolhido(srv):
    pedido = {"modelo": "drop-cedo", "musica": "midia/musica.m4a", "midias": ["midia/nova.png"], "formato": "1:1"}
    assert _post(srv.port, "/api/save", {"montagem": {"usar": pedido}})[0].status == 200
    assert json.loads((srv.edit / ".cutmind" / "pendente.json").read_text(encoding="utf-8"))["montagem"]["usar"]["formato"] == "1:1"
    assert _post(srv.port, "/api/save", {"montagem": {"usar": {**pedido, "formato": "21:9"}}})[0].status == 400


def test_o_aviso_ao_agente_diz_o_formato(tmp_path):
    import watch_edits as we

    (tmp_path / "edl.json").write_text(json.dumps({"montagem": {"lugares": []}}), encoding="utf-8")
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"montagem": {"lugares": [], "formato": "16:9"}}), encoding="utf-8")
    txt = we.digest(p)
    assert "formato deitado (16:9)" in txt and "montagem.py aplicar" in txt and "montagem inteira" in txt


def test_miniatura_da_foto_sem_o_marcador_de_fim(srv):
    """Foto baixada da internet que termina sem o marcador de fim do JPEG: o ffmpeg a lê pelo demuxer
    image2, que com `-ss` descartava o único quadro, e a miniatura do Trocar e da Nova montagem saía vazia."""
    foto = srv.edit / "midia" / "cortada.jpg"
    _ffmpeg("-f", "lavfi", "-i", "color=c=green:s=90x160", "-frames:v", "1", foto)
    foto.write_bytes(foto.read_bytes()[:-2])  # sem o FF D9 do fim
    r, dados = pedir(srv.port, f"/gen/montagem-quadro?midia={q('midia/cortada.jpg')}&t=0.00&h=240")
    assert r.status == 200 and r.getheader("Content-Type") == "image/jpeg" and dados[:2] == b"\xff\xd8"


def test_salvar_o_enquadre_de_um_lugar(srv):
    ler = lambda: json.loads((srv.edit / ".cutmind" / "pendente.json").read_text(encoding="utf-8"))["montagem"]  # noqa: E731
    e = {"escala": 1.5, "x": 0.4, "y": 0.6}
    r, dados = _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 1, "enquadre": e}]}})
    assert r.status == 200, dados
    assert ler() == {"lugares": [{"vaga": 1, "enquadre": e}]}
    # outra mídia depois, no mesmo lugar e antes de o agente refazer: o enquadre era da mídia de antes
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 1, "midia": "midia/nova.png"}]}})[0].status == 200
    assert ler() == {"lugares": [{"vaga": 1, "midia": "midia/nova.png"}]}
    # de volta ao automático vai como null
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 2, "enquadre": None}]}})[0].status == 200
    assert {x["vaga"]: x for x in ler()["lugares"]}[2] == {"vaga": 2, "enquadre": None}
    # formato novo: o enquadre salvo antes era do quadro de antes
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 2, "enquadre": e}]}})[0].status == 200
    assert _post(srv.port, "/api/save", {"montagem": {"lugares": [], "formato": "16:9"}})[0].status == 200
    assert all("enquadre" not in x for x in ler()["lugares"]) and ler()["formato"] == "16:9"
    for ruim in ({"escala": 9, "x": 0.5, "y": 0.5}, {"escala": 1, "x": -1, "y": 0.5}, "perto", {"escala": 1}):
        assert _post(srv.port, "/api/save", {"montagem": {"lugares": [{"vaga": 1, "enquadre": ruim}]}})[0].status == 400, ruim


def test_o_aviso_ao_agente_diz_o_enquadre(tmp_path):
    import watch_edits as we

    (tmp_path / "edl.json").write_text(json.dumps({"montagem": {"lugares": []}}), encoding="utf-8")
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"montagem": {"lugares": [{"vaga": 3, "enquadre": {"escala": 1.25, "x": 0.4, "y": 0.5}},
                                                      {"vaga": 4, "enquadre": None}]}}), encoding="utf-8")
    txt = we.digest(p)
    assert "lugar 3: enquadrado à mão: 1.25× de caber inteira, centro em 40% × 50% da tela" in txt
    assert "lugar 4: enquadramento automático" in txt
