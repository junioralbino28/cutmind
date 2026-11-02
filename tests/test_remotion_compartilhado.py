"""Um node_modules do Remotion para todos os projetos (montagem.pasta_compartilhada).

Cada projeto instalava o seu (0,83 GB): em dois dias, ~10 GB e o disco cheio. Agora o projeto liga o
node_modules dele à pasta compartilhada do mesmo package.json (junção no Windows). O npm de verdade não roda
aqui: o "npm install" de mentira cria o @remotion/cli na pasta em que foi chamado.
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import montagem as m  # noqa: E402


@pytest.fixture
def npm(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_HOME", str(tmp_path / "home"))
    chamadas = []

    def run(cmd, cwd=None, **kw):
        if Path(cmd[0]).name.startswith("npm"):
            chamadas.append(Path(cwd))
            (Path(cwd) / "node_modules" / "@remotion" / "cli").mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(m.subprocess, "run", run)
    monkeypatch.setattr(m.shutil, "which", lambda n: n)
    monkeypatch.setattr(m, "remotion_carrega", lambda r: None if (Path(r) / "node_modules" / "@remotion" / "cli").is_dir() else "falta")
    return chamadas


def _projeto(base: Path, nome: str, pacote: dict | None = None) -> Path:
    rem = base / nome / "remotion"
    rem.mkdir(parents=True)
    (rem / "package.json").write_text(json.dumps(pacote or {"dependencies": {"remotion": "4.0.482"}}), encoding="utf-8")
    return rem


def test_dois_projetos_instalam_uma_vez_so(tmp_path, npm):
    a, b = _projeto(tmp_path, "a"), _projeto(tmp_path, "b")
    m._instalar_remotion(a)
    m._instalar_remotion(b)
    alvo = m.pasta_compartilhada(a / "package.json")
    assert npm == [alvo] and str(alvo).startswith(str(tmp_path / "home"))
    for rem in (a, b):
        assert m._ligacao(rem / "node_modules")
        assert (rem / "node_modules" / "@remotion" / "cli").is_dir()  # pela ligação
        assert os.path.realpath(rem / "node_modules") == os.path.realpath(alvo / "node_modules")


def test_projeto_com_node_modules_proprio_segue_com_ele(tmp_path, npm):
    velho = _projeto(tmp_path, "velho")
    (velho / "node_modules" / "@remotion" / "cli").mkdir(parents=True)
    m._instalar_remotion(velho)
    assert npm == [] and not m._ligacao(velho / "node_modules")


def test_package_json_novo_ganha_outra_pasta_e_a_velha_fica(tmp_path, npm):
    a = _projeto(tmp_path, "a")
    m._instalar_remotion(a)
    velha = m.pasta_compartilhada(a / "package.json")
    (a / "package.json").write_text(json.dumps({"dependencies": {"remotion": "4.0.999"}}), encoding="utf-8")
    m._instalar_remotion(a)
    nova = m.pasta_compartilhada(a / "package.json")
    assert nova != velha and npm == [velha, nova]
    assert os.path.realpath(a / "node_modules") == os.path.realpath(nova / "node_modules")
    assert (velha / "node_modules" / "@remotion" / "cli").is_dir()  # tirar a ligação não apaga o que ela apontava


def test_ligacao_quebrada_e_refeita(tmp_path, npm):
    import shutil
    a = _projeto(tmp_path, "a")
    m._instalar_remotion(a)
    shutil.rmtree(m.pasta_compartilhada(a / "package.json"))  # alguém limpou a pasta compartilhada
    m._instalar_remotion(a)
    assert len(npm) == 2 and (a / "node_modules" / "@remotion" / "cli").is_dir()


def test_trocar_o_modelo_nao_instala_dentro_da_pasta_compartilhada(tmp_path, npm, monkeypatch):
    import atualizar_template as at
    a = _projeto(tmp_path, "a")
    m._instalar_remotion(a)
    velha = m.pasta_compartilhada(a / "package.json")
    novo_pacote = {"dependencies": {"remotion": "4.0.999"}}
    monkeypatch.setattr(at, "planejar", lambda edit, assets: {"a_mao": [], "remotion": a, "kit": tmp_path, "trocados": [],
                                                              "novos": [], "npm": True})
    (a / "package.json").write_text(json.dumps(novo_pacote), encoding="utf-8")
    pl = at.aplicar(a.parent, rodar=lambda *x, **k: pytest.fail("npm install dentro do projeto ligado"))
    assert pl["npm_feito"] and npm == [velha, m.pasta_compartilhada(a / "package.json")]
