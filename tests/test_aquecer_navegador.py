"""O Chrome do Remotion abre uma vez, sem prazo, antes do primeiro render do projeto.

No Mac a 1ª abertura de um Chrome recém-baixado passa pelo exame do macOS e levou 26 s num MacBook Air
de 2015; o Remotion dá 25 s fixos e o render caía. Aqui o node e o Chrome são falsos: o teste confere
a ordem (baixar, abrir, marcar) e que nada para o trabalho quando não dá para aquecer.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import aquecer_navegador as aq  # noqa: E402


def _projeto(tmp_path: Path) -> Path:
    rem = tmp_path / "remotion"
    cli = rem / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("// cli", encoding="utf-8")
    return rem


def _chrome(rem: Path) -> Path:
    exe = rem / "node_modules" / ".remotion" / "chrome-headless-shell" / "mac-x64" / "chrome-headless-shell-mac-x64" / "chrome-headless-shell"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    return exe


def test_sem_node_modules_nao_chama_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(aq.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia rodar")))
    assert "npm install" in aq.aquecer(tmp_path / "remotion")


def test_baixa_abre_uma_vez_e_marca(tmp_path, monkeypatch):
    rem = _projeto(tmp_path)
    chamadas = []

    def run(cmd, **kw):
        chamadas.append([str(c) for c in cmd])
        if cmd[-2:] == ["browser", "ensure"]:
            _chrome(rem)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(aq.subprocess, "run", run)
    assert "pronto" in aq.aquecer(rem)
    assert chamadas[0][-2:] == ["browser", "ensure"]
    assert chamadas[1][0].endswith("chrome-headless-shell") and "--headless" in chamadas[1]
    assert "já aberto" in aq.aquecer(rem)          # a 2ª vez no mesmo projeto não abre de novo
    assert len(chamadas) == 2


def test_chrome_que_nao_abre_nao_marca_e_nao_para_o_trabalho(tmp_path, monkeypatch):
    rem = _projeto(tmp_path)

    def run(cmd, **kw):
        if cmd[-2:] == ["browser", "ensure"]:
            _chrome(rem)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(aq.subprocess, "run", run)
    assert "não abriu" in aq.aquecer(rem, prazo=1)
    assert not (rem / "node_modules" / ".remotion" / aq.MARCA).exists()


def test_download_que_nao_deixa_o_chrome_explica(tmp_path, monkeypatch):
    rem = _projeto(tmp_path)
    monkeypatch.setattr(aq.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "sem rede"))
    msg = aq.aquecer(rem)
    assert "não achei o Chrome" in msg and "sem rede" in msg
