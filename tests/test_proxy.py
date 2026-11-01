"""A cópia leve de cada gravação inteira (helpers/proxy.py): o editor mostra e toca dela o que o
cut.mp4 não tem. O que importa é que ela esteja no MESMO relógio da gravação (um flash da gravação
cai no mesmo instante da cópia), que a busca seja imediata (quadro-chave a cada 15) e que o som
chegue no nível do corte."""
from __future__ import annotations

import http.client
import json
import re
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
import proxy  # noqa: E402

FPS = 30
FLASHES = [0.5, 1.4, 2.3]


@pytest.fixture(scope="module")
def gravacao(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("prx")
    p = pasta / "IMG_0001.MOV"
    janelas = "+".join(f"between(t,{t:.2f},{t + 0.1:.2f})" for t in FLASHES)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c=black:s=360x640:r={FPS}:d=3",
                    "-f", "lavfi", "-i", f"aevalsrc='0.05*sin(2*PI*440*t)':s=48000:d=3",
                    "-filter_complex", f"[0:v]geq=lum='255*({janelas.replace('(t,', '(T,')})':cb=128:cr=128[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "60",
                    "-c:a", "aac", "-f", "mov", str(p)], check=True)
    return p


def _projeto(tmp_path: Path, gravacao: Path) -> Path:
    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "edl.json").write_text(json.dumps({"sources": {"A": str(gravacao)}, "ranges": []}), encoding="utf-8")
    return edit


def _flashes(video: Path) -> list[float]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=8:8,format=gray",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    luz = [sum(raw[i:i + 64]) / 64 for i in range(0, len(raw), 64)]
    return [i / FPS for i in range(1, len(luz)) if luz[i] >= 128 > luz[i - 1]]


def test_a_copia_fica_no_relogio_da_gravacao_e_busca_rapido(gravacao, tmp_path):
    edit = _projeto(tmp_path, gravacao)
    assert proxy.estado(edit)["fontes"] == {"A": False}
    assert proxy.gerar_todas(edit) == 0
    p = proxy.pronto(edit, gravacao)
    assert p and p.parent == edit / proxy.PASTA and proxy.estado(edit)["fontes"] == {"A": True}
    assert not list(p.parent.glob("*.parte.mp4")) and not list(p.parent.glob("*.trava"))

    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                      "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (540, 960)  # em pé: o lado menor vira 540
    assert abs(float(info["format"]["duration"]) - 3.0) < 0.05
    assert _flashes(p) == pytest.approx(_flashes(gravacao), abs=1 / FPS + 1e-6)  # o mesmo relógio

    chaves = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                             "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(p)],
                            capture_output=True, text=True, check=True).stdout.split()
    tempos = [float(x.strip(",")) for x in chaves]
    assert max(b - a for a, b in zip(tempos, tempos[1:])) <= proxy.GOP / FPS + 1e-3

    # o som chega no nível do corte (-14 LUFS), não no da gravação (bem mais baixo)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-vn", "-af", "loudnorm=print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    nivel = float(re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', r.stderr).group(1))
    assert abs(nivel - proxy.ALVO_LUFS) < 1.5, nivel


def test_a_prioridade_vem_primeiro_e_a_trava_de_outro_processo_e_respeitada(gravacao, tmp_path):
    edit = _projeto(tmp_path, gravacao)
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    edl["sources"]["B"] = str(gravacao)  # a mesma gravação com outro nome: a mesma cópia
    edl["sources"]["foto"] = str(tmp_path / "nao-existe.jpg")
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    assert list(proxy.fontes(edit)) == ["A", "B"]  # o que não existe fica de fora
    (edit / proxy.PASTA).mkdir(parents=True)
    (edit / proxy.PASTA / "prioridade.txt").write_text("B", encoding="utf-8")
    assert proxy._proxima(edit, set())[0] == "B"
    trava = proxy._travar(proxy.caminho(edit, gravacao))
    assert trava and proxy._travar(proxy.caminho(edit, gravacao)) is None  # um processo por cópia
    trava.unlink()


def test_hdr_vira_rec709_como_no_corte(gravacao, monkeypatch):
    monkeypatch.setattr(proxy.render, "is_hdr_source", lambda f: True)
    assert proxy.render.TONEMAP_CHAIN in proxy.filtro_video(gravacao)
    monkeypatch.setattr(proxy.render, "is_hdr_source", lambda f: False)
    monkeypatch.setattr(proxy.render, "wide_gamut_chain", lambda f: "")
    assert proxy.filtro_video(gravacao).endswith("format=yuv420p") and "tonemap" not in proxy.filtro_video(gravacao)


# ---------- pelo servidor do editor ----------
@pytest.fixture
def srv(gravacao, tmp_path):
    edit = _projeto(tmp_path, gravacao)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}), encoding="utf-8")
    pedidos_de_quadro = []

    class H(ps.Handler):
        def _quadro_jpg(self, path, t, h, guardar=False):
            pedidos_de_quadro.append(Path(path))
            return super()._quadro_jpg(path, t, h, guardar)

    H.root = edit.resolve()
    H.token = None
    H.allow_hosts = ()
    H.bind_host = "127.0.0.1"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=server.server_address[1], edit=edit, quadros=pedidos_de_quadro)
    server.shutdown()
    server.server_close()
    p = ps._proxy_jobs.get(str(edit.resolve()))
    if p is not None:
        p.wait(timeout=60)


