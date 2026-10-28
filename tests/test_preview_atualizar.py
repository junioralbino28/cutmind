"""A atualização pelo editor: o servidor diz se há versão nova sem esperar a rede, lança a atualização num
processo solto (trocado por um falso aqui; o de verdade está em test_atualizar.py), espera o trabalho do
projeto acabar em vez de recusar, desliga quando a versão nova pede reinício e guarda o interruptor."""
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

NOVA = {"nova": True, "atual": "0.2.0", "versao": "0.3.0", "notas": {"pt": ["x"], "en": ["x"]}, "muda": ["editor"],
        "reiniciar": False, "agente": False, "remotion": False}
FALSO = """
import sys
sys.path.insert(0, sys.argv[1])
import trabalhos as tb
andamento, marca = sys.argv[2], sys.argv[3]
open(marca, 'w').write('lancado')
tb.escritor(andamento, 'atualizar')('pronto', 'Atualizado', 1.0, versao='0.3.0', agente=False, reiniciou=False)
"""


@pytest.fixture
def srv(tmp_path, monkeypatch):
    edit = tmp_path / "videos" / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    casa = tmp_path / "casa"
    monkeypatch.setenv("CUTMIND_HOME", str(casa))
    monkeypatch.setattr(ps, "ATUALIZACAO", {"resultado": None, "pedido": False})
    monkeypatch.setattr(ps, "copia_de_desenvolvimento", lambda: False)
    monkeypatch.setattr(ps.atu, "procurar", lambda *a, **k: dict(NOVA))
    falso = tmp_path / "atualizar_falso.py"
    falso.write_text(FALSO, encoding="utf-8")
    marca = tmp_path / "lancado.txt"
    monkeypatch.setattr(ps, "comando_atualizar", lambda andamento, servidor: [
        sys.executable, "-I", str(falso), str(HELPERS), str(andamento), str(marca)])

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.allow_hosts = ()
    H.upload_dir = edit.parent.resolve()
    H.max_upload = 50_000
    H.bind_host = "127.0.0.1"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit, casa=casa, marca=marca, thread=t, server=server,
                          handler=H)
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


def esperar(cond, prazo=10.0):
    fim = time.time() + prazo
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_antes_da_procura_diz_que_esta_procurando(srv):
    r, d = pedir(srv.port, "GET", "/api/atualizacao")
    assert r.status == 200 and d == {"nova": False, "procurando": True, "ligado": True}


def test_mostra_o_que_a_procura_achou(srv):
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    d = pedir(srv.port, "GET", "/api/atualizacao")[1]
    assert d["nova"] and d["versao"] == "0.3.0" and d["reiniciar"] is False and d["ligado"] is True


def test_depois_de_atualizar_sem_reiniciar_nao_oferece_a_mesma_versao(srv, tmp_path, monkeypatch):
    """O servidor é o mesmo depois de uma atualização só do editor: a procura de antes dizia 0.3.0, e a
    0.3.0 já está instalada. A página recarrega e a faixa não pode voltar."""
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    instalada = tmp_path / "instalada"
    instalada.mkdir()
    ps.atu.vs._escrever(instalada, {"versao": "0.3.0", "notas": {}, "arquivos": {}})
    monkeypatch.setattr(ps, "SKILL", instalada)
    d = pedir(srv.port, "GET", "/api/atualizacao")[1]
    assert d["nova"] is False and d["atual"] == "0.3.0"
    assert pedir(srv.port, "POST", "/api/atualizar", {})[0].status == 409 and not srv.marca.exists()


def test_o_andamento_antigo_nao_vale_enquanto_o_clique_espera(srv):
    """O andamento.json da atualização anterior diz "pronto"; a página que espera um trabalho acabar não
    pode ler isso e recarregar como se a nova tivesse sido instalada."""
    pasta = srv.casa / "atualizacao"
    pasta.mkdir(parents=True)
    ps.tb.escritor(str(pasta / "andamento.json"), "atualizar")("pronto", "Atualizado", 1.0, versao="0.2.0")
    assert pedir(srv.port, "GET", "/api/atualizacao/andamento")[1]["etapa"] == "pronto"
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    assert ps.tb.iniciar(srv.edit, "gerar", [sys.executable, "-c", "import time; time.sleep(1.5)"])
    assert pedir(srv.port, "POST", "/api/atualizar", {})[1]["esperando"] == "trabalho"
    assert pedir(srv.port, "GET", "/api/atualizacao/andamento")[1]["etapa"] is None


def test_recusa_sem_versao_nova_e_na_copia_de_desenvolvimento(srv, monkeypatch):
    ps.ATUALIZACAO["resultado"] = {"nova": False}
    r, d = pedir(srv.port, "POST", "/api/atualizar", {})
    assert r.status == 409 and "versão nova" in d["error"]
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    monkeypatch.setattr(ps, "copia_de_desenvolvimento", lambda: True)
    r, d = pedir(srv.port, "POST", "/api/atualizar", {})
    assert r.status == 409 and "git" in d["error"]
    assert not srv.marca.exists()


