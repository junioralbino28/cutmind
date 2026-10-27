"""O que o Salvar do editor guarda para depois, sem acordar o agente.

  - `<edit>/.cutmind/pendente.json`: o que o Baixar (gerar.py) ou um trabalho do servidor aplica e
    tira daqui: a montagem (`montagem.lugares`, `montagem.formato`, `montagem.usar`) e a escolha do
    Melhorar voz (`melhorar`);
  - `<edit>/pedidos.json`: as marcações (tecla M) e os pedidos da caixa "O que você quer mudar?", que
    esperam o Pronto. O Pronto os leva para o pronto.json, que acorda o agente uma vez.

Antes desta versão tudo ia para o preview_edits.json, e cada Salvar acordava o agente.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ARQ = Path(".cutmind") / "pendente.json"
PEDIDOS = "pedidos.json"


def _ler(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _grava(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_bytes(json.dumps(d, ensure_ascii=False, indent=2).encode("utf-8"))
    for _ in range(40):  # o editor pode estar lendo o arquivo nesse instante (Windows)
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)


def ler(edit: Path) -> dict:
    return _ler(Path(edit) / ARQ)


def gravar(edit: Path, d: dict) -> None:
    """Grava o pendente; vazio, apaga o arquivo."""
    p = Path(edit) / ARQ
    if any(v not in (None, {}, []) for v in d.values()):
        _grava(p, d)
    else:
        p.unlink(missing_ok=True)


def tirar(edit: Path, chave: str, *dentro: str) -> None:
    """Tira o que já foi aplicado: `tirar(edit, "melhorar")`, `tirar(edit, "montagem", "lugares", "formato")`."""
    d = ler(edit)
    if chave not in d:
        return
    if dentro and isinstance(d[chave], dict):
        for k in dentro:
            d[chave].pop(k, None)
        if not d[chave]:
            d.pop(chave)
    else:
        d.pop(chave)
    gravar(edit, d)


def pedidos(edit: Path) -> list[dict]:
    lista = _ler(Path(edit) / PEDIDOS).get("pedidos")
    return lista if isinstance(lista, list) else []


def somar_pedidos(edit: Path, novos: list[dict]) -> int:
    """Os pedidos e marcações do Salvar somam aos que já esperam o Pronto. Devolve quantos esperam."""
    lista = pedidos(edit) + [n for n in novos if isinstance(n, dict)]
    _grava(Path(edit) / PEDIDOS, {"pedidos": lista})
    return len(lista)


def levar_pedidos(edit: Path) -> list[dict]:
    """O Pronto: devolve os pedidos que esperavam e esvazia a lista."""
    lista = pedidos(edit)
    (Path(edit) / PEDIDOS).unlink(missing_ok=True)
    return lista
