"""O instalador não termina dizendo "Tudo pronto!" sem as dependências do Python.

No primeiro piloto real o disco tinha 1,15 GB livres: o uv sync parou no meio do torch
e o resumo anunciava a instalação como pronta. Nada aqui instala de verdade: o uv, o
node, a cópia e o espaço do disco são falsos, e o teste confere a decisão e o que a
pessoa lê no fim.
"""
import importlib.util
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("instalador_deps", RAIZ / "cutmind_install.py")
inst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inst)

Uso = namedtuple("Uso", "total used free")
GB = 2**30


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    """Um computador de mentira: o que o uv sync responde e quanto sobra no disco."""
    m = type("M", (), {})()
    m.livre = 50 * GB
    m.sync = (0, "")          # (código de saída, stderr) do uv sync
    m.syncs = 0
    m.skills = tmp_path / "skills"

    def run(cmd, **kw):
        if cmd[:2] == ["uv", "sync"]:
            m.syncs += 1
            m.cmd_sync = cmd
            return subprocess.CompletedProcess(cmd, m.sync[0], "", m.sync[1])
        if cmd[:3] == ["uv", "cache", "dir"]:
            return subprocess.CompletedProcess(cmd, 0, str(tmp_path / "cache-uv") + "\n", "")
        if cmd[-1] == "--version":
            return subprocess.CompletedProcess(cmd, 0, "v24.8.0\n", "")
        raise AssertionError(f"comando inesperado: {cmd}")

    def copia(src, dest):     # o que importa aqui é a decisão, não copiar o kit inteiro
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text("---\nname: cutmind\n---\n", encoding="utf-8")

    monkeypatch.setattr(inst.subprocess, "run", run)
    monkeypatch.setattr(inst.shutil, "which", lambda nome: f"/bin/{nome}")
    monkeypatch.setattr(inst.shutil, "disk_usage",
                        lambda p: Uso(500 * GB, 500 * GB - m.livre, m.livre))
    monkeypatch.setattr(inst, "_copy_payload", copia)
    monkeypatch.setattr(sys, "argv", ["cutmind_install.py", "--source", str(RAIZ),
                                      "--target", str(m.skills), "--no-remotion", "--no-node",
                                      "--idioma", "pt"])
    return m


def instalar(capsys):
    """Roda o instalador e devolve (código de saída, o que a pessoa leu)."""
    try:
        inst.main()
        codigo = 0
    except SystemExit as e:
        codigo = e.code
    return codigo, capsys.readouterr().out


def test_tudo_certo_diz_tudo_pronto(maquina, capsys):
    codigo, saida = instalar(capsys)
    assert codigo == 0
    assert maquina.syncs == 1
    assert "ok dependências" in saida
    assert "Tudo pronto!" in saida
    assert "Deixe pelo menos" not in saida


def test_uv_sync_falhou_nao_diz_tudo_pronto(maquina, capsys):
    maquina.sync = (2, "error: Failed to download `torch==2.8.0`\n  Caused by: connection reset")
    codigo, saida = instalar(capsys)
    assert codigo == 1
    assert "Tudo pronto" not in saida
    assert "x dependências — o uv sync falhou" in saida
    assert "NÃO terminou" in saida


@pytest.mark.parametrize("plataforma, erro", [
    ("win32", "error: Failed to install: torch-2.8.0\n"
              "  Caused by: Espaço insuficiente no disco. (os error 112)"),
    ("win32", "  Caused by: There is not enough space on the disk. (os error 112)"),
    ("linux", "  Caused by: No space left on device (os error 28)"),
])
def test_disco_encheu_no_meio_pede_para_liberar(maquina, capsys, monkeypatch, plataforma, erro):
    monkeypatch.setattr(sys, "platform", plataforma)
    maquina.sync = (2, erro)
    # o disco tinha espaço quando o download começou e encheu no meio
    monkeypatch.setattr(inst.shutil, "disk_usage", lambda p: Uso(
        500 * GB, 0, 50 * GB if maquina.syncs == 0 else int(0.3 * GB)))
    codigo, saida = instalar(capsys)
    assert maquina.syncs == 1
    assert codigo == 1
    assert "Tudo pronto" not in saida
    assert "x dependências — falta espaço no disco (0,3 GB livres" in saida
    assert "NÃO terminou: falta espaço no disco. Libere até ter uns 15 GB livres" in saida


def test_pouco_espaco_nem_comeca_o_download(maquina, capsys):
    maquina.livre = int(1.3 * GB)
    codigo, saida = instalar(capsys)
    assert codigo == 1
    assert maquina.syncs == 0          # não baixa 1 GB de torch para parar no meio
    assert "falta espaço no disco (1,3 GB livres" in saida
    assert "Tudo pronto" not in saida


