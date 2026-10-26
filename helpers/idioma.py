#!/usr/bin/env python3
"""O idioma da tela e as mensagens que a pessoa lê sem o agente no meio (o que o servidor do editor
devolve para a tela). O resto dos helpers fala com o agente, que já responde no idioma da pessoa.

O português é a chave, como no editor (`assets/preview/i18n.js`): sem tradução, sai o português.
O inglês fica em `assets/i18n/scripts-en.json`. Uma mensagem já montada com valor
("não encontrado: x.mp4") é achada pelo padrão da chave ("não encontrado: {rel}"), e o valor de dentro
também passa pela tradução (é assim que "montagem: {e}" traduz o motivo que vem da exceção).

    idioma.do_pedido(cabecalho_do_editor, accept_language)  -> "pt" | "en"
    idioma.traduzir("o projeto ainda não tem o corte", "en")
"""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path

DICIONARIO = Path(__file__).resolve().parent.parent / "assets" / "i18n" / "scripts-en.json"
MARCADOR = re.compile(r"\{(\w+)\}")


def normalizar(valor: object) -> str | None:
    """"pt", "pt-BR", "pt_PT" → "pt"; qualquer outro idioma → "en"; vazio ou lixo → None."""
    s = str(valor or "").strip().lower()
    if not re.match(r"^[a-z]{2,3}([-_][a-z0-9]{1,8})*$", s):
        return None
    return "pt" if s.split("-")[0].split("_")[0] == "pt" else "en"


def do_pedido(cabecalho: str | None, accept_language: str | None) -> str:
    """O do editor (o botão PT | EN manda em cada pedido); sem ele, o primeiro do navegador; sem nada, pt."""
    escolhido = normalizar(cabecalho)
    if escolhido:
        return escolhido
    primeiro = (accept_language or "").split(",")[0].split(";")[0]
    return normalizar(primeiro) or "pt"


@lru_cache(maxsize=1)
def _dicionario() -> dict[str, str]:
    try:
        d = json.loads(DICIONARIO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


@lru_cache(maxsize=1)
def _padroes() -> list[tuple[re.Pattern, str]]:
    """As chaves com marcador viram padrão; a de mais texto fixo é tentada primeiro."""
    out = []
    for k, v in _dicionario().items():
        partes = MARCADOR.split(k)  # texto, nome, texto, nome, ..., texto
        if len(partes) == 1 or len(set(partes[1::2])) < len(partes[1::2]):
            continue  # sem marcador, ou o mesmo marcador duas vezes: só vale a frase exata
        rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(partes))
        fixo = sum(len(p) for p in partes[::2])
        out.append((fixo, re.compile(f"^{rx}$", re.S), v))
    return [(rx, v) for _, rx, v in sorted(out, key=lambda x: -x[0])]


def traduzir(msg: object, idioma: str) -> str:
    """A mensagem no idioma da tela; em português (ou sem tradução), ela mesma."""
    s = str(msg)
    if idioma != "en" or not s:
        return s
    en = _dicionario().get(s)
    if en is not None:
        return en
    for rx, modelo in _padroes():
        m = rx.match(s)
        if m:
            valores = {k: traduzir(x, idioma) for k, x in m.groupdict().items()}
            return MARCADOR.sub(lambda mm: valores.get(mm.group(1), mm.group(0)), modelo)
    return s


def mensagem(chave: str, **valores: object) -> dict:
    """O aviso que um script grava no `state.json` para a barra do editor: a frase em português
    (`message`, a que o agente lê) e a chave com os valores, para o editor mostrar no idioma da tela.
    O editor só usa a chave quando ela ainda monta a mesma `message`: se o agente escreveu outra por
    cima, vale a dele."""
    texto = MARCADOR.sub(lambda m: str(valores.get(m.group(1), m.group(0))), chave)
    return {"message": texto, "messageKey": chave, "messageVals": {k: str(v) for k, v in valores.items()}}
