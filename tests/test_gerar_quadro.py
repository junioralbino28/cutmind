"""O Baixar não cai por um quadro que o compositor perdeu com o computador ocupado (medido em 02/11)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import gerar  # noqa: E402


class _Proc:
    def __init__(self, saida, codigo):
        self.stdout = _Fluxo(saida)
        self._codigo = codigo

    def wait(self):
        return self._codigo


class _Fluxo:
    def __init__(self, dados):
        self.dados = [dados, b""]

    def read1(self, _n):
        return self.dados.pop(0)


@pytest.fixture
def projeto(tmp_path):
    rem = tmp_path / "edit" / "remotion"
    (rem / "out").mkdir(parents=True)
    return rem


def _simular(monkeypatch, rem, respostas):
    pedidos = []

    def popen(cmd, **kw):
        pedidos.append(cmd)
        saida, codigo, gravou = respostas.pop(0)
        if gravou:
            (rem / "out" / "render.mp4").write_bytes(b"x")
        return _Proc(saida, codigo)

    monkeypatch.setattr(gerar.subprocess, "Popen", popen)
    monkeypatch.setattr(gerar.aquecer_navegador, "flags", lambda r: [])
    return pedidos


def test_quadro_perdido_tenta_de_novo_com_uma_aba(projeto, monkeypatch):
    pedidos = _simular(monkeypatch, projeto, [(b"Error: Compositor error: No frame found at position 59391\n", 1, False), (b"Rendered 1/1\n", 0, True)])
    assert gerar.renderizar(projeto, lambda *a, **k: None, 0.25, 0.85).name == "render.mp4"
    assert len(pedidos) == 2 and "--concurrency=1" not in pedidos[0] and "--concurrency=1" in pedidos[1]


def test_outra_falha_nao_repete(projeto, monkeypatch):
    pedidos = _simular(monkeypatch, projeto, [(b"TypeError: nada a ver\n", 1, False)])
    with pytest.raises(gerar.ErroGerar):
        gerar.renderizar(projeto, lambda *a, **k: None, 0.25, 0.85)
    assert len(pedidos) == 1


def test_repete_uma_vez_so(projeto, monkeypatch):
    erro = b"Compositor error: No frame found\n"
    pedidos = _simular(monkeypatch, projeto, [(erro, 1, False), (erro, 1, False)])
    with pytest.raises(gerar.ErroGerar):
        gerar.renderizar(projeto, lambda *a, **k: None, 0.25, 0.85)
    assert len(pedidos) == 2