def _get(port, caminho, cabecalhos=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    conn.request("GET", caminho, headers=cabecalhos or {})
    r = conn.getresponse()
    corpo = r.read()
    conn.close()
    return r, corpo


def test_o_servidor_faz_entrega_e_usa_a_copia(srv, gravacao):
    r, corpo = _get(srv.port, "/api/proxies?primeiro=A")
    st = json.loads(corpo)
    assert r.status == 200 and st["fontes"] == {"A": False} and st["vivo"] is True
    assert (srv.edit / proxy.PASTA / "prioridade.txt").read_text(encoding="utf-8") == "A"
    assert _get(srv.port, "/gen/proxy?src=A")[0].status == 404  # ainda não: o editor espera

    fim = time.time() + 60
    while time.time() < fim and not json.loads(_get(srv.port, "/api/proxies")[1])["fontes"]["A"]:
        time.sleep(0.2)
    r, corpo = _get(srv.port, "/gen/proxy?src=A")
    assert r.status == 200 and r.getheader("Content-Type") == "video/mp4" and corpo[4:8] == b"ftyp"
    r, corpo = _get(srv.port, "/gen/proxy?src=A", {"Range": "bytes=0-99"})
    assert r.status == 206 and len(corpo) == 100  # o <video> busca por pedaços

    r, corpo = _get(srv.port, "/gen/frame?src=A&t=1.45&h=240")
    assert r.status == 200 and corpo[:2] == b"\xff\xd8"
    assert srv.quadros[-1] == proxy.pronto(srv.edit, gravacao)  # o quadro da alça sai da cópia


def test_nome_que_o_edl_nao_da_nao_entra(srv):
    assert _get(srv.port, "/gen/proxy?src=..%2F..%2Fedl.json")[0].status == 404
    _get(srv.port, "/api/proxies?primeiro=..%2Fqualquer")
    pr = srv.edit / proxy.PASTA / "prioridade.txt"
    assert not pr.exists() or pr.read_text(encoding="utf-8") != "../qualquer"


# ---------- no editor: a tomada que passa do que o corte tem toca da cópia ----------
PREVIEW = Path(__file__).resolve().parents[1] / "assets" / "preview"
sem_node = pytest.mark.skipif(not shutil.which("node"), reason="sem Node")


def _trecho(js: str, inicio: str, fim: str = "\n") -> str:
    i = js.index(inicio)
    return js[i:js.index(fim, i) + len(fim)]


def _editor(codigo: str, S: dict, prontos: dict):
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    partes = [_trecho(js, "const pedsD = "), _trecho(js, "const comCurva = "),
              _trecho(js, "function foraDoCorte(", "\n}\n"), _trecho(js, "const usaOrigem = "),
              _trecho(js, "const naGravacao = "), _trecho(js, "const noRascunho = ")]
    script = (f"const Tempo = require({json.dumps(str(PREVIEW / 'tempo.js'))});\n"
              f"const S = {json.dumps(S)};\nconst ORIG = {{ prontos: {json.dumps(prontos)} }};\n"
              + "".join(partes) + f"console.log(JSON.stringify((() => {{ {codigo} }})()));")
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


RENDER = [{"source": "A", "start": 4.46, "end": 13.37, "vel": 1.1}]


@sem_node
def test_so_a_tomada_esticada_alem_do_corte_toca_da_copia():
    S = {"view": "corte", "rendered": RENDER}
    d = {"from": 0, "source": "A", "start": 4.46, "end": 13.37, "vel": 1.1, "out": 0, "lead": 0}
    casos = {"igual": d, "aparada": {**d, "end": 12.0}, "fim": {**d, "end": 18.5}, "comeco": {**d, "start": 0.0}}
    r = _editor("return Object.fromEntries(Object.entries(CASOS).map(([k, d]) => [k, usaOrigem(d)]));".replace(
        "CASOS", json.dumps(casos)), S, {"A": True})
    assert r == {"igual": False, "aparada": False, "fim": True, "comeco": True}
    assert _editor(f"return usaOrigem({json.dumps(casos['fim'])});", S, {"A": False}) is False  # sem cópia: como antes
    assert _editor(f"return usaOrigem({json.dumps(casos['fim'])});", {**S, "view": "final"}, {"A": True}) is False


@sem_node
def test_o_relogio_da_copia_e_o_da_gravacao_na_velocidade_da_tomada():
    S = {"view": "corte", "rendered": RENDER}
    d = {"from": 0, "source": "A", "start": 4.46, "end": 18.5, "vel": 1.1, "out": 100.0, "lead": 0}
    s, t = _editor(f"const d = {json.dumps(d)}; return [naGravacao(d, 102.0), noRascunho(d, 15.0)];", S, {"A": True})
    assert s == pytest.approx(4.46 + 2.0 * 1.1)  # 2 s de agulha = 2,2 s de gravação a 1,1×
    assert t == pytest.approx(100.0 + (15.0 - 4.46) / 1.1)


def test_o_editor_toca_e_mostra_a_copia_no_lugar_do_corte():
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    html = (PREVIEW / "celular.html").read_text(encoding="utf-8")
    seguir = _trecho(js, "function followDraft(", "\n}\n")
    # a cópia manda na agulha ANTES da espera pela busca do corte (senão ela passava ~0,5 s do fim)
    assert seguir.index("if (usaOrigem(d))") < seguir.index("if (video.seeking) return;")
    assert "syncOrigem();" in _trecho(js, "function loop(", "\n}\n")
    assert "ORIG.ativo" in _trecho(js, "function fxDesenhar(", "\n}\n")  # o filtro do corte não desenha por cima
    assert "if (ORIG.ativo) v = 0" in _trecho(js, "function syncVolTomada(", "\n}\n")  # o som é o da cópia
    assert 'id="videoOrig"' in html and "/gen/proxy?src=" in js and "/api/proxies" in js
