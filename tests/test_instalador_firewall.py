"""No Windows, o instalador deixa pronta a permissão de rede do editor no celular (o firewall): quem usa
pelo app do celular não está na frente do PC para responder a pergunta do Windows.

Nada aqui mexe no firewall: o PowerShell é trocado por um falso que guarda os comandos e conta as regras.
"""
import base64
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("instalador", RAIZ / "cutmind_install.py")
inst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inst)


def _decodifica(b64: str) -> str:
    return base64.b64decode(b64).decode("utf-16-le")


@pytest.fixture
def windows(tmp_path, monkeypatch):
    """Um Windows de mentira: o .venv aponta para um Python base, e o PowerShell responde quantas regras
    liberam esse Python; o pedido de administrador cria uma (ou não, se a pessoa recusa)."""
    s = SimpleNamespace(regras=0, aceita=True, consultas=[], elevados=[])
    base = tmp_path / "uv python" / "cpython-3.13"
    base.mkdir(parents=True)
    (base / "python.exe").write_bytes(b"")
    s.dest = tmp_path / "skill"
    (s.dest / ".venv").mkdir(parents=True)
    (s.dest / ".venv" / "pyvenv.cfg").write_text(f"home = {base}\nversion = 3.13.5\n", encoding="utf-8")
    s.python = base / "python.exe"

    def run(cmd, **kw):
        assert cmd[:2] == ["powershell", "-NoProfile"]
        texto = _decodifica(cmd[cmd.index("-EncodedCommand") + 1])
        if "Start-Process" in texto:
            assert "-Verb RunAs" in texto
            s.elevados.append(_decodifica(re.search(r"'-EncodedCommand','([^']+)'", texto).group(1)))
            if s.aceita:
                s.regras += 1
            return subprocess.CompletedProcess(cmd, 0 if s.aceita else 1, "", "")
        s.consultas.append(texto)
        return subprocess.CompletedProcess(cmd, 0, f"{s.regras}\n", "")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(inst.subprocess, "run", run)
    return s


def test_acha_o_python_que_escuta(windows, tmp_path):
    assert inst.python_do_editor(windows.dest) == windows.python
    assert inst.python_do_editor(tmp_path / "sem-venv") is None


def test_com_a_regra_pronta_nao_pede_nada(windows):
    windows.regras = 2   # o "Permitir" da janela do Windows cria duas (TCP e UDP)
    assert inst.garantir_firewall([windows.dest], pode_pedir=True) == "ok"
    assert not windows.elevados and str(windows.python) in windows.consultas[0]


def test_sem_regra_pede_uma_vez_e_so_para_redes_privadas(windows):
    assert inst.garantir_firewall([windows.dest], pode_pedir=True) == "ok"
    assert len(windows.elevados) == 1
    regra = windows.elevados[0]
    assert "New-NetFirewallRule" in regra and "-Direction Inbound" in regra and "-Action Allow" in regra
    assert "-Profile Private" in regra and f"-Program '{windows.python}'" in regra


def test_recusou_o_pedido_fica_a_dica(windows):
    windows.aceita = False
    assert inst.garantir_firewall([windows.dest], pode_pedir=True) == "falta"


def test_sem_poder_pedir_so_confere(windows):
    assert inst.garantir_firewall([windows.dest], pode_pedir=False) == "falta"
    assert not windows.elevados


def test_caminho_com_aspas_nao_quebra_o_comando(windows, tmp_path):
    base = tmp_path / "O'Brien" / "py"
    base.mkdir(parents=True)
    (base / "python.exe").write_bytes(b"")
    (windows.dest / ".venv" / "pyvenv.cfg").write_text(f"home = {base}\n", encoding="utf-8")
    inst.garantir_firewall([windows.dest], pode_pedir=True)
    assert "O''Brien" in windows.consultas[0] and "O''Brien" in windows.elevados[0]


def test_fora_do_windows_nao_faz_nada(windows, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert inst.garantir_firewall([windows.dest], pode_pedir=True) is None
    assert not windows.consultas and not windows.elevados
