#!/usr/bin/env python3
"""Abre uma vez, sem prazo, o Chrome que o Remotion usa, antes do primeiro render de um projeto.

O Remotion dá 25 s fixos para o navegador abrir (open-browser.js, sem opção para mudar). No Mac, a
primeira abertura de um Chrome recém-baixado passa pelo exame do macOS (XProtect): num MacBook Air de
2015 com macOS 12 ela levou 26 s, e o render caía com "Timed out after 25000 ms while trying to connect
to the browser". Da segunda vez abriu em 4 s, e uma cópia nova do mesmo Chrome noutra pasta também (o
exame fica guardado pelo conteúdo): basta abrir uma vez antes (medido em 26/10/2026).

    uv run python -X utf8 helpers/aquecer_navegador.py <edit>/remotion
    uv run python -X utf8 helpers/aquecer_navegador.py <edit>/remotion --flags   (Windows, pasta funda)

Também roda sozinho na montagem (montagem.py) e nos efeitos (efeitos_render.py). Depois da primeira
vez num projeto deixa uma marca em node_modules/.remotion e não abre de novo. `--flags` imprime as opções
que levam o render ao Chrome e ao compositor copiados para um caminho curto (vazio quando não precisa).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

MARCA = ".cutmind-aquecido"
MACOS_MINIMO = 13
# Windows: o Node lança o Chrome e o compositor do Remotion pelo caminho inteiro, e o lançamento falha com
# ENOENT quando ele passa de ~260 caracteres, mesmo com caminhos longos ligados no Windows. Num projeto em
# pasta funda, os dois rodam de uma cópia em ~/.cutmind/remotion-curto/<versão>/ (curtos, flags, ambiente).
LIMITE_CAMINHO = 240
COMPOSITOR = "remotion.exe"


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


def compositor(rem: Path) -> Path | None:
    """A pasta do compositor do Remotion no projeto (o remotion.exe e as bibliotecas dele; só no Windows)."""
    base = Path(rem) / "node_modules" / "@remotion"
    return next((p for p in sorted(base.glob("compositor-*")) if (p / COMPOSITOR).is_file()), None)


def casa() -> Path:
    return Path(os.environ.get("CUTMIND_HOME") or Path.home() / ".cutmind")


def _sem_limite(p: Path) -> str:
    """O caminho com o prefixo do Windows que passa dos 260 caracteres (para copiar de uma pasta funda)."""
    s = str(Path(p).resolve())
    return s if sys.platform != "win32" or s.startswith("\\\\?\\") else "\\\\?\\" + s


def _baixar(rem: Path) -> subprocess.CompletedProcess | str:
    """`remotion browser ensure`: baixa o Chrome do Remotion se ainda não está no projeto."""
    cli = Path(rem) / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli.is_file():
        return "sem o node_modules do projeto (rode o npm install antes)"
    try:
        return subprocess.run([shutil.which("node") or "node", str(cli), "browser", "ensure"], cwd=rem,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        return f"o download não rodou ({e})"


def _copia(origem: Path, destino: Path) -> Path:
    """Copia a pasta uma vez por versão. Duas cópias ao mesmo tempo não se atrapalham: cada uma grava ao lado
    e troca o nome; a que chega depois apaga a sua."""
    if destino.is_dir():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f"{destino.name}.{os.getpid()}.tmp")
    shutil.rmtree(_sem_limite(tmp), ignore_errors=True)
    shutil.copytree(_sem_limite(origem), _sem_limite(tmp))
    try:
        os.replace(tmp, destino)
    except OSError:
        shutil.rmtree(_sem_limite(tmp), ignore_errors=True)
    return destino


def curtos(rem: Path) -> dict[str, str]:
    """No Windows, com o projeto numa pasta funda: {"chrome": executável, "binarios": pasta do compositor},
    cópias em ~/.cutmind/remotion-curto/<versão>/. Vazio fora do Windows ou num caminho que cabe. Baixa o
    Chrome antes, se faltar: o render baixaria para dentro do node_modules, no caminho que não abre."""
    if sys.platform != "win32":
        return {}
    rem = Path(rem)
    if executavel(rem) is None and len(str(rem.resolve())) + 110 >= LIMITE_CAMINHO:
        _baixar(rem)
    exe, comp = executavel(rem), compositor(rem)
    if not any(p and len(str(p.resolve())) >= LIMITE_CAMINHO for p in (exe, comp and comp / COMPOSITOR)):
        return {}
    try:
        versao = json.loads((rem / "node_modules" / "@remotion" / "cli" / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        versao = "sem-versao"
    destino = casa() / "remotion-curto" / versao
    r: dict[str, str] = {}
    try:
        if exe:
            r["chrome"] = str(_copia(exe.parent, destino / "chrome") / exe.name)
        if comp:
            r["binarios"] = str(_copia(comp, destino / "compositor"))
    except OSError as e:
        print(f"navegador do Remotion: não copiei para um caminho curto ({e})", flush=True)
        return {}
    return r


def flags(rem: Path) -> list[str]:
    """As opções do `remotion render` que usam as cópias curtas (vazio quando não precisa)."""
    d = curtos(rem)
    return ([f"--browser-executable={d['chrome']}"] if "chrome" in d else []) + \
        ([f"--binaries-directory={d['binarios']}"] if "binarios" in d else [])


def ambiente(rem: Path) -> dict[str, str]:
    """As mesmas cópias para os scripts Node do kit (partes.mjs, efeitos_render.mjs), por variável."""
    d = curtos(rem)
    return {**({"CUTMIND_CHROME": d["chrome"]} if "chrome" in d else {}),
            **({"CUTMIND_BINARIOS": d["binarios"]} if "binarios" in d else {})}


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
    r = _baixar(rem)
    if isinstance(r, str):
        return f"navegador do Remotion: {r}"
    exe = executavel(rem)
    if exe is None:
        return "navegador do Remotion: não achei o Chrome depois do download; " + (r.stderr or r.stdout).strip()[-200:]
    exe = Path(curtos(rem).get("chrome") or exe)
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
    if len(sys.argv) == 3 and sys.argv[2] == "--flags":  # para colar no fim de um `remotion render`/`still`
        print(" ".join(f'"{f}"' for f in flags(Path(sys.argv[1]))), flush=True)
    elif len(sys.argv) == 2:
        print(aquecer(Path(sys.argv[1])), flush=True)
    else:
        sys.exit("uso: aquecer_navegador.py <pasta do projeto do Remotion> [--flags]")
