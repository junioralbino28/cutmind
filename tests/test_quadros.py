"""Quadros de conferência: um bundle para todos, a pasta temporária apagada e uma folha só (quadros.py)."""
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import quadros  # noqa: E402


@pytest.fixture
def projeto(tmp_path):
    rem = tmp_path / "edit" / "remotion"
    cli = rem / "node_modules" / "@remotion" / "cli"
    cli.mkdir(parents=True)
    (cli / "remotion-cli.js").write_text("", encoding="utf-8")
    (rem / "src").mkdir()
    (rem / "src" / "CustomGraphics.tsx").write_text("", encoding="utf-8")
    return tmp_path / "edit"


def _simular(monkeypatch, falha=None):
    pedidos = []

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    def run(cmd, **kw):
        pedidos.append((cmd, kw))
        if falha and falha in cmd:
            r = R()
            r.returncode, r.stderr = 1, "linha 1\nerro do remotion"
            return r
        if "still" in cmd:
            Image.new("RGB", (108, 192), "#336699").save(cmd[cmd.index("still") + 3])
        return R()

    monkeypatch.setattr(quadros.subprocess, "run", run)
    monkeypatch.setattr(quadros.aquecer_navegador, "flags", lambda r: [])
    return pedidos


def test_um_bundle_para_todos_e_uma_folha(projeto, monkeypatch):
    pedidos = _simular(monkeypatch)
    saida = quadros.tirar(projeto, [10, 20, 30])
    cmds = [c for c, _ in pedidos]
    assert sum("bundle" in c for c in cmds) == 1 and sum("still" in c for c in cmds) == 3
    assert "bundle" in cmds[0]  # antes dos quadros
    pacote = next(a for a in cmds[0] if a.startswith("--out-dir=")).split("=", 1)[1]
    assert all(c[c.index("still") + 1] == pacote for c in cmds[1:])  # os quadros usam o mesmo pacote
    assert all(c[c.index("still") + 2] == "Reels" for c in cmds[1:])
    assert [p.name for p in saida] == ["quadro-10.png", "quadro-20.png", "quadro-30.png", "quadros.png"]
    with Image.open(saida[-1]) as folha:
        assert folha.height == quadros.ALTURA_FOLHA


def test_a_pasta_temporaria_e_propria_e_some_no_fim(projeto, monkeypatch):
    pedidos = _simular(monkeypatch)
    quadros.tirar(projeto, [10])
    tmp = Path(pedidos[0][1]["env"]["TEMP"])
    assert tmp.parent == Path(tempfile.gettempdir()) and tmp.name.startswith("cutmind-")
    assert not tmp.exists()
    assert all(k["env"]["TEMP"] == str(tmp) for _, k in pedidos)


def test_um_quadro_nao_faz_folha_e_a_saida_escolhida_vale(projeto, tmp_path, monkeypatch):
    _simular(monkeypatch)
    saida = quadros.tirar(projeto, [10], tmp_path / "fora")
    assert saida == [tmp_path / "fora" / "quadro-10.png"]


def test_a_falha_do_remotion_vira_erro_legivel(projeto, monkeypatch):
    _simular(monkeypatch, falha="bundle")
    with pytest.raises(quadros.ErroQuadros, match="erro do remotion"):
        quadros.tirar(projeto, [10])


def test_sem_o_remotion_instalado_para_com_a_causa(tmp_path):
    with pytest.raises(quadros.ErroQuadros, match="não está instalado"):
        quadros.tirar(tmp_path, [10])


def test_longform_usa_a_composicao_dele(projeto, monkeypatch):
    (projeto / "remotion" / "src" / "CustomGraphics.tsx").unlink()
    pedidos = _simular(monkeypatch)
    quadros.tirar(projeto, [10])
    cmd = pedidos[1][0]
    assert cmd[cmd.index("still") + 2] == "Longform"
