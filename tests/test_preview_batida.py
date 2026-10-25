"""A grade de batida pelo editor: o servidor analisa a música num processo à parte (um por vez), entrega
as batidas quando ficam prontas e conta a falha. A análise de verdade é trocada por uma falsa, que grava
uma grade no lugar certo: nada de torch aqui."""
from __future__ import annotations

import http.client
import json
import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import batida as bt  # noqa: E402
import preview_server as ps  # noqa: E402

FALSO = """
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import batida as bt
arquivo, edit, espera = Path(sys.argv[2]), Path(sys.argv[3]), float(sys.argv[4])
with open(edit / "vezes.txt", "a", encoding="utf-8") as f:
    f.write(arquivo.name + "\\n")
time.sleep(espera)
sha = bt.sha256_arquivo(arquivo)
destino = bt.caminho_grade(sha, bt.MODELO_PADRAO, edit)
destino.parent.mkdir(parents=True, exist_ok=True)
batidas = [round(0.5 * k + 0.25, 3) for k in range(8)]
destino.write_text(json.dumps({"versao": bt.VERSAO, "arquivo": arquivo.name, "sha256": sha, "duracao": 4.0,
                               "modelo": "falso", "bpm": 120.0, "confianca": "alta", "drop": None,
                               "batidas": batidas, "fortes": batidas[::4], "compassos": [], "acentos": []}),
                   encoding="utf-8")
"""


def _wav(caminho: Path, freq: float) -> None:
    sr = 8000
    t = np.arange(sr) / sr
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2").tobytes())


@pytest.fixture
def srv(tmp_path, monkeypatch):
    edit = tmp_path / "videos" / "edit"
    (edit / "midia").mkdir(parents=True)
    _wav(edit / "midia" / "musica.wav", 440)
    _wav(edit / "midia" / "outra música.wav", 660)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    falso = tmp_path / "batida_falsa.py"
    falso.write_text(FALSO, encoding="utf-8")
    espera = {"s": 0.3}
    monkeypatch.setattr(ps, "comando_batida", lambda arq, e: [sys.executable, "-I", str(falso), str(HELPERS),
                                                              str(arq), str(e), str(espera["s"])])
    monkeypatch.setattr(ps, "_batida_jobs", {})

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.allow_hosts = ()
    H.upload_dir = edit.parent.resolve()
    H.max_upload = 50_000
    H.bind_host = "0.0.0.0"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit, espera=espera)
    server.shutdown()
    server.server_close()
    for p in ps._batida_jobs.values():  # nenhum processo falso fica para trás
        p.wait(timeout=30)


def pedir(port, caminho, remoto=False):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30,
                                      source_address=("127.0.0.2", 0) if remoto else None)
    conn.request("GET", caminho)
    r = conn.getresponse()
    dados = r.read()
    conn.close()
    return r.status, json.loads(dados)


def esperar(port, caminho, prazo=30):
    fim = time.time() + prazo
    while time.time() < fim:
        status, j = pedir(port, caminho)
        if j.get("estado") in ("pronta", "falhou"):
            return status, j
        time.sleep(0.1)
    raise AssertionError(f"a grade não ficou pronta em {prazo} s")


def test_analisa_uma_vez_e_entrega_a_grade(srv):
    status, j = pedir(srv.port, "/api/batida?arquivo=midia/musica.wav")
    assert status == 202 and j["estado"] == "calculando"
    assert pedir(srv.port, "/api/batida?arquivo=midia/musica.wav")[1]["estado"] == "calculando"  # não dispara outra
    status, j = esperar(srv.port, "/api/batida?arquivo=midia/musica.wav")
    assert status == 200 and j["estado"] == "pronta" and j["bpm"] == 120.0 and j["confianca"] == "alta"
    assert j["batidas"][:3] == [0.25, 0.75, 1.25] and j["fortes"] == [0.25, 2.25]
    assert "acentos" not in j and "compassos" not in j  # o editor só precisa das batidas
    assert pedir(srv.port, "/api/batida?arquivo=midia/musica.wav")[0] == 200  # do cache, na hora
    assert (srv.edit / "vezes.txt").read_text(encoding="utf-8").split() == ["musica.wav"]


def test_nome_com_espaco_e_acento(srv):
    status, j = esperar(srv.port, "/api/batida?arquivo=midia/outra%20m%C3%BAsica.wav")
    assert status == 200 and j["estado"] == "pronta"


@pytest.mark.parametrize("arquivo,codigo", [
    ("edl.json", 400),                 # fora de midia/
    ("midia/foto.png", 400),           # não é áudio
    ("midia/nao-existe.mp3", 404),
    ("midia/../../fora.mp3", 404),     # a trava de pasta
    ("", 400),
])
def test_so_audio_de_midia(srv, arquivo, codigo):
    assert pedir(srv.port, f"/api/batida?arquivo={arquivo}")[0] == codigo


def test_analise_que_falha_aparece_com_o_motivo(srv, monkeypatch):
    monkeypatch.setattr(ps, "comando_batida", lambda arq, e: [  # -X utf8, como o comando de verdade
        sys.executable, "-X", "utf8", "-c", "import sys; sys.exit('batida: o ffmpeg não conseguiu ler musica.wav: teste')"])
    status, j = esperar(srv.port, "/api/batida?arquivo=midia/musica.wav")
    assert status == 500 and j == {"estado": "falhou", "erro": "o ffmpeg não conseguiu ler musica.wav: teste"}


def test_uma_analise_por_vez(srv):
    srv.espera["s"] = 1.5
    assert pedir(srv.port, "/api/batida?arquivo=midia/musica.wav")[1]["estado"] == "calculando"
    status, j = pedir(srv.port, "/api/batida?arquivo=midia/outra%20m%C3%BAsica.wav")
    assert status == 202 and j["estado"] == "na fila"
    assert esperar(srv.port, "/api/batida?arquivo=midia/musica.wav")[1]["estado"] == "pronta"
    assert esperar(srv.port, "/api/batida?arquivo=midia/outra%20m%C3%BAsica.wav")[1]["estado"] == "pronta"


def test_celular_sem_codigo_nao_ve(srv):
    assert pedir(srv.port, "/api/batida?arquivo=midia/musica.wav", remoto=True)[0] == 403
