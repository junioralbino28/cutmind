"""Um trabalho por projeto em segundo plano: o que o editor pede sem acordar o agente (refazer o
corte, aplicar a voz, gerar o vídeo final).

Cada trabalho é um processo à parte, como o preparo da voz (preview_server.py): é pesado, e a
memória volta quando ele termina. O andamento vai para `<edit>/.cutmind/trabalho/andamento.json`, que
o editor pergunta a cada segundo; a saída do processo, para `trabalho.log`, de onde sai a última linha
quando ele falha.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

PASTA = Path(".cutmind") / "trabalho"

_lock = threading.Lock()
_jobs: dict[str, tuple[str, subprocess.Popen]] = {}  # pasta edit → (tipo, processo)


def pasta(edit: Path) -> Path:
    return Path(edit).resolve() / PASTA


def _grava(arquivo: Path, dados: dict) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = arquivo.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(dados, ensure_ascii=False).encode("utf-8"))
    for _ in range(40):  # o editor pode estar lendo o arquivo nesse instante (Windows)
        try:
            os.replace(tmp, arquivo)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)


def escritor(arquivo: Path, tipo: str) -> Callable[..., None]:
    """O `andamento(etapa, texto, fracao, **extra)` que cada programa recebe."""
    arquivo = Path(arquivo)

    def andamento(etapa: str, texto: str, fracao: float, **extra) -> None:
        _grava(arquivo, {"tipo": tipo, "etapa": etapa, "texto": texto, "fracao": round(float(fracao), 3),
                         "vivo": etapa not in ("pronto", "falhou", "confirmar"), "pid": os.getpid(), **extra})
    return andamento


def ler(edit: Path) -> dict | None:
    try:
        d = json.loads((pasta(edit) / "andamento.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def vivo(edit: Path) -> str | None:
    """O tipo do trabalho que está rodando neste projeto, ou None."""
    with _lock:
        t = _jobs.get(str(Path(edit).resolve()))
        return t[0] if t and t[1].poll() is None else None


def iniciar(edit: Path, tipo: str, cmd: list[str]) -> bool:
    """Começa o trabalho. False quando já tem um rodando neste projeto (o editor espera)."""
    edit = Path(edit).resolve()
    p = pasta(edit)
    with _lock:
        t = _jobs.get(str(edit))
        if t and t[1].poll() is None:
            return False
        p.mkdir(parents=True, exist_ok=True)
        _grava(p / "andamento.json", {"tipo": tipo, "etapa": "comecando", "texto": "Começando", "fracao": 0.0,
                                      "vivo": True})
        with open(p / "trabalho.log", "wb") as log:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _jobs[str(edit)] = (tipo, proc)
    return True


def _ultima_linha(edit: Path) -> str:
    try:
        linhas = [x.strip() for x in (pasta(edit) / "trabalho.log").read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return ""
    return next((x for x in reversed(linhas) if x), "")


def andamento(edit: Path) -> dict | None:
    """O andamento, também nos dois instantes que o arquivo não mostra: o processo morreu sem escrever o
    fim (falhou, com a última linha do log) e o processo acabou de nascer."""
    edit = Path(edit).resolve()
    a = ler(edit)
    with _lock:
        t = _jobs.get(str(edit))
    if t is None:
        return a
    tipo, proc = t
    cod = proc.poll()
    if cod is None:
        return a or {"tipo": tipo, "etapa": "comecando", "texto": "Começando", "fracao": 0.0, "vivo": True}
    if a is None or a.get("vivo"):
        return {"tipo": tipo, "etapa": "falhou" if cod else "pronto", "texto": _ultima_linha(edit) if cod else "Pronto",
                "fracao": 1.0, "vivo": False, **({"erro": _ultima_linha(edit)} if cod else {})}
    return a
