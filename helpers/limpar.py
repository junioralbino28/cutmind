"""Libera o disco depois da entrega: só o que o kit refaz sozinho quando precisar.

    uv run python -X utf8 helpers/limpar.py <edit> [--fundo] [--aplicar]
    uv run python -X utf8 helpers/limpar.py --temporarios [--aplicar]

Sem --aplicar só mostra o que sairia e quanto libera.

No projeto, sai:
- o node_modules próprio do Remotion (0,83 GB): o próximo render liga o projeto à pasta compartilhada
  (montagem.pasta_compartilhada). Uma ligação já compartilhada fica (não ocupa espaço);
- os caches da prévia (.preview_cache), os renders parciais (remotion/out), as conferências (verify) e os
  temporários que um render interrompido deixou.
Com --fundo, também o que custa minutos para refazer: os trechos do corte (clips_graded: o próximo Salvar
das tomadas refaz o corte) e os recortes da pessoa (o Baixar refaz).
Nunca sai: as gravações, o edl.json, o cut.mp4, o final.mp4, as transcrições, as camadas, os efeitos, o
state.json, midia/ e a memória do projeto.

--temporarios: no computador, as pastas que renders antigos deixaram no temporário do sistema. Edição real de
01/11: 54 GB em 71 pastas remotion-*. Só sai o que é provadamente de render acabado: as cutmind-<pid>-* de
processo morto e as remotion-* com mais de uma hora, e nenhuma remotion-* enquanto um render do Remotion roda
(não dá para saber de quem é cada uma; foi assim que um render de outra conversa caiu com 404).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import vez  # mesma pasta deste arquivo

UMA_HORA = 3600


def _ligacao(p: Path) -> bool:
    return p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())


def tamanho(p: Path) -> int:
    """Bytes de uma pasta ou arquivo, sem entrar em ligação (junção ou link)."""
    if _ligacao(p) or not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for raiz, pastas, arquivos in os.walk(p):
        pastas[:] = [d for d in pastas if not _ligacao(Path(raiz) / d)]
        for a in arquivos:
            try:
                total += (Path(raiz) / a).stat().st_size
            except OSError:
                pass
    return total


def do_projeto(edit: Path, fundo: bool = False) -> list[tuple[Path, str]]:
    """O que pode sair do projeto, com o motivo."""
    edit = Path(edit)
    rem = edit / "remotion"
    out = []
    nm = rem / "node_modules"
    if nm.is_dir() and not _ligacao(nm):
        out.append((nm, "o Remotion do projeto; o próximo render usa a pasta compartilhada"))
    for p, motivo in ((edit / ".preview_cache", "os desenhos da prévia (onda, quadros); o editor refaz"),
                      (rem / "out", "o render antes do som; o final fica, e mudar só um volume depois pede o render de novo"),
                      (edit / "verify", "as folhas de conferência"),
                      (edit / ".alta", "sobra de um corte em 4K interrompido")):
        if p.exists() and not _ligacao(p):
            out.append((p, motivo))
    out += [(p, "temporário de um render interrompido") for p in edit.glob("*.tmp.mp4")]
    if fundo:
        if (edit / "clips_graded").is_dir():
            out.append((edit / "clips_graded", "os trechos do corte; o próximo Salvar das tomadas refaz"))
        pub = rem / "public"
        out += [(p, "recorte da pessoa; o Baixar refaz") for p in sorted(pub.glob("pessoa-*")) if p.is_file()]
    return out


def _render_rodando() -> bool:
    """Algum render do Remotion (ou o Chrome dele) rodando agora, de qualquer projeto ou conversa."""
    if os.name == "nt":
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        linhas = r.stdout.splitlines()
    else:
        r = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True)
        linhas = r.stdout.splitlines()
    return any(("remotion" in x.lower() and ("node" in x.lower() or "chrome-headless" in x.lower())) for x in linhas)


def temporarios(agora: float | None = None, rodando: bool | None = None) -> tuple[list[tuple[Path, str]], str | None]:
    """As pastas de renders acabados no temporário do sistema, e um aviso quando parte delas ficou."""
    agora = time.time() if agora is None else agora
    base = Path(tempfile.gettempdir())
    out, aviso = [], None
    for p in sorted(base.glob("cutmind-*-*")):
        pid = p.name.split("-")[1]
        if p.is_dir() and pid.isdigit() and int(pid) != os.getpid() and not vez.vivo(int(pid)):
            out.append((p, "pasta de um render que já acabou"))
    remotion = [p for p in sorted(base.glob("remotion-*")) if p.is_dir() and not _ligacao(p)]
    if remotion and (_render_rodando() if rodando is None else rodando):
        aviso = (f"{len(remotion)} pasta(s) remotion-* ficaram: tem um render do Remotion rodando agora e não dá para "
                 "saber de quem é cada uma. Rode de novo quando nenhum render estiver rodando")
    else:
        for p in remotion:
            if agora - p.stat().st_mtime > UMA_HORA:
                out.append((p, "cópia de um render antigo do Remotion"))
    return out, aviso


def apagar(lista: list[tuple[Path, str]]) -> int:
    livre = 0
    for p, _ in lista:
        n = tamanho(p)
        if _ligacao(p):
            continue
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)  # desde o Python 3.8 o rmtree não entra em junção
        else:
            p.unlink(missing_ok=True)
        if not p.exists():
            livre += n
    return livre


def _gb(n: int) -> str:
    return f"{n / 1024 ** 3:.2f} GB".replace(".", ",")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path, nargs="?")
    ap.add_argument("--fundo", action="store_true")
    ap.add_argument("--temporarios", action="store_true")
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()
    if not a.edit and not a.temporarios:
        ap.error("diga a pasta edit do projeto ou --temporarios")
    lista, aviso = [], None
    if a.edit:
        lista += do_projeto(a.edit, a.fundo)
    if a.temporarios:
        t, aviso = temporarios()
        lista += t
    total = 0
    for p, motivo in lista:
        n = tamanho(p)
        total += n
        print(f"  {_gb(n):>10}  {p}  ({motivo})")
    if aviso:
        print(aviso)
    if not lista:
        print("nada para limpar")
        return 0
    if a.aplicar:
        print(f"liberado: {_gb(apagar(lista))}")
    else:
        print(f"sairia: {_gb(total)} (rode com --aplicar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
