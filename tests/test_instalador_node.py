"""O instalador põe o Node.js (Fase 2, Remotion) sozinho quando ele falta.

Nada aqui instala de verdade: o gerenciador do sistema (winget, brew) e o `node`
são trocados por falsos, e o teste confere o comando e a decisão.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("instalador", RAIZ / "cenno_edit_install.py")
inst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inst)


@pytest.fixture
def sistema(monkeypatch):
    """Um sistema de mentira: quais programas existem e o que cada comando responde."""
    s = type("S", (), {})()
    s.programas = {}       # nome → caminho
    s.versao = "v24.8.0"   # o que o node responde
    s.comandos = []
    s.depois = None        # onde o node aparece depois de instalar

    def which(nome):
        return s.programas.get(nome)

    def run(cmd, **kw):
        s.comandos.append(list(cmd))
        if cmd[-1] == "--version":
            return subprocess.CompletedProcess(cmd, 0, s.versao + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(inst.shutil, "which", which)
    monkeypatch.setattr(inst.subprocess, "run", run)
    monkeypatch.setattr(inst, "_node_apos_instalar", lambda: s.depois)
    return s


def _instalou(s):
    return [c for c in s.comandos if c[-1] != "--version"]


def test_versao_do_node(sistema):
    sistema.programas["node"] = "/bin/node"
    assert inst.node_version() == 24
    sistema.versao = "v16.20.1"
    assert inst.node_version() == 16
    sistema.versao = "não sei"
    assert inst.node_version() is None
    del sistema.programas["node"]
    assert inst.node_version() is None


def test_ja_tem_node_nao_instala_nada(sistema, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    sistema.programas.update(node="C:/nodejs/node.exe", winget="C:/winget.exe")
    assert inst.garantir_node(pode_instalar=True) == ("ok", "v24")
    assert _instalou(sistema) == []


def test_sem_node_no_windows_instala_pelo_winget(sistema, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    sistema.programas["winget"] = "C:/winget.exe"
    sistema.depois = "C:/Program Files/nodejs/node.exe"  # o PATH deste terminal ainda não tem
    estado, onde = inst.garantir_node(pode_instalar=True)
    assert (estado, onde) == ("instalado", "C:/Program Files/nodejs/node.exe")
    cmd = _instalou(sistema)[0]
    assert cmd[:5] == ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e"]
    assert {"--silent", "--accept-package-agreements", "--accept-source-agreements"} <= set(cmd)


def test_sem_node_no_mac_instala_pelo_brew(sistema, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    sistema.programas["brew"] = "/opt/homebrew/bin/brew"
    sistema.depois = "/opt/homebrew/bin/node"
    assert inst.garantir_node(pode_instalar=True)[0] == "instalado"
    assert _instalou(sistema) == [["brew", "install", "node"]]


def test_linux_fica_na_dica(sistema, monkeypatch):
    """apt pede senha e a versão da distro pode ser velha demais: só o comando."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert inst.garantir_node(pode_instalar=True) == ("falta", "")
    assert _instalou(sistema) == []


def test_sem_winget_nao_tenta(sistema, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert inst.garantir_node(pode_instalar=True) == ("falta", "")
    assert _instalou(sistema) == []


def test_node_antigo_nao_e_trocado_sozinho(sistema, monkeypatch):
    """Atualizar sozinho pode quebrar outros projetos da pessoa: só avisa."""
    monkeypatch.setattr(sys, "platform", "win32")
    sistema.programas.update(node="C:/nodejs/node.exe", winget="C:/winget.exe")
    sistema.versao = "v16.20.1"
    assert inst.garantir_node(pode_instalar=True) == ("velho", "v16")
    assert _instalou(sistema) == []


def test_sem_permissao_de_instalar_so_confere(sistema, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    sistema.programas["winget"] = "C:/winget.exe"
    assert inst.garantir_node(pode_instalar=False) == ("falta", "")
    assert _instalou(sistema) == []


def test_instalou_mas_nao_achou_o_node(sistema, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    sistema.programas["winget"] = "C:/winget.exe"
    assert inst.garantir_node(pode_instalar=True) == ("falta", "")  # não finge que deu certo
