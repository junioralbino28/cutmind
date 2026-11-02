"""Limpar o disco depois da entrega (limpar.py): só o que o kit refaz sozinho, nunca o que é da pessoa, nunca
entrando numa ligação, e nenhuma pasta do Remotion de um render que pode estar rodando agora."""
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import limpar  # noqa: E402
import montagem  # noqa: E402


def _arq(p: Path, n: int = 1000) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * n)
    return p


@pytest.fixture
def projeto(tmp_path):
    e = tmp_path / "edit"
    for rel in ("cut.mp4", "final.mp4", "edl.json", "state.json", "camadas.json", "transcripts/cut.json", "midia/foto.jpg",
                "remotion/public/edit-data.json", "remotion/public/pessoa-t1-1-2.mov", "clips_graded/seg_00.mp4",
                ".preview_cache/onda.png", "remotion/out/render.mp4", "verify/folha.png", "remotion/node_modules/x/y.js",
                ".cut.tmp.mp4"):
        _arq(e / rel)
    return e


def test_o_projeto_perde_so_o_que_o_kit_refaz(projeto):
    sai = {p.relative_to(projeto).as_posix() for p, _ in limpar.do_projeto(projeto)}
    assert sai == {"remotion/node_modules", ".preview_cache", "remotion/out", "verify", ".cut.tmp.mp4"}
    fundo = {p.relative_to(projeto).as_posix() for p, _ in limpar.do_projeto(projeto, fundo=True)}
    assert fundo - sai == {"clips_graded", "remotion/public/pessoa-t1-1-2.mov"}
    limpar.apagar(limpar.do_projeto(projeto, fundo=True))
    for fica in ("cut.mp4", "final.mp4", "edl.json", "state.json", "camadas.json", "transcripts/cut.json", "midia/foto.jpg",
                 "remotion/public/edit-data.json"):
        assert (projeto / fica).is_file(), fica


def test_node_modules_ligado_a_pasta_compartilhada_fica_e_ela_nao_e_tocada(projeto, tmp_path):
    import shutil
    shutil.rmtree(projeto / "remotion" / "node_modules")
    compartilhada = tmp_path / "home" / "remotion" / "abc" / "node_modules"
    _arq(compartilhada / "@remotion" / "cli" / "remotion-cli.js")
    montagem._ligar(projeto / "remotion" / "node_modules", compartilhada)
    assert all(p.name != "node_modules" for p, _ in limpar.do_projeto(projeto))
    # uma ligação dentro do que sai (um verify que aponta para fora) não leva o que ela aponta junto
    montagem._ligar(projeto / "verify" / "atalho", compartilhada)
    limpar.apagar(limpar.do_projeto(projeto))
    assert (compartilhada / "@remotion" / "cli" / "remotion-cli.js").is_file()


def test_temporarios_so_de_render_acabado(tmp_path, monkeypatch):
    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    velha = base / "remotion-webpack-bundle-velha"
    _arq(velha / "public" / "x.mov", 5000)
    os.utime(velha, (time.time() - 3 * 3600, time.time() - 3 * 3600))
    _arq(base / "remotion-v4-assets-agora" / "a.mp4")  # de agora: pode ser de um render rodando
    _arq(base / "cutmind-999999-abc" / "perfil" / "x")  # de um processo morto
    _arq(base / f"cutmind-{os.getppid()}-def" / "x")  # de um processo vivo
    lista, aviso = limpar.temporarios(rodando=False)
    assert {p.name for p, _ in lista} == {"remotion-webpack-bundle-velha", "cutmind-999999-abc"} and aviso is None
    lista, aviso = limpar.temporarios(rodando=True)  # um render do Remotion rodando: nenhuma remotion-* sai
    assert {p.name for p, _ in lista} == {"cutmind-999999-abc"} and "rodando" in aviso
