#!/usr/bin/env python3
"""Abre uma vez, sem prazo, o Chrome que o Remotion usa, antes do primeiro render de um projeto.

O Remotion dá 25 s fixos para o navegador abrir (open-browser.js, sem opção para mudar). No Mac, a
primeira abertura de um Chrome recém-baixado passa pelo exame do macOS (XProtect): num MacBook Air de
2015 com macOS 12 ela levou 26 s, e o render caía com "Timed out after 25000 ms while trying to connect
to the browser". Da segunda vez abriu em 4 s, e uma cópia nova do mesmo Chrome noutra pasta também (o
exame fica guardado pelo conteúdo): basta abrir uma vez antes (medido em 26/10/2026).

    uv run python -X utf8 helpers/aquecer_navegador.py <edit>/remotion

Também roda sozinho na montagem (montagem.py) e nos efeitos (efeitos_render.py). Depois da primeira
vez num projeto deixa uma marca em node_modules/.remotion e não abre de novo.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

MARCA = ".cutmind-aquecido"
MACOS_MINIMO = 13


def macos_antigo() -> str | None:
    """A versão do macOS quando ela é anterior à 13, em que o Remotion não renderiza: o compositor dele
    (que tira os quadros do vídeo) é compilado para o macOS 13 ou mais novo e, no 12, cai com "Symbol
    not found: _AVCaptureDeviceTypeContinuityCamera" (medido num MacBook Air 2015 com macOS 12.7.6 em
    26/10/2026; issues #4515 e #4879 do Remotion). None em outro sistema ou num macOS novo."""
    if sys.platform != "darwin":
        return None
    v = platform.mac_ver()[0]
    try:
        return v if int(v.split(".")[0]) < MACOS_MINIMO else None
    except ValueError:
        return None


NOMES = ("chrome-headless-shell", "chrome-headless-shell.exe")


def executavel(rem: Path) -> Path | None:
    """O Chrome que o Remotion baixou: node_modules/.remotion/chrome-headless-shell/<plataforma>/…"""
    base = Path(rem) / "node_modules" / ".remotion" / "chrome-headless-shell"
    if not base.is_dir():
        return None
    return next((p for p in sorted(base.glob("*/*/*")) if p.name in NOMES and p.is_file()), None)


def aquecer(rem: Path, prazo: float = 600) -> str:
    """Garante o Chrome do Remotion e abre ele uma vez. Devolve, em uma linha, o que aconteceu. Nunca
    para o trabalho: se não der para aquecer, o render tenta do jeito de sempre."""
    v = macos_antigo()
    if v:
        return f"navegador do Remotion: o Remotion não renderiza no macOS {v} (precisa do {MACOS_MINIMO} ou mais novo)"
    rem = Path(rem)
    marca = rem / "node_modules" / ".remotion" / MARCA
    if marca.is_file():
        return "navegador do Remotion: já aberto antes neste projeto"
    cli = rem / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli.is_file():
        return "navegador do Remotion: sem o node_modules do projeto (rode o npm install antes)"
    try:
        r = subprocess.run([shutil.which("node") or "node", str(cli), "browser", "ensure"], cwd=rem,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        return f"navegador do Remotion: o download não rodou ({e})"
    exe = executavel(rem)
    if exe is None:
        return "navegador do Remotion: não achei o Chrome depois do download; " + (r.stderr or r.stdout).strip()[-200:]
    t0 = time.time()
    try:
        subprocess.run([str(exe), "--headless", "--disable-gpu", "--no-sandbox", "--dump-dom", "about:blank"],
                       capture_output=True, timeout=prazo)
    except subprocess.TimeoutExpired:
        return f"navegador do Remotion: não abriu em {prazo:.0f} s"
    except OSError as e:
        return f"navegador do Remotion: não abriu ({e})"
    seg = time.time() - t0
    marca.write_bytes(f"{seg:.1f}\n".encode("utf-8"))
    return f"navegador do Remotion: pronto (a primeira abertura levou {seg:.0f} s)"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: aquecer_navegador.py <pasta do projeto do Remotion>")
    print(aquecer(Path(sys.argv[1])), flush=True)