def test_atualiza_sem_reiniciar_e_o_editor_continua(srv):
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    r, d = pedir(srv.port, "POST", "/api/atualizar", {})
    assert r.status == 200 and d == {"ok": True, "reiniciar": False, "versao": "0.3.0"}
    assert esperar(lambda: pedir(srv.port, "GET", "/api/atualizacao/andamento")[1].get("etapa") == "pronto")
    assert srv.marca.exists() and srv.thread.is_alive()
    linha = json.loads((srv.casa / "atualizacao" / "servidor.json").read_text(encoding="utf-8"))
    assert linha["argv"][linha["argv"].index("--root") + 1] == str(srv.edit.resolve())
    assert linha["pid"] > 0 and linha["script"].endswith("preview_server.py")


def test_versao_que_pede_reinicio_desliga_o_editor(srv):
    ps.ATUALIZACAO["resultado"] = {**NOVA, "reiniciar": True, "muda": ["servidor"]}
    r, d = pedir(srv.port, "POST", "/api/atualizar", {})
    assert r.status == 200 and d["reiniciar"] is True
    assert esperar(lambda: not srv.thread.is_alive(), 5.0)   # o atualizador religa depois de instalar


def test_com_trabalho_rodando_espera_e_comeca_quando_acaba(srv):
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    assert ps.tb.iniciar(srv.edit, "gerar", [sys.executable, "-c", "import time; time.sleep(1.5)"])
    r, d = pedir(srv.port, "POST", "/api/atualizar", {})
    assert r.status == 200 and d["esperando"] == "trabalho"
    assert pedir(srv.port, "GET", "/api/atualizacao")[1]["esperando"] == "trabalho"
    assert not srv.marca.exists()
    threading.Thread(target=ps.vigiar_atualizacao, args=(srv.server, srv.handler, 0.1), daemon=True).start()
    assert esperar(srv.marca.exists, 10.0)                   # o trabalho acabou: a atualização começou
    assert ps.ATUALIZACAO["pedido"] is False


def test_com_o_agente_trabalhando_tambem_espera(srv):
    ps.ATUALIZACAO["resultado"] = dict(NOVA)
    (srv.edit / "state.json").write_text(json.dumps({"phase": 1, "agente": {"trabalhando": True, "desde": time.time()}}),
                                         encoding="utf-8")
    d = pedir(srv.port, "POST", "/api/atualizar", {})[1]
    assert d["esperando"] == "agente" and not srv.marca.exists()


def test_o_interruptor_grava_e_procura_de_novo(srv, monkeypatch):
    chamadas = []
    monkeypatch.setattr(ps.atu, "procurar", lambda *a, **k: chamadas.append(k) or {"nova": False, "motivo": "desligado"})
    r, d = pedir(srv.port, "POST", "/api/atualizacao/config", {"procurar": False})
    assert r.status == 200 and d == {"ok": True, "ligado": False}
    cfg = json.loads((srv.casa / "config.json").read_text(encoding="utf-8"))
    assert cfg["procurarAtualizacao"] is False
    assert esperar(lambda: chamadas and chamadas[-1].get("forcar") is True)
    assert pedir(srv.port, "GET", "/api/atualizacao")[1]["ligado"] is False
    assert pedir(srv.port, "POST", "/api/atualizacao/config", {"procurar": "sim"})[0].status == 400


def test_a_procura_roda_ao_subir_sem_prender_a_pagina(srv):
    threading.Thread(target=ps.vigiar_atualizacao, args=(srv.server, srv.handler, 0.1), daemon=True).start()
    assert esperar(lambda: pedir(srv.port, "GET", "/api/atualizacao")[1].get("versao") == "0.3.0")


# ---- o "Gostou do CutMind?" (estrela, erro e sugestão no GitHub)

def test_sobre_da_so_a_versao_e_o_sistema(srv):
    """O formulário do GitHub abre com a versão e o sistema; nunca o nome da máquina ou da pessoa."""
    import getpass
    import socket
    r, d = pedir(srv.port, "GET", "/api/sobre")
    assert r.status == 200 and set(d) == {"versao", "sistema", "repo"}
    assert d["versao"] == ps.atu.vs.ler(ps.SKILL)["versao"] and d["repo"] == "https://github.com/junioralbino28/cutmind"
    assert d["sistema"] and socket.gethostname().lower() not in d["sistema"].lower()
    assert getpass.getuser().lower() not in d["sistema"].lower()


# ---- a DLL presa logo depois de instalar (o conserto do Papory 0.1.9)

def test_espera_a_dll_presa_e_so_ela():
    tentativas = []

    def presa_duas_vezes():
        tentativas.append(1)
        if len(tentativas) <= 2:
            raise ImportError("DLL load failed while importing _multiarray_umath: o arquivo já está sendo usado")

    assert ps.esperar_dlls(presa_duas_vezes, prazo=5, pausa=0.01) == 2

    def outro_erro():
        raise ImportError("No module named numpy")

    with pytest.raises(ImportError, match="No module"):
        ps.esperar_dlls(outro_erro, prazo=5, pausa=0.01)

    def sempre_presa():
        raise ImportError("x") from OSError("DLL load failed while importing _imaging")

    inicio = time.monotonic()
    with pytest.raises(ImportError):
        ps.esperar_dlls(sempre_presa, prazo=0.2, pausa=0.01)
    assert time.monotonic() - inicio < 2
