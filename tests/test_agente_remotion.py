"""O agente e o "Gerar e baixar" sem se atropelar (teste no celular de 28/10).

O agente montava a Fase 2 a pedido da conversa, sem avisar o editor, e o Gerar instalou o Remotion na mesma pasta
ao mesmo tempo: o npm perdeu 787 arquivos, terminou "ok", e o render falhou com uma pilha de erro na tela.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import agente  # noqa: E402
import efeitos_render  # noqa: E402
import montagem as mt  # noqa: E402
import preparar_remotion  # noqa: E402
import preview_server as ps  # noqa: E402


# ---- agente.py: a marca que o editor respeita

def test_trabalhando_e_livre_sem_mexer_no_resto(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"phase": 2, "message": "oi"}), encoding="utf-8")
    agente.marcar(tmp_path, True)
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["phase"] == 2 and st["message"] == "oi" and st["agente"]["trabalhando"] is True
    assert ps.agente_trabalhando(tmp_path)
    agente.marcar(tmp_path, False)
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "agente" not in st and st["message"] == "oi"
    assert not ps.agente_trabalhando(tmp_path)


def test_marca_velha_nao_segura_o_editor(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    agente.marcar(tmp_path, True, agora=time.time() - ps.AGENTE_PARADO_S - 5)
    assert not ps.agente_trabalhando(tmp_path)


def test_cli_sem_state_json(tmp_path):
    r = subprocess.run([sys.executable, "-X", "utf8", str(Path(agente.__file__)), "trabalhando", str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1 and "state.json" in r.stderr


# ---- a trava do Remotion: um por vez montando e instalando

def test_quem_chega_depois_espera(tmp_path):
    ordem = []

    def primeiro():
        with mt.trava_remotion(tmp_path, pausa=0.05):
            ordem.append("1 entrou")
            time.sleep(0.6)
            ordem.append("1 saiu")

    t = threading.Thread(target=primeiro)
    t.start()
    time.sleep(0.15)
    with mt.trava_remotion(tmp_path, pausa=0.05):
        ordem.append("2 entrou")
    t.join()
    assert ordem == ["1 entrou", "1 saiu", "2 entrou"]
    assert not (tmp_path / ".cutmind" / "remotion.trava").exists()


def test_trava_de_quem_caiu_e_tomada(tmp_path):
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait()
    trava = tmp_path / ".cutmind" / "remotion.trava"
    trava.parent.mkdir(parents=True)
    trava.write_text(json.dumps({"pid": morto.pid, "desde": time.time()}), encoding="utf-8")
    inicio = time.time()
    with mt.trava_remotion(tmp_path, pausa=0.05):
        assert time.time() - inicio < 2


def test_trava_presa_por_tempo_demais_desiste(tmp_path):
    trava = tmp_path / ".cutmind" / "remotion.trava"
    trava.parent.mkdir(parents=True)
    import os
    trava.write_text(json.dumps({"pid": os.getpid(), "desde": time.time()}), encoding="utf-8")  # dono vivo
    with pytest.raises(mt.ErroMontagem, match="há muito tempo"):
        with mt.trava_remotion(tmp_path, prazo=0.3, pausa=0.05):
            pass
    assert trava.exists()  # a trava do outro fica


# ---- a instalação quebrada se conserta sozinha

def _rem(tmp_path):
    rem = tmp_path / "remotion"
    (rem / "node_modules" / "@remotion" / "cli").mkdir(parents=True)
    return rem


def test_instalacao_quebrada_e_refeita_do_zero(tmp_path, monkeypatch):
    rem = _rem(tmp_path)
    respostas = ["Error: Cannot find module '...\\bundler\\dist\\index.js'", None]
    monkeypatch.setattr(mt, "remotion_carrega", lambda r: respostas.pop(0))
    monkeypatch.setattr(mt.shutil, "which", lambda nome: "npm")
    apagados, rodados = [], []
    monkeypatch.setattr(mt.shutil, "rmtree", lambda p, ignore_errors=False: apagados.append(Path(p)))
    monkeypatch.setattr(mt.subprocess, "run", lambda cmd, cwd=None: rodados.append(cmd) or SimpleNamespace(returncode=0))
    mt._instalar_remotion(rem)
    assert apagados == [rem / "node_modules"] and len(rodados) == 1 and rodados[0][:2] == ["npm", "install"]


def test_instalacao_que_nao_carrega_nem_de_novo_para_com_motivo(tmp_path, monkeypatch):
    rem = _rem(tmp_path)
    monkeypatch.setattr(mt, "remotion_carrega", lambda r: "Error: Cannot find module 'x'")
    monkeypatch.setattr(mt.shutil, "which", lambda nome: "npm")
    monkeypatch.setattr(mt.shutil, "rmtree", lambda p, ignore_errors=False: None)
    monkeypatch.setattr(mt.subprocess, "run", lambda cmd, cwd=None: SimpleNamespace(returncode=0))
    with pytest.raises(mt.ErroMontagem, match="não carrega nem depois de instalar de novo"):
        mt._instalar_remotion(rem)


def test_instalacao_boa_nao_reinstala(tmp_path, monkeypatch):
    rem = _rem(tmp_path)
    monkeypatch.setattr(mt, "remotion_carrega", lambda r: None)
    monkeypatch.setattr(mt.subprocess, "run", lambda *a, **k: pytest.fail("não devia instalar"))
    mt._instalar_remotion(rem)


# ---- o erro dos efeitos: uma frase na tela, o motivo no registro

def test_erro_do_remotion_nos_efeitos_e_curto(monkeypatch, capsys):
    pilha = "Error: Cannot find module 'C:\\\\Users\\\\x\\\\remotion\\\\node_modules\\\\@remotion\\\\bundler'\n" + "    at Module._load\n" * 40
    monkeypatch.setattr(efeitos_render.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr=pilha, stdout=""))
    with pytest.raises(RuntimeError) as e:
        efeitos_render._node("render", projeto=Path("."))
    assert "registro do trabalho" in str(e.value) and "node_modules" not in str(e.value) and len(str(e.value)) < 120
    assert "Cannot find module" in capsys.readouterr().out


# ---- preparar_remotion.py: o agente monta pelo mesmo caminho, sem apagar a Fase 2 dele

def _projeto(tmp_path, ed: dict | None) -> Path:
    rem = tmp_path / "remotion"
    (rem / "public").mkdir(parents=True)
    (rem / "package.json").write_text("{}", encoding="utf-8")
    if ed is not None:
        (rem / "public" / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    return rem


def test_projeto_do_gerar_recebe_os_dados_do_modelo(tmp_path, monkeypatch):
    rem = _projeto(tmp_path, {"_gerar": "editor", "hook": {"enabled": False}})
    monkeypatch.setattr(preparar_remotion.mt, "projeto_remotion", lambda e: rem)
    preparar_remotion.preparar(tmp_path)
    ed = json.loads((rem / "public" / "edit-data.json").read_text(encoding="utf-8"))
    assert "_gerar" not in ed


def test_fase2_do_agente_nao_e_tocada(tmp_path, monkeypatch):
    minha = {"hook": {"enabled": True, "text": "meu gancho"}}
    rem = _projeto(tmp_path, minha)
    monkeypatch.setattr(preparar_remotion.mt, "projeto_remotion", lambda e: rem)
    preparar_remotion.preparar(tmp_path)
    assert json.loads((rem / "public" / "edit-data.json").read_text(encoding="utf-8")) == minha
