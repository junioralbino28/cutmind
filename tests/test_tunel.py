"""O editor no celular de qualquer lugar: o túnel (tunel.py), a porta do túnel no servidor e o envio em pedaços.

A porta do túnel é o ponto de segurança: pelo túnel todo pedido da internet chega como 127.0.0.1, e na porta
do editor 127.0.0.1 entra sem código. Na do túnel o código é sempre cobrado.
"""
from __future__ import annotations

import hashlib
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
import tunel as tn  # noqa: E402

CODIGO = "codigo-de-teste-0123456789"          # o do projeto (Wi-Fi)
CODIGO_TUNEL = "codigo-do-tunel-abcdefghijk"     # o da porta do túnel (tunel.py)


@pytest.fixture
def srv(tmp_path):
    """O editor com as duas portas, como o main() abre com --tunel-port."""
    videos = tmp_path / "videos"
    edit = videos / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1}), encoding="utf-8")

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = CODIGO
    H.upload_dir = videos.resolve()
    H.max_upload = 50_000
    H.bind_host = "127.0.0.1"
    H.arquivo_codigo_tunel = tmp_path / "casa" / "tunel" / "codigo"
    H.arquivo_codigo_tunel.parent.mkdir(parents=True)
    H.arquivo_codigo_tunel.write_bytes(CODIGO_TUNEL.encode())
    editor = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    tunel = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    tunel.remoto = True
    H.porta_tunel = tunel.server_address[1]
    H.servidor_principal = editor
    for s in (editor, tunel):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    ps._ENVIOS.clear()
    yield SimpleNamespace(editor=editor.server_address[1], tunel=tunel.server_address[1], edit=edit, videos=videos,
                          H=H, servidor_editor=editor)
    for s in (editor, tunel):
        s.shutdown()
        s.server_close()
    ps._ENVIOS.clear()


