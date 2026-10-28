#!/usr/bin/env python3
"""A versão do CutMind instalada e a publicada (versao.json), o manifesto dos arquivos e o que uma versão
nova muda: é isso que decide entre "Atualizar" e "Atualizar e reiniciar" no editor (atualizar.py).

    uv run python -X utf8 helpers/versao.py manifesto [--raiz R] [--escrever]
    uv run python -X utf8 helpers/versao.py conferir [--raiz R] [--base origin/main]   (o pre-push da main)

Só biblioteca padrão: o instalador e o servidor importam sem dependência.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ARQ = "versao.json"
# o que o instalador copia (cutmind_install.SKILL_PAYLOAD), menos o próprio versao.json
PAYLOAD = ("README.md", "README.pt-BR.md", "SKILL.md", "agents", "assets", "cutmind_install.py", "helpers",
           "install.md", "pyproject.toml", "references", "uv.lock")
PULAR = ("__pycache__", ".pyc", ".DS_Store")
# a ordem importa: o primeiro prefixo que casa decide
GRUPOS = (("dependencias", ("pyproject.toml", "uv.lock")),
          ("servidor", ("helpers/", "assets/i18n/")),
          ("editor", ("assets/preview/", "assets/efeitos/")),
          ("remotion", ("assets/shortform/package.json", "assets/shortform/package-lock.json")),
          ("modelos", ("assets/",)),
          ("agente", ("SKILL.md", "references/", "agents/", "install.md")))
REINICIA = {"dependencias", "servidor"}


def numero(v: object) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def ler(raiz: Path) -> dict | None:
    try:
        d = json.loads((Path(raiz) / ARQ).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("versao"), str) else None


def _arquivos(raiz: Path) -> list[str]:
    """Os arquivos do payload; num clone git, só os versionados (nada de cache nem arquivo solto)."""
    raiz = Path(raiz)
    if (raiz / ".git").exists():
        r = subprocess.run(["git", "-C", str(raiz), "ls-files", "-z", "--", *PAYLOAD], capture_output=True)
        if r.returncode == 0:
            return sorted(x for x in r.stdout.decode("utf-8").split("\0") if x)
    nomes = []
    for entrada in PAYLOAD:
        p = raiz / entrada
        if p.is_file():
            nomes.append(entrada)
        elif p.is_dir():
            nomes += [f.relative_to(raiz).as_posix() for f in p.rglob("*")
                      if f.is_file() and not any(s in f.as_posix() for s in PULAR)]
    return sorted(nomes)


def manifesto(raiz: Path) -> dict[str, str]:
    raiz = Path(raiz)
    return {n: hashlib.sha256((raiz / n).read_bytes()).hexdigest() for n in _arquivos(raiz)}


def grupo(caminho: str) -> str:
    for nome, prefixos in GRUPOS:
        if any(caminho == p or (p.endswith("/") and caminho.startswith(p)) for p in prefixos):
            return nome
    return "outros"


def o_que_muda(local: dict[str, str], remoto: dict[str, str]) -> set[str]:
    nomes = {n for n in set(local) | set(remoto) if local.get(n) != remoto.get(n)}
    return {grupo(n) for n in nomes}


def resumo(local: dict | None, remoto: dict | None) -> dict:
    """O que a barra do editor precisa: há versão nova? reinicia? o agente precisa de conversa nova?"""
    if not remoto:
        return {"nova": False}
    atual = (local or {}).get("versao", "0")
    nova = numero(remoto["versao"]) > numero(atual)
    muda = sorted(o_que_muda((local or {}).get("arquivos") or {}, remoto.get("arquivos") or {})) if nova else []
    return {"nova": nova, "atual": atual, "versao": remoto["versao"], "data": remoto.get("data"),
            "notas": remoto.get("notas") or {}, "muda": muda, "reiniciar": bool(REINICIA & set(muda)),
            "agente": "agente" in muda, "remotion": "remotion" in muda}


def _escrever(raiz: Path, d: dict) -> None:
    (Path(raiz) / ARQ).write_bytes((json.dumps(d, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def conferir(raiz: Path, base: str | None) -> list[str]:
    """O que impede publicar: manifesto velho, ou arquivo mudado sem subir a versão (contra `base`)."""
    raiz, erros = Path(raiz), []
    d = ler(raiz)
    if not d:
        return [f"{ARQ} ausente ou quebrado"]
    if d.get("arquivos") != manifesto(raiz):
        erros.append(f"o manifesto do {ARQ} não bate com os arquivos: rode helpers/versao.py manifesto --escrever")
    if base:
        r = subprocess.run(["git", "-C", str(raiz), "show", f"{base}:{ARQ}"], capture_output=True)
        try:
            antes = json.loads(r.stdout.decode("utf-8")) if r.returncode == 0 else None
        except ValueError:
            antes = None
        if antes and antes.get("arquivos") != d.get("arquivos") and numero(d["versao"]) <= numero(antes.get("versao")):
            erros.append(f"arquivos mudaram e a versão não subiu ({antes.get('versao')} -> {d['versao']})")
    return erros


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=("manifesto", "conferir"))
    ap.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--escrever", action="store_true")
    ap.add_argument("--base", default=None)
    a = ap.parse_args()
    if a.acao == "manifesto":
        d = ler(a.raiz) or {"versao": "0.1.0", "data": "", "notas": {"pt": [], "en": []}}
        d["arquivos"] = manifesto(a.raiz)
        if a.escrever:
            _escrever(a.raiz, d)
        print(f"{len(d['arquivos'])} arquivos no manifesto" + (" (gravado)" if a.escrever else ""))
        return 0
    erros = conferir(a.raiz, a.base)
    for e in erros:
        print(f"  x {e}", file=sys.stderr)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
