"""Os modelos de montagem da biblioteca de pacotes (tipo `montagem`): o modelo vem escrito no
catálogo, aparece no painel junto dos do kit, passa pela mesma conferência, e o vídeo de exemplo é a
prévia do pacote, baixada só quando a pessoa toca em ver."""
from __future__ import annotations

import hashlib
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import montagens as mg  # noqa: E402
import pacotes as pk  # noqa: E402

MODELO = {"versao": 1, "comeca": "forte", "drop_na_vaga": 3, "golpe": True, "formato": "9:16",
          "vagas": [{"batidas": 4, "repetir": 2}, {"batidas": 1, "repetir": 8}],
          "textos": [{"nome": "Título", "texto": "SEU TÍTULO", "vaga": 1, "batidas": 8, "x": 540, "y": 700, "estilo": {}}],
          "transicoes": []}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _pacote(pid, nome, modelo, video=b"V" * 3000):
    arq = json.dumps({**modelo, "nome": nome}).encode()
    return {"id": pid, "tipo": "montagem", "nome": nome, "release": "montagens-1", "duracao": 20,
            "arquivo": f"{pid}.json", "tamanho": len(arq), "sha256": _sha(arq),
            "previa": {"arquivo": f"{pid}.mp4", "tamanho": len(video), "sha256": _sha(video)},
            "modelo": modelo}, arq, video


@pytest.fixture
def biblioteca(tmp_path, monkeypatch):
    """Uma Release de mentira com dois modelos (um torto), servida por HTTP local, e o catálogo dela
    no lugar do catálogo do kit."""
    raiz = tmp_path / "release" / "montagens-1"
    raiz.mkdir(parents=True)
    pedidos: list[str] = []

    class H(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            pedidos.append(self.path)
            super().do_GET()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(H, directory=str(raiz.parent)))
    threading.Thread(target=partial(srv.serve_forever, poll_interval=0.05), daemon=True).start()
    bom, arq_bom, video = _pacote("m-drop-rapido", "Drop rápido", MODELO)
    torto, arq_torto, _ = _pacote("m-torto", "Torto", {**MODELO, "formato": "4:3"})
    for p, arq in ((bom, arq_bom), (torto, arq_torto)):
        (raiz / p["arquivo"]).write_bytes(arq)
    (raiz / bom["previa"]["arquivo"]).write_bytes(video)
    cat = {"versao": 1, "gerado": "2026-10-26T12:00:00Z", "repo": "", "base": f"http://127.0.0.1:{srv.server_address[1]}",
           "pacotes": [bom, torto]}
    cat_p = tmp_path / "catalogo.json"
    cat_p.write_text(json.dumps(cat), encoding="utf-8")
    monkeypatch.setenv("CUTMIND_PACOTES_CATALOGO", str(cat_p))
    monkeypatch.setenv("CUTMIND_PACOTES_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("CUTMIND_PACOTES_BASE", raising=False)
    yield SimpleNamespace(cat=cat, video=video, pedidos=pedidos)
    srv.shutdown()
    srv.server_close()


def test_aparece_no_painel_junto_dos_do_kit_sem_baixar_nada(biblioteca):
    por_id = {m["id"]: m for m in mg.listar()}
    assert "drop-rapido" in por_id and "drop-cedo" in por_id  # o da biblioteca e o de assets/montagens
    assert "torto" not in por_id  # um modelo que o kit recusaria não aparece
    m = por_id["drop-rapido"]
    assert m["doKit"] and m["vagas"] == MODELO["vagas"] and m["nome"] == "Drop rápido"
    r = mg.resumo(m)
    assert r["previa"] == "m-drop-rapido" and r["lugares"] == 10 and r["doKit"]
    assert biblioteca.pedidos == []  # listar não baixa nada
    assert mg.resumo(por_id["drop-cedo"])["previa"] is None


def test_obter_pelo_id_do_modelo_e_o_da_pessoa_vale_no_lugar(biblioteca):
    assert mg.obter("drop-rapido")["drop_na_vaga"] == 3
    assert not mg.apagar("drop-rapido")  # o da biblioteca não se apaga
    mg.salvar({"nome": "Drop rápido", "vagas": [{"batidas": 2, "repetir": 4}]})
    assert mg.obter("drop-rapido")["vagas"] == [{"batidas": 2, "repetir": 4}]
    assert [m for m in mg.listar() if m["id"] == "drop-rapido"][0].get("doKit") is not True


def test_o_exemplo_desce_so_quando_pede(biblioteca):
    pac = pk.Pacotes.do_ambiente()
    caminho = pac.previa("m-drop-rapido")
    assert caminho.read_bytes() == biblioteca.video
    assert biblioteca.pedidos == ["/montagens-1/m-drop-rapido.mp4"]


@pytest.mark.parametrize("estrago", [
    lambda p: p.pop("modelo"),
    lambda p: p.update(modelo="não é objeto"),
    lambda p: p.update(modelo={"textos": [{"texto": "x" * 400}] * 60}),  # passa de 20 KB
])
def test_catalogo_com_montagem_sem_modelo_e_recusado(estrago):
    p, _, _ = _pacote("m-x", "X", MODELO)
    estrago(p)
    with pytest.raises(pk.CatalogoInvalido):
        pk.validar({"versao": 1, "base": "https://exemplo.invalid", "pacotes": [p]})


def test_catalogo_sem_montagem_nao_muda_nada(monkeypatch, tmp_path):
    """O catálogo do kit hoje: nenhum modelo da biblioteca, e o painel segue com os de sempre."""
    monkeypatch.setenv("CUTMIND_PACOTES_DIR", str(tmp_path / "cache"))
    assert [m["id"] for m in mg.listar() if m.get("pacote")] == []
    assert mg.obter("drop-cedo") is not None