def test_espaco_curto_instala_e_avisa(maquina, capsys):
    maquina.livre = 6 * GB
    codigo, saida = instalar(capsys)
    assert codigo == 0
    assert maquina.syncs == 1
    assert "Tudo pronto!" in saida
    assert "sobram 6,0 GB" in saida
    assert "Deixe pelo menos 12 GB livres." in saida


def test_atualizacao_nao_e_barrada_pelo_espaco(maquina, capsys):
    """Com o .venv já lá, o uv sync só acerta a diferença."""
    (maquina.skills / "cutmind" / ".venv").mkdir(parents=True)
    maquina.livre = 1 * GB
    codigo, saida = instalar(capsys)
    assert maquina.syncs == 1
    assert codigo == 0
    assert "ok dependências" in saida


def test_erro_112_no_linux_nao_e_disco_cheio(monkeypatch):
    """112 é disco cheio no Windows e "host fora do ar" no Linux."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert not inst._disco_cheio("  Caused by: Host is down (os error 112)")
    assert inst._disco_cheio("  Caused by: No space left on device (os error 28)")
    monkeypatch.setattr(sys, "platform", "win32")
    assert inst._disco_cheio("  Caused by: Espaço insuficiente no disco. (os error 112)")


@pytest.mark.parametrize("plataforma, maquina_cpu, pede_312", [
    ("darwin", "x86_64", True),     # Mac Intel: torch 2.2.2 não tem roda para Python 3.13
    ("darwin", "arm64", False),
    ("win32", "AMD64", False),
    ("linux", "x86_64", False),
])
def test_mac_intel_pede_python_312_ao_uv_sync(maquina, capsys, monkeypatch, plataforma,
                                               maquina_cpu, pede_312):
    monkeypatch.setattr(sys, "platform", plataforma)
    monkeypatch.setattr(inst.platform, "machine", lambda: maquina_cpu)
    codigo, _ = instalar(capsys)
    assert codigo == 0
    assert (maquina.cmd_sync[-2:] == ["--python", "3.12"]) is pede_312
    assert maquina.cmd_sync[:4] == ["uv", "sync", "--directory", maquina.cmd_sync[3]]


def _venv_mac_intel(raiz: Path) -> Path:
    site = raiz / ".venv" / "lib" / "python3.12" / "site-packages"
    for rel in ("ctranslate2/.dylibs", "torch/lib", "functorch/.dylibs"):
        (site / rel).mkdir(parents=True)
        (site / rel / "libiomp5.dylib").write_bytes(rel.encode())
    return site


def _atalho_possivel(tmp_path: Path) -> bool:
    try:
        (tmp_path / "_lk").symlink_to(tmp_path)
        (tmp_path / "_lk").unlink()
        return True
    except OSError:
        return False


def test_mac_intel_fica_com_um_so_openmp(tmp_path, monkeypatch):
    """torch 2.2.2 e ctranslate2 trazem cada um o seu libiomp5: com os dois no processo a transcrição
    cai (SIGSEGV, medido no MacBook Air). Fica a cópia do ctranslate2; as outras viram atalho."""
    if not _atalho_possivel(tmp_path):
        pytest.skip("este Windows não cria atalho sem permissão de administrador")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(inst.platform, "machine", lambda: "x86_64")
    site = _venv_mac_intel(tmp_path / "skill")
    alvo = site / "ctranslate2" / ".dylibs" / "libiomp5.dylib"
    assert inst.um_so_openmp(tmp_path / "skill") == 2
    for rel in ("torch/lib", "functorch/.dylibs"):
        p = site / rel / "libiomp5.dylib"
        assert p.is_symlink() and p.resolve() == alvo.resolve()
    assert alvo.read_bytes() == b"ctranslate2/.dylibs" and not alvo.is_symlink()
    assert inst.um_so_openmp(tmp_path / "skill") == 0      # rodar de novo não mexe em nada


@pytest.mark.parametrize("plataforma, maquina_cpu", [("darwin", "arm64"), ("win32", "AMD64"), ("linux", "x86_64")])
def test_openmp_so_mexe_no_mac_intel(tmp_path, monkeypatch, plataforma, maquina_cpu):
    monkeypatch.setattr(sys, "platform", plataforma)
    monkeypatch.setattr(inst.platform, "machine", lambda: maquina_cpu)
    site = _venv_mac_intel(tmp_path / "skill")
    assert inst.um_so_openmp(tmp_path / "skill") == 0
    assert (site / "torch/lib/libiomp5.dylib").read_bytes() == b"torch/lib"
