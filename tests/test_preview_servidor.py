"""O servidor do editor quando ele abre para a rede (o celular).

Um pedido que vem de 127.0.0.2 faz o papel do celular na rede: o servidor só
confia em 127.0.0.1, então para ele 127.0.0.2 é "de fora" — sem precisar de
um segundo aparelho no teste.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
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


def test_um_editor_so_no_computador_e_no_celular(srv):
    """O editor do celular é o editor único: `/` (computador) e `/celular` servem a mesma
    página, que se arruma pela largura da tela; a desktop antiga fica em `/classico` até ser
    aprovada a troca (PLANO-editor-unico-desktop)."""
    _, raiz = pedir(srv.port, "GET", "/")
    _, cel = pedir(srv.port, "GET", "/celular")
    assert raiz == cel and b"/assets/celular.js" in raiz
    r, antiga = pedir(srv.port, "GET", "/classico")
    assert r.status == 200 and b"/assets/app.js" in antiga


def test_editor_unico_traz_o_que_so_a_desktop_tinha():
    """O que antes só existia na desktop antiga. Etapa 1: o nome do projeto e a mensagem do
    agente no cabeçalho (o laço com o agente) e o "Abrir no celular" com o QR. Etapa 2: o
    quadro de atalhos do teclado e a régua de zoom com "Ajustar". Etapa 3: mover e aparar os
    blocos da Fase 2 vai no Salvar como `editData`, o que o watch_edits avisa ao agente.
    Etapa 6: as faixas A1/A2 do J-cut (abertas ou não, lembrado no navegador) e a trilha da
    Fase 2 (`soundtrack` do edit-data) como bloco."""
    app = Path(ps.APP_DIR)
    html = (app / "celular.html").read_text(encoding="utf-8")
    js = (app / "celular.js").read_text(encoding="utf-8")
    for id_ in ("projectName", "agentMsg", "btnPhone", "phoneModal", "phoneBody",
                "btnHelp", "helpModal", "zoomRange", "zoomFit"):
        assert f'id="{id_}"' in html, id_
    assert "S.state.message" in js and "fetch('/api/celular')" in js
    assert "payload.editData = {" in js and "splitInserts:" in js and "wordAccents:" in js
    assert "edl.jcut_timeline" in js and "cutmind.jcutOpen" in js and "renderJcutLane" in js
    assert "S.editData && S.editData.soundtrack" in js and "renderTrilhaF2" in js


def test_video_sendo_baixado_nao_impede_o_agente_de_troca_lo(srv):
    """O navegador baixa o vídeo devagar. Se o servidor ficasse com o arquivo aberto a
    transmissão inteira, no Windows o agente não conseguiria trocar o cut.mp4 por cima
    (os.replace dá PermissionError) enquanto o editor estivesse aberto."""
    video = srv.edit / "cut.mp4"
    video.write_bytes(bytes(8 << 20))  # maior que o que o socket aceita sem a outra ponta ler
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=15)
    conn.request("GET", "/media/cut.mp4")
    r = conn.getresponse()
    assert r.status == 200
    r.read(1024)  # começou a baixar e parou de ler, como o navegador com o buffer cheio
    time.sleep(0.3)
    novo = srv.edit / "cut.novo.mp4"
    novo.write_bytes(b"corte novo")
    os.replace(novo, video)  # no Windows, com o arquivo preso, isto dava PermissionError
    conn.close()
    assert video.read_bytes() == b"corte novo"


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
    # recusa pelo nome, sem ler o corpo; mandando o corpo, o Windows às vezes derruba a
    # conexão no meio do envio (ConnectionAbortedError) e o teste falhava por acaso
    r, _ = pedir_so_cabecalho(srv.port, "/api/upload?name=programa.exe", 2)
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


# ---- frases do Empilhado (modo "Posição das frases") ----
def test_frases_do_empilhado_saem_do_diretor(srv):
    pasta = srv.edit / "transcripts"
    pasta.mkdir()
    falas = [("Ação", 0.0), ("rápida", 0.4), ("é", 0.8), ("tudo.", 1.2), ("Agora", 2.5), ("vai", 2.9)]
    palavras = [{"type": "word", "text": t, "start": s, "end": s + 0.3} for t, s in falas]
    (pasta / "cut.json").write_text(json.dumps({"words": palavras}, ensure_ascii=False), encoding="utf-8")
    r, corpo = pedir(srv.port, "GET", "/gen/frases?estilo=stacked")
    assert r.status == 200
    frases = json.loads(corpo)["frases"]
    assert frases[0]["text"].startswith("Ação")  # lido em UTF-8 até sem o modo UTF-8 do Python
    import caption_style
    cues = caption_style.build_cues(caption_style.load_words(pasta / "cut.json"))
    assert [f["start"] for f in frases] == [c["startMs"] / 1000 for c in cues]  # as do diretor, não uma cópia
    assert pedir(srv.port, "GET", "/gen/frases?estilo=karaoke")[0].status == 400
    assert pedir(srv.port, "GET", "/gen/frases?estilo=stacked", remoto=True)[0].status == 403  # dado: só com o código


# ---- camadas: imagem e áudio do projeto ----
def test_imagem_e_audio_vao_para_a_midia_do_projeto(srv):
    """Vídeo é material novo (vai para a pasta dos vídeos e avisa o agente); imagem e
    áudio são camadas do projeto: vão para <edit>/midia/, sem aviso de vídeo novo."""
    r, corpo = pedir(srv.port, "POST", "/api/upload?name=print.PNG", remoto=True, cookie=CODIGO, corpo=b"png")
    dados = json.loads(corpo)
    assert r.status == 200 and dados["tipo"] == "imagem" and dados["arquivo"] == "midia/print.png"
    r, corpo = pedir(srv.port, "POST", "/api/upload?name=voz.m4a", remoto=True, cookie=CODIGO, corpo=b"m4a")
    assert json.loads(corpo)["arquivo"] == "midia/voz.m4a"
    assert (srv.edit / "midia" / "print.png").read_bytes() == b"png"
    assert not (srv.videos / "voz.m4a").exists()
    assert not (srv.edit / "preview_upload.json").exists()
    r, corpo = pedir(srv.port, "GET", "/api/midia", remoto=True, cookie=CODIGO)
    assert [(m["arquivo"], m["tipo"]) for m in json.loads(corpo)["midia"]] == [
        ("midia/print.png", "imagem"), ("midia/voz.m4a", "audio")]
    r, corpo = pedir(srv.port, "GET", "/media/midia/voz.m4a", remoto=True, cookie=CODIGO)
    assert r.status == 200 and r.getheader("Content-Type") == "audio/mp4"


def test_midia_com_espaco_e_acento_abre_pelo_endereco_do_navegador(srv):
    """O navegador pede /media/midia/Grava%C3%A7%C3%A3o%20de%20voz.m4a: o servidor tem
    de achar o arquivo pelo nome de verdade. E o caminho codificado não abre porta:
    %2e%2e continua sendo "..", barrado como antes."""
    r, corpo = pedir(srv.port, "POST", "/api/upload?name=Grava%C3%A7%C3%A3o%20de%20voz.m4a",
                     remoto=True, cookie=CODIGO, corpo=b"m4a")
    assert json.loads(corpo)["arquivo"] == "midia/Gravação de voz.m4a"
    r, corpo = pedir(srv.port, "GET", "/media/midia/Grava%C3%A7%C3%A3o%20de%20voz.m4a", remoto=True, cookie=CODIGO)
    assert r.status == 200 and corpo == b"m4a"
    r, corpo = pedir(srv.port, "GET", "/media/%2e%2e/edit-segredo/x.txt")
    assert r.status == 400 and "daqui".encode() not in corpo


def _salvar(srv, corpo):
    return pedir(srv.port, "POST", "/api/save", remoto=True, cookie=CODIGO,
                 corpo=json.dumps(corpo).encode("utf-8"))


def test_salvar_camadas_grava_o_arquivo_do_projeto(srv):
    camadas = {"video": {"mudo": True}, "faixas": [
        {"id": "a1", "tipo": "audio", "mudo": False, "itens": [
            {"id": "a1-1", "arquivo": "midia/Gravação.m4a", "inicio": 1.23456, "duracao": 4, "volume": 0.8}]},
        {"id": "i1", "tipo": "imagem", "oculto": True, "itens": [
            {"id": "i1-1", "arquivo": "midia/print.png", "inicio": 2, "duracao": 3}]}]}
    r, corpo = _salvar(srv, {"type": "timeline-edits", "camadas": camadas})
    assert r.status == 200, corpo
    salvo = json.loads((srv.edit / "camadas.json").read_text(encoding="utf-8"))
    assert salvo["video"]["mudo"] is True
    assert salvo["faixas"][0]["itens"][0] == {"id": "a1-1", "arquivo": "midia/Gravação.m4a", "inicio": 1.235,
                                              "duracao": 4.0, "corte": 0.0, "volume": 0.8, "melhorar": False}
    assert salvo["faixas"][1]["oculto"] is True
    aviso = json.loads((srv.edit / "preview_edits.json").read_text(encoding="utf-8"))
    assert aviso["camadas"] == salvo


def test_camadas_com_arquivo_de_fora_sao_recusadas(srv):
    for arquivo in ("../state.json", "midia/../state.json", "midia/x/../../state.json", "midia/voz.exe"):
        corpo = {"type": "timeline-edits", "camadas": {"faixas": [
            {"id": "a1", "tipo": "audio", "itens": [{"id": "a1-1", "arquivo": arquivo, "duracao": 1}]}]}}
        r, dados = _salvar(srv, corpo)
        assert r.status == 400 and "camadas" in json.loads(dados)["error"], arquivo
    assert not (srv.edit / "camadas.json").exists()
    assert not (srv.edit / "preview_edits.json").exists()


def test_salvar_efeitos_grava_o_arquivo_do_projeto(srv):
    efeitos = {"itens": [{"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 1, "duracao": 2,
                          "intensidade": 0.5},
                         {"id": "t1", "tipo": "transicao", "pacote": "zoom-central", "corte": 3.333333, "duracao": 1.1}]}
    r, corpo = _salvar(srv, {"type": "timeline-edits", "efeitos": efeitos})
    assert r.status == 200, corpo
    salvo = json.loads((srv.edit / "efeitos.json").read_text(encoding="utf-8"))
    assert salvo["itens"][1] == {"id": "t1", "tipo": "transicao", "pacote": "zoom-central", "corte": 3.333,
                                 "duracao": 1.1}
    assert json.loads((srv.edit / "preview_edits.json").read_text(encoding="utf-8"))["efeitos"] == salvo


def test_efeitos_tortos_nao_gravam_nada(srv):
    r, dados = _salvar(srv, {"type": "timeline-edits", "camadas": {"faixas": []}, "efeitos": {"itens": [
        {"id": "f1", "tipo": "filtro", "pacote": "../../x", "inicio": 0, "duracao": 1}]}})
    assert r.status == 400 and "efeitos" in json.loads(dados)["error"]
    assert not (srv.edit / "efeitos.json").exists() and not (srv.edit / "preview_edits.json").exists()
    assert not (srv.edit / "camadas.json").exists()  # as camadas boas do mesmo Salvar também esperam


# ---- biblioteca de trilhas: o celular escolhe, o servidor baixa ----
@pytest.fixture
def trilhas(srv, tmp_path):
    """Uma Release local com uma trilha, e o servidor usando esse catálogo."""
    import hashlib
    from functools import partial
    from http.server import SimpleHTTPRequestHandler

    import pacotes as pk

    raiz = tmp_path / "release"
    (raiz / "trilhas-1").mkdir(parents=True)
    musica, previa = b"M" * 3000, b"m" * 300
    (raiz / "trilhas-1" / "calma-01.m4a").write_bytes(musica)
    (raiz / "trilhas-1" / "calma-01.previa.m4a").write_bytes(previa)
    rel = ps.ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(raiz)))
    threading.Thread(target=partial(rel.serve_forever, poll_interval=0.05), daemon=True).start()
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    cat = pk.validar({"base": f"http://127.0.0.1:{rel.server_address[1]}", "pacotes": [
        {"id": "calma-01", "tipo": "trilha", "nome": "Manhã leve", "clima": "calma", "duracao": 61.0,
         "release": "trilhas-1", "arquivo": "calma-01.m4a", "tamanho": len(musica), "sha256": sha(musica),
         "previa": {"arquivo": "calma-01.previa.m4a", "tamanho": len(previa), "sha256": sha(previa)}}]})
    ps.Handler.pacotes = pk.Pacotes(cat, tmp_path / "cache", 10**9)
    yield SimpleNamespace(musica=musica, previa=previa)
    ps.Handler.pacotes = None
    rel.shutdown()
    rel.server_close()


def _post_json(srv, caminho, corpo, **kw):
    return pedir(srv.port, "POST", caminho, corpo=json.dumps(corpo).encode("utf-8"), **kw)


def test_lista_de_trilhas_com_o_que_ja_baixou(srv, trilhas):
    r, corpo = pedir(srv.port, "GET", "/api/pacotes?tipo=trilha", remoto=True, cookie=CODIGO)
    dados = json.loads(corpo)
    assert r.status == 200
    assert [(p["id"], p["nome"], p["baixado"], p["favorito"]) for p in dados["pacotes"]] == [
        ("calma-01", "Manhã leve", False, False)]


def test_previa_da_trilha_sai_pelo_servidor(srv, trilhas):
    r, corpo = pedir(srv.port, "GET", "/gen/pacote-previa?id=calma-01", remoto=True, cookie=CODIGO)
    assert r.status == 200 and corpo == trilhas.previa and r.getheader("Content-Type") == "audio/mp4"
    r, corpo = pedir(srv.port, "GET", "/gen/pacote-previa?id=nao-existe", remoto=True, cookie=CODIGO)
    assert r.status == 404 and "error" in json.loads(corpo)


def test_usar_trilha_poe_o_arquivo_na_midia_do_projeto(srv, trilhas):
    r, corpo = _post_json(srv, "/api/pacotes/usar", {"id": "calma-01"}, remoto=True, cookie=CODIGO)
    dados = json.loads(corpo)
    assert r.status == 200, corpo
    assert dados == {"arquivo": "midia/calma-01.m4a", "id": "calma-01", "nome": "Manhã leve", "duracao": 61.0}
    assert (srv.edit / "midia" / "calma-01.m4a").read_bytes() == trilhas.musica
    r, corpo = pedir(srv.port, "GET", "/api/pacotes?tipo=trilha", remoto=True, cookie=CODIGO)
    assert json.loads(corpo)["pacotes"][0]["baixado"] is True


def test_favoritar_trilha(srv, trilhas):
    r, _ = _post_json(srv, "/api/pacotes/favorito", {"id": "calma-01", "on": True}, remoto=True, cookie=CODIGO)
    assert r.status == 200
    r, corpo = pedir(srv.port, "GET", "/api/pacotes", remoto=True, cookie=CODIGO)
    assert json.loads(corpo)["pacotes"][0]["favorito"] is True


def test_trilhas_sem_codigo_sao_barradas(srv, trilhas):
    assert pedir(srv.port, "GET", "/api/pacotes", remoto=True)[0].status == 403
    assert pedir(srv.port, "GET", "/gen/pacote-previa?id=calma-01", remoto=True)[0].status == 403
    assert _post_json(srv, "/api/pacotes/usar", {"id": "calma-01"}, remoto=True)[0].status == 403
    assert not (srv.edit / "midia").exists()


# ---- efeitos: o motor é código aberto; os arquivos do pacote são dados ----
@pytest.fixture
def filtro(srv, tmp_path):
    """Uma Release local com um filtro em zip, e o servidor usando esse catálogo."""
    import hashlib
    import io
    import zipfile
    from functools import partial
    from http.server import SimpleHTTPRequestHandler

    import pacotes as pk

    raiz = tmp_path / "release"
    (raiz / "efeitos-1").mkdir(parents=True)
    arquivos = {"efeito.json": b'{"formato": 1, "tipo": "filtro"}', "efeito.frag": b"void main(){}"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    (raiz / "efeitos-1" / "filme-pb.zip").write_bytes(buf.getvalue())
    rel = ps.ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(raiz)))
    threading.Thread(target=partial(rel.serve_forever, poll_interval=0.05), daemon=True).start()
    cat = pk.validar({"base": f"http://127.0.0.1:{rel.server_address[1]}", "pacotes": [
        {"id": "filme-pb", "tipo": "filtro", "nome": "Filme P&B", "release": "efeitos-1",
         "arquivo": "filme-pb.zip", "tamanho": len(buf.getvalue()),
         "sha256": hashlib.sha256(buf.getvalue()).hexdigest()}]})
    ps.Handler.pacotes = pk.Pacotes(cat, tmp_path / "cache", 10**9)
    yield SimpleNamespace(arquivos=arquivos)
    ps.Handler.pacotes = None
    rel.shutdown()
    rel.server_close()


def test_arquivos_do_efeito_saem_pelo_servidor(srv, filtro):
    r, corpo = pedir(srv.port, "GET", "/gen/pacote/filme-pb/efeito.json", remoto=True, cookie=CODIGO)
    assert r.status == 200 and corpo == filtro.arquivos["efeito.json"]
    assert r.getheader("Content-Type").startswith("application/json")
    r, corpo = pedir(srv.port, "GET", "/gen/pacote/filme-pb/efeito.frag", remoto=True, cookie=CODIGO)
    assert r.status == 200 and corpo == filtro.arquivos["efeito.frag"]
    assert r.getheader("Content-Type").startswith("text/plain")


def test_efeito_nao_entrega_o_que_esta_fora_dele(srv, filtro):
    pedir(srv.port, "GET", "/gen/pacote/filme-pb/efeito.json", remoto=True, cookie=CODIGO)  # baixa e abre
    for caminho in ("/gen/pacote/filme-pb/.sha256", "/gen/pacote/filme-pb/../filme-pb.zip",
                    "/gen/pacote/filme-pb/%2e%2e/%2e%2e/estado.json", "/gen/pacote/filme-pb/"):
        r, _ = pedir(srv.port, "GET", caminho, remoto=True, cookie=CODIGO)
        assert r.status == 400, caminho
    r, _ = pedir(srv.port, "GET", "/gen/pacote/nao-existe/efeito.json", remoto=True, cookie=CODIGO)
    assert r.status == 404
    assert pedir(srv.port, "GET", "/gen/pacote/filme-pb/efeito.json", remoto=True)[0].status == 403


def test_motor_de_efeitos_e_interface_sem_codigo(srv):
    r, corpo = pedir(srv.port, "GET", "/efeitos/motor.js", remoto=True)
    assert r.status == 200 and b"carregarEfeito" in corpo
    assert r.getheader("Content-Type").startswith("text/javascript")
    r, _ = pedir(srv.port, "GET", "/efeitos/vendor/three.module.min.js", remoto=True)
    assert r.status == 200
    r, _ = pedir(srv.port, "GET", "/efeitos/../preview/index.html", remoto=True)
    assert r.status == 400


def test_usar_pacote_desconhecido_ou_pedido_torto(srv, trilhas):
    r, corpo = _post_json(srv, "/api/pacotes/usar", {"id": "nao-existe"}, remoto=True, cookie=CODIGO)
    assert r.status == 404 and "desconhecido" in json.loads(corpo)["error"]
    r, corpo = _post_json(srv, "/api/pacotes/usar", ["não", "é", "objeto"], remoto=True, cookie=CODIGO)
    assert r.status == 400
