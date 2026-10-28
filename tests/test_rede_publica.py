"""O editor avisa quando o Windows marcou a rede como Pública: o firewall barra o celular mesmo com a
permissão do CutMind, que vale para redes privadas (visto no PC do dono ao preparar o teste pelo app)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import preview_server as ps  # noqa: E402


def _powershell(monkeypatch, resposta: str, chamadas: list):
    def run(cmd, **kw):
        chamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, resposta, "")
    monkeypatch.setattr(ps.os, "name", "nt")
    monkeypatch.setattr(ps.subprocess, "run", run)


def test_rede_publica_no_windows(monkeypatch):
    chamadas = []
    _powershell(monkeypatch, "Public\r\n", chamadas)
    assert ps.rede_publica("192.0.2.10") is True
    assert "Get-NetConnectionProfile" in chamadas[0][-1] and "'192.0.2.10'" in chamadas[0][-1]


def test_rede_privada_ou_sem_resposta(monkeypatch):
    chamadas = []
    _powershell(monkeypatch, "Private\r\n", chamadas)
    assert ps.rede_publica("192.0.2.10") is False
    _powershell(monkeypatch, "", chamadas)
    assert ps.rede_publica("192.0.2.10") is False


def test_so_aceita_um_ip_de_verdade(monkeypatch):
    chamadas = []
    _powershell(monkeypatch, "Public", chamadas)
    assert ps.rede_publica("1.2.3.4'; Remove-Item C:\\") is False and not chamadas


def test_fora_do_windows_nem_pergunta(monkeypatch):
    chamadas = []
    _powershell(monkeypatch, "Public", chamadas)
    monkeypatch.setattr(ps.os, "name", "posix")
    assert ps.rede_publica("192.0.2.10") is False and not chamadas


def test_o_link_do_celular_leva_o_ip(monkeypatch):
    monkeypatch.setattr(ps, "phone_hosts", lambda host: [("Wi-Fi de casa", "192.0.2.10")])
    u = ps.phone_urls("0.0.0.0", 4820, "abc")[0]
    assert u == {"label": "Wi-Fi de casa", "url": "http://192.0.2.10:4820/c?t=abc", "ip": "192.0.2.10"}
