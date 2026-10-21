"""Nada de segredo, e-mail de gente, caminho absoluto de usuário ou mídia pesada no repositório.
Lê só arquivos VERSIONADOS: um arquivo novo é conferido depois do `git add`."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PADROES: list[tuple[str, str]] = [
    (r"[Cc]:[\/]+Users[\/]+(?![<%$\{])", "caminho absoluto de usuário"),
    (r"sk-ant-[A-Za-z0-9_-]{10}|ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}"
     r"|AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10}", "segredo"),
]
# o repositório é público: e-mail de gente não entra. Passam só o endereço privado do
# GitHub, o coautor e os exemplos; pacote@1.2.3 não é e-mail.
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
EMAIL_OK = re.compile(r"users\.noreply\.github\.com$|^noreply@anthropic\.com$|@example\.(com|org|net)$|^[\w.+-]+@\d")
EXTENSOES_TEXTO = {".py", ".md", ".ts", ".tsx", ".js", ".mjs", ".json", ".css",
                   ".html", ".toml", ".yaml", ".yml", ".txt", ".sh", ".ps1", ".bat", ".cfg"}
ISENTOS = {"tests/test_repo_limpo.py"}
LIMITE_BINARIO = 2_000_000  # bytes


def versionados() -> list[str]:
    saida = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ,
                           capture_output=True, check=True).stdout
    return [p for p in saida.decode("utf-8").split("\0") if p]


def achados(texto: str) -> list[str]:
    motivos = [motivo for padrao, motivo in PADROES if re.search(padrao, texto)]
    if any(not EMAIL_OK.search(m.group(0)) for m in EMAIL.finditer(texto)):
        motivos.append("e-mail")
    return motivos


def test_detector_pega_o_que_deve():
    assert "caminho absoluto de usuário" in achados("C:/Users/fulano/video.mp4")
    assert "segredo" in achados("ghp_" + "a" * 24)
    assert "e-mail" in achados("fale com fulano" + "@" + "gmail.com")  # em pedaços: o arquivo não traz o endereço
    assert achados(r"C:\Users\<voce>\Videos") == []
    assert achados("Co-Authored-By: Claude <noreply@anthropic.com>") == []
    assert achados("1+fulano@users.noreply.github.com e remotion@4.0.482") == []
    assert achados("texto limpo") == []


def test_nenhum_texto_proibido():
    problemas = []
    for rel in versionados():
        if rel in ISENTOS or Path(rel).suffix.lower() not in EXTENSOES_TEXTO:
            continue
        texto = (RAIZ / rel).read_text(encoding="utf-8", errors="replace")
        for n, linha in enumerate(texto.splitlines(), 1):
            problemas += [f"{rel}:{n}: {m}" for m in achados(linha)]
    assert not problemas, "\n".join(problemas)


def test_nenhum_binario_pesado():
    pesados = [rel for rel in versionados()
               if (RAIZ / rel).is_file() and (RAIZ / rel).stat().st_size > LIMITE_BINARIO]
    assert not pesados, "\n".join(pesados)