def pedir(port, metodo, caminho, *, cookie=None, host=None, corpo=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
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


# ---- a porta do túnel

def test_pelo_tunel_127_0_0_1_nao_entra_sem_o_codigo(srv):
    for caminho in ("/api/state", "/media/state.json", "/gen/frame?t=1"):
        assert pedir(srv.tunel, "GET", caminho)[0].status == 403, caminho
    assert pedir(srv.tunel, "GET", "/api/state", cookie=CODIGO_TUNEL)[0].status == 200
    assert pedir(srv.tunel, "GET", "/api/state", cookie="codigo-errado-000000000")[0].status == 403


def test_o_codigo_do_wifi_nao_abre_o_tunel(srv):
    """Um QR do Wi-Fi que vazou não abre o editor pela internet."""
    assert pedir(srv.tunel, "GET", "/api/state", cookie=CODIGO)[0].status == 403
    r, _ = pedir(srv.tunel, "GET", f"/c?t={CODIGO}", host="abc.trycloudflare.com")
    assert r.status == 403


def test_tunel_novo_troca_o_codigo_sem_reiniciar_o_editor(srv):
    assert pedir(srv.tunel, "GET", "/api/state", cookie=CODIGO_TUNEL)[0].status == 200
    novo = "codigo-do-tunel-novo-zyxwvut"
    srv.H.arquivo_codigo_tunel.write_bytes(novo.encode())
    os.utime(srv.H.arquivo_codigo_tunel, ns=(1, 2_000_000_000_000_000_000))   # data nova garantida
    assert pedir(srv.tunel, "GET", "/api/state", cookie=CODIGO_TUNEL)[0].status == 403
    assert pedir(srv.tunel, "GET", "/api/state", cookie=novo)[0].status == 200


def test_a_porta_do_editor_continua_igual(srv):
    assert pedir(srv.editor, "GET", "/api/state")[0].status == 200


def test_o_nome_do_tunel_so_vale_na_porta_dele(srv):
    assert pedir(srv.tunel, "GET", "/", host="abc-def.trycloudflare.com")[0].status == 200
    assert pedir(srv.tunel, "GET", "/", host="evil.example")[0].status == 403
    assert pedir(srv.tunel, "GET", "/", host="trycloudflare.com.evil.example")[0].status == 403
    assert pedir(srv.editor, "GET", "/", host="abc-def.trycloudflare.com")[0].status == 403


def test_o_cookie_do_tunel_e_secure(srv):
    r, _ = pedir(srv.tunel, "GET", f"/c?t={CODIGO_TUNEL}", host="abc.trycloudflare.com")
    assert r.status == 303 and "Secure" in r.getheader("Set-Cookie") and CODIGO_TUNEL in r.getheader("Set-Cookie")
    r, _ = pedir(srv.editor, "GET", f"/c?t={CODIGO}")
    assert "Secure" not in r.getheader("Set-Cookie")


def test_o_link_do_tunel_so_aparece_no_computador(srv, monkeypatch):
    monkeypatch.setattr(ps.tn, "estado", lambda casa: {"url": "https://abc.trycloudflare.com", "pid": 1,
                                                       "porta": srv.tunel})
    d = json.loads(pedir(srv.editor, "GET", "/api/celular")[1])
    assert d["enabled"] and d["urls"][0]["url"] == f"https://abc.trycloudflare.com/c?t={CODIGO_TUNEL}"
    assert pedir(srv.tunel, "GET", "/api/celular", cookie=CODIGO_TUNEL)[0].status == 403


def test_o_tunel_de_outro_editor_nao_aparece(srv, monkeypatch):
    monkeypatch.setattr(ps.tn, "estado", lambda casa: {"url": "https://abc.trycloudflare.com", "pid": 1,
                                                       "porta": srv.tunel + 1000})
    d = json.loads(pedir(srv.editor, "GET", "/api/celular")[1])
    assert not d["enabled"] and d["urls"] == []


def test_atualizar_pelo_celular_fecha_o_editor_e_nao_a_porta_do_tunel(srv, monkeypatch):
    fechados = []
    monkeypatch.setattr(ps, "resultado_atual", lambda: {"nova": True, "reiniciar": True, "versao": "9.9.9"})
    monkeypatch.setattr(ps, "copia_de_desenvolvimento", lambda: False)
    monkeypatch.setattr(ps, "_esperando", lambda root: None)
    monkeypatch.setattr(ps, "comecar_atualizacao", lambda servidor, root, r: fechados.append(servidor))
    r, corpo = pedir(srv.tunel, "POST", "/api/atualizar", cookie=CODIGO_TUNEL, corpo=b"{}")
    assert r.status == 200, corpo
    assert fechados == [srv.servidor_editor]


# ---- o envio em pedaços

def _pedaco(srv, dados, inicio, total, envio_id=None, nome="video.mp4", porta=None):
    q = f"/api/upload?name={nome}&total={total}&inicio={inicio}" + (f"&id={envio_id}" if envio_id else "")
    r, corpo = pedir(porta or srv.editor, "POST", q, corpo=dados)
    return r.status, json.loads(corpo or b"{}")


def test_o_arquivo_chega_inteiro_em_pedacos(srv):
    dados = bytes(range(256)) * 40   # 10.240 bytes
    st, d = _pedaco(srv, dados[:4000], 0, len(dados))
    assert st == 200 and d["recebido"] == 4000 and d["id"]
    st, d = _pedaco(srv, dados[4000:8000], 4000, len(dados), d["id"])
    assert st == 200 and d["recebido"] == 8000
    st, d = _pedaco(srv, dados[8000:], 8000, len(dados), d["id"])
    assert st == 200 and d["file"] == "video.mp4" and "id" not in d
    final = srv.videos / "video.mp4"
    assert hashlib.sha256(final.read_bytes()).hexdigest() == hashlib.sha256(dados).hexdigest()
    aviso = json.loads((srv.edit / "preview_upload.json").read_text(encoding="utf-8"))
    assert aviso["files"][0]["file"] == "video.mp4" and not list(srv.videos.glob(".*.parte"))


def test_pedaco_fora_de_ordem_diz_de_onde_continuar(srv):
    _, d = _pedaco(srv, b"a" * 1000, 0, 3000)
    st, r = _pedaco(srv, b"b" * 1000, 2000, 3000, d["id"])
    assert st == 409 and r["recebido"] == 1000
    r, corpo = pedir(srv.editor, "GET", f"/api/upload?id={d['id']}")
    assert r.status == 200 and json.loads(corpo) == {"recebido": 1000, "total": 3000}
    st, r = _pedaco(srv, b"b" * 1000, 1000, 3000, d["id"])
    assert st == 200 and r["recebido"] == 2000


def test_envio_que_nao_existe(srv):
    st, d = _pedaco(srv, b"x" * 10, 10, 20, "id-inventado")
    assert st == 404 and "de novo" in d["error"]
    assert pedir(srv.editor, "GET", "/api/upload?id=id-inventado")[0].status == 404


def test_pedaco_maior_que_o_arquivo_e_recusado(srv):
    """Sem isso, `total=10` com 32 MB de corpo furava o limite de envio."""
    st, d = _pedaco(srv, b"x" * 1000, 0, 10)
    assert st == 400 and not list(srv.videos.glob("*.mp4")) and not list(srv.videos.glob(".*.parte"))


def test_cancelar_apaga_o_pedaco_recebido(srv):
    _, d = _pedaco(srv, b"a" * 1000, 0, 3000)
    parte = ps._ENVIOS[d["id"]]["part"]
    assert parte.exists()
    r, _ = pedir(srv.editor, "POST", f"/api/upload/cancelar?id={d['id']}")
    assert r.status == 200 and not parte.exists() and d["id"] not in ps._ENVIOS
    st, _ = _pedaco(srv, b"b" * 1000, 1000, 3000, d["id"])
    assert st == 404


def test_parte_esquecida_no_disco_e_apagada(srv):
    """A lista de envios só vive na memória: o .parte de um servidor que fechou no meio fica no disco."""
    velha = srv.videos / ".esquecido.mp4.parte"
    nova = srv.videos / ".agora.mp4.parte"
    velha.write_bytes(b"x" * 100)
    nova.write_bytes(b"x" * 100)
    antes = velha.stat().st_mtime - ps.ENVIO_LARGADO_S - 60
    os.utime(velha, (antes, antes))
    ps._limpar_envios_largados(pastas=(srv.videos,))
    assert not velha.exists() and nova.exists()


def test_o_limite_vale_para_o_total(srv):
    st, d = _pedaco(srv, b"x" * 100, 0, 60_000)
    assert st == 413 and not list(srv.videos.glob("*.mp4")) and not ps._ENVIOS


def test_pelo_tunel_o_envio_precisa_do_codigo(srv):
    st, _ = _pedaco(srv, b"x" * 10, 0, 10, porta=srv.tunel)
    assert st == 403 and not list(srv.videos.glob("*.mp4"))


def test_envio_largado_e_apagado(srv):
    _, d = _pedaco(srv, b"a" * 1000, 0, 3000)
    parte = ps._ENVIOS[d["id"]]["part"]
    assert parte.exists()
    # o servidor responde "recebido" antes de soltar a trava do envio (o finally vem depois do _json); com a
    # máquina ocupada a limpeza achava o envio ainda travado e o pulava, de propósito (não apaga envio em andamento)
    for _ in range(100):
        if not ps._ENVIOS[d["id"]]["trava"].locked():
            break
        time.sleep(0.02)
    ps._limpar_envios_largados(agora=time.time() + ps.ENVIO_LARGADO_S + 10)
    assert not parte.exists() and d["id"] not in ps._ENVIOS


# ---- tunel.py

def test_acha_o_link_no_registro_do_cloudflared(tmp_path):
    log = tmp_path / "tunel.log"
    log.write_text("INF Requesting new quick Tunnel on trycloudflare.com...\n"
                   "INF |  https://pale-river-sound-art.trycloudflare.com                    |\n", encoding="utf-8")

    class Vivo:
        def poll(self):
            return None

    assert tn._url_no_log(log, Vivo(), 2) == "https://pale-river-sound-art.trycloudflare.com"


def test_o_cloudflared_que_fecha_sem_link_diz_onde_olhar(tmp_path):
    log = tmp_path / "tunel.log"
    log.write_text("ERR failed to connect\n", encoding="utf-8")

    class Morto:
        def poll(self):
            return 1

    with pytest.raises(tn.ErroTunel, match="fechou"):
        tn._url_no_log(log, Morto(), 2)


def test_binario_confere_o_hash_e_nao_baixa_de_novo(tmp_path, monkeypatch):
    certo = b"programa de mentira"
    monkeypatch.setattr(tn, "_arquivo_do_sistema",
                        lambda: ("cloudflared-teste", hashlib.sha256(certo).hexdigest(), len(certo)))
    baixados = []

    def baixar(url, destino):
        baixados.append(url)
        destino.write_bytes(certo)

    exe = tn.binario(tmp_path, baixar)
    assert exe.read_bytes() == certo and baixados == [tn.BASE + "cloudflared-teste"]
    assert tn.binario(tmp_path, baixar) == exe and len(baixados) == 1


def test_binario_trocado_no_caminho_e_recusado(tmp_path, monkeypatch):
    monkeypatch.setattr(tn, "_arquivo_do_sistema", lambda: ("cloudflared-teste", "0" * 64, 5))
    with pytest.raises(tn.ErroTunel, match="não bate"):
        tn.binario(tmp_path, lambda url, destino: destino.write_bytes(b"outro"))
    pasta = tmp_path / "tunel" / "bin"
    assert not any(pasta.glob("cloudflared*"))


def test_tunel_morto_nao_conta(tmp_path, monkeypatch):
    ps.atu._gravar_json(tmp_path / "tunel" / "tunel.json", {"url": "https://x.trycloudflare.com", "pid": 4242,
                                                           "porta": 4821})
    monkeypatch.setattr(tn.atu, "_vivo", lambda pid: False)
    assert tn.estado(tmp_path) is None


# ---- o vigia: o túnel não pode sobrar apontando para uma porta que não é a do editor

def test_quem_atende_a_porta(srv):
    assert tn._quem_atende(srv.tunel) == "editor"
    assert tn._quem_atende(srv.editor) == "outro"    # a porta comum recusa o nome do túnel
    livre = ps.ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
    porta = livre.server_address[1]
    livre.server_close()
    assert tn._quem_atende(porta) == "ninguem"


def _vigia(tmp_path, monkeypatch, respostas):
    """Roda o vigia com um relógio de mentira: cada volta avança 5 s e responde o próximo da lista."""
    ps.atu._gravar_json(tmp_path / "tunel" / "tunel.json", {"url": "https://x.trycloudflare.com", "pid": 77,
                                                           "porta": 4821})
    monkeypatch.setattr(tn, "_e_o_tunel", lambda pid, exe=None: True)
    fila = list(respostas)
    monkeypatch.setattr(tn, "_quem_atende", lambda porta: fila.pop(0) if fila else "editor")
    desligou = []
    monkeypatch.setattr(tn, "desligar", lambda casa: desligou.append(casa))
    relogio = [1000.0]
    voltas = [0]

    def dormir(s):
        relogio[0] += s
        voltas[0] += 1
        if voltas[0] > 500:
            raise AssertionError("o vigia não parou")
        if not fila:
            (tmp_path / "tunel" / "tunel.json").unlink(missing_ok=True)   # acaba o teste: o túnel sumiu

    motivo = tn.vigiar(4821, 77, tmp_path, graca=60, intervalo=5, agora=lambda: relogio[0], dormir=dormir)
    return motivo, desligou


def test_outro_programa_na_porta_desliga_na_hora(tmp_path, monkeypatch):
    motivo, desligou = _vigia(tmp_path, monkeypatch, ["editor", "editor", "outro"])
    assert desligou == [tmp_path] and "outro programa" in motivo


def test_editor_fechado_desliga_depois_da_carencia(tmp_path, monkeypatch):
    motivo, desligou = _vigia(tmp_path, monkeypatch, ["editor"] + ["ninguem"] * 20)
    assert desligou == [tmp_path] and motivo == "o editor fechou"


def test_editor_que_volta_a_tempo_mantem_o_link(tmp_path, monkeypatch):
    motivo, desligou = _vigia(tmp_path, monkeypatch, ["ninguem"] * 10 + ["editor"] + ["ninguem"] * 10)
    assert desligou == [] and motivo == "o túnel já não está ligado"


def test_desligar_nao_derruba_o_que_nao_e_o_tunel(tmp_path):
    """Depois de reiniciar o computador, o PID gravado pode ser de outro programa."""
    outro = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        ps.atu._gravar_json(tmp_path / "tunel" / "tunel.json", {"url": "https://x.trycloudflare.com",
                                                               "pid": outro.pid, "porta": 4821,
                                                               "exe": str(tmp_path / "tunel" / "bin" / "x.exe")})
        assert tn.estado(tmp_path) is None
        tn.desligar(tmp_path)
        assert outro.poll() is None and not (tmp_path / "tunel" / "tunel.json").exists()
    finally:
        outro.kill()
        outro.wait()


@pytest.mark.skipif(os.name != "nt", reason="cópia de um programa do Windows")
def test_desligar_nao_derruba_um_cloudflared_da_pessoa(tmp_path):
    """Mesmo com "cloudflared" no nome: só o programa da pasta do CutMind conta como o túnel."""
    dela = tmp_path / "cloudflared-da-pessoa.exe"
    shutil.copy(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "PING.EXE", dela)
    proc = subprocess.Popen([str(dela), "-n", "60", "127.0.0.1"], stdout=subprocess.DEVNULL)
    try:
        nosso = tmp_path / "tunel" / "bin" / "cloudflared.exe"
        ps.atu._gravar_json(tmp_path / "tunel" / "tunel.json", {"url": "https://x.trycloudflare.com",
                                                               "pid": proc.pid, "porta": 4821, "exe": str(nosso)})
        assert tn.estado(tmp_path) is None
        tn.desligar(tmp_path)
        assert proc.poll() is None
        assert tn._e_o_tunel(proc.pid, str(dela))   # o detector reconhece o programa pelo caminho
    finally:
        proc.kill()
        proc.wait()


def test_codigo_do_tunel_e_guardado_e_trocado_num_tunel_novo(tmp_path):
    a = tn.codigo(tmp_path)
    assert len(a) >= 20 and tn.codigo(tmp_path) == a
    b = tn.codigo(tmp_path, novo=True)
    assert b != a and tn.codigo(tmp_path) == b
    assert tn.arquivo_codigo(tmp_path).read_text(encoding="utf-8") == b
